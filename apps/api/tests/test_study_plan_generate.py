"""Sprint 2 验收 ⑥–⑪：周计划只排真实 lesson、R1/R2 预算与学习日、幂等与 done/skipped 保护、时区。

注意：`generate_plan()` 现接收显式 `user_id`，用例可自建用户（见
test_study_plan_isolation.py）。本文件仍跑在种子用户身上，因为重点在于「同一用户重复
生成时的幂等与终态保护」；因此断言只写**规则**（上限、预算、幂等、终态不可改写），
不写「库里应该还有多少活可排」这类数据属性。

隔离策略：接口是单用户语义，因此"读基线 → 写 → 断言 → 复原"并依赖外层事务回滚；
行数断言一律按 (user_id, week_start) 维度，绝不使用全表绝对值。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import ARRAY, SmallInteger, bindparam, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.services import study_plan as study_plan_service

pytestmark = pytest.mark.integration

STUDY_DAYS = [1, 3, 5]
DAILY_MINUTES = 45
WEEKDAYS = set(STUDY_DAYS)

SET_USER_TIMEZONE = text(
    "UPDATE users SET timezone = :timezone, timezone_source = :source WHERE id = :user_id"
)
SET_PROFILE = text(
    "UPDATE user_profiles SET study_days = :days, daily_minutes = :daily_minutes "
    "WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))
SELECT_WEEK_START = text(
    "SELECT (date_trunc('week', now() AT TIME ZONE :timezone))::date"
)
SELECT_PLAN_ROWS = text(
    """
    SELECT id, week_start, plan_date, kind, target_id, planned_minutes, status, rationale,
           dedupe_key, updated_at
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
    ORDER BY plan_date, id
    """
)
COUNT_USER_PLAN = text("SELECT count(*) FROM study_plan_items WHERE user_id = :user_id")
COUNT_WEEK_PLAN = text(
    "SELECT count(*) FROM study_plan_items WHERE user_id = :user_id AND week_start = :week_start"
)
# v0.1.2 起 review 也是生成器会写的 kind：计划里的复习行必须对应一条真实到期的
# 错题（review_items pending 且 next_review_on 落在 [today, week_end]）。
COUNT_DUE_REVIEWS = text(
    "SELECT count(*) FROM review_items "
    "WHERE user_id = :user_id AND status = 'pending' "
    "AND next_review_on BETWEEN :today AND :week_end"
)
SELECT_LOCAL_TODAY = text("SELECT (now() AT TIME ZONE :timezone)::date")
SELECT_PUBLISHED_LESSON_IDS = text(
    "SELECT id FROM lessons WHERE status = 'published' AND deleted_at IS NULL"
)
SELECT_PUBLISHED_EXERCISE_IDS = text(
    "SELECT id FROM exercises WHERE status = 'published' AND deleted_at IS NULL"
)
SET_ITEM_STATUS = text("UPDATE study_plan_items SET status = :status WHERE id = :id")
SELECT_ITEM = text(
    "SELECT id, plan_date, target_id, status, updated_at FROM study_plan_items WHERE id = :id"
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


async def _confirmed(
    db_session: AsyncSession, user_id: int, *, timezone_name: str = "Asia/Shanghai"
) -> None:
    """Confirmed timezone plus a fixed budget, so R1/R2 assertions are deterministic."""
    await db_session.execute(
        SET_USER_TIMEZONE,
        {"user_id": user_id, "timezone": timezone_name, "source": "user_confirmed"},
    )
    await db_session.execute(
        SET_PROFILE,
        {"user_id": user_id, "days": STUDY_DAYS, "daily_minutes": DAILY_MINUTES},
    )


async def test_06_generated_plan_only_points_at_real_lessons_and_obeys_r1_r2(
    api, db_session: AsyncSession
) -> None:
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        response = await api.post("/api/v1/study-plan/generate")
        assert response.status_code == 200, response.text
        body = response.json()
        week_start = date.fromisoformat(body["week_start"])
        monday = (
            await db_session.execute(SELECT_WEEK_START, {"timezone": "Asia/Shanghai"})
        ).scalar_one()
        assert week_start == monday
        assert week_start.isoweekday() == 1
        assert date.fromisoformat(body["week_end"]) == date.fromordinal(
            week_start.toordinal() + 6
        )

        rows = (
            await db_session.execute(
                SELECT_PLAN_ROWS, {"user_id": user_id, "week_start": week_start}
            )
        ).mappings().all()
        assert rows, "生成后必须落库"
        # expired 是历史行：作废后不计入 R1/R2，也不出现在响应里
        active = [row for row in rows if row["status"] != "expired"]
        assert active, "生成后必须至少有一条有效计划项"
        assert body["items_total"] == len(active)
        assert body["expired_items"] == len(rows) - len(active)

        # ⑥ 只调度真实存在的已发布 lesson / exercise；v0.1.2 起 review 也是合法 kind
        assert {row["kind"] for row in active} <= {"lesson", "exercise", "review"}
        published = set(
            (await db_session.execute(SELECT_PUBLISHED_LESSON_IDS)).scalars().all()
        )
        published_exercises = set(
            (await db_session.execute(SELECT_PUBLISHED_EXERCISE_IDS)).scalars().all()
        )
        for row in active:
            if row["kind"] in ("exercise", "review"):
                assert int(row["target_id"]) in published_exercises, row["target_id"]
            else:
                assert int(row["target_id"]) in published, row["target_id"]
        review_rows = [row for row in active if row["kind"] == "review"]
        assert body["review_items"] == len(review_rows)
        assert (
            body["lesson_items"] + body["exercise_items"] + body["review_items"]
            == len(active)
        )
        # 复习行的三条硬不变量：15 分钟、每天最多 1 个、只来自真实到期的错题
        assert all(int(row["planned_minutes"]) == 15 for row in review_rows)
        assert len({row["plan_date"] for row in review_rows}) == len(review_rows)
        due_reviews = int(
            (
                await db_session.execute(
                    COUNT_DUE_REVIEWS,
                    {
                        "user_id": user_id,
                        "today": (
                            await db_session.execute(
                                SELECT_LOCAL_TODAY, {"timezone": "Asia/Shanghai"}
                            )
                        ).scalar_one(),
                        "week_end": week_start + timedelta(days=6),
                    },
                )
            ).scalar_one()
        )
        assert len(review_rows) <= due_reviews

        # ⑦ R1：同一 plan_date 的 sum(planned_minutes) <= daily_minutes
        per_date: dict[date, int] = {}
        for row in active:
            per_date[row["plan_date"]] = per_date.get(row["plan_date"], 0) + int(
                row["planned_minutes"]
            )
        assert all(total <= DAILY_MINUTES for total in per_date.values()), per_date
        for day in body["days"]:
            assert day["planned_minutes"] <= DAILY_MINUTES
            assert day["planned_minutes"] == sum(
                item["planned_minutes"] for item in day["items"]
            )

        # ⑧ R2：非学习日没有任何任务，且日期数不超过学习日数
        assert all(plan_date.isoweekday() in WEEKDAYS for plan_date in per_date)
        assert len(per_date) <= len(STUDY_DAYS)
        assert all(date.fromisoformat(day["plan_date"]).isoweekday() in WEEKDAYS for day in body["days"])

        # R5：每条任务都有可解释的 rationale（含等级与当日可用时长）
        for row in active:
            rationale = str(row["rationale"])
            assert rationale.strip()
            assert "L" in rationale
            assert f"当日可用 {DAILY_MINUTES} 分钟" in rationale
            assert len(rationale) <= 200
        # 容量不足时给出取舍说明
        for item in body["unscheduled"]:
            assert item["reason"].strip()
            assert int(item["lesson_id"]) in published

        print(
            f"R1 max_day_minutes={max(per_date.values())} daily_minutes={DAILY_MINUTES} "
            f"days={len(per_date)} items={len(active)} "
            f"kinds={sorted({r['kind'] for r in active})}"
        )
        print(
            f"R2 plan_weekdays={sorted({d.isoweekday() for d in per_date})} "
            f"study_days={STUDY_DAYS} week_start={week_start.isoformat()} "
            f"unscheduled={len(body['unscheduled'])}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_07_regeneration_is_idempotent_and_never_rewrites_done_or_skipped(
    api, db_session: AsyncSession
) -> None:
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        first = await api.post("/api/v1/study-plan/generate")
        assert first.status_code == 200, first.text
        week_start = date.fromisoformat(first.json()["week_start"])
        count_1 = int(
            (
                await db_session.execute(
                    COUNT_WEEK_PLAN, {"user_id": user_id, "week_start": week_start}
                )
            ).scalar_one()
        )
        keys_1 = [
            row["dedupe_key"]
            for row in (
                await db_session.execute(
                    SELECT_PLAN_ROWS, {"user_id": user_id, "week_start": week_start}
                )
            ).mappings()
        ]

        second = await api.post("/api/v1/study-plan/generate")
        assert second.status_code == 200, second.text
        assert second.json()["items_total"] == first.json()["items_total"]
        count_2 = int(
            (
                await db_session.execute(
                    COUNT_WEEK_PLAN, {"user_id": user_id, "week_start": week_start}
                )
            ).scalar_one()
        )
        keys_2 = [
            row["dedupe_key"]
            for row in (
                await db_session.execute(
                    SELECT_PLAN_ROWS, {"user_id": user_id, "week_start": week_start}
                )
            ).mappings()
        ]
        assert count_2 == count_1
        assert keys_2 == keys_1

        # 置 done / skipped：只改 status，不动 updated_at
        ids = [
            int(row["id"])
            for row in (
                await db_session.execute(
                    SELECT_PLAN_ROWS, {"user_id": user_id, "week_start": week_start}
                )
            ).mappings()
            if row["status"] != "expired"
        ]
        assert len(ids) >= 2, "至少需要两行才能同时验证 done 与 skipped"
        await db_session.execute(SET_ITEM_STATUS, {"id": ids[0], "status": "done"})
        await db_session.execute(SET_ITEM_STATUS, {"id": ids[1], "status": "skipped"})
        frozen = {
            int(row["id"]): dict(row)
            for row in (
                await db_session.execute(
                    SELECT_PLAN_ROWS, {"user_id": user_id, "week_start": week_start}
                )
            ).mappings()
            if int(row["id"]) in (ids[0], ids[1])
        }
        assert frozen[ids[0]]["status"] == "done"
        assert frozen[ids[1]]["status"] == "skipped"

        third = await api.post("/api/v1/study-plan/generate")
        assert third.status_code == 200, third.text
        count_3 = int(
            (
                await db_session.execute(
                    COUNT_WEEK_PLAN, {"user_id": user_id, "week_start": week_start}
                )
            ).scalar_one()
        )
        assert count_3 == count_1, "同周重复生成行数必须不变"

        for item_id in (ids[0], ids[1]):
            current = (
                await db_session.execute(SELECT_ITEM, {"id": item_id})
            ).mappings().one()
            assert current["status"] == frozen[item_id]["status"]
            assert current["updated_at"] == frozen[item_id]["updated_at"], "done/skipped 不得被改写"
            assert current["plan_date"] == frozen[item_id]["plan_date"], "跳过不顺延到次日"

        # R3：跳过不产生第二条计划行，也不写任何失败记录（mistakes 表不存在）
        # 按 (kind, target_id) 计数：v0.1.2 起同一道 exercise 可以同时是"新练习"和
        # "复习"两个不同的计划项，同 kind 同 target 才叫第二条。
        skipped_target = frozen[ids[1]]["target_id"]
        skipped_kind = frozen[ids[1]]["kind"]
        same_target = (
            await db_session.execute(
                text(
                    "SELECT count(*) FROM study_plan_items "
                    "WHERE user_id = :user_id AND week_start = :week_start "
                    "AND kind = :kind AND target_id = :target_id"
                ),
                {
                    "user_id": user_id,
                    "week_start": week_start,
                    "kind": skipped_kind,
                    "target_id": skipped_target,
                },
            )
        ).scalar_one()
        assert int(same_target) == 1
        assert (
            await db_session.execute(text("SELECT to_regclass('public.mistakes')"))
        ).scalar_one() is None

        # GET 读回同样两行，状态不再是 scheduled
        plan = await api.get("/api/v1/study-plan")
        assert plan.status_code == 200, plan.text
        statuses = {
            item["id"]: item["status"]
            for day in plan.json()["days"]
            for item in day["items"]
        }
        assert statuses[ids[0]] == "done"
        assert statuses[ids[1]] == "skipped"

        print(
            f"idempotent rows_before={count_1} rows_after={count_2} rows_third={count_3} "
            f"done_id={ids[0]} skipped_id={ids[1]} keys_stable={keys_2 == keys_1}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_08_timezone_confirmation_and_local_calendar_dates(
    api, db_session: AsyncSession
) -> None:
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        before = int(
            (await db_session.execute(COUNT_USER_PLAN, {"user_id": user_id})).scalar_one()
        )

        # ⑪ 时区未确认：两个接口都 409，且一行都不写
        await db_session.execute(
            SET_USER_TIMEZONE,
            {"user_id": user_id, "timezone": "Asia/Shanghai", "source": "default"},
        )
        read_blocked = await api.get("/api/v1/study-plan")
        assert read_blocked.status_code == 409, read_blocked.text
        assert read_blocked.json()["error"]["code"] == "CONFLICT"
        assert read_blocked.json()["error"]["details"]["reason"] == "timezone_not_confirmed"
        write_blocked = await api.post("/api/v1/study-plan/generate")
        assert write_blocked.status_code == 409, write_blocked.text
        assert int(
            (await db_session.execute(COUNT_USER_PLAN, {"user_id": user_id})).scalar_one()
        ) == before

        # 确认后：week_start 等于该时区的本地周一
        await _confirmed(db_session, user_id, timezone_name="Asia/Shanghai")
        shanghai = await api.post("/api/v1/study-plan/generate")
        assert shanghai.status_code == 200, shanghai.text
        shanghai_week = date.fromisoformat(shanghai.json()["week_start"])
        expected_shanghai = (
            await db_session.execute(SELECT_WEEK_START, {"timezone": "Asia/Shanghai"})
        ).scalar_one()
        assert shanghai_week == expected_shanghai
        assert shanghai_week.isoweekday() == 1

        # 换成 America/New_York 重新生成：日期按新时区的本地日历重算并落库为 date
        await db_session.execute(
            SET_USER_TIMEZONE,
            {"user_id": user_id, "timezone": "America/New_York", "source": "user_confirmed"},
        )
        new_york = await api.post("/api/v1/study-plan/generate")
        assert new_york.status_code == 200, new_york.text
        new_york_week = date.fromisoformat(new_york.json()["week_start"])
        expected_new_york = (
            await db_session.execute(SELECT_WEEK_START, {"timezone": "America/New_York"})
        ).scalar_one()
        assert new_york_week == expected_new_york
        assert new_york_week.isoweekday() == 1

        # 该周的每一行都落在 [week_start, week_start+7) 且是本地学习日
        for row in (
            await db_session.execute(
                SELECT_PLAN_ROWS, {"user_id": user_id, "week_start": new_york_week}
            )
        ).mappings():
            if row["status"] == "expired":
                continue
            assert new_york_week <= row["plan_date"]
            assert row["plan_date"].toordinal() - new_york_week.toordinal() < 7
            assert row["plan_date"].isoweekday() in WEEKDAYS

        # 与服务器时钟无关的确定性证据：同一个固定时刻在两个时区会落在不同的 ISO 周，
        # 而服务端用的正是同一条 date_trunc('week', ... AT TIME ZONE users.timezone) 规则。
        fixed_instant_check = text(
            "SELECT (date_trunc('week', TIMESTAMPTZ '2026-11-01 23:30:00+00' "
            "AT TIME ZONE :timezone))::date"
        )
        week_in_shanghai = (
            await db_session.execute(fixed_instant_check, {"timezone": "Asia/Shanghai"})
        ).scalar_one()
        week_in_new_york = (
            await db_session.execute(fixed_instant_check, {"timezone": "America/New_York"})
        ).scalar_one()
        assert week_in_shanghai == date(2026, 11, 2)
        assert week_in_new_york == date(2026, 10, 26)
        assert week_in_shanghai != week_in_new_york

        print(
            f"timezone Asia/Shanghai week_start={shanghai_week.isoformat()} | "
            f"America/New_York week_start={new_york_week.isoformat()} | "
            f"shifted_now={shanghai_week != new_york_week} | "
            f"fixed_instant shifted=True ({week_in_shanghai} vs {week_in_new_york}) | "
            f"未确认时 409 且零写入"
        )
    finally:
        await _restore(db_session, baseline)


# ---------------------------------------------------------------------------
# Sprint 6：练习进入周计划（kind='exercise'、等级驱动上限、按 kind 的 target 校验）
#
# 隔离策略与本文件其余用例一致：单用户语义下用 test_01 的真实用户，读基线 →
# 事务内改档案/等级 → 生成/断言 → 复原，外层事务整体回滚，全程不执行 DELETE。
# 等级用 tier 2 证据（practice + static_rule）覆盖：它比诊断证据高一档，
# resolve_current_levels 会选中它，于是"六域平均等级"可以被本文件精确控制。
# ---------------------------------------------------------------------------

SET_SPRINT6_PROFILE = text(
    "UPDATE user_profiles SET study_days = :days, daily_minutes = :daily_minutes "
    "WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))
INSERT_SPRINT6_DOMAIN_LEVELS = text(
    """
    INSERT INTO user_skill_levels (user_id, skill_id, level, evidence_kind,
                                   verification_method, assessment_state, evidence_count)
    SELECT :user_id, s.id, :level, 'practice', 'static_rule', 'established', 1
    FROM skills s WHERE s.level = 'domain'
    """
)
INSERT_SPRINT6_FAKE_EXERCISE_ITEM = text(
    """
    INSERT INTO study_plan_items (
        user_id, week_start, plan_date, kind, target_id, planned_minutes, status,
        rationale, dedupe_key
    )
    VALUES (
        :user_id, :week_start, :plan_date, 'exercise', :target_id, 15, 'scheduled',
        '构造的假练习 target_id，必须被拒', :dedupe_key
    )
    RETURNING id
    """
)
SELECT_SPRINT6_ROWS = text(
    """
    SELECT id, plan_date, kind, target_id, planned_minutes, status, rationale,
           dedupe_key, updated_at
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
    ORDER BY plan_date, id
    """
)
SELECT_LESSON_TITLES = text("SELECT id, title FROM lessons")
SELECT_EXERCISE_TITLES = text("SELECT id, title FROM exercises")


async def _sprint6_rows(
    db_session: AsyncSession, user_id: int, monday: date
) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in (
            await db_session.execute(
                SELECT_SPRINT6_ROWS, {"user_id": user_id, "week_start": monday}
            )
        ).mappings()
    ]


def _sprint6_counts(
    rows: list[dict[str, object]], kind: str
) -> dict[date, int]:
    """每个 plan_date 上该 kind 的有效行数（expired 是历史，不计）。"""
    counts: dict[date, int] = {}
    for row in rows:
        if row["status"] == "expired" or row["kind"] != kind:
            continue
        day = row["plan_date"]
        counts[day] = counts.get(day, 0) + 1  # type: ignore[index]
    return counts


def _sprint6_minutes(
    rows: list[dict[str, object]], days: set[date] | None = None
) -> dict[date, int]:
    """每个 plan_date 上所有有效行的分钟合计（lesson + exercise）。

    days 限定只统计本次生成涉及的日期：更早日期上的 done/skipped 属于历史，
    用户事后调小 daily_minutes 时它会超过新额度（响应 schema 已写明这一点）。
    """
    totals: dict[date, int] = {}
    for row in rows:
        if row["status"] == "expired":
            continue
        if days is not None and row["plan_date"] not in days:
            continue
        day = row["plan_date"]
        totals[day] = totals.get(day, 0) + int(row["planned_minutes"])  # type: ignore[index]
    return totals


async def _sprint6_monday(db_session: AsyncSession) -> date:
    return (
        await db_session.execute(SELECT_WEEK_START, {"timezone": "Asia/Shanghai"})
    ).scalar_one()


# ④⑤ 断言的预算边界（45 分钟 = 30 分钟课 + 15 分钟练习，40 分钟就放不下练习）只有在
# 计划排到「30 分钟那三节」时才成立。开发库里用户刚好学完前两节（20 + 25 分钟两节），
# 干净库里没有这层进度，于是同一段代码在干净库上排出 20/25 分钟的课。所以由用例自己
# 写下这两条进度：课程位置是夹具，不再依赖产品库里的既有学习记录。
COMPLETE_FIRST_LESSONS = text(
    """
    INSERT INTO learning_progress (
        user_id, lesson_id, status, progress_pct, started_at, completed_at
    )
    SELECT :user_id, id, 'completed', 100, now(), now()
    FROM (
        SELECT id FROM lessons
        WHERE status = 'published' AND deleted_at IS NULL
        ORDER BY stage, order_index, id
        LIMIT :count
    ) AS first_lessons
    ON CONFLICT (user_id, lesson_id) DO UPDATE
    SET status = 'completed',
        progress_pct = 100,
        started_at = COALESCE(learning_progress.started_at, now()),
        completed_at = COALESCE(learning_progress.completed_at, now()),
        updated_at = now()
    WHERE learning_progress.status <> 'completed'
    """
)


async def _complete_first_lessons(
    db_session: AsyncSession, user_id: int, count: int = 2
) -> None:
    """把前 count 节标成已学完：计划从第 3 节（30 分钟）开始，预算断言才确定。

    写在外层事务里，用例结束随回滚消失；已完成的真实进度不会被改写。
    """
    await db_session.execute(COMPLETE_FIRST_LESSONS, {"user_id": user_id, "count": count})


async def test_sprint6_01_items_carry_kind_target_title_and_href(
    api, db_session: AsyncSession
) -> None:
    """① 每条计划项补 kind / target_title / target_href，并按 kind 指向真实存在的行。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        # 每天 480 分钟、每天都是学习日：无论今天星期几，当天都能同时排课与练习
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [1, 2, 3, 4, 5, 6, 7], "daily_minutes": 480},
        )
        response = await api.post("/api/v1/study-plan/generate")
        assert response.status_code == 200, response.text
        body = response.json()

        published_lessons = set(
            (await db_session.execute(SELECT_PUBLISHED_LESSON_IDS)).scalars().all()
        )
        published_exercises = set(
            (await db_session.execute(SELECT_PUBLISHED_EXERCISE_IDS)).scalars().all()
        )
        lesson_titles = {
            int(row["id"]): str(row["title"])
            for row in (await db_session.execute(SELECT_LESSON_TITLES)).mappings()
        }
        exercise_titles = {
            int(row["id"]): str(row["title"])
            for row in (await db_session.execute(SELECT_EXERCISE_TITLES)).mappings()
        }

        items = [item for day in body["days"] for item in day["items"]]
        assert items, "生成后必须至少有一条计划项"
        for item in items:
            assert {"kind", "target_title", "target_href"} <= set(item), set(item)
            if item["kind"] == "lesson":
                assert int(item["target_id"]) in published_lessons
                assert item["target_href"] == f"/learn/{item['target_id']}"
                assert item["target_title"] == lesson_titles[int(item["target_id"])]
            else:
                # v0.1.2：复习项指向的同样是那道练习，客户端入口与练习一致
                assert item["kind"] in ("exercise", "review"), item["kind"]
                assert int(item["target_id"]) in published_exercises
                assert item["target_href"] == f"/practice/{item['target_id']}"
                assert item["target_title"] == exercise_titles[int(item["target_id"])]
        assert body["exercise_items"] == sum(
            1 for item in items if item["kind"] == "exercise"
        )
        assert body["exercise_items"] >= 1, "Sprint 6 起当天的计划必须能排到练习"
        assert body["review_items"] == sum(1 for item in items if item["kind"] == "review")

        for day in body["days"]:
            if not day["items"]:
                continue
            print(
                f"plan {day['plan_date']} total={day['total_minutes']}min "
                + " | ".join(
                    f"{item['kind']}#{item['target_id']}《{item['target_title']}》"
                    f"{item['target_href']} {item['planned_minutes']}m"
                    for item in day["items"]
                )
            )
    finally:
        await _restore(db_session, baseline)


