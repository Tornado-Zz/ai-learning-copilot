"""练习详情携带复习上下文：GET /exercises/{id} 的 review 块（v0.1.15）。

错题本能跳到 /practice/{id}，但详情此前只有 passed_count / last_submission 这类
提交状态，页面没法说"这道题是欠着的复习"，也答不出下次复习是哪天。本文件钉住四件事：

* 有 review_items 行 -> review 非空，且 streak / interval_days / next_review_on
  与库内那一行逐个相等；
* 没有行 -> review 是 null，不是一个空对象；
* 别人的错题本行永远进不来（按 user_id 限定，不是"恰好没有"）；
* due 只与 users.timezone 的今天比较：今天 -> true，明天 -> false，done -> false。

隔离口径沿用既有集成用例：所有写入都在 conftest.db_session 的外层事务里，测试结束
整体回滚；行一律 upsert，不执行 DELETE / TRUNCATE / DROP。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import exercises as exercises_service
from app.services import review as review_service
from app.services import users as users_service
from tests.conftest import create_isolated_learner

pytestmark = pytest.mark.integration

ANSWER_KEYS = ("required_patterns", "forbidden_patterns", "expected_output")
# 前端并行按这七个键实现，顺序无关，多一个少一个都是契约破坏。
REVIEW_KEYS = {
    "status",
    "due",
    "streak",
    "interval_days",
    "next_review_on",
    "last_result",
    "last_reviewed_at",
}

# 挑"这个用户还没有复习行"的已发布练习：集成库里种子用户可能已经有真实错题本行，
# 断言不能依赖真实使用留下的状态，也不允许为了测试去删它。
SELECT_PUBLISHED_WITHOUT_REVIEW = text(
    """
    SELECT e.id
    FROM exercises e
    WHERE e.status = 'published' AND e.deleted_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM review_items ri
          WHERE ri.user_id = :user_id AND ri.exercise_id = e.id
      )
    ORDER BY e.id
    LIMIT CAST(:count AS integer)
    """
)

INSERT_REVIEW_ROW = text(
    """
    INSERT INTO review_items (
        user_id, exercise_id, source_submission_id, streak, interval_days,
        next_review_on, last_result, last_reviewed_at, status
    )
    VALUES (
        :user_id, :exercise_id, NULL, :streak, :interval_days,
        :next_review_on, :last_result, :last_reviewed_at, :status
    )
    ON CONFLICT (user_id, exercise_id) DO UPDATE SET
        streak = EXCLUDED.streak,
        interval_days = EXCLUDED.interval_days,
        next_review_on = EXCLUDED.next_review_on,
        last_result = EXCLUDED.last_result,
        last_reviewed_at = EXCLUDED.last_reviewed_at,
        status = EXCLUDED.status,
        updated_at = now()
    RETURNING id, status, streak, interval_days, next_review_on, last_result
    """
)

SELECT_REVIEW_ROW = text(
    """
    SELECT id, status, streak, interval_days, next_review_on, last_result
    FROM review_items
    WHERE user_id = :user_id AND exercise_id = :exercise_id
    """
)


async def _me(session: AsyncSession) -> int:
    """单用户路由解析出来的那个 id（SELECT_SINGLE_USER），与服务层同一口径。"""
    return int((await users_service.get_single_user(session))["id"])


async def _exercises_without_review(
    session: AsyncSession, user_id: int, count: int
) -> list[int]:
    ids = [
        int(exercise_id)
        for exercise_id in (
            await session.execute(
                SELECT_PUBLISHED_WITHOUT_REVIEW, {"user_id": user_id, "count": count}
            )
        )
        .scalars()
        .all()
    ]
    assert len(ids) == count, "已发布练习不足，或该用户的错题本行覆盖了太多题"
    return ids


async def _seed_review(
    session: AsyncSession,
    user_id: int,
    exercise_id: int,
    *,
    next_review_on,
    streak: int = 0,
    interval_days: int = 1,
    status: str = "pending",
    last_result: str | None = "failed",
    last_reviewed_at: datetime | None = None,
):
    return (
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
                    "last_reviewed_at": last_reviewed_at,
                    "status": status,
                },
            )
        )
        .mappings()
        .one()
    )


async def _detail(api: Any, exercise_id: int) -> dict[str, Any]:
    response = await api.get(f"/api/v1/exercises/{exercise_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_detail_carries_the_stored_review_row(api: Any, db_session: AsyncSession) -> None:
    """有复习行时，review 的每个字段都等于库内那一行（不重算、不猜）。"""
    user_id = await _me(db_session)
    exercise_id = (await _exercises_without_review(db_session, user_id, 1))[0]
    today = await review_service.local_today(db_session, user_id)
    reviewed_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    row = await _seed_review(
        db_session,
        user_id,
        exercise_id,
        next_review_on=today + timedelta(days=1),
        streak=2,
        interval_days=7,
        status="pending",
        last_result="passed",
        last_reviewed_at=reviewed_at,
    )

    body = await _detail(api, exercise_id)

    review = body["review"]
    assert review is not None
    assert set(review) == REVIEW_KEYS
    assert review["status"] == row["status"] == "pending"
    assert review["streak"] == int(row["streak"]) == 2
    assert review["interval_days"] == int(row["interval_days"]) == 7
    assert review["next_review_on"] == row["next_review_on"].isoformat()
    assert review["last_result"] == row["last_result"] == "passed"
    # timestamptz 按既有口径序列化成带 Z 的 UTC 串，null 原样为 null
    assert review["last_reviewed_at"] == "2026-01-02T03:04:05Z"
    assert review["due"] is False
    # 答案键仍然不在响应里：加字段没有顺手把题库答案带出来
    for key in ANSWER_KEYS:
        assert key not in body


async def test_detail_review_is_null_without_a_row(api: Any, db_session: AsyncSession) -> None:
    """没有复习行就是一个 null，不凭空造一个空对象。"""
    user_id = await _me(db_session)
    exercise_id = (await _exercises_without_review(db_session, user_id, 1))[0]

    body = await _detail(api, exercise_id)

    assert "review" in body
    assert body["review"] is None


async def test_another_users_review_row_never_reaches_my_detail(
    api: Any, db_session: AsyncSession
) -> None:
    """隔离：同一道题上别人的复习行，在我这里必须还是 null。"""
    my_id = await _me(db_session)
    exercise_id = (await _exercises_without_review(db_session, my_id, 1))[0]
    other_id = await create_isolated_learner(
        db_session, study_days=[1, 2, 3, 4, 5], daily_minutes=60, level=0
    )
    assert other_id != my_id
    other_today = await review_service.local_today(db_session, other_id)
    await _seed_review(
        db_session,
        other_id,
        exercise_id,
        next_review_on=other_today,
        streak=1,
        interval_days=3,
        status="pending",
        last_result="passed",
    )

    body = await _detail(api, exercise_id)
    assert body["review"] is None
    assert (
        (
            await db_session.execute(
                SELECT_REVIEW_ROW, {"user_id": my_id, "exercise_id": exercise_id}
            )
        )
        .mappings()
        .first()
        is None
    )

    # 同一个查询换成对方 user_id 就必须有内容：null 是因为按用户过滤，不是查不到行。
    theirs = await exercises_service.get_exercise(db_session, other_id, exercise_id)
    assert theirs["review"] is not None
    assert theirs["review"]["streak"] == 1
    assert theirs["review"]["interval_days"] == 3
    assert theirs["review"]["due"] is True


async def test_due_uses_the_users_local_today(api: Any, db_session: AsyncSession) -> None:
    """due 只与 users.timezone 的今天比较：今天 true、明天 false、done 不是到期。"""
    user_id = await _me(db_session)
    today = await review_service.local_today(db_session, user_id)
    due_exercise, later_exercise, done_exercise = await _exercises_without_review(
        db_session, user_id, 3
    )
    await _seed_review(db_session, user_id, due_exercise, next_review_on=today)
    await _seed_review(
        db_session, user_id, later_exercise, next_review_on=today + timedelta(days=1)
    )
    await _seed_review(
        db_session,
        user_id,
        done_exercise,
        next_review_on=today,
        streak=3,
        interval_days=14,
        status="done",
        last_result="passed",
    )

    due_body = await _detail(api, due_exercise)
    later_body = await _detail(api, later_exercise)
    done_body = await _detail(api, done_exercise)

    assert due_body["review"]["next_review_on"] == today.isoformat()
    assert due_body["review"]["due"] is True
    assert later_body["review"]["next_review_on"] == (today + timedelta(days=1)).isoformat()
    assert later_body["review"]["due"] is False
    # done 也是一种状态，不是删除：块还在，但不算今天到期。
    assert done_body["review"] is not None
    assert done_body["review"]["status"] == "done"
    assert done_body["review"]["due"] is False
