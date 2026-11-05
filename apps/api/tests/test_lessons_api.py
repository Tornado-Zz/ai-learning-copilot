"""Sprint 2 验收 ③④⑤：五节课种子内容、读取不写进度、写入路径与自评上限。

隔离策略：只读断言用迁移种子（lessons 是版本化内容，产品不会改写）；写入路径用本测试
在事务内自建的一节课，因此不依赖真实用户已有的进度行；所有断言都按 user_id 限定，
且外层事务回滚，全程不执行 DELETE。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

# 播种顺序：0003 的 5 节 Python 基础课，0011 的 a3 / a4，0012 的 a5 / a6，
# 0013 的 a2 编程实践两节（order_index 接着 9 排到 11），0017 的 a3 / a4 两节核心课
# 接在 12 / 13，0018 的 a5 / a6 两节第二课接在 14 / 15，0019 的 a6「跟着做」实战课接在 16。
EXPECTED_CODES = [
    "route_a.py.variables",
    "route_a.py.control_flow",
    "route_a.py.list_dict",
    "route_a.py.functions",
    "route_a.py.debugging",
    "route_a.api.json",
    "route_a.llm.messages",
    "route_a.rag.retrieval",
    "route_a.agent.tool",
    "route_a.practice.decompose",
    "route_a.practice.debug",
    "route_a.api.errors",
    "route_a.llm.prompt",
    "route_a.rag.grounding",
    "route_a.project.scope",
    "route_a.project.build",
]

# 列表接口按 (stage, order_index) 排序，不是按 order_index：a2 的两节课 order_index
# 是 10 / 11、0017 的两节 a3 / a4 课是 12 / 13、0018 的两节 a5 / a6 课是 14 / 15、
# 0019 的 a6 实战课是 16（迁移只发 INSERT，不改写既有行，只能接在末尾），stage 却是
# 2 / 3 / 4 / 5 / 6，所以在产品里它们各自落在同域既有课之后。两种顺序都逐条钉死。
EXPECTED_CODES_BY_API_ORDER = [
    "route_a.py.variables",
    "route_a.py.control_flow",
    "route_a.py.list_dict",
    "route_a.py.functions",
    "route_a.py.debugging",
    "route_a.practice.decompose",
    "route_a.practice.debug",
    "route_a.api.json",
    "route_a.api.errors",
    "route_a.llm.messages",
    "route_a.llm.prompt",
    "route_a.rag.retrieval",
    "route_a.rag.grounding",
    "route_a.agent.tool",
    "route_a.project.scope",
    "route_a.project.build",
]

SELECT_PUBLISHED_LESSON_IDS = text(
    "SELECT id FROM lessons WHERE status = 'published' AND deleted_at IS NULL "
    "ORDER BY stage, order_index, id"
)
COUNT_PROGRESS = text("SELECT count(*) FROM learning_progress WHERE user_id = :user_id")
COUNT_LEVELS = text("SELECT count(*) FROM user_skill_levels WHERE user_id = :user_id")

INSERT_TEST_LESSON = text(
    """
    INSERT INTO lessons (code, skill_id, stage, title, summary, content, estimated_minutes,
                         order_index, status)
    VALUES (:code, (SELECT id FROM skills WHERE code = 'route_a.a1'), 1, :title, :summary,
            :content, 20, 99, 'published')
    RETURNING id
    """
).bindparams(bindparam("content", type_=JSONB))

TEST_CONTENT = {
    "schema_version": 1,
    "goal": "验证写入路径用的一节课",
    "explanation": ["只用于测试，迁移种子之外不会出现"],
    "example": {"title": "示例", "code": "print(1)", "notes": []},
    "common_mistakes": [{"mistake": "无", "why": "无", "fix": "无"}],
    "self_check": [
        {"question": "问题一？", "answer": "答案一"},
        {"question": "问题二？", "answer": "答案二"},
    ],
}


async def _single_user_id(api) -> int:
    return int((await api.get("/api/v1/users/me")).json()["user"]["id"])


async def _make_lesson(session: AsyncSession) -> int:
    """本测试专属课程：保证写入路径不依赖真实产品的进度状态。"""
    suffix = uuid.uuid4().hex[:8]
    return int(
        (
            await session.execute(
                INSERT_TEST_LESSON,
                {
                    "code": f"pytest.lesson.{suffix}",
                    "title": f"测试课程 {suffix}",
                    "summary": "仅测试用",
                    "content": TEST_CONTENT,
                },
            )
        ).scalar_one()
    )


async def test_03_five_lessons_are_seeded_with_complete_content(
    db_session: AsyncSession, api
) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT code, title, stage, order_index, estimated_minutes, content_version, "
                "status, content FROM lessons WHERE status = 'published' ORDER BY order_index"
            )
        )
    ).mappings().all()
    # AC-S2-05 冻结的是「0003 播种的 3–5 节」；0011/0012/0013 之后产品是 11 节，
    # 因此只保留下限，课程清单由 EXPECTED_CODES 逐条钉死。
    assert 3 <= len(rows)
    assert [row["code"] for row in rows] == EXPECTED_CODES

    for row in rows:
        assert row["title"].strip()
        assert 1 <= row["stage"] <= 6
        assert 1 <= row["estimated_minutes"] <= 240
        assert row["content_version"] >= 1
        content = row["content"]
        assert content["schema_version"] == 1
        assert content["goal"].strip(), row["code"]
        assert content["explanation"] and all(part.strip() for part in content["explanation"])
        assert content["example"]["code"].strip(), row["code"]
        assert content["common_mistakes"], row["code"]
        assert len(content["self_check"]) >= 2, row["code"]
        for item in content["self_check"]:
            assert item["question"].strip() and item["answer"].strip(), row["code"]

    listed = await api.get("/api/v1/lessons")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == len(rows)
    assert [item["code"] for item in body["items"]] == EXPECTED_CODES_BY_API_ORDER
    for item in body["items"]:
        assert {"stage", "order_index", "estimated_minutes", "content_version"} <= set(item)
        assert "content" not in item, "列表不下发正文"
        assert "progress" in item


async def test_04_reading_a_lesson_writes_nothing_and_completion_is_explicit(
    db_session: AsyncSession, api
) -> None:
    user_id = await _single_user_id(api)
    lesson_id = await _make_lesson(db_session)
    before = int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    )

    # GET 列表 / 详情各两次：一次都不写库
    for _ in range(2):
        assert (await api.get("/api/v1/lessons")).status_code == 200
        detail = await api.get(f"/api/v1/lessons/{lesson_id}")
        assert detail.status_code == 200, detail.text
    assert detail.json()["progress"] is None, "打开课程不得产生进度行"
    assert int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    ) == before

    # 第一节课的详情也要含正文五块
    published = (
        await db_session.execute(SELECT_PUBLISHED_LESSON_IDS)
    ).scalars().all()
    seeded_id = int(published[0])
    seeded = (await api.get(f"/api/v1/lessons/{seeded_id}")).json()
    assert seeded["content"]["goal"].strip()
    assert len(seeded["content"]["self_check"]) >= 2

    # 显式标记 in_progress：写入一行，且不是 completed
    started = await api.put(
        f"/api/v1/lessons/{lesson_id}/progress",
        json={"status": "in_progress", "time_spent_seconds": 60},
    )
    assert started.status_code == 200, started.text
    progress = started.json()
    assert progress["status"] == "in_progress"
    assert progress["completed_at"] is None
    assert progress["started_at"] is not None
    assert progress["time_spent_seconds"] == 60
    assert progress["progress_pct"] >= 1
    assert int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    ) == before + 1

    # 停留时长按累计值上报，只增不减
    assert (
        await api.put(
            f"/api/v1/lessons/{lesson_id}/progress",
            json={"status": "in_progress", "time_spent_seconds": 30},
        )
    ).json()["time_spent_seconds"] == 60
    assert (
        await api.put(
            f"/api/v1/lessons/{lesson_id}/progress",
            json={"status": "in_progress", "time_spent_seconds": 120},
        )
    ).json()["time_spent_seconds"] == 120

    # progress_pct 只增不减，上限 100
    assert (
        await api.put(
            f"/api/v1/lessons/{lesson_id}/progress",
            json={"status": "in_progress", "progress_pct": 40},
        )
    ).json()["progress_pct"] == 40
    assert (
        await api.put(
            f"/api/v1/lessons/{lesson_id}/progress",
            json={"status": "in_progress", "progress_pct": 20},
        )
    ).json()["progress_pct"] == 40

    # 明确标记 completed：完成率 100，完成时间落在行上
    completed = await api.put(
        f"/api/v1/lessons/{lesson_id}/progress", json={"status": "completed"}
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "completed"
    assert body["progress_pct"] == 100
    assert body["completed_at"] is not None
    # 重复提交 completed 幂等：完成时间不被改写
    again = await api.put(
        f"/api/v1/lessons/{lesson_id}/progress", json={"status": "completed"}
    )
    assert again.json()["completed_at"] == body["completed_at"]
    assert int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    ) == before + 1

    # 未知课程 404
    assert (await api.get("/api/v1/lessons/999999999")).status_code == 404
    assert (
        await api.put(
            "/api/v1/lessons/999999999/progress", json={"status": "in_progress"}
        )
    ).status_code == 404


async def test_05_self_assessment_is_capped_at_l2_and_never_writes_skill_levels(
    db_session: AsyncSession, api
) -> None:
    user_id = await _single_user_id(api)
    lesson_id = await _make_lesson(db_session)
    levels_before = int(
        (await db_session.execute(COUNT_LEVELS, {"user_id": user_id})).scalar_one()
    )
    progress_before = int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    )

    for value in (3, 4):
        rejected = await api.put(
            f"/api/v1/lessons/{lesson_id}/progress",
            json={"status": "in_progress", "self_assessment": value},
        )
        assert rejected.status_code == 422, (value, rejected.text)
        error = rejected.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["details"]["field"] == "self_assessment"
        assert rejected.json()["request_id"]

    # 被拒绝的请求一行都不写
    assert int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    ) == progress_before
    assert int(
        (await db_session.execute(COUNT_LEVELS, {"user_id": user_id})).scalar_one()
    ) == levels_before

    accepted = await api.put(
        f"/api/v1/lessons/{lesson_id}/progress",
        json={"status": "in_progress", "self_assessment": 2},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["self_assessment"] == 2
    # 自评只落 learning_progress：user_skill_levels 一行都不增加
    assert int(
        (await db_session.execute(COUNT_LEVELS, {"user_id": user_id})).scalar_one()
    ) == levels_before
    stored = (
        await db_session.execute(
            text(
                "SELECT status, self_assessment FROM learning_progress "
                "WHERE user_id = :user_id AND lesson_id = :lesson_id"
            ),
            {"user_id": user_id, "lesson_id": lesson_id},
        )
    ).mappings().one()
    assert (stored["status"], stored["self_assessment"]) == ("in_progress", 2)

    # 数据库层兜底：>L2 直接写也会被 CHECK 拒绝
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE learning_progress SET self_assessment = 3 "
                    "WHERE user_id = :user_id AND lesson_id = :lesson_id"
                ),
                {"user_id": user_id, "lesson_id": lesson_id},
            )
    assert "ck_learning_progress_self_assessment" in str(error.value)
