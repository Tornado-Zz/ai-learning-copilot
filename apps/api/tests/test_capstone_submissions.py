"""v0.1.3 后端验收：结业作品提交（capstone_submissions）与本人自评。

隔离策略沿用其它集成用例：外层事务整体回滚，全程不执行 DELETE / TRUNCATE。
端点级用例走单用户 API，断言只针对本用例自己创建的行（或带随机标记的行），
并与另写的一条 SQL 交叉核对；"别人的作品"由 fixture test_user 另建一行来构造。

诚实性口径同样是用例的一部分：reviewer 只能是 'self'，数据库 CHECK 让
"已评审但缺结论 / 缺评审者 / 评审者不是本人"的行根本写不进去。
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

BASE_URL = "/api/v1/capstone/submissions"
READINESS_URL = "/api/v1/capstone/readiness"
FROZEN_REQUIREMENT_KEYS = [
    "lessons_completed",
    "exercises_passed",
    "domains_at_l2",
    "plan_items_done",
]

SINGLE_USER_ID = text("SELECT id FROM users ORDER BY id LIMIT 1")
COUNT_OWN_ROWS = text(
    "SELECT count(*) FROM capstone_submissions WHERE user_id = :user_id"
)
SELECT_ROW = text(
    """
    SELECT id, user_id, title, summary, repo_url, run_instructions, self_checks,
           readiness_snapshot, status, verdict, reviewer, reviewer_note,
           submitted_at, reviewed_at
    FROM capstone_submissions WHERE id = :submission_id
    """
)
INSERT_FOREIGN_ROW = text(
    """
    INSERT INTO capstone_submissions (user_id, title, summary, run_instructions)
    VALUES (:user_id, :title, :summary, :run_instructions)
    RETURNING id
    """
)
INSERT_AGED_ROW = text(
    """
    INSERT INTO capstone_submissions (
        user_id, title, summary, run_instructions, created_at, updated_at
    )
    VALUES (
        :user_id, :title, :summary, :run_instructions,
        now() - CAST(:age_days AS integer) * INTERVAL '1 day',
        now() - CAST(:age_days AS integer) * INTERVAL '1 day'
    )
    RETURNING id
    """
)

# 14 张既有产品表：本版本的端点前后逐表行数必须相等。
ROW_COUNTS = text(
    """
    SELECT
        (SELECT count(*) FROM users) AS users,
        (SELECT count(*) FROM user_profiles) AS user_profiles,
        (SELECT count(*) FROM skills) AS skills,
        (SELECT count(*) FROM diagnostic_attempts) AS diagnostic_attempts,
        (SELECT count(*) FROM user_skill_levels) AS user_skill_levels,
        (SELECT count(*) FROM lessons) AS lessons,
        (SELECT count(*) FROM learning_progress) AS learning_progress,
        (SELECT count(*) FROM study_plan_items) AS study_plan_items,
        (SELECT count(*) FROM exercises) AS exercises,
        (SELECT count(*) FROM submissions) AS submissions,
        (SELECT count(*) FROM ai_interactions) AS ai_interactions,
        (SELECT count(*) FROM knowledge_sources) AS knowledge_sources,
        (SELECT count(*) FROM knowledge_chunks) AS knowledge_chunks,
        (SELECT count(*) FROM review_items) AS review_items
    """
)


def draft_body(**overrides: object) -> dict[str, object]:
    """A valid POST body; kept long enough to stay inside every length limit."""
    body: dict[str, object] = {
        "title": f"结业作品 {uuid.uuid4().hex[:8]}",
        "summary": "一个能跑起来的本地学习助手，涵盖课程、练习与错题本。",
        "run_instructions": "uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app",
    }
    body.update(overrides)
    return body


async def single_user_id(session: AsyncSession) -> int:
    return int((await session.execute(SINGLE_USER_ID)).scalar_one())


async def own_row_count(session: AsyncSession, user_id: int) -> int:
    return int((await session.execute(COUNT_OWN_ROWS, {"user_id": user_id})).scalar_one())


async def created(session: AsyncSession, submission_id: int) -> dict[str, object]:
    row = (
        (await session.execute(SELECT_ROW, {"submission_id": submission_id}))
        .mappings()
        .one()
    )
    return dict(row)


async def new_draft(api, **overrides: object) -> dict[str, object]:
    response = await api.post(BASE_URL, json=draft_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def table_counts(session: AsyncSession) -> dict[str, int]:
    row = (await session.execute(ROW_COUNTS)).mappings().one()
    return {name: int(row[name]) for name in row}


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------
async def test_01_create_draft_returns_the_complete_object(
    api, db_session: AsyncSession
) -> None:
    body = draft_body(self_checks=["README 写清了启动步骤", "示例数据能重跑"])
    response = await api.post(BASE_URL, json=body)

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["title"] == body["title"]
    assert payload["summary"] == body["summary"]
    assert payload["run_instructions"] == body["run_instructions"]
    assert payload["repo_url"] is None
    assert payload["self_checks"] == body["self_checks"]
    # S1：创建只产生 draft，评审相关的列一个都不许有值。
    assert payload["status"] == "draft"
    assert payload["verdict"] is None
    assert payload["reviewer"] is None
    assert payload["reviewer_note"] is None
    assert payload["submitted_at"] is None
    assert payload["reviewed_at"] is None
    assert payload["readiness_snapshot"] is None
    assert payload["user_id"] == await single_user_id(db_session)

    row = await created(db_session, int(payload["id"]))
    assert row["status"] == "draft"
    assert row["title"] == body["title"]


async def test_02_over_length_and_bad_url_fields_are_422(
    api, db_session: AsyncSession
) -> None:
    user_id = await single_user_id(db_session)
    before = await own_row_count(db_session, user_id)
    cases = [
        (draft_body(title="x" * 121), "title"),
        (draft_body(summary="x" * 4001), "summary"),
        (draft_body(run_instructions="x" * 4001), "run_instructions"),
        (draft_body(repo_url="ftp://example.com/repo"), "repo_url"),
        (draft_body(repo_url="https://example.com/" + "x" * 300), "repo_url"),
        (draft_body(title=""), "title"),
    ]
    for body, field in cases:
        response = await api.post(BASE_URL, json=body)
        assert response.status_code == 422, (field, response.text)
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["details"]["field"] == field
    # 422 全程零写入。
    assert await own_row_count(db_session, user_id) == before


# ---------------------------------------------------------------------------
# 修改（只有 draft 可改）
# ---------------------------------------------------------------------------
async def test_03_patch_draft_changes_only_the_fields_sent(api, db_session: AsyncSession) -> None:
    draft = await new_draft(api)
    response = await api.patch(
        f"{BASE_URL}/{draft['id']}",
        json={"title": "结业作品（改名）", "self_checks": ["只有这一条"]},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "结业作品（改名）"
    assert payload["self_checks"] == ["只有这一条"]
    # 没出现在 PATCH 里的列保持原值。
    assert payload["summary"] == draft["summary"]
    assert payload["run_instructions"] == draft["run_instructions"]
    assert payload["status"] == "draft"
    row = await created(db_session, int(draft["id"]))
    assert row["title"] == "结业作品（改名）"


async def test_04_patch_outside_draft_is_409_and_writes_nothing(
    api, db_session: AsyncSession
) -> None:
    draft = await new_draft(api)
    submitted = await api.post(f"{BASE_URL}/{draft['id']}/submit")
    assert submitted.status_code == 200, submitted.text

    blocked = await api.patch(f"{BASE_URL}/{draft['id']}", json={"title": "不该生效"})
    assert blocked.status_code == 409, blocked.text
    error = blocked.json()["error"]
    assert error["code"] == "CAPSTONE_INVALID_STATE"
    assert error["details"]["current_status"] == "submitted"
    row = await created(db_session, int(draft["id"]))
    assert row["title"] == draft["title"]

    reviewed = await api.post(
        f"{BASE_URL}/{draft['id']}/review",
        json={"verdict": "pass", "self_review_confirmed": True},
    )
    assert reviewed.status_code == 200, reviewed.text
    again = await api.patch(f"{BASE_URL}/{draft['id']}", json={"summary": "更不该生效"})
    assert again.status_code == 409
    assert again.json()["error"]["details"]["current_status"] == "reviewed"
    assert (await created(db_session, int(draft["id"])))["summary"] == draft["summary"]


# ---------------------------------------------------------------------------
# 提交（draft -> submitted，同事务写 readiness_snapshot）
# ---------------------------------------------------------------------------
async def test_05_submit_records_the_readiness_snapshot(api, db_session: AsyncSession) -> None:
    readiness = await api.get(READINESS_URL)
    assert readiness.status_code == 200, readiness.text
    expected = readiness.json()

    draft = await new_draft(api)
    response = await api.post(f"{BASE_URL}/{draft['id']}/submit")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "submitted"
    assert payload["submitted_at"] is not None
    snapshot = payload["readiness_snapshot"]
    assert snapshot["ready"] is expected["ready"]
    assert [item["key"] for item in snapshot["requirements"]] == FROZEN_REQUIREMENT_KEYS
    assert snapshot["requirements"] == expected["requirements"]
    assert payload["verdict"] is None and payload["reviewer"] is None

    row = await created(db_session, int(draft["id"]))
    assert row["status"] == "submitted"
    assert row["submitted_at"] is not None
    assert row["readiness_snapshot"] is not None
    stored = row["readiness_snapshot"]
    # jsonb 落库的四条要求与响应逐条一致（不因序列化而丢字段）。
    decoded = json.loads(stored) if isinstance(stored, str) else stored
    assert decoded == snapshot


async def test_06_submit_twice_is_409(api, db_session: AsyncSession) -> None:
    draft = await new_draft(api)
    first = await api.post(f"{BASE_URL}/{draft['id']}/submit")
    assert first.status_code == 200, first.text
    submitted_at = first.json()["submitted_at"]

    second = await api.post(f"{BASE_URL}/{draft['id']}/submit")
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "CAPSTONE_INVALID_STATE"
    assert second.json()["error"]["details"]["current_status"] == "submitted"
    # 第一次的快照与时间戳没有被第二次调用改写。
    assert (await created(db_session, int(draft["id"])))["submitted_at"].isoformat().startswith(
        submitted_at[:19]
    )


# ---------------------------------------------------------------------------
# 自评（submitted -> reviewed）
# ---------------------------------------------------------------------------
async def test_07_review_without_confirmation_is_400(api, db_session: AsyncSession) -> None:
    draft = await new_draft(api)
    assert (await api.post(f"{BASE_URL}/{draft['id']}/submit")).status_code == 200

    for body in (
        {"verdict": "pass"},
        {"verdict": "pass", "self_review_confirmed": False},
        {"verdict": "needs_work", "note": "还差 README"},
    ):
        response = await api.post(f"{BASE_URL}/{draft['id']}/review", json=body)
        assert response.status_code == 400, (body, response.text)
        assert response.json()["error"]["code"] == "SELF_REVIEW_NOT_CONFIRMED"
    # 未确认的请求不进入状态机：行仍是 submitted，评审列全空。
    row = await created(db_session, int(draft["id"]))
    assert row["status"] == "submitted"
    assert row["verdict"] is None and row["reviewer"] is None and row["reviewed_at"] is None


async def test_08_review_writes_self_verdict_and_the_db_check_holds(
    api, db_session: AsyncSession
) -> None:
    draft = await new_draft(api)
    assert (await api.post(f"{BASE_URL}/{draft['id']}/submit")).status_code == 200

    response = await api.post(
        f"{BASE_URL}/{draft['id']}/review",
        json={"verdict": "pass", "note": "我自己跑通了启动步骤", "self_review_confirmed": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "reviewed"
    assert payload["verdict"] == "pass"
    # 诚实性红线：评审者只会是本人。
    assert payload["reviewer"] == "self"
    assert payload["reviewer_note"] == "我自己跑通了启动步骤"
    assert payload["reviewed_at"] is not None

    row = await created(db_session, int(draft["id"]))
    assert (row["status"], row["verdict"], row["reviewer"]) == ("reviewed", "pass", "self")
    assert row["reviewed_at"] is not None

    # ck_capstone_submissions_reviewed_complete / _reviewer：数据库自己拒绝
    # "已评审但没有结论"、"评审者不是本人"、"已评审但没有时间戳" 这三种行。
    # （按 SQL 的三值逻辑，reviewer = NULL 会让 OR 的右支整体为 NULL 而不为 FALSE，
    # 因此那种行由服务层保证——reviewer 在 UPDATE 里写死 'self'——而不是由这个
    # 冻结的 CHECK 拦下；这里只断言契约真正拦得住的三条。）
    for statement in (
        "UPDATE capstone_submissions SET verdict = NULL WHERE id = :submission_id",
        "UPDATE capstone_submissions SET reviewer = 'peer' WHERE id = :submission_id",
        "UPDATE capstone_submissions SET reviewed_at = NULL WHERE id = :submission_id",
    ):
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(text(statement), {"submission_id": draft["id"]})
    # 违规写入都被退回，行仍是那一行合法的自评记录。
    after = await created(db_session, int(draft["id"]))
    assert (after["status"], after["verdict"], after["reviewer"]) == ("reviewed", "pass", "self")


async def test_09_review_of_a_draft_is_409(api, db_session: AsyncSession) -> None:
    draft = await new_draft(api)
    response = await api.post(
        f"{BASE_URL}/{draft['id']}/review",
        json={"verdict": "pass", "self_review_confirmed": True},
    )
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "CAPSTONE_INVALID_STATE"
    assert error["details"]["current_status"] == "draft"
    assert (await created(db_session, int(draft["id"])))["status"] == "draft"


async def test_10_review_with_an_invalid_verdict_is_422(api) -> None:
    draft = await new_draft(api)
    assert (await api.post(f"{BASE_URL}/{draft['id']}/submit")).status_code == 200
    response = await api.post(
        f"{BASE_URL}/{draft['id']}/review",
        json={"verdict": "ok", "self_review_confirmed": True},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# 别人的行与列表口径
# ---------------------------------------------------------------------------
async def test_11_someone_elses_submission_is_404(
    api, db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    foreign_id = int(
        (
            await db_session.execute(
                INSERT_FOREIGN_ROW,
                {
                    "user_id": int(test_user["id"]),
                    "title": "别人的作品",
                    "summary": "不属于单用户视角",
                    "run_instructions": "python main.py",
                },
            )
        ).scalar_one()
    )
    single_user = await single_user_id(db_session)
    assert int(test_user["id"]) != single_user

    checks = [
        await api.get(f"{BASE_URL}/{foreign_id}"),
        await api.patch(f"{BASE_URL}/{foreign_id}", json={"title": "改名"}),
        await api.post(f"{BASE_URL}/{foreign_id}/submit"),
        await api.post(
            f"{BASE_URL}/{foreign_id}/review",
            json={"verdict": "pass", "self_review_confirmed": True},
        ),
    ]
    for response in checks:
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"
    # 别人的行一个字节都没动。
    row = await created(db_session, foreign_id)
    assert row["status"] == "draft" and row["title"] == "别人的作品"

    missing = await api.get(f"{BASE_URL}/999999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


async def test_12_list_orders_created_at_desc_then_id_desc(
    api, db_session: AsyncSession
) -> None:
    user_id = await single_user_id(db_session)
    # 三条显式时间的行：API 新建的行 now() 相同，只有这三条能证明时间优先于 id。
    aged_ids = []
    for age in (3, 2, 1):
        aged_ids.append(
            int(
                (
                    await db_session.execute(
                        INSERT_AGED_ROW,
                        {
                            "user_id": user_id,
                            "title": f"旧作品 {age} 天前",
                            "summary": "历史作品",
                            "run_instructions": "python main.py",
                            "age_days": age,
                        },
                    )
                ).scalar_one()
            )
        )
    newest = await new_draft(api)
    newer = await new_draft(api)

    response = await api.get(BASE_URL, params={"limit": 100})
    assert response.status_code == 200, response.text
    payload = response.json()
    ids = [int(item["id"]) for item in payload["items"]]
    assert payload["total"] >= 5
    # 只对本用例自己创建的行断言相对顺序：库里可能已有别处留下的作品（人工验收、
    # 其它用例），用「第 N 位」断言会随外部数据漂移。
    mine = {int(newest["id"]), int(newer["id"]), *aged_ids}
    ordered = [item for item in ids if item in mine]
    # 时间新的在前，时间相同的按 id 倒序。
    assert ordered == [
        max(int(newer["id"]), int(newest["id"])),
        min(int(newer["id"]), int(newest["id"])),
        aged_ids[2],
        aged_ids[1],
        aged_ids[0],
    ]
    created_at = [item["created_at"] for item in payload["items"]]
    assert created_at == sorted(created_at, reverse=True)

    limited = await api.get(BASE_URL, params={"limit": 2})
    assert limited.status_code == 200
    assert len(limited.json()["items"]) == 2
    # total 与 limit 无关。
    assert limited.json()["total"] == payload["total"]


# ---------------------------------------------------------------------------
# 端点的作用域：只写 capstone_submissions
# ---------------------------------------------------------------------------
async def test_13_the_whole_flow_leaves_every_other_table_unchanged(
    api, db_session: AsyncSession
) -> None:
    before = await table_counts(db_session)

    draft = await new_draft(api)
    assert (await api.patch(f"{BASE_URL}/{draft['id']}", json={"title": "改过的标题"})).status_code == 200
    assert (await api.post(f"{BASE_URL}/{draft['id']}/submit")).status_code == 200
    assert (
        await api.post(
            f"{BASE_URL}/{draft['id']}/review",
            json={"verdict": "needs_work", "note": "再补一个示例", "self_review_confirmed": True},
        )
    ).status_code == 200
    assert (await api.get(BASE_URL)).status_code == 200
    assert (await api.get(f"{BASE_URL}/{draft['id']}")).status_code == 200

    after = await table_counts(db_session)
    assert after == before, {name: (before[name], after[name]) for name in before}
