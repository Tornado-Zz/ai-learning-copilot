"""Sprint 7 验收：a3（API）与 a4（LLM）两节 AI 课，以及每课两道练习（迁移 0011）。

隔离与只读策略与 test_lessons_api.py 一致：lessons / exercises 是迁移播种的版本化
内容，产品不会改写，所以按 code 逐条断言；用户数据（submissions 等）一行都不碰。
幂等性用 migration_probe 开的一次性临时库验证：0010 -> head -> head，逐表行数不变、
内容版本不变、正文与迁移常量逐字相同。全程不执行 DELETE / DROP 产品表。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0011_sprint7_ai_content.py"
)
SPRINT7_REVISION = "0011_sprint7_ai_content"
PREVIOUS_REVISION = "0010_capstone_review_requires_reviewer"

AI_LESSON_CODES = ["route_a.api.json", "route_a.llm.messages"]
LEGACY_LESSON_CODES = [
    "route_a.py.variables",
    "route_a.py.control_flow",
    "route_a.py.list_dict",
    "route_a.py.functions",
    "route_a.py.debugging",
]
LEGACY_EXERCISE_COUNT = 10
CONTENT_KEYS = {
    "schema_version",
    "goal",
    "explanation",
    "example",
    "common_mistakes",
    "self_check",
}
# 离线契约：正文与练习里不允许出现真实网络地址，也不允许出现任何密钥字样。
NETWORK_MARKERS = ("http://", "https://", "api_key")
NETWORK_GUARD_MARKERS = ("https?://", "urlopen", "requests")

SELECT_AI_LESSONS = text(
    """
    SELECT l.id, l.code, l.title, l.summary, l.stage, l.estimated_minutes, l.order_index,
           l.difficulty, l.status, l.content_version, l.content, s.code AS skill_code
    FROM lessons l
    JOIN skills s ON s.id = l.skill_id
    WHERE l.code = ANY(:codes) AND l.deleted_at IS NULL
    ORDER BY l.order_index
    """
)

SELECT_AI_EXERCISES = text(
    """
    SELECT e.code, e.lesson_id, e.title, e.prompt, e.starter_code, e.visible_tests,
           e.required_patterns, e.forbidden_patterns, e.expected_output, e.estimated_minutes,
           e.difficulty, e.order_index, e.content_version, e.status, l.code AS lesson_code
    FROM exercises e
    JOIN lessons l ON l.id = e.lesson_id
    WHERE l.code = ANY(:codes)
    ORDER BY l.code, e.order_index
    """
)

PROBE_TABLES = (
    "users",
    "skills",
    "lessons",
    "exercises",
    "learning_progress",
    "study_plan_items",
    "submissions",
)


def _load_migration(path: Path) -> Any:
    """迁移文件按路径加载：versions 目录里的模块名以数字开头，不是可导入的包成员。"""
    spec = importlib.util.spec_from_file_location("sprint7_ai_content", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load_migration(MIGRATION_PATH)


async def _ai_lessons(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(SELECT_AI_LESSONS, {"codes": AI_LESSON_CODES})
    ).mappings().all()
    return [dict(row) for row in rows]


async def _ai_exercises(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(SELECT_AI_EXERCISES, {"codes": AI_LESSON_CODES})
    ).mappings().all()
    return [dict(row) for row in rows]


async def test_01_two_ai_lessons_are_published(db_session: AsyncSession) -> None:
    """a3 与 a4 各有一节课，且都是已发布、可直接学习的状态。"""
    rows = await _ai_lessons(db_session)
    assert [row["code"] for row in rows] == AI_LESSON_CODES

    expected = {
        "route_a.api.json": {
            "title": "请求、响应与 JSON",
            "skill_code": "route_a.a3",
            "stage": 3,
            "estimated_minutes": 25,
            "order_index": 6,
        },
        "route_a.llm.messages": {
            "title": "调用大模型的请求长什么样",
            "skill_code": "route_a.a4",
            "stage": 4,
            "estimated_minutes": 30,
            "order_index": 7,
        },
    }
    for row in rows:
        want = expected[row["code"]]
        assert row["title"] == want["title"], row["code"]
        assert row["skill_code"] == want["skill_code"], row["code"]
        assert row["stage"] == want["stage"], row["code"]
        assert row["estimated_minutes"] == want["estimated_minutes"], row["code"]
        assert row["order_index"] == want["order_index"], row["code"]
        assert row["status"] == "published", row["code"]
        assert row["content_version"] == 1, row["code"]
        # lessons.estimated_minutes 的库约束是 1–240，这里收紧到产品口径的 >= 15。
        assert row["estimated_minutes"] >= 15, row["code"]
        assert 1 <= row["difficulty"] <= 5, row["code"]
        assert row["summary"].strip(), row["code"]

    # 两节课必须接在既有 5 节之后，而不是插进 Python 基础课中间。
    assert [row["order_index"] for row in rows] == [6, 7]


async def test_02_each_ai_lesson_has_two_published_exercises(
    db_session: AsyncSession,
) -> None:
    """每节新课 2 道练习，order_index 1、2，全部 published。"""
    rows = await _ai_exercises(db_session)
    assert len(rows) == 4, [row["code"] for row in rows]

    per_lesson: dict[str, list[dict[str, Any]]] = {code: [] for code in AI_LESSON_CODES}
    for row in rows:
        per_lesson[row["lesson_code"]].append(row)
        assert row["status"] == "published", row["code"]
        assert row["content_version"] == 1, row["code"]
        assert row["title"].strip() and row["prompt"].strip(), row["code"]
        assert row["starter_code"].strip(), row["code"]

    for lesson_code, exercises in per_lesson.items():
        assert len(exercises) == 2, lesson_code
        assert [row["order_index"] for row in exercises] == [1, 2], lesson_code


async def test_03_lesson_content_carries_the_same_five_blocks(
    db_session: AsyncSession,
) -> None:
    """正文与既有 5 节课同款：schema_version / goal / explanation / example /
    common_mistakes / self_check，且讲解是成段文字而不是要点堆砌。"""
    rows = await _ai_lessons(db_session)
    assert len(rows) == 2

    for row in rows:
        content = row["content"]
        assert set(content) == CONTENT_KEYS, row["code"]
        assert content["schema_version"] == 1, row["code"]
        assert content["goal"].strip(), row["code"]

        parts = content["explanation"]
        assert isinstance(parts, list) and len(parts) >= 3, row["code"]
        for part in parts:
            assert isinstance(part, str) and len(part.strip()) >= 30, row["code"]

        example = content["example"]
        assert example["title"].strip(), row["code"]
        assert example["code"].strip(), row["code"]
        assert isinstance(example["output"], str) and example["output"].strip(), row["code"]
        assert isinstance(example["notes"], list) and example["notes"], row["code"]

        mistakes = content["common_mistakes"]
        assert len(mistakes) >= 3, row["code"]
        for item in mistakes:
            assert set(item) == {"mistake", "why", "fix"}, row["code"]
            assert all(str(item[key]).strip() for key in ("mistake", "why", "fix")), row["code"]

        checks = content["self_check"]
        assert len(checks) >= 3, row["code"]
        for item in checks:
            assert set(item) == {"question", "answer"}, row["code"]
            assert item["question"].strip() and item["answer"].strip(), row["code"]


async def test_04_exercise_answer_keys_can_tell_written_from_unwritten(
    db_session: AsyncSession,
) -> None:
    """判题是纯文本静态规则，所以答案键必须自洽：正则合法、可见用例够 2 条、
    而且照着 starter 原样提交一定通不过（否则规则分不出「写了」和「没写」）。"""
    rows = await _ai_exercises(db_session)
    assert len(rows) == 4

    for row in rows:
        code = row["code"]
        required = row["required_patterns"]
        forbidden = row["forbidden_patterns"]

        assert isinstance(required, list) and required, code
        assert isinstance(forbidden, list) and forbidden, code
        assert all(isinstance(pattern, str) and pattern.strip() for pattern in required), code
        for pattern in [*required, *forbidden]:
            re.compile(pattern)  # 不是合法正则会在这里抛 re.error

        visible = row["visible_tests"]
        assert isinstance(visible, list) and len(visible) >= 2, code
        for case in visible:
            assert {"name", "expect"} <= set(case), code
            assert str(case["name"]).strip() and str(case["expect"]).strip(), code

        assert row["estimated_minutes"] >= 15, code
        assert 1 <= row["difficulty"] <= 5, code
        assert row["expected_output"] is None or row["expected_output"].strip(), code

        unsatisfied = [
            pattern for pattern in required if not re.search(pattern, row["starter_code"])
        ]
        assert len(unsatisfied) >= 2, (code, unsatisfied)
        # 离线契约要落到判题里：禁止项必须堵住联网写法。
        assert any(
            marker in pattern for pattern in forbidden for marker in NETWORK_GUARD_MARKERS
        ), code


async def test_05_content_never_asks_for_a_real_network_call(
    db_session: AsyncSession,
) -> None:
    """正文与练习 JSON 里不得出现真实地址或密钥字样：整节课离线可学、离线可判。"""
    lessons = await _ai_lessons(db_session)
    exercises = await _ai_exercises(db_session)
    assert len(lessons) == 2 and len(exercises) == 4

    blobs: list[tuple[str, str]] = []
    for row in lessons:
        blobs.append(
            (
                row["code"],
                json.dumps(
                    {
                        "title": row["title"],
                        "summary": row["summary"],
                        "content": row["content"],
                    },
                    ensure_ascii=False,
                ),
            )
        )
    for row in exercises:
        blobs.append(
            (
                row["code"],
                json.dumps(
                    {
                        "title": row["title"],
                        "prompt": row["prompt"],
                        "starter_code": row["starter_code"],
                        "visible_tests": row["visible_tests"],
                        "required_patterns": row["required_patterns"],
                        "forbidden_patterns": row["forbidden_patterns"],
                        "expected_output": row["expected_output"],
                    },
                    ensure_ascii=False,
                ),
            )
        )

    for code, blob in blobs:
        for marker in NETWORK_MARKERS:
            assert marker not in blob, (code, marker)


async def test_06_migration_is_idempotent_on_a_clean_database(migration_probe) -> None:
    """干净库：0010 -> head -> head。第二次升级不新增、不改写，正文与迁移常量逐字相同。"""
    async with migration_probe() as probe:
        probe.upgrade(PREVIOUS_REVISION)
        before = await probe.counts(PROBE_TABLES)
        assert before["lessons"] == 5, before
        assert before["exercises"] == 10, before

        probe.upgrade("head")
        assert SPRINT7_REVISION in probe.current()
        first = await probe.counts(PROBE_TABLES)
        assert first["lessons"] == before["lessons"] + 2, first
        assert first["exercises"] == before["exercises"] + 4, first

        # 再升一次 head：alembic 已在 head，种子必须一行不加、一行不改。
        probe.upgrade("head")
        second = await probe.counts(PROBE_TABLES)
        assert second == first, {table: (first[table], second[table]) for table in first}

        async with probe.connect() as connection:
            lesson_rows = await connection.fetch(
                "SELECT code, content_version, content FROM lessons WHERE code = ANY($1::text[])",
                AI_LESSON_CODES,
            )
            exercise_rows = await connection.fetch(
                "SELECT code, content_version, starter_code, required_patterns, visible_tests "
                "FROM exercises WHERE code = ANY($1::text[])",
                [exercise["code"] for exercise in MIGRATION.EXERCISES_V2],
            )

        assert len(lesson_rows) == 2 and len(exercise_rows) == 4
        stored_content = {
            row["code"]: (row["content_version"], json.loads(row["content"]))
            for row in lesson_rows
        }
        for lesson in MIGRATION.LESSONS_V2:
            assert stored_content[lesson["code"]] == (1, lesson["content"]), lesson["code"]

        stored_exercise = {row["code"]: row for row in exercise_rows}
        for exercise in MIGRATION.EXERCISES_V2:
            stored = stored_exercise[exercise["code"]]
            assert stored["content_version"] == 1, exercise["code"]
            assert stored["starter_code"] == exercise["starter_code"], exercise["code"]
            assert json.loads(stored["required_patterns"]) == exercise["required_patterns"]
            assert json.loads(stored["visible_tests"]) == exercise["visible_tests"]


async def test_07_python_lessons_and_their_exercises_are_untouched(
    db_session: AsyncSession,
) -> None:
    """0003 / 0004 的 5 节课与 10 道练习一行未改：新内容只是追加。"""
    lessons = (
        await db_session.execute(
            text(
                "SELECT code, status, content_version FROM lessons "
                "WHERE deleted_at IS NULL ORDER BY order_index"
            )
        )
    ).mappings().all()
    assert [row["code"] for row in lessons] == LEGACY_LESSON_CODES + AI_LESSON_CODES
    assert all(row["status"] == "published" for row in lessons)
    assert all(int(row["content_version"]) == 1 for row in lessons)

    legacy_exercises = (
        await db_session.execute(
            text(
                "SELECT code, status, content_version FROM exercises "
                "WHERE code ~ '^route_a[.]py[.]' ORDER BY code"
            )
        )
    ).mappings().all()
    assert len(legacy_exercises) == LEGACY_EXERCISE_COUNT
    assert all(row["status"] == "published" for row in legacy_exercises)
    assert all(int(row["content_version"]) == 1 for row in legacy_exercises)
