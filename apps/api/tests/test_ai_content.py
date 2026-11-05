"""Sprint 7 / Sprint 8 / Sprint 9 验收：a3（API）、a4（LLM）、a5（RAG）、a6（Agent）
四节 AI 课，加上 a2（编程实践）两节补课，以及每课两道练习（迁移 0011 + 0012 + 0013）。

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

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
MIGRATION_PATHS = (
    VERSIONS_DIR / "0011_sprint7_ai_content.py",
    VERSIONS_DIR / "0012_sprint8_rag_agent.py",
    VERSIONS_DIR / "0013_sprint9_practice_content.py",
)
SPRINT7_REVISION = "0011_sprint7_ai_content"
SPRINT8_REVISION = "0012_sprint8_rag_agent"
SPRINT9_REVISION = "0013_sprint9_practice_content"
# 0014 只给 exercises 加 requirement_labels 并回填标签，不动课程与练习的正文：
# 它仍然让 head 前移，所以「第二次 upgrade 不新增行」这条断言要跟着 head 走。
LABELS_REVISION = "0014_sprint10_requirement_labels"
HEAD_REVISION = "0015_sprint11_print_rule"
PREVIOUS_REVISION = "0010_capstone_review_requires_reviewer"

AI_LESSON_CODES = [
    "route_a.api.json",
    "route_a.llm.messages",
    "route_a.rag.retrieval",
    "route_a.agent.tool",
    # 0013 补上 a2「编程实践」两节：order_index 接着 9 排到 11。
    "route_a.practice.decompose",
    "route_a.practice.debug",
]
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
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load_migration(MIGRATION_PATHS[0])
RAG_MIGRATION = _load_migration(MIGRATION_PATHS[1])
PRACTICE_MIGRATION = _load_migration(MIGRATION_PATHS[2])
# 三个迁移各自导出的常量名不同（V2 / V3 / V4），合起来才是这批新增课的全部内容。
SEEDED_LESSONS = (
    *MIGRATION.LESSONS_V2,
    *RAG_MIGRATION.LESSONS_V3,
    *PRACTICE_MIGRATION.LESSONS_V4,
)
SEEDED_EXERCISES = (
    *MIGRATION.EXERCISES_V2,
    *RAG_MIGRATION.EXERCISES_V3,
    *PRACTICE_MIGRATION.EXERCISES_V4,
)


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
    """a3 / a4 / a5 / a6 各有一节课、a2 补两节，且都是已发布、可直接学习的状态。"""
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
        "route_a.rag.retrieval": {
            "title": "检索增强：让回答有出处",
            "skill_code": "route_a.a5",
            "stage": 5,
            "estimated_minutes": 30,
            "order_index": 8,
        },
        "route_a.agent.tool": {
            "title": "第一次让模型用工具",
            "skill_code": "route_a.a6",
            "stage": 6,
            "estimated_minutes": 30,
            "order_index": 9,
        },
        "route_a.practice.decompose": {
            "title": "把一段需求拆成几个函数",
            "skill_code": "route_a.a2",
            "stage": 2,
            "estimated_minutes": 30,
            "order_index": 10,
        },
        "route_a.practice.debug": {
            "title": "读懂报错，自己定位",
            "skill_code": "route_a.a2",
            "stage": 2,
            "estimated_minutes": 30,
            "order_index": 11,
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

    # 新课必须接在既有 5 节之后，而不是插进 Python 基础课中间；0013 的 a2 两节只能
    # 接在 9 之后（迁移只发 INSERT、不改写既有行），所以 order_index 排到 10 / 11。
    assert [row["order_index"] for row in rows] == [6, 7, 8, 9, 10, 11]


async def test_02_each_ai_lesson_has_two_published_exercises(
    db_session: AsyncSession,
) -> None:
    """每节新课 2 道练习，order_index 1、2，全部 published。"""
    rows = await _ai_exercises(db_session)
    assert len(rows) == 12, [row["code"] for row in rows]

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
    assert len(rows) == 6

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
    assert len(rows) == 12

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
    assert len(lessons) == 6 and len(exercises) == 12

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
    """干净库：0010 -> head（0011 + 0012 + 0013 + 0014）-> head。第二次升级不新增、不改写。"""
    async with migration_probe() as probe:
        probe.upgrade(PREVIOUS_REVISION)
        before = await probe.counts(PROBE_TABLES)
        assert before["lessons"] == 5, before
        assert before["exercises"] == 10, before

        probe.upgrade("head")
        # 0011 / 0012 / 0013 三段种子都在这一次 0010 -> head 里跑过；0014 补标签，
        # 0015 只给既有题追加 print 规则（不新增行）。断言「到了最新版本」，
        # 而不是钉死某一个历史版本号——否则每加一个迁移都要改这里。
        assert HEAD_REVISION in probe.current()
        first = await probe.counts(PROBE_TABLES)
        # 0011 追加 2 节 + 4 道，0012 再追加 2 节 + 4 道，0013 再追加 2 节 + 4 道：
        # 0010 -> head 一共 +6 节、+12 道。
        assert first["lessons"] == before["lessons"] + 6, first
        assert first["exercises"] == before["exercises"] + 12, first

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
                [exercise["code"] for exercise in SEEDED_EXERCISES],
            )

        assert len(lesson_rows) == len(AI_LESSON_CODES)
        assert len(exercise_rows) == len(SEEDED_EXERCISES)
        stored_content = {
            row["code"]: (row["content_version"], json.loads(row["content"]))
            for row in lesson_rows
        }
        for lesson in SEEDED_LESSONS:
            assert stored_content[lesson["code"]] == (1, lesson["content"]), lesson["code"]

        stored_exercise = {row["code"]: row for row in exercise_rows}
        for exercise in SEEDED_EXERCISES:
            stored = stored_exercise[exercise["code"]]
            assert stored["content_version"] == 1, exercise["code"]
            assert stored["starter_code"] == exercise["starter_code"], exercise["code"]
            # 0015 会给「要求打印但不检查 print」的题追加一条 print 规则，
            # 因此库内规则要么与种子一致，要么正好多出那一条。
            stored_patterns = json.loads(stored["required_patterns"])
            seeded_patterns = exercise["required_patterns"]
            assert stored_patterns == seeded_patterns or stored_patterns == [
                *seeded_patterns,
                r"print\s*\(",
            ], exercise["code"]
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
