"""Sprint 2 Patch 的计划口径（S1 / S2 / S5）：受控复活、周中与周末首次生成、预算分离。

九条验收里 ①②③④⑧⑨ 在本文件，⑤⑥⑦ 在 test_sprint2_patch_lessons.py。

隔离策略沿用既有集成用例：读基线 → 事务内改档案 → 生成/断言 → 复原。所有断言只按
(user_id, week_start) 与本次写入的行限定；done/skipped 的历史用「快照后比对」证明未被动过。
外层事务整体回滚，全程不执行 DELETE / TRUNCATE / 迁移回退。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import ARRAY, SmallInteger, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import study_plan as study_plan_service

pytestmark = pytest.mark.integration

SET_USER_TIMEZONE = text(
    "UPDATE users SET timezone = :timezone, timezone_source = :source WHERE id = :user_id"
)
SET_PROFILE = text(
    "UPDATE user_profiles SET study_days = :days, daily_minutes = :daily_minutes "
    "WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))
SELECT_WEEK_START = text("SELECT (date_trunc('week', now() AT TIME ZONE :timezone))::date")
SELECT_LOCAL_TODAY = text("SELECT (now() AT TIME ZONE :timezone)::date")
SELECT_WEEK_ROWS = text(
    """
    SELECT id, plan_date, target_id, kind, planned_minutes, status, dedupe_key, updated_at
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
    ORDER BY plan_date, id
    """
)


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


async def _set_profile(
    db_session: AsyncSession, user_id: int, *, study_days: list[int], daily_minutes: int
) -> None:
    await db_session.execute(
        SET_PROFILE,
        {"user_id": user_id, "days": study_days, "daily_minutes": daily_minutes},
    )


async def _confirmed(
    db_session: AsyncSession,
    user_id: int,
    *,
    study_days: list[int],
    daily_minutes: int,
    timezone_name: str = "Asia/Shanghai",
) -> tuple[date, date]:
    """确认时区 + 固定档案，返回 (本周周一, 本地今天)。"""
    await db_session.execute(
        SET_USER_TIMEZONE,
        {"user_id": user_id, "timezone": timezone_name, "source": "user_confirmed"},
    )
    await _set_profile(db_session, user_id, study_days=study_days, daily_minutes=daily_minutes)
    monday = (
        await db_session.execute(SELECT_WEEK_START, {"timezone": timezone_name})
    ).scalar_one()
    today = (
        await db_session.execute(SELECT_LOCAL_TODAY, {"timezone": timezone_name})
    ).scalar_one()
    return monday, today


async def _calendar(db_session: AsyncSession) -> tuple[date, date]:
    """只读地取本周周一与本地今天，不改任何档案。"""
    timezone_name = "Asia/Shanghai"
    monday = (
        await db_session.execute(SELECT_WEEK_START, {'timezone': timezone_name})
    ).scalar_one()
    today = (
        await db_session.execute(SELECT_LOCAL_TODAY, {'timezone': timezone_name})
    ).scalar_one()
    return monday, today


def _future_days(today: date, count: int) -> list[int]:
    """本周内「今天及以后」的 count 个连续星期号；放不下时返回空列表。

    这些用例原先硬编码 study_days=[3]（周三）。一旦运行日越过周三，
    排课器不会给过去的日子排东西，用例就整片变红——不是代码坏了，是测试
    跟着星期几漂移。改为从今天推算，并在本周放不下时明确跳过。
    """
    start = today.isoweekday()
    days = [start + offset for offset in range(count)]
    return days if days and days[-1] <= 7 else []


async def _rows(
    db_session: AsyncSession, user_id: int, monday: date
) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in (
            await db_session.execute(
                SELECT_WEEK_ROWS, {"user_id": user_id, "week_start": monday}
            )
        ).mappings()
    ]


def _terminal(rows: list[dict[str, object]]) -> dict[int, tuple[str, object]]:
    """done/skipped 行的 (status, updated_at) 快照：终态行一旦变化就说明被改写了。"""
    return {
        int(row["id"]): (str(row["status"]), row["updated_at"])
        for row in rows
        if row["status"] in ("done", "skipped")
    }


def _day_totals(
    rows: list[dict[str, object]], days: list[date]
) -> dict[date, int]:
    """指定日期上「非 expired」行的分钟合计（expired 是历史，不占预算）。"""
    totals = {day: 0 for day in days}
    for row in rows:
        if row["status"] == "expired":
            continue
        if row["plan_date"] in totals:
            totals[row["plan_date"]] += int(row["planned_minutes"])
    return totals


async def test_patch_01_expired_item_is_resurrected_when_its_study_day_returns(
    api, db_session: AsyncSession
) -> None:
    """① 学习日 A→B→A 后原课程能重新排入：expired 行在同一 dedupe_key 上复活，不新增行。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        monday, today = await _calendar(db_session)
        days = _future_days(today, 2)
        if len(days) < 2:
            pytest.skip("本周放不下两个「今天及以后」的学习日（今天已是周日）")
        day_a, day_b = days
        await _confirmed(db_session, user_id, study_days=[day_a], daily_minutes=120)
        target_day = monday + timedelta(days=day_a - 1)

        await api.post("/api/v1/study-plan/generate")
        rows_a = await _rows(db_session, user_id, monday)
        terminal_before = _terminal(rows_a)
        carrier = next(
            row
            for row in rows_a
            if row["plan_date"] == target_day and row["status"] == "scheduled"
        )

        # A→B：学习日改到另一天，原学习日的行作废（expired），不是删除
        await _set_profile(db_session, user_id, study_days=[day_b], daily_minutes=120)
        await api.post("/api/v1/study-plan/generate")
        rows_b = await _rows(db_session, user_id, monday)
        by_id_b = {int(row["id"]): row for row in rows_b}
        assert by_id_b[int(carrier["id"])]["status"] == "expired", "周三作废为过期行"
        count_b = len(rows_b)

        # B→A：学习日改回周三，同一行受控复活
        await _set_profile(db_session, user_id, study_days=[day_a], daily_minutes=120)
        await api.post("/api/v1/study-plan/generate")
        rows_c = await _rows(db_session, user_id, monday)
        by_id_c = {int(row["id"]): row for row in rows_c}
        assert int(carrier["id"]) in by_id_c, "复活必须在原行上发生，不能删了重插"
        assert by_id_c[int(carrier["id"])]["status"] == "scheduled"
        assert by_id_c[int(carrier["id"])]["dedupe_key"] == carrier["dedupe_key"]
        assert by_id_c[int(carrier["id"])]["target_id"] == carrier["target_id"]
        assert len(rows_c) == count_b, "复活不新增行，作废的行也不删除"
        assert _terminal(rows_c) == terminal_before, "done/skipped 终态行全程未被改写"

        print(
            f"复活: id={carrier['id']} scheduled->expired->scheduled keys稳定; "
            f"rows A={len(rows_a)} B={count_b} A'={len(rows_c)}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_patch_02_budget_shrink_then_restore_never_overspends_nor_loses_lessons(
    api, db_session: AsyncSession
) -> None:
    """② 每日预算调小再恢复：不超支、可执行课程不丢、被作废的课程重新排得进来。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        monday, today = await _calendar(db_session)
        days = _future_days(today, 2)
        if len(days) < 2:
            pytest.skip("本周放不下两个「今天及以后」的学习日（今天已是周日）")
        day_a, day_b = days
        await _confirmed(db_session, user_id, study_days=[day_a, day_b], daily_minutes=60)
        study_dates = [
            monday + timedelta(days=day_a - 1),
            monday + timedelta(days=day_b - 1),
        ]
        assert all(day >= today for day in study_dates), "两个学习日都必须还没过去"

        await api.post("/api/v1/study-plan/generate")
        rows_1 = await _rows(db_session, user_id, monday)
        terminal_before = _terminal(rows_1)
        targets_1 = {int(row["target_id"]) for row in rows_1 if row["status"] == "scheduled"}
        assert len(targets_1) >= 2

        # 预算 60 -> 30：只能花剩下的额度
        await _set_profile(db_session, user_id, study_days=[day_a, day_b], daily_minutes=30)
        await api.post("/api/v1/study-plan/generate")
        rows_2 = await _rows(db_session, user_id, monday)
        totals_2 = _day_totals(rows_2, study_dates)
        assert all(total <= 30 for total in totals_2.values()), totals_2
        assert len(rows_2) >= len(rows_1), "缩预算只能作废行，不能删除行"
        expired_at_2 = {
            int(row["id"]) for row in rows_2 if row["status"] == "expired"
        }

        # 预算 30 -> 60：已作废的行随目标集合回来（受控复活），课程一门不丢
        await _set_profile(db_session, user_id, study_days=[day_a, day_b], daily_minutes=60)
        await api.post("/api/v1/study-plan/generate")
        rows_3 = await _rows(db_session, user_id, monday)
        totals_3 = _day_totals(rows_3, study_dates)
        assert all(total <= 60 for total in totals_3.values()), totals_3

        targets_3 = {int(row["target_id"]) for row in rows_3 if row["status"] == "scheduled"}
        assert targets_1 <= targets_3, "恢复预算后原来的可执行课程必须重新排得进来"
        assert len(rows_3) == len(rows_2), "复活是原地改状态，不新增行"
        assert _terminal(rows_3) == terminal_before, "done/skipped 终态行全程未被改写"
        # 缩预算时被作废的行，在预算恢复后于同一行复活（受控复活）
        by_id_3 = {int(row["id"]): row for row in rows_3}
        resurrected = sorted(
            item_id for item_id in expired_at_2 if by_id_3[item_id]["status"] == "scheduled"
        )
        assert resurrected, "缩预算作废的课程必须能在预算恢复后重新排入"

        print(
            f"预算 60->30->60: rows={len(rows_1)}/{len(rows_2)}/{len(rows_3)} "
            f"day_totals_30={sorted(totals_2.values())} day_totals_60={sorted(totals_3.values())} "
            f"targets_kept={sorted(targets_1)} targets_final={sorted(targets_3)} "
            f"resurrected={resurrected}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_patch_03_first_generation_on_tuesday_creates_no_monday_scheduled_row(
    api, db_session: AsyncSession
) -> None:
    """③ 周二首次生成不产生周一的 scheduled：对照周一生成，再切到周二。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        monday, today = await _confirmed(
            db_session, user_id, study_days=[1, 3], daily_minutes=480
        )
        if today.isoweekday() > 2:
            # 场景要求「周二还没到」。越过周二后，生成器本来就不会排周一之后的过去日期，
            # 断言会变成恒真（空过）——那比红更危险，所以显式跳过。
            pytest.skip("本周的周二已过去，该场景无法复现（避免空过）")
        tuesday = monday + timedelta(days=1)

        # 对照：把「今天」钉在周一，周一确实会被排课（证明过滤器不是空转）
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        rows_monday = await _rows(db_session, user_id, monday)
        assert [
            row["id"] for row in rows_monday if row["plan_date"] == monday and row["status"] == "scheduled"
        ], "周一首次生成应把课程排到周一"

        # 周二首次生成：周一一行 scheduled 都不新增，原来的行作废保存
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=tuesday)
        rows_tuesday = await _rows(db_session, user_id, monday)
        assert not [
            row
            for row in rows_tuesday
            if row["status"] == "scheduled" and row["plan_date"] < tuesday
        ], "不得给已过去的日期新增 scheduled 任务"
        assert not [
            row for row in rows_tuesday if row["plan_date"] == monday and row["status"] == "scheduled"
        ]
        monday_before = [row for row in rows_monday if row["plan_date"] == monday]
        monday_after = [row for row in rows_tuesday if row["plan_date"] == monday]
        assert len(monday_after) >= len(monday_before), "周一的行只作废、不删除"
        assert any(row["status"] == "expired" for row in monday_after)

        # 真实时钟端到端（today 来自 users.timezone）：同样没有过去的 scheduled
        generated = await api.post("/api/v1/study-plan/generate")
        assert generated.status_code == 200, generated.text
        assert date.fromisoformat(generated.json()["today"]) == today
        rows_http = await _rows(db_session, user_id, monday)
        assert not [
            row
            for row in rows_http
            if row["status"] == "scheduled" and row["plan_date"] < today
        ], "线上路径同样不得排到过去"
        assert len(rows_http) >= len(rows_tuesday), "作废不改行数"

        print(
            f"周二首次生成: today={today} monday_scheduled_after={0} "
            f"rows_monday={len(rows_monday)} rows_tuesday={len(rows_tuesday)} rows_http={len(rows_http)}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_patch_04_first_generation_on_the_weekend_only_schedules_the_weekend(
    api, db_session: AsyncSession
) -> None:
    """④ 周末首次生成同理：周六只排周六，周日再无可排日期。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        monday, today = await _confirmed(
            db_session, user_id, study_days=[1, 3, 5, 6], daily_minutes=480
        )
        if today.isoweekday() > 6:
            pytest.skip("本周的周六已过去，该场景无法复现（避免空过）")
        saturday = monday + timedelta(days=5)
        sunday = monday + timedelta(days=6)

        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=saturday)
        rows_saturday = await _rows(db_session, user_id, monday)
        scheduled = [row for row in rows_saturday if row["status"] == "scheduled"]
        assert scheduled, "周六仍在候选区间内，应能排课"
        assert {row["plan_date"] for row in scheduled} == {saturday}, "不得排到周一/周三/周五"
        assert {row["plan_date"] for row in scheduled} <= {saturday, sunday}

        # 周日首次生成：本周已经没有可排日期
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=sunday)
        rows_sunday = await _rows(db_session, user_id, monday)
        assert not [row for row in rows_sunday if row["status"] == "scheduled"]
        assert len(rows_sunday) == len(rows_saturday), "改状态不改行数"

        print(
            f"周末首次生成: saturday_scheduled={len(scheduled)} "
            f"dates={sorted({str(row['plan_date']) for row in scheduled})} "
            f"rows_sat={len(rows_saturday)} rows_sun={len(rows_sunday)}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_patch_08_regeneration_never_rewrites_done_or_skipped(
    api, db_session: AsyncSession
) -> None:
    """⑧ 重生成后 done/skipped 的 status / updated_at 不变，也不被重排成第二行。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        monday, _today = await _confirmed(
            db_session, user_id, study_days=[3, 5], daily_minutes=60
        )
        first = await api.post("/api/v1/study-plan/generate")
        assert first.status_code == 200, first.text
        rows_1 = await _rows(db_session, user_id, monday)
        scheduled = [row for row in rows_1 if row["status"] == "scheduled"]
        assert len(scheduled) >= 2, "至少两行才能同时验证 done 与 skipped"
        done_row, skipped_row = scheduled[0], scheduled[1]
        assert (
            await api.patch(
                f"/api/v1/study-plan/items/{done_row['id']}", json={"status": "done"}
            )
        ).status_code == 200
        assert (
            await api.patch(
                f"/api/v1/study-plan/items/{skipped_row['id']}", json={"status": "skipped"}
            )
        ).status_code == 200

        settled = await _rows(db_session, user_id, monday)
        frozen = _terminal(settled)
        keys_before = sorted(str(row["dedupe_key"]) for row in settled)
        count_before = len(settled)
        assert frozen[int(done_row["id"])][0] == "done"
        assert frozen[int(skipped_row["id"])][0] == "skipped"

        for _ in range(2):
            again = await api.post("/api/v1/study-plan/generate")
            assert again.status_code == 200, again.text

        after = await _rows(db_session, user_id, monday)
        assert len(after) == count_before, "同输入重复生成行数不变"
        assert sorted(str(row["dedupe_key"]) for row in after) == keys_before
        assert _terminal(after) == frozen, "done/skipped 的 status 与 updated_at 都必须原样"
        for item_id in (int(done_row["id"]), int(skipped_row["id"])):
            target = int(next(row for row in after if int(row["id"]) == item_id)["target_id"])
            executable = [
                row
                for row in after
                if int(row["target_id"]) == target and row["status"] != "expired"
            ]
            assert len(executable) == 1, "终态课程不得被重排成第二条可执行计划行"

        print(
            f"重生成 x2: rows={count_before}->{len(after)} keys稳定={sorted(str(r['dedupe_key']) for r in after) == keys_before} "
            f"done_id={done_row['id']} skipped_id={skipped_row['id']} 终态快照未变"
        )
    finally:
        await _restore(db_session, baseline)


