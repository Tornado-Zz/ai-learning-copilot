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
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import ARRAY, SmallInteger, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.exercises import SubmissionCreateRequest
from app.services import exercises as exercises_service
from app.services import review as review_service
from app.services import study_plan as study_plan_service
from app.services import users as users_service

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[1]
REVISION = "0004_sprint3_exercises"
# Sprint 4 追加 0005、Sprint 5 追加 0006、Sprint 6 追加 0007、v0.1.2 追加 0008、
# v0.1.3 追加 0009 后 head 继续前移；0004 建的表与列必须保持原样。
# 0011 追加 a3/a4、0012 追加 a5/a6 四节 AI 课与 8 道练习，0013 再补 a2 两节课与
# 4 道练习，0014 给 exercises 加一列 requirement_labels，0017 再补 2 节课与 4 道
# 练习；head 一路前移，0004 建的 2 张表除这一列外不受影响。
HEAD_REVISION = "0017_sprint12_ai_core_content"
# 0005 与 0006 各建的表：结构的正确性由 Sprint 4 / Sprint 5 的测试负责，
# 这里只需要把它们算进"已存在的表"集合。
LATER_TABLES = {
    "ai_interactions",
    "knowledge_sources",
    "knowledge_chunks",
    "review_items",
    "capstone_submissions",
}
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
    # 0014：题面要求的中文清单，逐条对应 required_patterns，不是答案键。
    "requirement_labels",
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
                # 只断言 0004 播种的那 5 节 Python 课：0011 后来又给 a3/a4 两节新课
                # 各加了 2 道练习，那是新内容，不在 0004 的验收范围内。
                "WHERE l.code IN ('route_a.py.variables', 'route_a.py.control_flow', "
                "'route_a.py.list_dict', 'route_a.py.functions', 'route_a.py.debugging') "
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


# ---------------------------------------------------------------------------
# v0.1.2 错题本与间隔复习（review_items）：调度规则、端点与周计划第三遍
# ---------------------------------------------------------------------------
# 为什么这些用例住在本文件：v0.1.2 的错题本由"提交判题"驱动，入口就是本文件覆盖的
# POST /exercises/{id}/submissions。与既有用例同一隔离口径：所有写入都在
# conftest.db_session 的外层事务里，测试结束整体回滚，产品数据一行不留痕。
STUDY_TIMEZONE = "Asia/Shanghai"