async def test_sprint6_02_fake_exercise_target_is_refused_at_both_layers(
    api, db_session: AsyncSession
) -> None:
    """② exercise 项只指向真实 exercises.id：服务层 422，数据库触发器 23503。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    monday = await _sprint6_monday(db_session)
    fake_exercise_id = 987654321
    try:
        # 服务层：生成前就拒绝（生成器用的正是这个校验函数）
        with pytest.raises(ApiError) as service_refusal:
            await study_plan_service.ensure_targets_exist(
                db_session,
                [
                    {"kind": "lesson", "target_id": 1},
                    {"kind": "exercise", "target_id": fake_exercise_id},
                ],
            )
        refusal = service_refusal.value
        assert refusal.status_code == 422
        assert refusal.details["reason"] == "target_not_found"
        assert refusal.details["kind"] == "exercise"
        assert refusal.details["missing"] == [fake_exercise_id]

        # 数据库层：绕过服务层直接 INSERT，触发器同样拒绝
        with pytest.raises(DBAPIError) as trigger_refusal:
            await db_session.execute(
                INSERT_SPRINT6_FAKE_EXERCISE_ITEM,
                {
                    "user_id": user_id,
                    "week_start": monday,
                    "plan_date": monday,
                    "target_id": fake_exercise_id,
                    "dedupe_key": (
                        f"{monday.isoformat()}|{monday.isoformat()}|exercise|{fake_exercise_id}"
                    ),
                },
            )
        trigger_message = str(trigger_refusal.value)
        assert "exercises.id" in trigger_message, trigger_message

        # 语句失败后回滚到本测试的 savepoint，再确认一行都没落库
        await db_session.rollback()
        stored = (
            await db_session.execute(
                text(
                    "SELECT count(*) FROM study_plan_items "
                    "WHERE kind = 'exercise' AND target_id = :target_id"
                ),
                {"target_id": fake_exercise_id},
            )
        ).scalar_one()
        assert int(stored) == 0
        print(
            f"假 exercise target_id={fake_exercise_id} 被拒："
            f"服务层 422 {refusal.message} | 触发器 {trigger_message.splitlines()[0][:120]}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_sprint6_03_daily_exercise_cap_follows_the_domain_level_average(
    api, db_session: AsyncSession
) -> None:
    """③ 六域平均 level ≤1 → 每日最多 1 个练习；≥2 → 每日最多 2 个。"""
    # 规则边界（1 < 平均 < 2 的空档取更严格的 1）
    assert study_plan_service.exercise_cap_for_levels([1] * 6) == 1
    assert study_plan_service.exercise_cap_for_levels([0] * 6) == 1
    assert study_plan_service.exercise_cap_for_levels([1, 1, 1, 2, 2, 2]) == 1
    assert study_plan_service.exercise_cap_for_levels([2] * 6) == 2

    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [1, 2, 3], "daily_minutes": 120},
        )
        monday = await _sprint6_monday(db_session)

        # 平均 L1：每日最多一个练习
        await db_session.execute(
            INSERT_SPRINT6_DOMAIN_LEVELS, {"user_id": user_id, "level": 1}
        )
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        low = _sprint6_counts(await _sprint6_rows(db_session, user_id, monday), "exercise")
        # 上限规则的可靠断言是「不超过」，而不是「一定能排到」：当日额度可能被课程与
        # 到期复习先占掉，此时排不进新练习是正确行为（v0.1.2 起复习优先占位）。
        assert max(low.values(), default=0) <= 1, low

        # 平均 L2（tier 2 证据更新，覆盖上一条）：上限升到 2
        await db_session.execute(
            INSERT_SPRINT6_DOMAIN_LEVELS, {"user_id": user_id, "level": 2}
        )
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        high = _sprint6_counts(await _sprint6_rows(db_session, user_id, monday), "exercise")
        # 只能断言「不超过上限」：每天能排到的练习数还受「当天排到几门课」限制，
        # 用户已完成部分课程后一天只有一门课，实测上限 2 也只会排到 1（属正确行为）。
        # 两档上限本身的差异由上面 exercise_cap_for_levels 的单元断言保证。
        assert max(high.values(), default=0) <= 2, high
        assert sum(high.values()) >= sum(low.values())
        print(f"每日练习上限：平均L1={low} 平均L2={high}")
    finally:
        await _restore(db_session, baseline)


async def test_sprint6_04_daily_minutes_never_overspent_with_exercises(
    api, db_session: AsyncSession
) -> None:
    """④ 当日总分钟（lesson + exercise）≤ daily_minutes − 历史终态分钟。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        await _complete_first_lessons(db_session, user_id)
        # 周二/周三/周四：避开周一那两条 done/skipped 历史行，断言才干净
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [2, 3, 4], "daily_minutes": 45},
        )
        monday = await _sprint6_monday(db_session)
        generated_days = {monday + timedelta(days=offset) for offset in (1, 2, 3)}
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        rows = await _sprint6_rows(db_session, user_id, monday)
        totals = _sprint6_minutes(rows, generated_days)
        assert totals, "生成后必须落库"
        assert all(total <= 45 for total in totals.values()), totals
        kinds = {
            day: {row["kind"] for row in rows if row["plan_date"] == day and row["status"] != "expired"}
            for day in totals
        }
        assert any("exercise" in seen for seen in kinds.values()), kinds
        # 45 分钟 = 30 分钟课 + 15 分钟练习：额度一点不超，也一点不浪费
        assert all(total == 45 for total in totals.values()), totals

        # 额度降到 40：剩余 10 分钟放不下 15 分钟的练习行 → 一个练习都不排
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [2, 3, 4], "daily_minutes": 40},
        )
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        rows_40 = await _sprint6_rows(db_session, user_id, monday)
        totals_40 = _sprint6_minutes(rows_40, generated_days)
        assert all(total <= 40 for total in totals_40.values()), totals_40
        assert not [
            row
            for row in rows_40
            if row["kind"] == "exercise" and row["status"] != "expired"
        ], "剩余额度不足时必须放弃练习，而不是超支"
        print(f"当日总分钟 45->{sorted(totals.values())} 40->{sorted(totals_40.values())}")
    finally:
        await _restore(db_session, baseline)


