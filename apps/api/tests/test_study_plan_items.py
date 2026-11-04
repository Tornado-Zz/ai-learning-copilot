"""Sprint 2 追加验收：PATCH /study-plan/items/{id} 的状态机与 GET /study-plan 的 today。

隔离策略沿用其它集成用例：读基线 → 用固定档案生成本测试专属的计划项 → 断言 → 复原，
外层事务整体回滚，全程不执行 DELETE。
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import ARRAY, SmallInteger, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

# 与真实档案不同的学习日：保证本测试生成的项目与库内既有行不共用 dedupe_key
STUDY_DAYS = [2, 4]
DAILY_MINUTES = 60
WEEKDAYS = set(STUDY_DAYS)

SET_USER_TIMEZONE = text(
    "UPDATE users SET timezone = :timezone, timezone_source = :source WHERE id = :user_id"
)
SET_PROFILE = text(
    "UPDATE user_profiles SET study_days = :days, daily_minutes = :daily_minutes "
    "WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))
SELECT_LOCAL_TODAY = text("SELECT (now() AT TIME ZONE :timezone)::date")
SELECT_ITEM = text(
    "SELECT id, user_id, week_start, plan_date, kind, target_id, planned_minutes, status, "
    "rationale, dedupe_key, updated_at FROM study_plan_items WHERE id = :item_id"
)
COUNT_WEEK_ITEMS = text(
    "SELECT count(*) FROM study_plan_items WHERE user_id = :user_id AND week_start = :week_start"
)
INSERT_OTHER_USER_ITEM = text(
    """
    INSERT INTO study_plan_items (
        user_id, week_start, plan_date, kind, target_id, planned_minutes, status,
        rationale, dedupe_key
    )
    VALUES (
        :user_id, :week_start, :plan_date, 'lesson',
        (SELECT min(id) FROM lessons), 20, 'scheduled', '另一个用户的计划项', :dedupe_key
    )
    RETURNING id
    """
)

ITEM_FIELDS = {
    "id",
    "kind",
    "target_id",
    "lesson_code",
    "lesson_title",
    # Sprint 6：练习进入周计划后，前端按 target_title / target_href 直接渲染
    "target_title",
    "target_href",
    "planned_minutes",
    "status",
    "rationale",
    "dedupe_key",
}


async def _baseline(api, db_session: AsyncSession) -> dict[str, object]:
    me = (await api.get("/api/v1/users/me")).json()
    return {
        "user_id": int(me["user"]["id"]),
        "timezone": me["user"]["timezone"],
        "timezone_source": me["user"]["timezone_source"],
        "study_days": me["profile"]["study_days"],
        "daily_minutes": me["profile"]["daily_minutes"],
    }


async def _restore(db_session: AsyncSession, baseline: dict[str, object]) -> None:
    await db_session.execute(
        SET_USER_TIMEZONE,
        {
            "user_id": baseline["user_id"],
            "timezone": baseline["timezone"],
            "source": baseline["timezone_source"],
        },
    )
    await db_session.execute(
        SET_PROFILE,
        {
            "user_id": baseline["user_id"],
            "days": baseline["study_days"],
            "daily_minutes": baseline["daily_minutes"],
        },
    )


async def _prepare(api, db_session: AsyncSession) -> tuple[dict[str, object], dict[str, object]]:
    """Confirmed timezone + fixed budget, then generate this test's own items."""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    await db_session.execute(
        SET_USER_TIMEZONE,
        {"user_id": user_id, "timezone": "Asia/Shanghai", "source": "user_confirmed"},
    )
    await db_session.execute(
        SET_PROFILE,
        {"user_id": user_id, "days": STUDY_DAYS, "daily_minutes": DAILY_MINUTES},
    )
    generated = await api.post("/api/v1/study-plan/generate")
    assert generated.status_code == 200, generated.text
    return baseline, generated.json()