async def test_patch_09_response_separates_history_from_scheduled_within_budget(
    api, db_session: AsyncSession
) -> None:
    """⑨ 响应 total_minutes <= daily_minutes，且 history 与 scheduled 分开计数与计量。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        monday, today = await _calendar(db_session)
        days = _future_days(today, 1)
        if not days:
            pytest.skip("本周已无「今天及以后」的学习日")
        study_day = days[0]
        await _confirmed(db_session, user_id, study_days=[study_day], daily_minutes=60)
        wednesday = monday + timedelta(days=study_day - 1)
        await api.post("/api/v1/study-plan/generate")
        rows_1 = await _rows(db_session, user_id, monday)
        target = next(
            row
            for row in rows_1
            if row["plan_date"] == wednesday and row["status"] == "scheduled"
        )
        target_minutes = int(target["planned_minutes"])
        # 该日本来就可能有历史终态（运行期间真实学习过），所以断言「增量」而不是绝对值：
        # 先读出标记前的 history_minutes，标记完成后必须正好多出 target_minutes。
        before_body = (await api.get("/api/v1/study-plan")).json()
        before_day = next(
            day for day in before_body["days"] if day["plan_date"] == wednesday.isoformat()
        )
        history_before = int(before_day["history_minutes"])
        history_minutes_expected = history_before + target_minutes
        assert (
            await api.patch(
                f"/api/v1/study-plan/items/{target['id']}", json={"status": "done"}
            )
        ).status_code == 200

        generated = await api.post("/api/v1/study-plan/generate")
        assert generated.status_code == 200, generated.text
        body = generated.json()
        read = await api.get("/api/v1/study-plan")
        assert read.status_code == 200, read.text
        read_body = read.json()

        day = next(day for day in body["days"] if day["plan_date"] == wednesday.isoformat())
        assert day["history_minutes"] == history_minutes_expected
        # 不再断言「该日一定还能排进新任务」：这是数据属性而非规则。运行期间真实学习后，
        # 当日额度可能已经被课程与到期复习占满，排不进新任务是正确行为。这里只断言结构规则。
        assert day["total_minutes"] == day["scheduled_minutes"] + day["history_minutes"]
        assert day["planned_minutes"] == day["total_minutes"]
        assert day["total_minutes"] <= body["daily_minutes"]
        assert day["history_minutes"] <= day["total_minutes"], "历史量不得混进待执行"

        for candidate_day in body["days"]:
            assert candidate_day["total_minutes"] <= body["daily_minutes"], candidate_day
            assert candidate_day["scheduled_minutes"] == sum(
                item["planned_minutes"]
                for item in candidate_day["items"]
                if item["status"] == "scheduled"
            )
            assert candidate_day["history_minutes"] == sum(
                item["planned_minutes"]
                for item in candidate_day["items"]
                if item["status"] in ("done", "skipped")
            )

        items = [item for day_payload in body["days"] for item in day_payload["items"]]
        assert body["scheduled_items"] == len(
            [item for item in items if item["status"] == "scheduled"]
        )
        assert body["history_items"] == len(
            [item for item in items if item["status"] in ("done", "skipped")]
        )
        assert body["items_total"] == body["scheduled_items"] + body["history_items"]
        assert sum(day_payload["scheduled_minutes"] for day_payload in body["days"]) == sum(
            item["planned_minutes"] for item in items if item["status"] == "scheduled"
        )
        assert sum(day_payload["history_minutes"] for day_payload in body["days"]) == sum(
            item["planned_minutes"] for item in items if item["status"] in ("done", "skipped")
        )

        read_day = next(
            day for day in read_body["days"] if day["plan_date"] == wednesday.isoformat()
        )
        assert read_day["scheduled_minutes"] == day["scheduled_minutes"]
        assert read_day["history_minutes"] == day["history_minutes"]
        assert read_day["total_minutes"] == day["total_minutes"]

        print(
            f"预算口径: wednesday scheduled={day['scheduled_minutes']} history={day['history_minutes']} "
            f"total={day['total_minutes']} <= daily={body['daily_minutes']} | "
            f"scheduled_items={body['scheduled_items']} history_items={body['history_items']} "
            f"items_total={body['items_total']}"
        )
    finally:
        await _restore(db_session, baseline)