async def test_sprint6_05_non_study_day_and_past_date_get_no_rows(
    api, db_session: AsyncSession
) -> None:
    """⑤ 非学习日与已过去的日期都不排（课与练习都不排）。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        await _complete_first_lessons(db_session, user_id)
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [2, 4], "daily_minutes": 45},
        )
        monday = await _sprint6_monday(db_session)
        tuesday = monday + timedelta(days=1)
        wednesday = monday + timedelta(days=2)
        thursday = monday + timedelta(days=3)

        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=wednesday)
        rows = await _sprint6_rows(db_session, user_id, monday)
        scheduled = [row for row in rows if row["status"] == "scheduled"]
        assert scheduled, "本周仍有周四这个学习日"
        assert all(row["plan_date"].isoweekday() in {2, 4} for row in scheduled)
        assert all(row["plan_date"] >= wednesday for row in scheduled), "不得排到已过去的日期"
        assert not [row for row in scheduled if row["plan_date"] == tuesday]
        # 练习与复习（v0.1.2 起的第三种 kind）都只能落在周四这个学习日
        exercises = [row for row in scheduled if row["kind"] == "exercise"]
        reviews = [row for row in scheduled if row["kind"] == "review"]
        assert all(row["plan_date"] == thursday for row in exercises + reviews)
        # 新顺序下复习优先占位：周三的 15 分钟余量可能被到期复习用掉，此时不排新练习；
        # 没有复习占位时，周四必须照旧排到练习。
        assert exercises or reviews, "周四至少排到练习或复习"
        if not reviews:
            assert exercises, "没有复习占位时必须排到练习"
        print(
            f"today={wednesday} 非学习日/过去日期 scheduled=0 "
            f"exercise_dates={sorted({str(row['plan_date']) for row in exercises})} "
            f"review_dates={sorted({str(row['plan_date']) for row in reviews})}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_sprint6_06_regeneration_is_idempotent_with_exercise_rows(
    api, db_session: AsyncSession
) -> None:
    """⑥ 同输入重复生成行数不变（含练习行），dedupe_key 集合与响应计数都不变。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [2, 3, 4], "daily_minutes": 120},
        )
        monday = await _sprint6_monday(db_session)

        first = await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        rows_1 = await _sprint6_rows(db_session, user_id, monday)
        keys_1 = sorted(str(row["dedupe_key"]) for row in rows_1)
        assert any(row["kind"] == "exercise" for row in rows_1 if row["status"] != "expired")

        for _ in range(2):
            again = await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
            assert again["items_total"] == first["items_total"]
            assert again["exercise_items"] == first["exercise_items"]
        rows_n = await _sprint6_rows(db_session, user_id, monday)
        assert len(rows_n) == len(rows_1), "同输入重复生成行数必须不变"
        assert sorted(str(row["dedupe_key"]) for row in rows_n) == keys_1
        print(
            f"幂等：rows={len(rows_1)}->{len(rows_n)} "
            f"exercise_items={first['exercise_items']} keys稳定={sorted(str(r['dedupe_key']) for r in rows_n) == keys_1}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_sprint6_07_done_and_skipped_exercise_items_are_never_rewritten(
    api, db_session: AsyncSession
) -> None:
    """⑦ 练习行的 done/skipped 终态不被改写，status 与 updated_at 都原样。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [2, 3, 4], "daily_minutes": 120},
        )
        monday = await _sprint6_monday(db_session)
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)

        rows = await _sprint6_rows(db_session, user_id, monday)
        scheduled_exercises = [
            row
            for row in rows
            if row["kind"] == "exercise" and row["status"] == "scheduled"
        ]
        assert len(scheduled_exercises) >= 2, scheduled_exercises
        done_id = int(scheduled_exercises[0]["id"])
        skipped_id = int(scheduled_exercises[1]["id"])
        await study_plan_service.update_plan_item(
            db_session, user_id=user_id, item_id=done_id, status="done"
        )
        await study_plan_service.update_plan_item(
            db_session, user_id=user_id, item_id=skipped_id, status="skipped"
        )
        frozen = {
            int(row["id"]): (str(row["status"]), row["updated_at"])
            for row in await _sprint6_rows(db_session, user_id, monday)
            if int(row["id"]) in (done_id, skipped_id)
        }
        assert frozen[done_id][0] == "done"
        assert frozen[skipped_id][0] == "skipped"
        count_before = len(await _sprint6_rows(db_session, user_id, monday))

        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        rows_after = await _sprint6_rows(db_session, user_id, monday)
        for item_id in (done_id, skipped_id):
            current = next(row for row in rows_after if int(row["id"]) == item_id)
            assert str(current["status"]) == frozen[item_id][0]
            assert current["updated_at"] == frozen[item_id][1], "终态行不得被改写"
            same_target = [
                row
                for row in rows_after
                if row["kind"] == "exercise"
                and int(row["target_id"]) == int(current["target_id"])
                and row["status"] != "expired"
            ]
            assert len(same_target) == 1, "终态练习不得被重排成第二条可执行计划行"
        assert len(rows_after) == count_before, "终态练习行占掉了当日练习额度，行数不变"
        print(
            f"练习终态保护：done_id={done_id} skipped_id={skipped_id} "
            f"rows={count_before}->{len(rows_after)} 终态快照未变"
        )
    finally:
        await _restore(db_session, baseline)


async def test_sprint6_08_patch_works_for_exercise_items(
    api, db_session: AsyncSession
) -> None:
    """⑧ PATCH /study-plan/items/{id} 对练习项同样生效，终态锁定规则不变。"""
    baseline = await _baseline(api, db_session)
    user_id = int(baseline["user_id"])
    try:
        await _confirmed(db_session, user_id)
        await db_session.execute(
            SET_SPRINT6_PROFILE,
            {"user_id": user_id, "days": [2, 3, 4], "daily_minutes": 120},
        )
        monday = await _sprint6_monday(db_session)
        await study_plan_service.generate_plan(db_session, user_id=user_id, today_override=monday)
        rows = await _sprint6_rows(db_session, user_id, monday)
        target = next(
            row
            for row in rows
            if row["kind"] == "exercise" and row["status"] == "scheduled"
        )
        exercise_titles = {
            int(row["id"]): str(row["title"])
            for row in (await db_session.execute(SELECT_EXERCISE_TITLES)).mappings()
        }

        response = await api.patch(
            f"/api/v1/study-plan/items/{target['id']}", json={"status": "done"}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["kind"] == "exercise"
        assert body["status"] == "done"
        assert body["target_id"] == int(target["target_id"])
        assert body["target_href"] == f"/practice/{target['target_id']}"
        assert body["target_title"] == exercise_titles[int(target["target_id"])]
        assert body["lesson_title"] is None, "练习项没有课程标题"

        stored = next(
            row
            for row in await _sprint6_rows(db_session, user_id, monday)
            if int(row["id"]) == int(target["id"])
        )
        assert str(stored["status"]) == "done"
        assert int(stored["planned_minutes"]) == int(target["planned_minutes"])
        assert str(stored["rationale"]) == str(target["rationale"])

        locked = await api.patch(
            f"/api/v1/study-plan/items/{target['id']}", json={"status": "skipped"}
        )
        assert locked.status_code == 409, locked.text
        assert locked.json()["error"]["code"] == "PLAN_ITEM_LOCKED"
        print(
            f"PATCH 练习项 id={target['id']}: 200 done -> /practice/{target['target_id']}；"
            f"再次 PATCH 409 PLAN_ITEM_LOCKED"
        )
    finally:
        await _restore(db_session, baseline)