def _item_pairs(plan: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    """(plan_date, item) — plan_date lives on the day, not on the item."""
    return [(day["plan_date"], item) for day in plan["days"] for item in day["items"]]


def _scheduled_pairs(plan: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    """只取 scheduled 行：done/skipped 是只读历史，PATCH 用例必须落在可执行项上。

    S1 冻结后终态行在响应里照样展示（前端只读展示），所以不能再用「第一条」定位
    PATCH 目标——那条可能已经是 done（409 PLAN_ITEM_LOCKED）。
    """
    return [(plan_date, item) for plan_date, item in _item_pairs(plan) if item["status"] == "scheduled"]


async def test_items_payload_carries_rationale_status_minutes_and_title(
    api, db_session: AsyncSession
) -> None:
    baseline, plan = await _prepare(api, db_session)
    try:
        # 计划项字段清单：R5 要求 rationale 可展开，前端据此渲染
        pairs = _item_pairs(plan)
        assert pairs, "生成后必须至少有一条计划项"
        for _plan_date, item in pairs:
            assert ITEM_FIELDS <= set(item), set(item)
            assert item["rationale"].strip()
            assert item["target_title"]
            if item["kind"] == "lesson":
                assert item["lesson_title"] == item["target_title"]
                assert item["target_href"] == f"/learn/{item['target_id']}"
            else:
                # practice 行没有课程标题，链接与标题都来自 exercises
                assert item["target_href"] == f"/practice/{item['target_id']}"
            assert item["planned_minutes"] >= 15
            assert item["status"] in {"scheduled", "done", "skipped"}

        # today 按 users.timezone 计算，与数据库口径一致
        expected_today = (
            await db_session.execute(SELECT_LOCAL_TODAY, {"timezone": "Asia/Shanghai"})
        ).scalar_one()
        assert date.fromisoformat(plan["today"]) == expected_today
        read = await api.get("/api/v1/study-plan")
        assert read.status_code == 200, read.text
        assert date.fromisoformat(read.json()["today"]) == expected_today
        assert read.json()["today"] == plan["today"]
    finally:
        await _restore(db_session, baseline)


async def test_patch_scheduled_item_to_done(api, db_session: AsyncSession) -> None:
    baseline, plan = await _prepare(api, db_session)
    try:
        target_date, target = _scheduled_pairs(plan)[0]
        response = await api.patch(
            f"/api/v1/study-plan/items/{target['id']}", json={"status": "done"}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == target["id"]
        assert body["status"] == "done"
        assert body["plan_date"] == target_date
        assert body["lesson_title"] == target["lesson_title"]

        stored = (
            await db_session.execute(SELECT_ITEM, {"item_id": target["id"]})
        ).mappings().one()
        assert stored["status"] == "done"
        # 其它字段一律不变
        assert stored["planned_minutes"] == target["planned_minutes"]
        assert stored["rationale"] == target["rationale"]
        assert stored["dedupe_key"] == target["dedupe_key"]
        print(f"PATCH scheduled->done: 200, db status={stored['status']}")
    finally:
        await _restore(db_session, baseline)


async def test_patch_scheduled_item_to_skipped_has_no_failure_side_effects(
    api, db_session: AsyncSession
) -> None:
    baseline, plan = await _prepare(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        target_date, target = _scheduled_pairs(plan)[0]
        week_start = date.fromisoformat(plan["week_start"])
        count_before = int(
            (
                await db_session.execute(
                    COUNT_WEEK_ITEMS, {"user_id": user_id, "week_start": week_start}
                )
            ).scalar_one()
        )

        response = await api.patch(
            f"/api/v1/study-plan/items/{target['id']}", json={"status": "skipped"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "skipped"

        stored = (
            await db_session.execute(SELECT_ITEM, {"item_id": target["id"]})
        ).mappings().one()
        assert stored["status"] == "skipped"
        assert stored["plan_date"] == date.fromisoformat(target_date), "跳过不顺延"
        # 跳过不写任何失败记录：mistakes / review_tasks 表都不存在，计划行数也不变
        assert (
            await db_session.execute(text("SELECT to_regclass('public.mistakes')"))
        ).scalar_one() is None
        assert (
            await db_session.execute(text("SELECT to_regclass('public.review_tasks')"))
        ).scalar_one() is None
        assert int(
            (
                await db_session.execute(
                    COUNT_WEEK_ITEMS, {"user_id": user_id, "week_start": week_start}
                )
            ).scalar_one()
        ) == count_before
        print(f"PATCH scheduled->skipped: 200, db status={stored['status']}, 行数不变")
    finally:
        await _restore(db_session, baseline)


async def test_patch_locked_item_is_rejected_with_409(api, db_session: AsyncSession) -> None:
    baseline, plan = await _prepare(api, db_session)
    try:
        target = _scheduled_pairs(plan)[0][1]
        first = await api.patch(
            f"/api/v1/study-plan/items/{target['id']}", json={"status": "done"}
        )
        assert first.status_code == 200, first.text
        settled_at = (
            await db_session.execute(SELECT_ITEM, {"item_id": target["id"]})
        ).mappings().one()

        second = await api.patch(
            f"/api/v1/study-plan/items/{target['id']}", json={"status": "skipped"}
        )
        assert second.status_code == 409, second.text
        error = second.json()["error"]
        assert error["code"] == "PLAN_ITEM_LOCKED"
        assert error["details"]["reason"] == "plan_item_locked"
        assert error["details"]["current_status"] == "done"

        unchanged = (
            await db_session.execute(SELECT_ITEM, {"item_id": target["id"]})
        ).mappings().one()
        assert unchanged["status"] == "done"
        assert unchanged["updated_at"] == settled_at["updated_at"]
        # 非法 status 不进入业务层：422
        invalid = await api.patch(
            f"/api/v1/study-plan/items/{target['id']}", json={"status": "expired"}
        )
        assert invalid.status_code == 422, invalid.text
        print(f"PATCH done->skipped: 409 PLAN_ITEM_LOCKED, db status={unchanged['status']}")
    finally:
        await _restore(db_session, baseline)


async def test_patch_unknown_or_foreign_item_is_404(api, db_session: AsyncSession) -> None:
    baseline, plan = await _prepare(api, db_session)
    try:
        missing = await api.patch(
            "/api/v1/study-plan/items/999999999", json={"status": "done"}
        )
        assert missing.status_code == 404, missing.text
        assert missing.json()["error"]["code"] == "NOT_FOUND"

        # 另一个用户的同名 id：本接口只认当前单用户，跨用户一律 404 而不是越权改写
        other_user_id = int(
            (
                await db_session.execute(
                    text(
                        "INSERT INTO users (display_name) VALUES ('pytest-plan-other') RETURNING id"
                    )
                )
            ).scalar_one()
        )
        week_start = date.fromisoformat(plan["week_start"])
        foreign_id = int(
            (
                await db_session.execute(
                    INSERT_OTHER_USER_ITEM,
                    {
                        "user_id": other_user_id,
                        "week_start": week_start,
                        "plan_date": week_start,
                        "dedupe_key": f"{week_start}|{week_start}|lesson|other",
                    },
                )
            ).scalar_one()
        )
        foreign = await api.patch(
            f"/api/v1/study-plan/items/{foreign_id}", json={"status": "done"}
        )
        assert foreign.status_code == 404, foreign.text
        still = (
            await db_session.execute(SELECT_ITEM, {"item_id": foreign_id})
        ).mappings().one()
        assert still["status"] == "scheduled", "跨用户写入必须被拒绝"
        print("PATCH 不存在/跨用户: 404 x2，跨用户行仍为 scheduled")
    finally:
        await _restore(db_session, baseline)
