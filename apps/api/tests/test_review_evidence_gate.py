"""错题本推进的证据门禁：自检申报的通过不算重新验证。

错题本的意义是把答错的题重新考一次。自检只是学习者声称自己本地跑通了，系统从未验证。
若自检也算通过，勾三次「我已跑通」就能清空错题本。
v0.1.21 起：自检通过不推进 streak，答错仍照常重置（申报失败没有作弊动机）。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import review as review_service

pytestmark = pytest.mark.integration

SEED_REVIEW = text(
    """
    INSERT INTO review_items (user_id, exercise_id, status, streak, interval_days, next_review_on)
    VALUES (:user_id, :exercise_id, 'pending', 1, 3, :next_review_on)
    ON CONFLICT (user_id, exercise_id) DO NOTHING
    """
)
SELECT_REVIEW = text(
    """
    SELECT id, streak, interval_days, status, last_result, next_review_on
    FROM review_items
    WHERE user_id = :user_id AND exercise_id = :exercise_id
    """
)


async def _seed(db_session: AsyncSession, user_id: int, exercise_id: int) -> None:
    await db_session.execute(
        SEED_REVIEW,
        {
            'user_id': user_id,
            'exercise_id': exercise_id,
            'next_review_on': date.today() + timedelta(days=3),
        },
    )


async def _row(db_session: AsyncSession, user_id: int, exercise_id: int):
    return (
        (await db_session.execute(SELECT_REVIEW, {'user_id': user_id, 'exercise_id': exercise_id}))
        .mappings()
        .first()
    )


async def _advance(
    db_session: AsyncSession,
    user_id: int,
    exercise_id: int,
    *,
    is_passed: bool,
    method: str,
):
    return await review_service.schedule_after_submission(
        db_session,
        user_id=user_id,
        exercise_id=exercise_id,
        # 来源提交列可空（外键 ON DELETE SET NULL），本组用例只关心推进与否，
        # 传 0 会触发外键约束，因此显式传 None。
        submission_id=None,  # type: ignore[arg-type]
        is_passed=is_passed,
        verification_method=method,
    )


async def test_a_self_reported_pass_does_not_advance_the_streak(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    """核心断言：自检通过后 streak / interval / next_review_on 一个都不动。"""
    user_id = int(test_user['id'])
    exercise_id = int(
        (await db_session.execute(text('SELECT id FROM exercises ORDER BY id LIMIT 1'))).scalar_one()
    )
    await _seed(db_session, user_id, exercise_id)
    before = await _row(db_session, user_id, exercise_id)

    result = await _advance(db_session, user_id, exercise_id, is_passed=True, method='self_report')

    after = await _row(db_session, user_id, exercise_id)
    assert result is None
    assert int(after['streak']) == int(before['streak'])
    assert int(after['interval_days']) == int(before['interval_days'])
    assert after['next_review_on'] == before['next_review_on']
    assert after['status'] == 'pending'


async def test_a_static_rule_pass_still_advances(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    """反向保证：真正通过静态规则的提交照常推进。"""
    user_id = int(test_user['id'])
    exercise_id = int(
        (await db_session.execute(text('SELECT id FROM exercises ORDER BY id LIMIT 1'))).scalar_one()
    )
    await _seed(db_session, user_id, exercise_id)

    result = await _advance(db_session, user_id, exercise_id, is_passed=True, method='static_rule')

    after = await _row(db_session, user_id, exercise_id)
    assert result is not None
    assert int(after['streak']) == 2
    assert int(after['interval_days']) == 7


async def test_a_self_reported_failure_still_resets(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    """申报失败照常重置：谎报失败对自己没有好处，拦它只会误伤。"""
    user_id = int(test_user['id'])
    exercise_id = int(
        (await db_session.execute(text('SELECT id FROM exercises ORDER BY id LIMIT 1'))).scalar_one()
    )
    await _seed(db_session, user_id, exercise_id)

    await _advance(db_session, user_id, exercise_id, is_passed=False, method='self_report')

    after = await _row(db_session, user_id, exercise_id)
    assert int(after['streak']) == 0
    assert after['last_result'] == 'failed'