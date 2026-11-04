"""计划生成的用户隔离：generate_plan(user_id) 让用例自带数据，不再依赖种子用户的真实进度。

这是 Round 10 偿还的技术债：此前 generate_plan() 内部解析「唯一那个用户」，于是所有计划
用例都跑在同一个真实用户身上，用户一旦真实学习（完成课程、产生复习项），断言就漂移。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import study_plan as study_plan_service

pytestmark = pytest.mark.integration


async def _fresh_user(session: AsyncSession, *, daily_minutes: int = 60) -> int:
    """自建一个用户：确认时区 + 档案 + 六域等级，全部在调用方事务里，结束回滚。"""
    suffix = uuid.uuid4().hex[:8]
    user_id = int(
        (
            await session.execute(
                text("INSERT INTO users (display_name, timezone, timezone_source) "
                     "VALUES (:name, 'Asia/Shanghai', 'user_confirmed') RETURNING id"),
                {"name": f"isolation-{suffix}"},
            )
        ).scalar_one()
    )
    await session.execute(
        text("INSERT INTO user_profiles (user_id, study_days, daily_minutes) "
             "VALUES (:user_id, ARRAY[1,2,3]::smallint[], :daily)"),
        {"user_id": user_id, "daily": daily_minutes},
    )
    await session.execute(
        # evidence_strength 是生成列，不能直接写；只插可写列。
        text("INSERT INTO user_skill_levels (user_id, skill_id, level, evidence_kind, "
             "verification_method, assessment_state) "
             "SELECT :user_id, id, 2, 'diagnostic', 'static_rule', 'established' "
             "FROM skills WHERE level = 'domain'"),
        {"user_id": user_id},
    )
    return user_id


async def test_generate_plan_works_for_a_user_that_is_not_the_seeded_one(
    db_session: AsyncSession,
) -> None:
    """自建用户能独立生成计划，且不触碰种子用户的计划行。"""
    seeded_id = int(
        (await db_session.execute(text("SELECT id FROM users ORDER BY id LIMIT 1"))).scalar_one()
    )
    seeded_before = int(
        (
            await db_session.execute(
                text("SELECT count(*) FROM study_plan_items WHERE user_id = :user_id"),
                {"user_id": seeded_id},
            )
        ).scalar_one()
    )

    user_id = await _fresh_user(db_session, daily_minutes=60)
    monday = await study_plan_service._week_start(db_session, "Asia/Shanghai")

    await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)

    mine = (
        await db_session.execute(
            text("SELECT kind, target_id, planned_minutes, week_start FROM study_plan_items "
                 "WHERE user_id = :user_id ORDER BY plan_date, kind"),
            {"user_id": user_id},
        )
    ).mappings().all()
    assert mine, "自建用户应当生成出计划行"
    assert all(row["week_start"] == monday for row in mine)
    assert all(int(row["planned_minutes"]) > 0 for row in mine)

    # 每个学习日的总分钟不超过该用户自己的额度
    per_day = (
        await db_session.execute(
            text("SELECT sum(planned_minutes) AS total FROM study_plan_items "
                 "WHERE user_id = :user_id GROUP BY plan_date"),
            {"user_id": user_id},
        )
    ).scalars().all()
    assert per_day and max(int(total) for total in per_day) <= 60

    # 种子用户的行数不变：隔离成立
    seeded_after = int(
        (
            await db_session.execute(
                text("SELECT count(*) FROM study_plan_items WHERE user_id = :user_id"),
                {"user_id": seeded_id},
            )
        ).scalar_one()
    )
    assert seeded_after == seeded_before, "生成别的用户的计划不得改动种子用户的行"


async def test_generate_plan_is_idempotent_for_the_same_user(
    db_session: AsyncSession,
) -> None:
    """同一用户重复生成行数不变——隔离之后依然幂等。"""
    user_id = await _fresh_user(db_session)
    monday = await study_plan_service._week_start(db_session, "Asia/Shanghai")

    first = await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
    count_1 = int(first["items_total"])
    second = await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
    assert int(second["items_total"]) == count_1