SET_USER_CONFIRMED = text(
    "UPDATE users SET timezone = :timezone, timezone_source = 'user_confirmed' WHERE id = :user_id"
)
SET_PROFILE_BUDGET = text(
    "UPDATE user_profiles SET study_days = :days, daily_minutes = :daily_minutes "
    "WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))
LOCAL_TODAY = text("SELECT (now() AT TIME ZONE :timezone)::date")
WEEK_START = text("SELECT (date_trunc('week', now() AT TIME ZONE :timezone))::date")
SELECT_PUBLISHED_EXERCISE_IDS = text(
    "SELECT id FROM exercises WHERE status = 'published' AND deleted_at IS NULL ORDER BY id"
)
SELECT_ONE_OPEN_LESSON = text(
    "SELECT id FROM lessons WHERE status = 'published' AND deleted_at IS NULL ORDER BY id LIMIT 1"
)
INSERT_REVIEW_ROW = text(
    """
    INSERT INTO review_items (
        user_id, exercise_id, source_submission_id, streak, interval_days,
        next_review_on, last_result, last_reviewed_at, status
    )
    VALUES (
        :user_id, :exercise_id, NULL, :streak, :interval_days,
        :next_review_on, :last_result, NULL, :status
    )
    ON CONFLICT (user_id, exercise_id) DO UPDATE SET
        streak = EXCLUDED.streak,
        interval_days = EXCLUDED.interval_days,
        next_review_on = EXCLUDED.next_review_on,
        last_result = EXCLUDED.last_result,
        status = EXCLUDED.status,
        updated_at = now()
    RETURNING id
    """
)
SELECT_REVIEW_ROW = text(
    """
    SELECT id, exercise_id, source_submission_id, streak, interval_days,
           next_review_on, last_result, last_reviewed_at, status
    FROM review_items
    WHERE user_id = :user_id AND exercise_id = :exercise_id
    """
)
COUNT_USER_REVIEWS = text("SELECT count(*) FROM review_items WHERE user_id = :user_id")
SELECT_REVIEW_PLAN_ROWS = text(
    """
    SELECT id, plan_date, target_id, planned_minutes, status, rationale, dedupe_key
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start AND kind = 'review'
      AND status <> 'expired'
    ORDER BY plan_date, id
    """
)
INSERT_SETTLED_DAY = text(
    """
    INSERT INTO study_plan_items (
        user_id, week_start, plan_date, kind, target_id, planned_minutes,
        status, rationale, dedupe_key
    )
    VALUES (
        :user_id, :week_start, :plan_date, 'lesson', :target_id, 15,
        'done', 'pytest 预算占位行', :dedupe_key
    )
    """
)


async def _confirm(
    session: AsyncSession,
    user_id: int,
    *,
    days: list[int] | None = None,
    daily_minutes: int = 240,
) -> None:
    await session.execute(
        SET_USER_CONFIRMED, {"user_id": user_id, "timezone": STUDY_TIMEZONE}
    )
    await session.execute(
        SET_PROFILE_BUDGET,
        {
            "user_id": user_id,
            "days": days or [1, 2, 3, 4, 5, 6, 7],
            "daily_minutes": daily_minutes,
        },
    )


async def _today(session: AsyncSession):
    return (await session.execute(LOCAL_TODAY, {"timezone": STUDY_TIMEZONE})).scalar_one()


async def _week_start(session: AsyncSession):
    return (await session.execute(WEEK_START, {"timezone": STUDY_TIMEZONE})).scalar_one()


async def _daily_minutes(session: AsyncSession, user_id: int) -> int:
    return int(
        (
            await session.execute(
                text("SELECT daily_minutes FROM user_profiles WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
        ).scalar_one()
    )


async def _exercise_ids(session: AsyncSession, count: int) -> list[int]:
    ids = [
        int(exercise_id)
        for exercise_id in (await session.execute(SELECT_PUBLISHED_EXERCISE_IDS)).scalars().all()
    ]
    assert len(ids) >= count, "题库种子不足"
    return ids[:count]


async def _submit(
    session: AsyncSession, user_id: int, exercise_id: int, *, passed: bool
) -> dict[str, object]:
    """判题入口：自检口径最省事，is_passed 就是 self_reported_passed。"""
    return await exercises_service.create_submission(
        session,
        user_id,
        exercise_id,
        SubmissionCreateRequest(code_text="print(1)", self_reported_passed=passed),
    )


# 第 1 课的 ex1 规则是固定的填空题，这段代码满足它的全部必须写法、不触发禁止写法。
# 间隔机制用例必须走「静态规则通过」：自检申报的通过按设计不推进错题本。
_STATIC_PASS_CODE = (
    'name = "小明"\n'
    "age = 18\n"
    "height = 1.75\n"
    "is_student = True\n"
    "print(type(name))\n"
    "print(type(is_student))\n"
    "print(str(age))\n"
)


async def _submit_static_pass(
    session: AsyncSession, user_id: int, exercise_id: int
) -> dict[str, object]:
    """提交一段能通过静态规则的代码，确保判题口径是 static_rule。"""
    judged = await exercises_service.create_submission(
        session,
        user_id,
        exercise_id,
        SubmissionCreateRequest(code_text=_STATIC_PASS_CODE),
    )
    assert judged["verification_strength"] == "assessed", (
        "预置代码必须走静态规则通过，否则间隔机制用例会测到错误的路径"
    )
    assert judged["is_passed"] is True
    return judged


async def _review_row(session: AsyncSession, user_id: int, exercise_id: int):
    return (
        (await session.execute(SELECT_REVIEW_ROW, {"user_id": user_id, "exercise_id": exercise_id}))
        .mappings()
        .first()
    )


async def _seed_review_row(
    session: AsyncSession,
    user_id: int,
    exercise_id: int,
    *,
    next_review_on,
    streak: int = 0,
    interval_days: int = 1,
    status: str = "pending",
    last_result: str = "failed",
) -> int:
    return int(
        (
            await session.execute(
                INSERT_REVIEW_ROW,
                {
                    "user_id": user_id,
                    "exercise_id": exercise_id,
                    "streak": streak,
                    "interval_days": interval_days,
                    "next_review_on": next_review_on,
                    "last_result": last_result,
                    "status": status,
                },
            )
        ).scalar_one()
    )


async def _park_review_rows(session: AsyncSession, user_id: int, *, far) -> None:
    """把该用户既有的错题本行推到窗口之外（UPDATE，不删除）。

    集成库可能已经有真实使用产生的错题本行（单用户语义下属于种子用户），断言"没有
    到期复习就不排"时必须先把它们移出 [today, week_end]；外层事务回滚后原样恢复。
    """
    await session.execute(
        text(
            "UPDATE review_items SET next_review_on = :far "
            "WHERE user_id = :user_id AND status = 'pending'"
        ),
        {"far": far, "user_id": user_id},
    )


async def test_12_a_wrong_answer_creates_one_review_row_due_tomorrow(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    await _confirm(db_session, user_id)
    exercise_id = (await _exercise_ids(db_session, 1))[0]

    judged = await _submit(db_session, user_id, exercise_id, passed=False)
    assert judged["is_passed"] is False

    row = await _review_row(db_session, user_id, exercise_id)
    assert row is not None
    today = await _today(db_session)
    assert int(row["streak"]) == 0
    assert int(row["interval_days"]) == 1
    assert row["next_review_on"] == today + timedelta(days=1)
    assert row["status"] == "pending"
    assert row["last_result"] == "failed"
    # 同事务：来源提交就是刚才那一行
    assert int(row["source_submission_id"]) == int(judged["submission_id"])


async def test_13_a_second_wrong_answer_resets_an_advanced_row(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    await _confirm(db_session, user_id)
    exercise_id = (await _exercise_ids(db_session, 1))[0]
    await _seed_review_row(
        db_session,
        user_id,
        exercise_id,
        next_review_on=(await _today(db_session)) + timedelta(days=14),
        streak=2,
        interval_days=7,
        status="done",
        last_result="passed",
    )

    await _submit(db_session, user_id, exercise_id, passed=False)

    row = await _review_row(db_session, user_id, exercise_id)
    today = await _today(db_session)
    assert int(row["streak"]) == 0
    assert int(row["interval_days"]) == 1
    assert row["next_review_on"] == today + timedelta(days=1)
    assert row["status"] == "pending"
    assert row["last_result"] == "failed"
    # 重置不是删除：仍然是同一行
    assert int((await db_session.execute(COUNT_USER_REVIEWS, {"user_id": user_id})).scalar_one()) == 1


async def test_14_a_passed_answer_takes_the_three_day_interval(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    await _confirm(db_session, user_id)
    exercise_id = (await _exercise_ids(db_session, 1))[0]
    today = await _today(db_session)
    await _seed_review_row(db_session, user_id, exercise_id, next_review_on=today)

    await _submit_static_pass(db_session, user_id, exercise_id)

    row = await _review_row(db_session, user_id, exercise_id)
    assert int(row["streak"]) == 1
    assert int(row["interval_days"]) == 3
    assert row["next_review_on"] == today + timedelta(days=3)
    assert row["status"] == "pending"
    assert row["last_result"] == "passed"
    assert row["last_reviewed_at"] is not None
    assert review_service.next_interval_days(1) == 3


async def test_15_seven_days_then_fourteen_days_and_done(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    await _confirm(db_session, user_id)
    exercise_id = (await _exercise_ids(db_session, 1))[0]
    today = await _today(db_session)
    await _seed_review_row(
        db_session,
        user_id,
        exercise_id,
        next_review_on=today + timedelta(days=3),
        streak=1,
        interval_days=3,
        last_result="passed",
    )

    await _submit_static_pass(db_session, user_id, exercise_id)
    row = await _review_row(db_session, user_id, exercise_id)
    assert (int(row["streak"]), int(row["interval_days"]), row["status"]) == (2, 7, "pending")
    assert row["next_review_on"] == today + timedelta(days=7)

    await _submit_static_pass(db_session, user_id, exercise_id)
    row = await _review_row(db_session, user_id, exercise_id)
    assert (int(row["streak"]), int(row["interval_days"]), row["status"]) == (3, 14, "done")
    assert row["next_review_on"] == today + timedelta(days=14)

    # 第 4 次答对：已经没有 pending 行，字段一个都不动（R3）
    await _submit_static_pass(db_session, user_id, exercise_id)
    again = await _review_row(db_session, user_id, exercise_id)
    assert (int(again["streak"]), int(again["interval_days"]), again["status"]) == (3, 14, "done")
    assert review_service.next_interval_days(2) == 7
    assert review_service.next_interval_days(3) == review_service.next_interval_days(9) == 14


async def test_16_a_passed_answer_without_a_row_creates_nothing(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    await _confirm(db_session, user_id)
    exercise_id = (await _exercise_ids(db_session, 1))[0]

    judged = await _submit_static_pass(db_session, user_id, exercise_id)
    assert judged["is_passed"] is True
    assert (await _review_row(db_session, user_id, exercise_id)) is None
    assert int((await db_session.execute(COUNT_USER_REVIEWS, {"user_id": user_id})).scalar_one()) == 0


async def test_17_a_done_row_is_kept_and_only_flips_back_to_pending(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    await _confirm(db_session, user_id)
    exercise_id = (await _exercise_ids(db_session, 1))[0]
    today = await _today(db_session)
    row_id = await _seed_review_row(
        db_session,
        user_id,
        exercise_id,
        next_review_on=today,
        streak=2,
        interval_days=7,
        last_result="passed",
    )

    await _submit_static_pass(db_session, user_id, exercise_id)
    row = await _review_row(db_session, user_id, exercise_id)
    assert row["status"] == "done" and int(row["streak"]) == 3
    assert int(row["id"]) == row_id
    assert int((await db_session.execute(COUNT_USER_REVIEWS, {"user_id": user_id})).scalar_one()) == 1

    # 答错只重置、不删除：done 行回到 pending，id 不变
    await _submit(db_session, user_id, exercise_id, passed=False)
    row = await _review_row(db_session, user_id, exercise_id)
    assert int(row["id"]) == row_id
    assert row["status"] == "pending" and row["last_result"] == "failed"
    assert int((await db_session.execute(COUNT_USER_REVIEWS, {"user_id": user_id})).scalar_one()) == 1


async def test_18_list_items_filters_due_rows_and_orders_by_next_review_on(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    exercises = await _exercise_ids(db_session, 4)
    today = await _today(db_session)
    overdue, finished, due_today, future = exercises
    await _seed_review_row(db_session, user_id, overdue, next_review_on=today - timedelta(days=2))
    await _seed_review_row(
        db_session,
        user_id,
        finished,
        next_review_on=today - timedelta(days=1),
        streak=3,
        interval_days=14,
        status="done",
        last_result="passed",
    )
    await _seed_review_row(db_session, user_id, due_today, next_review_on=today)
    await _seed_review_row(
        db_session, user_id, future, next_review_on=today + timedelta(days=5), interval_days=3
    )

    everything = await review_service.list_items(
        db_session, user_id=user_id, due_only=False, limit=20
    )
    assert [item["exercise_id"] for item in everything["items"]] == [
        overdue,
        finished,
        due_today,
        future,
    ]
    assert [item["due"] for item in everything["items"]] == [True, False, True, False]
    assert everything["total"] == 4
    assert everything["due_total"] == 2
    first = everything["items"][0]
    assert int(first["lesson_id"]) >= 1 and first["exercise_title"].strip()

    due_only = await review_service.list_items(db_session, user_id=user_id, due_only=True, limit=20)
    assert [item["exercise_id"] for item in due_only["items"]] == [overdue, due_today]
    assert due_only["total"] == 2 and due_only["due_total"] == 2

    limited = await review_service.list_items(db_session, user_id=user_id, due_only=False, limit=1)
    assert len(limited["items"]) == 1
    # total 不受 limit 影响
    assert limited["total"] == 4


async def test_19_summary_counts_pending_due_and_done(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    empty = await review_service.summary(db_session, user_id=user_id)
    assert empty == {"pending": 0, "due_today": 0, "done": 0, "next_due_on": None}

    exercises = await _exercise_ids(db_session, 3)
    today = await _today(db_session)
    await _seed_review_row(db_session, user_id, exercises[0], next_review_on=today)
    await _seed_review_row(
        db_session, user_id, exercises[1], next_review_on=today + timedelta(days=3), interval_days=3
    )
    await _seed_review_row(
        db_session,
        user_id,
        exercises[2],
        next_review_on=today + timedelta(days=1),
        streak=3,
        interval_days=14,
        status="done",
        last_result="passed",
    )

    summary = await review_service.summary(db_session, user_id=user_id)
    assert summary["pending"] == 2
    assert summary["due_today"] == 1
    assert summary["done"] == 1
    assert summary["next_due_on"] == today


async def test_20_review_result_answers_404_for_another_users_row(
    api, db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    exercise_id = (await _exercise_ids(db_session, 1))[0]
    row_id = await _seed_review_row(
        db_session, user_id, exercise_id, next_review_on=await _today(db_session)
    )

    foreign = await api.post(f"/api/v1/review/items/{row_id}/result", json={"passed": True})
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "NOT_FOUND"

    missing = await api.post("/api/v1/review/items/999999999/result", json={"passed": False})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"

    row = await _review_row(db_session, user_id, exercise_id)
    assert int(row["streak"]) == 0 and row["status"] == "pending"


async def _due_review_count(session: AsyncSession, user_id: int, week_start) -> int:
    """[today, week_end] 内仍然 pending 的错题条数：周计划复习行的上界。"""
    return int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM review_items "
                    "WHERE user_id = :user_id AND status = 'pending' "
                    "AND next_review_on BETWEEN :today AND :week_end"
                ),
                {
                    "user_id": user_id,
                    "today": await _today(session),
                    "week_end": week_start + timedelta(days=6),
                },
            )
        ).scalar_one()
    )


async def _week_rows(session: AsyncSession, user_id: int, week_start) -> list[dict[str, object]]:
    rows = (
        (
            await session.execute(
                SELECT_REVIEW_PLAN_ROWS, {"user_id": user_id, "week_start": week_start}
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def _planned_minutes_by_date(session: AsyncSession, user_id: int, week_start) -> dict:
    """当日有效计划项（不含 expired）的分钟数与各 kind 条数。"""
    rows = (
        (
            await session.execute(
                text(
                    "SELECT plan_date, kind, planned_minutes FROM study_plan_items "
                    "WHERE user_id = :user_id AND week_start = :week_start "
                    "AND status <> 'expired'"
                ),
                {"user_id": user_id, "week_start": week_start},
            )
        )
        .mappings()
        .all()
    )
    summary: dict = {}
    for row in rows:
        bucket = summary.setdefault(row["plan_date"], {"minutes": 0, "kinds": {}})
        bucket["minutes"] += int(row["planned_minutes"])
        bucket["kinds"][str(row["kind"])] = bucket["kinds"].get(str(row["kind"]), 0) + 1
    return summary


async def test_21_the_plan_schedules_at_most_one_review_a_day_for_due_rows(
    db_session: AsyncSession,
) -> None:
    seeded = await users_service.get_single_user(db_session)
    user_id = int(seeded["id"])
    await _confirm(db_session, user_id)
    today = await _today(db_session)
    week_start = await _week_start(db_session)
    exercises = await _exercise_ids(db_session, 6)
    for exercise_id in exercises[:2]:
        await _seed_review_row(db_session, user_id, exercise_id, next_review_on=today)
    due_items = await _due_review_count(db_session, user_id, week_start)
    # 集成库里可能已有真实使用留下的到期行：断言只依赖"到期上界"，不假定绝对条数
    assert due_items >= 2

    payload = await study_plan_service.generate_plan(db_session, user_id=user_id)

    rows = await _week_rows(db_session, user_id, week_start)
    assert len(rows) >= 1, "有到期复习且额度足够时必须排进复习"
    assert len(rows) <= due_items, "复习行不得多于到期错题"
    plan_dates = [row["plan_date"] for row in rows]
    assert len(set(plan_dates)) == len(plan_dates), "每天最多 1 个复习"
    assert plan_dates == sorted(plan_dates)
    assert all(int(row["planned_minutes"]) == 15 for row in rows)
    assert all(row["status"] == "scheduled" for row in rows)
    # target 必须指向真实存在的已发布 exercise，且一周内不重复排同一道题
    published = set(
        int(exercise_id)
        for exercise_id in (await db_session.execute(SELECT_PUBLISHED_EXERCISE_IDS)).scalars().all()
    )
    targets = [int(row["target_id"]) for row in rows]
    assert set(targets) <= published
    assert len(set(targets)) == len(targets)
    assert all(row["rationale"].strip() for row in rows)
    assert payload["review_items"] == len(rows)
    # R1：复习行占用的 15 分钟之后，当日总分钟仍然不超额度
    budget = await _daily_minutes(db_session, user_id)
    per_date = await _planned_minutes_by_date(db_session, user_id, week_start)
    assert all(bucket["minutes"] <= budget for bucket in per_date.values()), per_date

    # 同周再生成一次：幂等，既有 review 行数不变
    again = await study_plan_service.generate_plan(db_session, user_id=user_id)
    rows_again = await _week_rows(db_session, user_id, week_start)
    assert len(rows_again) == len(rows)
    assert again["review_items"] == len(rows)


async def test_22_a_full_day_gets_neither_a_review_nor_an_exercise(
    db_session: AsyncSession,
) -> None:
    """(a) 课程已用满当日额度时，复习与练习都不排——额度是硬约束。"""
    seeded = await users_service.get_single_user(db_session)
    user_id = int(seeded["id"])
    # 每天只有 15 分钟，而且这 15 分钟已经被 done 的学习行用掉：额度已用满。
    await _confirm(db_session, user_id, daily_minutes=15)
    today = await _today(db_session)
    week_start = await _week_start(db_session)
    lesson_id = int((await db_session.execute(SELECT_ONE_OPEN_LESSON)).scalar_one())
    dates = [
        week_start + timedelta(days=offset)
        for offset in range(7)
        if today <= week_start + timedelta(days=offset)
    ]
    for plan_date in dates:
        await db_session.execute(
            INSERT_SETTLED_DAY,
            {
                "user_id": user_id,
                "week_start": week_start,
                "plan_date": plan_date,
                "target_id": lesson_id,
                "dedupe_key": f"pytest-review-quota-{plan_date.isoformat()}",
            },
        )
    exercises = await _exercise_ids(db_session, 2)
    for exercise_id in exercises:
        await _seed_review_row(db_session, user_id, exercise_id, next_review_on=today)
    assert await _due_review_count(db_session, user_id, week_start) >= 2, "到期行确实存在"

    payload = await study_plan_service.generate_plan(db_session, user_id=user_id)

    assert await _week_rows(db_session, user_id, week_start) == []
    per_date = await _planned_minutes_by_date(db_session, user_id, week_start)
    assert all(
        "review" not in bucket["kinds"] and "exercise" not in bucket["kinds"]
        for bucket in per_date.values()
    ), per_date
    assert payload["review_items"] == 0


async def test_22b_a_due_review_takes_the_slot_before_a_new_exercise(
    db_session: AsyncSession,
) -> None:
    """(b) 有到期复习时复习优先占位：同一天比"没有复习"时少排或不排新练习，且不超额度。"""
    seeded = await users_service.get_single_user(db_session)
    user_id = int(seeded["id"])
    budget = 45
    await _confirm(db_session, user_id, daily_minutes=budget)
    today = await _today(db_session)
    week_start = await _week_start(db_session)
    # 先把真实使用留下的 pending 行推出窗口：本次比较只由下面塞进来的到期行驱动
    await _park_review_rows(db_session, user_id, far=week_start + timedelta(days=60))
    assert await _due_review_count(db_session, user_id, week_start) == 0
    await study_plan_service.generate_plan(db_session, user_id=user_id)
    without_review = await _planned_minutes_by_date(db_session, user_id, week_start)
    exercises_before = sum(
        bucket["kinds"].get("exercise", 0) for bucket in without_review.values()
    )
    assert exercises_before >= 1, "对照前提：没有复习时当天能排到练习"
    assert all(bucket["minutes"] <= budget for bucket in without_review.values())

    exercise_id = (await _exercise_ids(db_session, 1))[0]
    await _seed_review_row(db_session, user_id, exercise_id, next_review_on=today)
    payload = await study_plan_service.generate_plan(db_session, user_id=user_id)

    rows = await _week_rows(db_session, user_id, week_start)
    assert rows, "有到期复习且额度够 15 分钟时必须排进复习"
    with_review = await _planned_minutes_by_date(db_session, user_id, week_start)
    for row in rows:
        plan_date = row["plan_date"]
        bucket = with_review[plan_date]
        assert bucket["kinds"].get("review", 0) == 1, "每天最多 1 个复习"
        # 复习占位之后，当日练习数不会比上年同一天的"无复习"方案更多
        assert bucket["kinds"].get("exercise", 0) <= without_review.get(plan_date, {}).get(
            "kinds", {}
        ).get("exercise", 0), (plan_date, bucket)
        # R1：复习的 15 分钟算在额度内，当日总分钟不超支
        assert bucket["minutes"] <= budget, (plan_date, bucket)
    assert payload["review_items"] == len(rows)
    print(
        f"review-vs-exercise daily_minutes={budget} | no-review: "
        + " ".join(
            f"{plan_date}={bucket['minutes']}min/ex{bucket['kinds'].get('exercise', 0)}"
            for plan_date, bucket in sorted(without_review.items())
        )
        + " | with-due-review: "
        + " ".join(
            f"{plan_date}={bucket['minutes']}min/rev{bucket['kinds'].get('review', 0)}"
            f"/ex{bucket['kinds'].get('exercise', 0)}"
            for plan_date, bucket in sorted(with_review.items())
        )
    )


async def test_23_endpoint_sequence_wrong_then_three_passes_reaches_done(
    api, db_session: AsyncSession
) -> None:
    """真实接口序列：答错建行 -> 三次答对 3/7/14 天 -> done。"""
    exercise_id = (await _exercise_ids(db_session, 1))[0]
    today = await _today(db_session)

    wrong = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": "print(1)", "self_reported_passed": False},
    )
    assert wrong.status_code == 201, wrong.text
    assert wrong.json()["is_passed"] is False

    listed = (await api.get("/api/v1/review/items", params={"due": 0, "limit": 20})).json()
    item = next(entry for entry in listed["items"] if entry["exercise_id"] == exercise_id)
    assert item["streak"] == 0 and item["interval_days"] == 1
    assert item["next_review_on"] == (today + timedelta(days=1)).isoformat()
    assert item["status"] == "pending" and item["due"] is False
    print("答错 -> GET /review/items:", item)

    for attempt, (days, status) in enumerate(((3, "pending"), (7, "pending"), (14, "done")), start=1):
        response = await api.post(
            f"/api/v1/review/items/{item['id']}/result", json={"passed": True}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["streak"] == attempt
        assert body["interval_days"] == days
        assert body["next_review_on"] == (today + timedelta(days=days)).isoformat()
        assert body["status"] == status
        assert body["due"] is False
        print(f"第 {attempt} 次答对 -> POST /review/items/{{id}}/result:", body)

    summary = (await api.get("/api/v1/review/summary")).json()
    assert summary["done"] >= 1
    assert summary["next_due_on"] is None or summary["next_due_on"] >= today.isoformat()
    print("GET /review/summary:", summary)

