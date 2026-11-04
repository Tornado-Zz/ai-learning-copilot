"""Sprint 3 阶段 B 的集成验收：0004 迁移、10 道种子、判题证据分级与历史接口。

隔离沿用既有集成用例：所有写入都发生在 conftest.db_session 的外层事务里，测试
结束整体回滚；既有表在本文件里一行都不改，也不执行任何 DELETE / TRUNCATE /
DROP。断言按本测试自己的 user_id 限定，不依赖真实用户已有的提交。

证据口径（B1）在这里被逐条钉住：静态规则只能得到 assessed + 「已验证（静态规则）」，
自检只能得到 self_reported + 「未验证（自检）」，任何判定都不写 user_skill_levels。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[1]
REVISION = "0004_sprint3_exercises"
# Sprint 4 追加 0005、Sprint 5 追加 0006、Sprint 6 追加 0007 后 head 前移三位；
# 0004 建的表与列必须保持原样。
HEAD_REVISION = "0007_sprint6_plan_exercise_targets"
# 0005 与 0006 各建的表：结构的正确性由 Sprint 4 / Sprint 5 的测试负责，
# 这里只需要把它们算进"已存在的表"集合。
LATER_TABLES = {"ai_interactions", "knowledge_sources", "knowledge_chunks"}
ANSWER_KEYS = ("required_patterns", "forbidden_patterns", "expected_output")

EXERCISE_COLUMNS = {
    "id",
    "lesson_id",
    "code",
    "title",
    "prompt",
    "starter_code",
    "visible_tests",
    "required_patterns",
    "forbidden_patterns",
    "expected_output",
    "estimated_minutes",
    "difficulty",
    "status",
    "order_index",
    "content_version",
    "created_at",
    "updated_at",
    "deleted_at",
}
SUBMISSION_COLUMNS = {
    "id",
    "user_id",
    "exercise_id",
    "attempt_no",
    "code_text",
    "claimed_output",
    "judging_mode",
    "verification_method",
    "verification_strength",
    "is_passed",
    "ai_assistance_level",
    "used_ai",
    "passed_with_ai",
    "created_at",
}

# 0004 之前的八张业务表：列数必须与迁移前完全一致（结构零变化）。
FROZEN_COLUMN_COUNTS = {
    "users": 7,
    "user_profiles": 8,
    "skills": 9,
    "diagnostic_attempts": 11,
    "user_skill_levels": 12,
    "lessons": 16,
    "learning_progress": 11,
    "study_plan_items": 12,
}

VARIABLES_EX1 = "route_a.py.variables.ex1"
CONTROL_FLOW_EX1 = "route_a.py.control_flow.ex1"

# 满足 variables.ex1 的 7 条必须写法，且不命中任何一条禁止写法。
PASS_CODE = (
    "name = \"\u5c0f\u660e\"\n"
    "age = 18\n"
    "height = 1.75\n"
    "is_student = True\n"
    "\n"
    "print(type(name))\n"
    "print(type(age))\n"
    "print(type(height))\n"
    "print(type(is_student))\n"
    "print(name + \" \u4eca\u5e74 \" + str(age) + \" \u5c81\")\n"
)

MISSING_PATTERN_CODE = "# \u8fd8\u6ca1\u5f00\u59cb\u5199\n"

SELECT_EXERCISE_ID = text("SELECT id FROM exercises WHERE code = :code")
SELECT_USK_SNAPSHOT = text(
    "SELECT level, count(*) AS total FROM user_skill_levels GROUP BY level ORDER BY level"
)


async def _exercise_id(session: AsyncSession, code: str) -> int:
    return int((await session.execute(SELECT_EXERCISE_ID, {"code": code})).scalar_one())


async def _usk_snapshot(session: AsyncSession) -> dict[int, int]:
    rows = (await session.execute(SELECT_USK_SNAPSHOT)).mappings().all()
    return {int(row["level"]): int(row["total"]) for row in rows}


def _table_columns(rows: list[dict[str, Any]], table: str) -> set[str]:
    return {str(row["column_name"]) for row in rows if row["table_name"] == table}


async def test_0004_is_on_the_alembic_chain_and_creates_exactly_two_tables(
    db_session: AsyncSession,
) -> None:
    current = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert current.returncode == 0, current.stderr
    assert f"{HEAD_REVISION} (head)" in current.stdout

    tables = set(
        (
            await db_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {"exercises", "submissions"} | LATER_TABLES <= tables
    assert tables - {"exercises", "submissions"} - LATER_TABLES == set(
        FROZEN_COLUMN_COUNTS
    ) | {"alembic_version"}

    rows = [
        dict(row)
        for row in (
            await db_session.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name IN ('exercises','submissions')"
                )
            )
        )
        .mappings()
        .all()
    ]
    assert _table_columns(rows, "exercises") == EXERCISE_COLUMNS
    assert _table_columns(rows, "submissions") == SUBMISSION_COLUMNS


async def test_existing_tables_kept_their_frozen_structure(db_session: AsyncSession) -> None:
    counts = {
        str(row["table_name"]): int(row["total"])
        for row in (
            await db_session.execute(
                text(
                    "SELECT table_name, count(*) AS total FROM information_schema.columns "
                    "WHERE table_schema = 'public' GROUP BY table_name"
                )
            )
        )
        .mappings()
        .all()
    }
    assert {table: counts[table] for table in FROZEN_COLUMN_COUNTS} == FROZEN_COLUMN_COUNTS


async def test_ten_exercises_two_per_lesson_and_every_lesson_exists(
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT e.code, e.lesson_id, e.order_index, l.code AS lesson_code, l.status "
                "FROM exercises e JOIN lessons l ON l.id = e.lesson_id "
                "ORDER BY e.lesson_id, e.order_index"
            )
        )
    ).mappings().all()
    assert len(rows) == 10
    assert all(row["status"] == "published" for row in rows)

    per_lesson: dict[int, int] = {}
    for row in rows:
        per_lesson[int(row["lesson_id"])] = per_lesson.get(int(row["lesson_id"]), 0) + 1
    assert sorted(per_lesson) == [1, 2, 3, 4, 5]
    assert set(per_lesson.values()) == {2}
    assert len({str(row["code"]) for row in rows}) == 10
    assert {str(row["lesson_code"]) for row in rows} == {
        "route_a.py.variables",
        "route_a.py.control_flow",
        "route_a.py.list_dict",
        "route_a.py.functions",
        "route_a.py.debugging",
    }


async def test_every_exercise_ships_two_visible_tests_and_pattern_arrays(
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT code, visible_tests, required_patterns, forbidden_patterns, "
                "expected_output, estimated_minutes, difficulty, content_version "
                "FROM exercises ORDER BY id"
            )
        )
    ).mappings().all()
    for row in rows:
        assert isinstance(row["visible_tests"], list), row["code"]
        assert len(row["visible_tests"]) >= 2, row["code"]
        assert all({"name", "expect"} <= set(case) for case in row["visible_tests"])
        assert isinstance(row["required_patterns"], list) and row["required_patterns"]
        assert isinstance(row["forbidden_patterns"], list)
        assert 1 <= int(row["estimated_minutes"]) <= 120
        assert 1 <= int(row["difficulty"]) <= 5
        assert int(row["content_version"]) >= 1


async def test_detail_endpoint_returns_no_answer_keys(api: Any, db_session: AsyncSession) -> None:
    response = await api.get(f"/api/v1/exercises/{await _exercise_id(db_session, VARIABLES_EX1)}")
    assert response.status_code == 200
    body = response.json()
    for key in ANSWER_KEYS:
        assert key not in body
    assert body["visible_tests"] and len(body["visible_tests"]) >= 2
    # name/expect 是后端口径；input/expected 是 Web 客户端已读取的兼容别名
    for case in body["visible_tests"]:
        assert {"name", "expect", "input", "expected"} <= set(case)
        assert case["expected"] == case["expect"] and case["input"] == case["name"]
    assert body["starter_code"] and body["prompt"]


async def test_static_rule_pass_is_recorded_as_assessed(api: Any, db_session: AsyncSession) -> None:
    exercise_id = await _exercise_id(db_session, VARIABLES_EX1)
    response = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions", json={"code_text": PASS_CODE}
    )
    assert response.status_code == 201
    body = response.json()
    print("PASS_RESPONSE:", json.dumps(body, ensure_ascii=False))
    assert body["judging_mode"] == "static_rule"
    assert body["verification_method"] == "static_rule"
    assert body["verification_strength"] == "assessed"
    assert body["evidence_label"] == "已验证（静态规则）"
    assert body["is_passed"] is True
    assert body["checks"] and all({"name", "passed", "detail"} <= set(c) for c in body["checks"])
    assert "required_patterns" not in json.dumps(body)


async def test_static_rule_missing_required_pattern_fails(
    api: Any, db_session: AsyncSession
) -> None:
    exercise_id = await _exercise_id(db_session, VARIABLES_EX1)
    response = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions", json={"code_text": MISSING_PATTERN_CODE}
    )
    assert response.status_code == 201
    body = response.json()
    print("FAIL_RESPONSE:", json.dumps(body, ensure_ascii=False))
    assert body["is_passed"] is False
    assert body["verification_strength"] == "assessed"
    assert [c["name"] for c in body["checks"] if not c["passed"]]


async def test_forbidden_pattern_hit_fails(api: Any, db_session: AsyncSession) -> None:
    exercise_id = await _exercise_id(db_session, VARIABLES_EX1)
    response = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": PASS_CODE + '\neval("1 + 1")\n'},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["is_passed"] is False
    assert "forbidden_1" in [check["name"] for check in body["checks"] if not check["passed"]]


async def test_claimed_output_must_match_after_normalisation(
    api: Any, db_session: AsyncSession
) -> None:
    exercise_id = await _exercise_id(db_session, "route_a.py.variables.ex2")
    code = "age_text = \"18\"\nage = int(age_text)\nprint(age + 1)\n"
    good = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": code, "claimed_output": "19  \n\n"},
    )
    assert good.status_code == 201 and good.json()["is_passed"] is True
    bad = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": code, "claimed_output": "20"},
    )
    assert bad.status_code == 201 and bad.json()["is_passed"] is False


async def test_self_check_is_self_reported_and_never_verified(
    api: Any, db_session: AsyncSession
) -> None:
    exercise_id = await _exercise_id(db_session, CONTROL_FLOW_EX1)
    response = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": MISSING_PATTERN_CODE, "self_reported_passed": True},
    )
    assert response.status_code == 201
    body = response.json()
    print("SELF_CHECK_RESPONSE:", json.dumps(body, ensure_ascii=False))
    assert body["judging_mode"] == "self_check"
    assert body["verification_method"] == "self_report"
    assert body["verification_strength"] == "self_reported"
    assert body["evidence_label"] == "未验证（自检）"
    assert body["is_passed"] is True


async def test_no_judgement_writes_user_skill_levels(api: Any, db_session: AsyncSession) -> None:
    before = await _usk_snapshot(db_session)
    exercise_id = await _exercise_id(db_session, VARIABLES_EX1)
    await api.post(f"/api/v1/exercises/{exercise_id}/submissions", json={"code_text": PASS_CODE})
    await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": MISSING_PATTERN_CODE, "self_reported_passed": False},
    )
    after = await _usk_snapshot(db_session)
    print("USK_BEFORE:", before, "USK_AFTER:", after)
    assert before == after
    assert set(after) <= {0, 1, 2}


async def test_history_appends_and_attempt_no_increases(
    api: Any, db_session: AsyncSession
) -> None:
    exercise_id = await _exercise_id(db_session, VARIABLES_EX1)
    first = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions", json={"code_text": MISSING_PATTERN_CODE}
    )
    second = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions", json={"code_text": PASS_CODE}
    )
    history = await api.get(f"/api/v1/exercises/{exercise_id}/submissions")
    assert history.status_code == 200
    body = history.json()
    print("HISTORY:", json.dumps(body, ensure_ascii=False))
    ids = [item["submission_id"] for item in body["items"]]
    assert ids[:2] == [second.json()["submission_id"], first.json()["submission_id"]]
    assert body["items"][0]["attempt_no"] > body["items"][1]["attempt_no"]
    assert body["total"] >= 2


async def test_recent_submissions_are_newest_first(api: Any, db_session: AsyncSession) -> None:
    variables = await _exercise_id(db_session, VARIABLES_EX1)
    control = await _exercise_id(db_session, CONTROL_FLOW_EX1)
    created = []
    for exercise_id, payload in (
        (variables, {"code_text": MISSING_PATTERN_CODE}),
        (control, {"code_text": MISSING_PATTERN_CODE, "self_reported_passed": True}),
        (variables, {"code_text": PASS_CODE}),
    ):
        response = await api.post(
            f"/api/v1/exercises/{exercise_id}/submissions", json=payload
        )
        assert response.status_code == 201
        created.append(response.json()["submission_id"])

    recent = await api.get("/api/v1/submissions/recent?limit=5")
    assert recent.status_code == 200
    body = recent.json()
    print("RECENT:", json.dumps(body, ensure_ascii=False))
    ids = [item["submission_id"] for item in body["items"]]
    assert ids == sorted(ids, reverse=True)
    assert ids[:3] == list(reversed(created))
    assert body["items"][0]["evidence_label"] in {"已验证（静态规则）", "未验证（自检）"}


async def test_list_filters_by_lesson_id(api: Any, db_session: AsyncSession) -> None:
    response = await api.get("/api/v1/exercises?lesson_id=4")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["lesson_code"] for item in body["items"]} == {"route_a.py.functions"}
    for item in body["items"]:
        assert "required_patterns" not in item and "expected_output" not in item


async def test_unknown_exercise_is_404(api: Any) -> None:
    assert (await api.get("/api/v1/exercises/999999")).status_code == 404
    response = await api.post(
        "/api/v1/exercises/999999/submissions", json={"code_text": "print(1)"}
    )
    assert response.status_code == 404


async def test_blank_code_text_is_refused(api: Any, db_session: AsyncSession) -> None:
    exercise_id = await _exercise_id(db_session, VARIABLES_EX1)
    response = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions", json={"code_text": "   "}
    )
    assert response.status_code == 422
