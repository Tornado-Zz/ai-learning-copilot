"""验收 13：计划预览是内存计算，调用前后不产生任何行。

Sprint 2 起 study_plan_items 表已由 0003 建立，但预览接口仍然一行都不写：
本文件改为断言"该用户的行数增量恒为 0"，而不是"表不存在"。


隔离策略：预览接口按契约是单用户（min id）语义，无法指定 user_id，因此
1. 断言只使用"该用户当前的档案"（从 GET /users/me 读取），不假设默认档案；
2. 时区两态（unconfirmed → 409 / confirmed → 200）在事务内临时切换并在 finally 复原；
3. 不写库的证据是调用前后的行数增量（含本测试自建用户的行数），不是全表绝对值。
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TRACKED_TABLES = (
    "users",
    "user_profiles",
    "skills",
    "diagnostic_attempts",
    "user_skill_levels",
    "lessons",
    "learning_progress",
    "study_plan_items",
)

SELECT_TZ_SOURCE = text("SELECT timezone_source FROM users WHERE id = :user_id")
SET_TZ_SOURCE = text("UPDATE users SET timezone_source = :source WHERE id = :user_id")
COUNT_USER_LEVELS = text("SELECT count(*) FROM user_skill_levels WHERE user_id = :user_id")
COUNT_USER_ATTEMPTS = text("SELECT count(*) FROM diagnostic_attempts WHERE user_id = :user_id")


async def test_13_preview_covers_both_timezone_states_and_persists_nothing(
    api, db_session: AsyncSession, test_user, row_counter
) -> None:
    me = (await api.get("/api/v1/users/me")).json()
    user_id = int(me["user"]["id"])
    profile = me["profile"]
    own_user_id = int(test_user["id"])
    original_source = (
        await db_session.execute(SELECT_TZ_SOURCE, {"user_id": user_id})
    ).scalar_one()

    async def snapshot() -> dict[str, int]:
        counts = {table: await row_counter(db_session, table) for table in TRACKED_TABLES}
        counts["test_user_levels"] = int(
            (await db_session.execute(COUNT_USER_LEVELS, {"user_id": own_user_id})).scalar_one()
        )
        counts["test_user_attempts"] = int(
            (await db_session.execute(COUNT_USER_ATTEMPTS, {"user_id": own_user_id})).scalar_one()
        )
        return counts

    before = await snapshot()

    # 路径 1：时区未确认 → 409，且不返回任何本周推导
    try:
        await db_session.execute(
            SET_TZ_SOURCE, {"user_id": user_id, "source": "default"}
        )
        blocked = await api.get("/api/v1/study-plan/preview")
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["error"]["code"] == "CONFLICT"
        assert blocked.json()["request_id"]
        assert "days" not in blocked.json()
    finally:
        await db_session.execute(
            SET_TZ_SOURCE, {"user_id": user_id, "source": original_source}
        )

    # 路径 2：时区已确认 → 200，persisted 恒为 false
    try:
        await db_session.execute(
            SET_TZ_SOURCE, {"user_id": user_id, "source": "user_confirmed"}
        )
        first = await api.get("/api/v1/study-plan/preview")
        second = await api.get("/api/v1/study-plan/preview")
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json() == second.json()
        body = first.json()

        assert body["computed"] is True
        assert body["persisted"] is False
        assert body["note"] == "Sprint 2 才落库"
        assert {"computed", "persisted", "days", "note"} <= set(body)
        assert "target_id" not in first.text
        assert "plan_id" not in first.text

        days = body["days"]
        assert [date.fromisoformat(day["date"]).isoweekday() for day in days] == sorted(
            profile["study_days"]
        )
        assert [day["minutes"] for day in days] == [profile["daily_minutes"]] * len(days)
        assert sum(day["minutes"] for day in days) == body["weekly_minutes"]
        assert body["weekly_minutes"] == profile["weekly_minutes"]
        assert body["timezone"] == me["user"]["timezone"]

        stages = body["stages"]
        assert len(stages) == 6
        expected_focus = next((stage["skill_code"] for stage in stages if stage["level"] < 2), None)
        assert body["focus_stage"] == expected_focus
        assert f"本周 {len(days)} 天" in body["advice"]
    finally:
        await db_session.execute(
            SET_TZ_SOURCE, {"user_id": user_id, "source": original_source}
        )

    after = await snapshot()
    assert after == before
    assert (
        await db_session.execute(SELECT_TZ_SOURCE, {"user_id": user_id})
    ).scalar_one() == original_source
    # 表由 0003 建立，但预览不写：该用户的计划行数增量恒为 0
    assert (
        await db_session.execute(text("SELECT to_regclass('public.study_plan_items')"))
    ).scalar_one() == "study_plan_items"
    # 库内可能已有真实计划行，因此只断言"预览没有新增/改写任何行"
    assert after["study_plan_items"] == before["study_plan_items"]
