"""Study plan: in-memory preview (never writes) and the persisted week plan.

Rules R1-R6 of the Sprint 2 contract are enforced here:

* R1 every plan_date sums to at most user_profiles.daily_minutes;
* R2 plan_date always falls inside user_profiles.study_days and a non-study day
  never receives a task;
* R3 skipping never shifts a task to another day - the generator is a pure
  function of the curriculum and learning_progress, and it writes no mistakes;
* R4 the same (user_id, week_start) regenerates the same row count, and rows in
  status done/skipped are never rewritten (neither value nor updated_at);
* R5 every row carries a rationale with the level and that day's budget;
* R6 every date comes from users.timezone, never from the server clock;
* R7 a plan_date is never earlier than today_local, so a mid-week first
  generation cannot add a task to a day that has already passed;
* R8 a day's remaining budget is daily_minutes minus the minutes of the
  done/skipped rows already settled on that day - history is never re-spent;
* R9 an 'expired' row comes back to 'scheduled' only from this generator
  (controlled resurrection on the same dedupe_key); done/skipped never change;
* R10 (Sprint 6) exercises are planned after the lesson of a day: at most one
  exercise per lesson that day, and no more than the level-driven daily cap
  (average domain level <= 1 -> 1, >= 2 -> 2 exercises a day), still inside the
  day's remaining minutes;
* R11 (Sprint 6) target_id points at a row that really exists - lessons for
  kind='lesson', exercises for kind='exercise' - checked twice: here before the
  write (ensure_targets_exist) and by the fn_spi_lesson_target_exists trigger;
  kind='review' also points at a real exercise, checked here (the 0003/0007
  trigger does not know that kind and is deliberately left alone).
* R12 (v0.1.2) reviews are a pass of their own, after lessons and BEFORE new
  exercises: a due review outranks a brand new exercise, because re-testing a
  question the learner got wrong is worth more than adding another one, and it
  never displaces a lesson. A review row is placed only when the day still has
  >= 15 minutes left (R8) and a review_items row is pending with next_review_on
  inside [today_local, week_end]; a day carries at most one review, an exercise is
  never planned twice in a week, and a row already planned this week is re-emitted
  (same values) so a regeneration neither retires nor duplicates it.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import ARRAY, BigInteger, String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import CONFLICT, NOT_FOUND, PLAN_ITEM_LOCKED, ApiError, validation_error
from app.services import catalog, levels, users
from app.services import lessons as lessons_service

PREVIEW_NOTE = "Sprint 2 才落库"

# "This week" is defined by users.timezone only; PostgreSQL owns the tz database.
SELECT_WEEK_START = text(
    "SELECT (date_trunc('week', now() AT TIME ZONE :timezone))::date AS monday"
)

# "today" comes from the same users.timezone the week is derived from, so the UI
# never has to trust the browser clock.
SELECT_LOCAL_TODAY = text("SELECT (now() AT TIME ZONE :timezone)::date")

PLAN_KIND_LESSON = "lesson"
PLAN_KIND_EXERCISE = "exercise"
PLAN_KIND_REVIEW = "review"
PLAN_STATUS_SCHEDULED = "scheduled"
PLAN_STATUS_EXPIRED = "expired"
PLAN_STATUS_DONE = "done"
PLAN_STATUS_SKIPPED = "skipped"
# done / skipped are terminal: no path in this module may rewrite them (S1).
PLAN_STATUS_TERMINAL = (PLAN_STATUS_DONE, PLAN_STATUS_SKIPPED)
# Only these two transitions are open to the learner (PATCH /study-plan/items/{id}).
PLAN_STATUS_USER_SETTABLE = ("done", "skipped")
# AC-S2-01: a day carries 0-3 lesson items. Since Sprint 6 the same day also
# carries its exercises (R10) and since v0.1.2 its review row (R12), each capped
# separately: this number stays a lesson cap.
MAX_ITEMS_PER_DAY = 3
# R10: the daily exercise cap is the learner's own level, never a guess. The six
# domain levels are averaged: <= 1 -> 1 exercise a day, >= 2 -> 2. An average
# strictly between the two keeps the stricter cap of 1.
MAX_EXERCISES_PER_DAY_LOW = 1
MAX_EXERCISES_PER_DAY_HIGH = 2
EXERCISE_CAP_LEVEL_THRESHOLD = 2
MIN_PLANNED_MINUTES = 15
MAX_PLANNED_MINUTES = 480
# R12: a review row always reserves the table's minimum, and one day carries at
# most one review - the mistake book is practice, not a second lesson.
REVIEW_PLANNED_MINUTES = MIN_PLANNED_MINUTES
MAX_REVIEWS_PER_DAY = 1
RATIONALE_MAX_LENGTH = 200
WEEK_LENGTH_DAYS = 7

SELECT_WEEK_PLAN = text(
    """
    SELECT s.id, s.plan_date, s.kind, s.target_id, s.planned_minutes, s.status,
           s.rationale, s.dedupe_key,
           l.code AS lesson_code, l.title AS lesson_title,
           e.title AS exercise_title
    FROM study_plan_items s
    LEFT JOIN lessons l ON s.kind = 'lesson' AND l.id = s.target_id
    LEFT JOIN exercises e ON s.kind IN ('exercise', 'review') AND e.id = s.target_id
    WHERE s.user_id = :user_id AND s.week_start = :week_start
    ORDER BY s.plan_date, s.id
    """
)

# R4/R9: ON CONFLICT touches only rows that are still open. An 'expired' row whose
# key is part of this run's target set is resurrected here - the generator is the
# single controlled path back to 'scheduled'. A done or skipped row keeps both its
# values and its updated_at (the WHERE fails), and nothing is ever deleted.
UPSERT_PLAN_ITEM = text(
    """
    INSERT INTO study_plan_items (
        user_id, week_start, plan_date, kind, target_id,
        planned_minutes, status, rationale, dedupe_key
    )
    VALUES (
        :user_id, :week_start, :plan_date, :kind, :target_id,
        :planned_minutes, 'scheduled', :rationale, :dedupe_key
    )
    ON CONFLICT (user_id, dedupe_key) DO UPDATE SET
        planned_minutes = EXCLUDED.planned_minutes,
        rationale = EXCLUDED.rationale,
        status = 'scheduled',
        updated_at = now()
    WHERE study_plan_items.status IN ('scheduled', 'expired')
    """
)

# R2 after a profile change: a task that is no longer part of the generated week
# (non-study day, lesson already completed, budget shrunk) is retired as
# 'expired'. Retiring is an UPDATE of a still-'scheduled' row - never a DELETE,
# and done/skipped rows are not touched.
EXPIRE_STALE_ITEMS = text(
    """
    UPDATE study_plan_items
    SET status = 'expired', updated_at = now()
    WHERE user_id = :user_id
      AND week_start = :week_start
      AND status = 'scheduled'
      AND NOT (dedupe_key = ANY(:keep_keys))
    """
).bindparams(bindparam("keep_keys", type_=ARRAY(String)))

# R8: minutes and rows the learner already settled on a given day. They are
# history - never rewritten - but they have consumed that day's budget, so the
# generator may only spend what is left. Every kind spends minutes; only a
# lesson spends one of the MAX_ITEMS_PER_DAY lesson slots, because Sprint 6 gives
# exercises their own cap (R10) - a settled exercise must not cost a lesson slot.
SELECT_DAY_HISTORY = text(
    """
    SELECT plan_date,
           sum(planned_minutes) AS minutes,
           count(*) FILTER (WHERE kind = 'lesson') AS lesson_items
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
      AND status IN ('done', 'skipped')
    GROUP BY plan_date
    """
)

# A lesson this week already settled (its row is done or skipped) is history, not
# work to plan again: planning it a second time would put a fresh row on a
# finished lesson and spend the week's budget twice.
SELECT_SETTLED_TARGETS = text(
    """
    SELECT DISTINCT target_id
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
      AND kind = 'lesson'
      AND status IN ('done', 'skipped')
    """
)

# R10: exercises this week the learner already settled are history as well - the
# row is never rewritten, and the day's exercise quota stays spent.
SELECT_SETTLED_EXERCISE_TARGETS = text(
    """
    SELECT DISTINCT target_id
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
      AND kind = 'exercise'
      AND status IN ('done', 'skipped')
    """
)

# R10: exercise rows settled on a day also count toward that day's exercise cap,
# exactly like done/skipped minutes count toward its minute budget.
# R10：一节课一天只有一个练习位，**终态**（done/skipped）行算占满。
#
# 这里必须只算终态：已排但未完成的 scheduled 行要被「重新发出」以保持幂等，
# 若把它也算作占位、让生成器跳过它，EXPIRE_STALE_ITEMS 会把它 retire 掉，
# 计划里的练习就会凭空消失（实测会导致 5 个计划用例失败）。
#
# 只算终态同时解决了口径之争：学习者跳过某课练习后，同一次重生成不会给同一
# 节课同一天再排一道新的——那既违反「一节课一天一个练习」，也像在追着人催。
SELECT_TAKEN_LESSON_DAYS = text(
    """
    SELECT e.lesson_id, spi.plan_date
    FROM study_plan_items spi
    JOIN exercises e ON e.id = spi.target_id
    WHERE spi.user_id = :user_id AND spi.week_start = :week_start
      AND spi.kind = 'exercise'
      AND spi.status IN ('done', 'skipped')
    """
)

SELECT_DAY_EXERCISE_HISTORY = text(
    """
    SELECT plan_date, count(*) AS items
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
      AND kind = 'exercise'
      AND status IN ('done', 'skipped')
    GROUP BY plan_date
    """
)

# The exercise catalogue the plan may point at: published, not soft-deleted, of a
# published lesson, and never one this learner already passed. Ordered so the
# generator takes the smallest order_index first (R10 is deterministic).
SELECT_SCHEDULEABLE_EXERCISES = text(
    """
    SELECT e.id, e.lesson_id, e.code, e.title, e.order_index, e.estimated_minutes,
           l.title AS lesson_title, s.code AS skill_code, s.name_zh AS skill_name
    FROM exercises e
    JOIN lessons l ON l.id = e.lesson_id
    LEFT JOIN skills s ON s.id = l.skill_id
    WHERE e.status = 'published' AND e.deleted_at IS NULL
      AND l.status = 'published' AND l.deleted_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM submissions sub
          WHERE sub.user_id = :user_id AND sub.exercise_id = e.id
            AND sub.is_passed IS TRUE
      )
    ORDER BY e.lesson_id, e.order_index, e.id
    """
)

# R12: the mistake book rows that come due inside this week window. Ordered like
# the review API (next_review_on, id) so a regeneration picks the same rows in the
# same order; an exercise that is no longer published is not scheduled.
SELECT_DUE_REVIEWS = text(
    """
    SELECT r.id AS review_item_id, r.exercise_id, r.next_review_on,
           r.streak, r.interval_days, e.title AS exercise_title,
           sk.code AS skill_code
    FROM review_items r
    JOIN exercises e ON e.id = r.exercise_id
    LEFT JOIN lessons l ON l.id = e.lesson_id
    LEFT JOIN skills sk ON sk.id = l.skill_id
    WHERE r.user_id = :user_id
      AND r.status = 'pending'
      AND r.next_review_on BETWEEN :today AND :week_end
      AND e.status = 'published' AND e.deleted_at IS NULL
    ORDER BY r.next_review_on, r.id
    """
)

# R12: what this week already carries: a day holding a review row is full (the cap
# is one), and an exercise already planned this week is never planned twice.
SELECT_WEEK_REVIEWS = text(
    """
    SELECT s.plan_date, s.target_id, s.planned_minutes,
           e.title AS exercise_title, sk.code AS skill_code
    FROM study_plan_items s
    LEFT JOIN exercises e ON e.id = s.target_id
    LEFT JOIN lessons l ON l.id = e.lesson_id
    LEFT JOIN skills sk ON sk.id = l.skill_id
    WHERE s.user_id = :user_id AND s.week_start = :week_start
      AND s.kind = 'review' AND s.status <> 'expired'
    ORDER BY s.plan_date, s.id
    """
)

# R11: the service-side half of the target check. The trigger is the database's
# half; this one refuses the batch before a single row is written.
TARGET_EXISTS_SQL = {
    PLAN_KIND_LESSON: text("SELECT id FROM lessons WHERE id = ANY(:ids)").bindparams(
        bindparam("ids", type_=ARRAY(BigInteger))
    ),
    PLAN_KIND_EXERCISE: text("SELECT id FROM exercises WHERE id = ANY(:ids)").bindparams(
        bindparam("ids", type_=ARRAY(BigInteger))
    ),
    # R12: a review row's target is an exercise as well. The trigger from 0007
    # only validates lesson/exercise, so this check is the review kind's only
    # guard - it runs before the batch is written, exactly like the other two.
    PLAN_KIND_REVIEW: text("SELECT id FROM exercises WHERE id = ANY(:ids)").bindparams(
        bindparam("ids", type_=ARRAY(BigInteger))
    ),
}

SELECT_EXERCISE_TITLE = text("SELECT title AS exercise_title FROM exercises WHERE id = :target_id")

SELECT_ITEM_FOR_UPDATE = text(
    """
    SELECT id, week_start, plan_date, kind, target_id, planned_minutes, status,
           rationale, dedupe_key, updated_at
    FROM study_plan_items
    WHERE id = :item_id AND user_id = :user_id
    """
)

UPDATE_ITEM_STATUS = text(
    """
    UPDATE study_plan_items
    SET status = :status, updated_at = now()
    WHERE id = :item_id AND user_id = :user_id AND status = 'scheduled'
    RETURNING id, week_start, plan_date, kind, target_id, planned_minutes, status,
              rationale, dedupe_key, updated_at
    """
)


def _stage_suggestion(level: int, state: str) -> str:
    if state == "requested_verification":
        return "已提交待核验：暂按 L0 安排投入，等待核验结果"
    if state == "unassessed":
        return "尚未评估：先完成 20 题诊断确认起点"
    if state == "assessed_below_threshold":
        return "已测未达 L1 门槛：先补本阶段基础，再重测该域"
    if level >= 2:
        return "已达到 L2：用一个可展示的小项目巩固，保持当前投入"
    return "已到 L1：完成本阶段练习并读通报错，冲刺 L2"


def _stage_label(order: int, name: str) -> str:
    return f"路线 A 阶段 {order}（{name}）"


def _level_label(level: int, state: str) -> str:
    """The level text a rationale carries, never invented when unassessed."""
    if state == "unassessed":
        return "L0（尚未评估）"
    if state == "requested_verification":
        return "L0（待核验）"
    if state == "assessed_below_threshold":
        return "L0（已测未达 L1）"
    return f"L{level}"


async def _require_confirmed_timezone(
    session: AsyncSession, user_id: int
) -> dict[str, object]:
    """409 until the user confirms its timezone: no local-calendar derivation before that.

    显式接收 user_id：路由先用 users.get_single_user 解析出 id，测试可以传入自建用户，
    计划生成因此不再隐式依赖「唯一那个用户」。
    """
    user = await users.get_user(session, user_id)
    if user["timezone_source"] != "user_confirmed":
        raise ApiError(
            409,
            CONFLICT,
            "请先在档案页确认时区，确认后才能查看本周计划预览",
            {"field": "timezone_confirmed", "reason": "timezone_not_confirmed"},
        )
    return user


async def _week_start(session: AsyncSession, timezone_name: str) -> date:
    return (await session.execute(SELECT_WEEK_START, {"timezone": timezone_name})).scalar_one()


async def _local_today(session: AsyncSession, timezone_name: str) -> date:
    return (await session.execute(SELECT_LOCAL_TODAY, {"timezone": timezone_name})).scalar_one()


def _study_dates(monday: date, study_days: list[int]) -> list[date]:
    """study_days (1=Monday … 7=Sunday) resolved inside the user's local week."""
    return [monday + timedelta(days=day - 1) for day in sorted(set(study_days))]


def _candidate_dates(monday: date, study_days: list[int], today: date) -> list[date]:
    """R7: the study days still ahead - [today_local, week_end] only.

    A date that has already passed never receives a new scheduled row; its
    done/skipped rows stay exactly as they are and are reported as history.
    """
    week_end = monday + timedelta(days=WEEK_LENGTH_DAYS - 1)
    return [
        plan_date
        for plan_date in _study_dates(monday, study_days)
        if today <= plan_date <= week_end
    ]


async def _settled_days(
    session: AsyncSession, user_id: int, monday: date
) -> dict[date, tuple[int, int]]:
    """plan_date -> (settled minutes, settled lesson rows) of the done/skipped history.

    Minutes are summed over every kind (an exercise spends the day's budget too),
    the row count only over lessons: the 3-per-day cap is a lesson cap, and R10
    counts exercise rows on its own.
    """
    rows = (
        (
            await session.execute(
                SELECT_DAY_HISTORY, {"user_id": user_id, "week_start": monday}
            )
        )
        .mappings()
        .all()
    )
    return {
        row["plan_date"]: (int(row["minutes"]), int(row["lesson_items"]))
        for row in rows
    }


async def _settled_targets(session: AsyncSession, user_id: int, monday: date) -> set[int]:
    """Lesson ids whose week row is already done/skipped: not planned again."""
    return {
        int(target)
        for target in (
            await session.execute(
                SELECT_SETTLED_TARGETS, {"user_id": user_id, "week_start": monday}
            )
        )
        .scalars()
        .all()
    }


async def _settled_exercise_targets(
    session: AsyncSession, user_id: int, monday: date
) -> set[int]:
    """Exercise ids whose week row is already done/skipped: never planned twice."""
    return {
        int(target)
        for target in (
            await session.execute(
                SELECT_SETTLED_EXERCISE_TARGETS, {"user_id": user_id, "week_start": monday}
            )
        )
        .scalars()
        .all()
    }


async def _taken_lesson_days(
    session: AsyncSession, user_id: int, monday: date
) -> set[tuple[int, date]]:
    """(lesson_id, plan_date) pairs that already hold an exercise row, any status."""
    rows = (
        await session.execute(
            SELECT_TAKEN_LESSON_DAYS, {"user_id": user_id, "week_start": monday}
        )
    ).mappings().all()
    return {(int(row["lesson_id"]), row["plan_date"]) for row in rows}


async def _settled_exercise_days(
    session: AsyncSession, user_id: int, monday: date
) -> dict[date, int]:
    """plan_date -> exercise rows already settled that day (they spend the cap)."""
    rows = (
        (
            await session.execute(
                SELECT_DAY_EXERCISE_HISTORY, {"user_id": user_id, "week_start": monday}
            )
        )
        .mappings()
        .all()
    )
    return {row["plan_date"]: int(row["items"]) for row in rows}


async def _due_reviews(
    session: AsyncSession, user_id: int, today: date, week_end: date
) -> list[dict[str, object]]:
    """R12 candidates: pending mistake-book rows due inside [today, week_end]."""
    rows = (
        (await session.execute(
            SELECT_DUE_REVIEWS, {"user_id": user_id, "today": today, "week_end": week_end}
        ))
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def _week_reviews(
    session: AsyncSession, user_id: int, monday: date
) -> list[dict[str, object]]:
    """This week's still-open review rows, in plan order.

    They are re-emitted by the review pass (not merely remembered): a regeneration
    has to keep their dedupe_key in this run's keep set, otherwise EXPIRE_STALE_ITEMS
    would retire a review the learner still owes and the next run would plan it
    again on another day - the plan would oscillate between two states.
    """
    rows = (
        (await session.execute(SELECT_WEEK_REVIEWS, {"user_id": user_id, "week_start": monday}))
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def scheduleable_exercises(
    session: AsyncSession, user_id: int
) -> list[dict[str, object]]:
    """Published exercises of published lessons this learner has not passed yet."""
    rows = (
        (await session.execute(SELECT_SCHEDULEABLE_EXERCISES, {"user_id": user_id}))
        .mappings()
        .all()
    )
    return [
        {
            "id": int(row["id"]),
            "lesson_id": int(row["lesson_id"]),
            "code": str(row["code"]),
            "title": str(row["title"]),
            "order_index": int(row["order_index"]),
            "estimated_minutes": int(row["estimated_minutes"]),
            "lesson_title": str(row["lesson_title"]),
            "skill_code": row["skill_code"],
            "skill_name": str(row["skill_name"] or ""),
        }
        for row in rows
    ]


def exercise_cap_for_levels(levels: list[int]) -> int:
    """R10: the daily exercise cap that follows from the six domain levels.

    The average decides: <= 1 -> one exercise a day, >= 2 -> two. An average
    strictly between the two has no rule of its own, so it keeps the stricter
    cap of one - the generator raises the cap only on clear evidence.
    """
    if not levels:
        return MAX_EXERCISES_PER_DAY_LOW
    average = sum(int(level) for level in levels) / len(levels)
    if average >= EXERCISE_CAP_LEVEL_THRESHOLD:
        return MAX_EXERCISES_PER_DAY_HIGH
    return MAX_EXERCISES_PER_DAY_LOW


async def ensure_targets_exist(
    session: AsyncSession, items: list[dict[str, object]]
) -> None:
    """R11: refuse a batch whose target_id does not exist for its own kind.

    The trigger repeats this inside the database, so a caller that skips this
    check still cannot store a dangling target; this one answers 422 with the
    offending ids instead of a 23503. A kind with no known target table (the
    generator never writes one) is refused here as well.
    """
    wanted: dict[str, set[int]] = {}
    for item in items:
        wanted.setdefault(str(item["kind"]), set()).add(int(item["target_id"]))
    for kind in sorted(wanted):
        statement = TARGET_EXISTS_SQL.get(kind)
        if statement is None:
            raise validation_error(
                f"计划项的 kind 只能是 lesson、exercise 或 review：{kind}",
                "kind",
                "unsupported_kind",
                kind=kind,
            )
        existing = {
            int(row)
            for row in (
                await session.execute(statement, {"ids": sorted(wanted[kind])})
            )
            .scalars()
            .all()
        }
        missing = sorted(wanted[kind] - existing)
        if missing:
            raise validation_error(
                f"计划项的 target_id 必须指向真实存在的 {kind} 行",
                "target_id",
                "target_not_found",
                kind=kind,
                missing=missing,
            )


async def _week_days(
    session: AsyncSession, study_days: list[int], daily_minutes: int, timezone_name: str
) -> list[dict[str, object]]:
    """This week's study dates, derived from users.timezone and nothing else."""
    monday = await _week_start(session, timezone_name)
    return [
        {"date": plan_date.isoformat(), "minutes": daily_minutes}
        for plan_date in _study_dates(monday, study_days)
    ]


async def build_preview(session: AsyncSession) -> dict[str, object]:
    user = await _require_confirmed_timezone(session, await _single_user_id(session))
    user_id = int(user["id"])
    timezone_name = str(user["timezone"])
    profile = await users.get_profile(session, user_id)
    resolved = await levels.resolve_current_levels(session, user_id)
    skill_rows = await catalog.list_domain_skills(session)
    names = {str(row["code"]): str(row["name_zh"]) for row in skill_rows}
    orders = {str(row["code"]): int(row["order_index"]) for row in skill_rows}

    days = await _week_days(
        session,
        [int(day) for day in profile["study_days"]],
        int(profile["daily_minutes"]),
        timezone_name,
    )
    weekly_minutes = sum(int(day["minutes"]) for day in days)

    stages: list[dict[str, object]] = []
    focus_stage: str | None = None
    for row in resolved:
        code = str(row["skill_code"])
        level = int(row["level"])
        state = str(row["state"])
        stages.append(
            {
                "skill_code": code,
                "name_zh": names.get(code, code),
                "level": level,
                "state": state,
                "suggestion": _stage_suggestion(level, state),
            }
        )
        if focus_stage is None and level < 2:
            focus_stage = code

    if focus_stage is None:
        advice = f"六个阶段均已达到 L2；本周 {len(days)} 天、每天 {profile['daily_minutes']} 分钟，共 {weekly_minutes} 分钟，建议进入项目阶段"
    else:
        advice = (
            f"{_stage_label(orders.get(focus_stage, 0), names.get(focus_stage, focus_stage))}，"
            f"本周 {len(days)} 天，每天 {profile['daily_minutes']} 分钟，共 {weekly_minutes} 分钟"
        )

    return {
        "computed": True,
        "persisted": False,
        "days": days,
        "note": PREVIEW_NOTE,
        "weekly_minutes": weekly_minutes,
        "timezone": timezone_name,
        "focus_stage": focus_stage,
        "advice": advice,
        "stages": stages,
    }


def _dedupe_key(monday: date, plan_date: date, kind: str, target_id: int) -> str:
    """DATABASE.md 4.14: '{week_start}|{plan_date}|{kind}|{target_id}'."""
    return f"{monday.isoformat()}|{plan_date.isoformat()}|{kind}|{target_id}"


def _rationale(
    plan_date: date,
    daily_minutes: int,
    used_minutes: int,
    lesson: dict[str, object],
    level_label: str,
) -> str:
    """R5: every row can be explained - level plus that day's budget."""
    return (
        f"{plan_date.isoformat()} 当日可用 {daily_minutes} 分钟（已排 {used_minutes} 分钟）-> "
        f"阶段 {lesson['stage']}·第 {lesson['order_index']} 课《{lesson['title']}》"
        f"{lesson['estimated_minutes']} 分钟，{lesson['skill_name']} 当前 {level_label}"
    )


def _schedule(
    candidates: list[dict[str, object]],
    dates: list[date],
    daily_minutes: int,
    level_labels: dict[str, str],
    monday: date,
    settled: dict[date, tuple[int, int]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Fill the days still ahead greedily in curriculum order, one budget each.

    A day may only spend what the done/skipped rows have left over (R8), and
    those settled rows also count toward MAX_ITEMS_PER_DAY so a day never ends
    up carrying more than the daily cap in total.
    """
    items: list[dict[str, object]] = []
    unscheduled: list[dict[str, object]] = []
    defer_note: str | None = None
    cursor = 0
    for plan_date in dates:
        history_minutes, history_lessons = settled.get(plan_date, (0, 0))
        used = 0
        count = history_lessons
        while cursor < len(candidates) and count < MAX_ITEMS_PER_DAY:
            lesson = candidates[cursor]
            minutes = int(lesson["estimated_minutes"])
            if not MIN_PLANNED_MINUTES <= minutes <= MAX_PLANNED_MINUTES:
                # A plan row's CHECK is 15-480: report it instead of writing a bad row.
                unscheduled.append(
                    {
                        "lesson_id": int(lesson["id"]),
                        "code": str(lesson["code"]),
                        "title": str(lesson["title"]),
                        "estimated_minutes": minutes,
                        "reason": (
                            f"预计时长 {minutes} 分钟不在计划项允许的 "
                            f"{MIN_PLANNED_MINUTES}–{MAX_PLANNED_MINUTES} 分钟内"
                        ),
                    }
                )
                cursor += 1
                continue
            remaining = daily_minutes - history_minutes - used
            if minutes > remaining:
                defer_note = (
                    f"{plan_date.isoformat()} 当日剩余 {remaining} 分钟不足本节 {minutes} 分钟"
                )
                break
            rationale = _rationale(
                plan_date,
                daily_minutes,
                history_minutes + used,
                lesson,
                level_labels.get(str(lesson["skill_code"]), "L0（尚未评估）"),
            )
            if defer_note:
                rationale = f"{defer_note}，顺延到 {plan_date.isoformat()}；{rationale}"
            items.append(
                {
                    "week_start": monday,
                    "plan_date": plan_date,
                    "kind": PLAN_KIND_LESSON,
                    "target_id": int(lesson["id"]),
                    "planned_minutes": minutes,
                    "rationale": rationale[:RATIONALE_MAX_LENGTH],
                    "dedupe_key": _dedupe_key(
                        monday, plan_date, PLAN_KIND_LESSON, int(lesson["id"])
                    ),
                }
            )
            used += minutes
            count += 1
            cursor += 1
            defer_note = None
        if cursor < len(candidates):
            if count >= MAX_ITEMS_PER_DAY:
                defer_note = f"{plan_date.isoformat()} 已排满每日 {MAX_ITEMS_PER_DAY} 项上限"
            elif history_minutes + used >= daily_minutes:
                defer_note = f"{plan_date.isoformat()} 当日 {daily_minutes} 分钟已排满"

    while cursor < len(candidates):
        lesson = candidates[cursor]
        unscheduled.append(
            {
                "lesson_id": int(lesson["id"]),
                "code": str(lesson["code"]),
                "title": str(lesson["title"]),
                "estimated_minutes": int(lesson["estimated_minutes"]),
                "reason": (
                    f"本周 {len(dates)} 个学习日、每天 {daily_minutes} 分钟的容量无法容纳本节"
                ),
            }
        )
        cursor += 1
    return items, unscheduled


def _exercise_rationale(
    plan_date: date,
    daily_minutes: int,
    used_minutes: int,
    exercise: dict[str, object],
    planned_minutes: int,
    level_label: str,
    daily_cap: int,
) -> str:
    """R5 for an exercise row: the day's budget, the cap and the level, in one line."""
    return (
        f"{plan_date.isoformat()} 当日可用 {daily_minutes} 分钟（已排 {used_minutes} 分钟）-> "
        f"练习《{exercise['title']}》{planned_minutes} 分钟"
        f"（预计 {exercise['estimated_minutes']} 分钟），"
        f"{exercise['skill_name'] or '本课'} 当前 {level_label}，每日练习上限 {daily_cap}"
    )[:RATIONALE_MAX_LENGTH]


def _schedule_exercises(
    lesson_items: list[dict[str, object]],
    dates: list[date],
    daily_minutes: int,
    level_labels: dict[str, str],
    monday: date,
    settled: dict[date, tuple[int, int]],
    settled_exercise_days: dict[date, int],
    settled_exercise_ids: set[int],
    taken_lesson_days: set[tuple[int, date]],
    exercises_by_lesson: dict[int, list[dict[str, object]]],
    daily_cap: int,
) -> list[dict[str, object]]:
    """R10: one exercise per lesson already placed that day, inside its budget.

    The list also carries the review rows of R12: they spend the day's minutes but
    take no lesson slot, so they only ever shrink what is left for a new exercise.
    The lesson pass runs first and is untouched, so an exercise never displaces a
    lesson. For every lesson placed on a day the generator takes that lesson's
    unfinished exercise with the smallest order_index and adds it only when all
    three hold: the day's exercise cap is not spent yet (settled exercise rows
    count against it), the row's planned_minutes fits in what the day has left
    (R8: daily_minutes minus settled history minus the lessons already placed),
    and that exercise is not already settled this week. A lesson that already holds an
    exercise row on that day - in any status, skipped included - is passed over, so a
    skip never turns into a second exercise from the same lesson on the same day.

    planned_minutes is max(MIN_PLANNED_MINUTES, estimated_minutes): the table's
    CHECK is 15-480, so a 10-minute exercise is reserved as 15 minutes and the
    day is charged the reserved value - the budget can only shrink, never grow.
    """
    by_date: dict[date, list[dict[str, object]]] = {}
    used_by_date: dict[date, int] = {}
    for item in lesson_items:
        item_date = item["plan_date"]
        used_by_date[item_date] = used_by_date.get(item_date, 0) + int(item["planned_minutes"])
        # R12: 复习行也在这份列表里，但它只花分钟，不占"一节课一个练习"的槽位。
        if item["kind"] == PLAN_KIND_LESSON:
            by_date.setdefault(item_date, []).append(item)  # type: ignore[arg-type]
    planned_ids: set[int] = set()
    items: list[dict[str, object]] = []
    for plan_date in dates:
        lessons = by_date.get(plan_date, [])
        if not lessons:
            continue
        history_minutes, _history_items = settled.get(plan_date, (0, 0))
        used = used_by_date.get(plan_date, 0)
        placed = settled_exercise_days.get(plan_date, 0)
        for lesson in lessons:
            if placed >= daily_cap:
                break
            # R10 严格读法：这节课当天已经有练习行（任何状态）就不再排第二道。
            if (int(lesson["target_id"]), plan_date) in taken_lesson_days:
                continue
            options = exercises_by_lesson.get(int(lesson["target_id"]), [])
            candidate = next(
                (
                    option
                    for option in options
                    if int(option["id"]) not in settled_exercise_ids
                    and int(option["id"]) not in planned_ids
                ),
                None,
            )
            if candidate is None:
                continue
            minutes = max(MIN_PLANNED_MINUTES, int(candidate["estimated_minutes"]))
            remaining = daily_minutes - history_minutes - used
            if minutes > remaining:
                # The ordered exercise does not fit: taking a cheaper one behind it
                # would break "smallest order_index first", so the day gets none.
                continue
            items.append(
                {
                    "week_start": monday,
                    "plan_date": plan_date,
                    "kind": PLAN_KIND_EXERCISE,
                    "target_id": int(candidate["id"]),
                    "planned_minutes": minutes,
                    "rationale": _exercise_rationale(
                        plan_date,
                        daily_minutes,
                        history_minutes + used,
                        candidate,
                        minutes,
                        level_labels.get(str(candidate["skill_code"]), "L0（尚未评估）"),
                        daily_cap,
                    ),
                    "dedupe_key": _dedupe_key(
                        monday, plan_date, PLAN_KIND_EXERCISE, int(candidate["id"])
                    ),
                }
            )
            used += minutes
            placed += 1
            planned_ids.add(int(candidate["id"]))
    return items


def _review_rationale(
    plan_date: date,
    daily_minutes: int,
    used_minutes: int,
    exercise_title: object,
    level_label: str,
    detail: str | None = None,
) -> str:
    """R5 for a review row: the day's budget and the level, plus the due-day detail.

    detail is present for a row planned in this run (original due day, streak,
    interval) and absent for one re-emitted from the week - the level and the
    budget are on every row either way, so R5 holds for both.
    """
    assert_detail = f"（{detail}）" if detail else ""
    return (
        f"{plan_date.isoformat()} 当日可用 {daily_minutes} 分钟（已排 {used_minutes} 分钟）-> "
        f"复习错题《{exercise_title}》{REVIEW_PLANNED_MINUTES} 分钟{assert_detail}，"
        f"{level_label}，每日复习上限 {MAX_REVIEWS_PER_DAY}"
    )[:RATIONALE_MAX_LENGTH]


def _schedule_reviews(
    placed_items: list[dict[str, object]],
    dates: list[date],
    daily_minutes: int,
    level_labels: dict[str, str],
    monday: date,
    settled: dict[date, tuple[int, int]],
    candidates: list[dict[str, object]],
    existing_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """R12: one review a day, only with 15 minutes left, never the same exercise twice.

    The pass runs after lessons (R10) but **before** new exercises: a due review
    outranks a brand new exercise for the same slot, because re-testing a question
    the learner already got wrong is worth more than adding another one. It still
    never displaces a lesson, and the day's budget (R1/R8) always wins over a
    review: a row that no longer fits is not re-emitted and is retired as expired.

    A review row already planned this week is re-emitted with the same values, so
    its dedupe_key stays in this run's keep set (otherwise EXPIRE_STALE_ITEMS would
    retire a review the learner still owes and the plan would oscillate). Its day
    then counts as taken (MAX_REVIEWS_PER_DAY is one) and its exercise as used.
    """
    used_by_date: dict[date, int] = {}
    for item in placed_items:
        item_date = item["plan_date"]
        used_by_date[item_date] = used_by_date.get(item_date, 0) + int(item["planned_minutes"])
    items: list[dict[str, object]] = []
    review_days: set[date] = set()
    taken: set[int] = set()
    for row in existing_rows:
        plan_date = row["plan_date"]
        if plan_date not in dates or row["exercise_title"] is None:
            # R7/R2: 已过去的日期、非学习日或目标已不可读的行不再保留；它的 key 不在
            # keep_keys 里，EXPIRE_STALE_ITEMS 会把它作废（作废不是删除）。
            continue
        history_minutes = settled.get(plan_date, (0, 0))[0]
        used = used_by_date.get(plan_date, 0) + sum(
            int(item["planned_minutes"]) for item in items if item["plan_date"] == plan_date
        )
        if daily_minutes - history_minutes - used < int(row["planned_minutes"]):
            # R1 高于复习：额度变小（或课程变多）时这次不再保留这一行，按"到期且放得下"
            # 重新找日子；否则当日总分钟会超支。
            continue
        items.append(
            {
                "week_start": monday,
                "plan_date": plan_date,
                "kind": PLAN_KIND_REVIEW,
                "target_id": int(row["target_id"]),
                "planned_minutes": int(row["planned_minutes"]),
                "rationale": _review_rationale(
                    plan_date,
                    daily_minutes,
                    history_minutes + used,
                    row["exercise_title"],
                    level_labels.get(str(row["skill_code"]), "L0（尚未评估）"),
                ),
                "dedupe_key": _dedupe_key(
                    monday, plan_date, PLAN_KIND_REVIEW, int(row["target_id"])
                ),
            }
        )
        review_days.add(plan_date)
        taken.add(int(row["target_id"]))

    cursor = 0
    for plan_date in dates:
        if plan_date in review_days:
            continue
        while cursor < len(candidates) and int(candidates[cursor]["exercise_id"]) in taken:
            cursor += 1
        if cursor >= len(candidates):
            break
        history_minutes = settled.get(plan_date, (0, 0))[0]
        used = used_by_date.get(plan_date, 0)
        if daily_minutes - history_minutes - used < REVIEW_PLANNED_MINUTES:
            # R8 again: the day's minutes are already spent by lessons.
            continue
        review = candidates[cursor]
        items.append(
            {
                "week_start": monday,
                "plan_date": plan_date,
                "kind": PLAN_KIND_REVIEW,
                "target_id": int(review["exercise_id"]),
                "planned_minutes": REVIEW_PLANNED_MINUTES,
                "rationale": _review_rationale(
                    plan_date,
                    daily_minutes,
                    history_minutes + used,
                    review["exercise_title"],
                    level_labels.get(str(review["skill_code"]), "L0（尚未评估）"),
                    (
                        f"原定复习日 {review['next_review_on'].isoformat()}，"
                        f"连续通过 {review['streak']} 次，当前间隔 {review['interval_days']} 天"
                    ),
                ),
                "dedupe_key": _dedupe_key(
                    monday, plan_date, PLAN_KIND_REVIEW, int(review["exercise_id"])
                ),
            }
        )
        taken.add(int(review["exercise_id"]))
        cursor += 1
    return items


def _day_payload(plan_date: date, day_items: list[dict[str, object]]) -> dict[str, object]:
    """One day of the plan, with what is left to do kept apart from history.

    scheduled_minutes is the work still ahead, history_minutes the done/skipped
    rows of that day, and total_minutes their sum - the number that must stay
    within daily_minutes. 'planned_minutes' remains as an alias of
    total_minutes for the existing client.
    """
    scheduled_minutes = sum(
        int(item["planned_minutes"])
        for item in day_items
        if item["status"] == PLAN_STATUS_SCHEDULED
    )
    history_minutes = sum(
        int(item["planned_minutes"])
        for item in day_items
        if item["status"] in PLAN_STATUS_TERMINAL
    )
    total_minutes = scheduled_minutes + history_minutes
    return {
        "plan_date": plan_date,
        "weekday": plan_date.isoweekday(),
        "planned_minutes": total_minutes,
        "scheduled_minutes": scheduled_minutes,
        "history_minutes": history_minutes,
        "total_minutes": total_minutes,
        "items": day_items,
    }


def _target_fields(
    kind: str, target_id: int, lesson_title: object, exercise_title: object
) -> dict[str, object]:
    """Sprint 6: what the client renders for this row without a second request.

    A lesson links to /learn/{id} and an exercise to /practice/{id}; a kind with
    neither (the generator writes none today) resolves to null rather than to a
    guessed route.
    """
    if kind == PLAN_KIND_LESSON:
        return {"target_title": lesson_title, "target_href": f"/learn/{target_id}"}
    if kind in (PLAN_KIND_EXERCISE, PLAN_KIND_REVIEW):
        # 一条复习项指向的就是那道练习：客户端的入口与练习一致。
        return {"target_title": exercise_title, "target_href": f"/practice/{target_id}"}
    return {"target_title": None, "target_href": None}


def _plan_payload(
    monday: date,
    timezone_name: str,
    study_days: list[int],
    daily_minutes: int,
    rows: list[dict[str, object]],
    today: date,
) -> dict[str, object]:
    """Group persisted rows by plan_date; empty study days are kept for the UI.

    'expired' rows are retired tasks: they stay in the table as history but are
    not part of the plan, so they never count against R1/R2 in this payload.
    Each day keeps the work still ahead (scheduled_minutes) apart from the
    settled history (history_minutes) so the UI never adds them up as one number.
    """
    expired_items = sum(1 for row in rows if row["status"] == PLAN_STATUS_EXPIRED)
    by_date: dict[date, list[dict[str, object]]] = {}
    for row in rows:
        if row["status"] == PLAN_STATUS_EXPIRED:
            continue
        by_date.setdefault(row["plan_date"], []).append(
            {
                "id": int(row["id"]),
                "kind": str(row["kind"]),
                "target_id": int(row["target_id"]),
                "lesson_code": row["lesson_code"],
                "lesson_title": row["lesson_title"],
                **_target_fields(
                    str(row["kind"]),
                    int(row["target_id"]),
                    row["lesson_title"],
                    row["exercise_title"],
                ),
                "planned_minutes": int(row["planned_minutes"]),
                "status": str(row["status"]),
                "rationale": str(row["rationale"]),
                "dedupe_key": str(row["dedupe_key"]),
            }
        )
    # Every study day of the week is reported (empty days included), plus any row
    # stored on a date the profile no longer marks as a study day: a defensive
    # branch that reports such a row instead of hiding it.
    plan_dates = set(_study_dates(monday, study_days)) | set(by_date)
    days = [
        _day_payload(plan_date, by_date.get(plan_date, [])) for plan_date in sorted(plan_dates)
    ]

    all_items = [item for day in days for item in day["items"]]
    scheduled_items = sum(1 for item in all_items if item["status"] == PLAN_STATUS_SCHEDULED)
    history_items = sum(1 for item in all_items if item["status"] in PLAN_STATUS_TERMINAL)
    return {
        "week_start": monday,
        "week_end": monday + timedelta(days=WEEK_LENGTH_DAYS - 1),
        "today": today,
        "timezone": timezone_name,
        "daily_minutes": daily_minutes,
        "study_days": sorted(set(study_days)),
        "weekly_planned_minutes": sum(int(item["planned_minutes"]) for item in all_items),
        "items_total": len(all_items),
        "scheduled_items": scheduled_items,
        "history_items": history_items,
        "expired_items": expired_items,
        "lesson_items": sum(1 for item in all_items if item["kind"] == PLAN_KIND_LESSON),
        # Serialised explicitly so R1/AC-S2-01 can be asserted from the response too.
        "exercise_items": sum(1 for item in all_items if item["kind"] == "exercise"),
        "review_items": sum(1 for item in all_items if item["kind"] == "review"),
        "days": days,
    }


async def _load_rows(
    session: AsyncSession, user_id: int, monday: date
) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in (
            await session.execute(
                SELECT_WEEK_PLAN, {"user_id": user_id, "week_start": monday}
            )
        )
        .mappings()
        .all()
    ]


async def _single_user_id(session: AsyncSession) -> int:
    """单用户路由的唯一入口：把「当前用户是谁」收敛成一次解析。"""
    return int((await users.get_single_user(session))["id"])


async def read_plan(session: AsyncSession) -> dict[str, object]:
    """The persisted plan of this week. Never writes and never generates."""
    user = await _require_confirmed_timezone(session, await _single_user_id(session))
    user_id = int(user["id"])
    timezone_name = str(user["timezone"])
    profile = await users.get_profile(session, user_id)
    study_days = [int(day) for day in profile["study_days"]]
    daily_minutes = int(profile["daily_minutes"])
    monday = await _week_start(session, timezone_name)
    today = await _local_today(session, timezone_name)
    rows = await _load_rows(session, user_id, monday)
    return _plan_payload(monday, timezone_name, study_days, daily_minutes, rows, today)


async def generate_plan(
    session: AsyncSession, *, user_id: int, today_override: date | None = None
) -> dict[str, object]:
    """Generate (or refresh) the plan of one user and persist it. Idempotent per week.

    user_id 是显式参数而不是在内部解析：路由传当前（唯一）用户，测试传自建用户，
    这样计划相关用例可以自带数据、不再随种子用户的真实学习进度漂移。

    today_override pins the local calendar day so a test can reproduce "first
    generation on a Tuesday / on a Saturday" at any real date; production reads
    users.timezone and passes nothing.
    """
    user = await _require_confirmed_timezone(session, user_id)
    timezone_name = str(user["timezone"])
    profile = await users.get_profile(session, user_id)
    study_days = [int(day) for day in profile["study_days"]]
    daily_minutes = int(profile["daily_minutes"])
    monday = await _week_start(session, timezone_name)
    today = today_override or await _local_today(session, timezone_name)
    dates = _candidate_dates(monday, study_days, today)

    resolved = await levels.resolve_current_levels(session, user_id)
    level_labels = {
        str(row["skill_code"]): _level_label(int(row["level"]), str(row["state"]))
        for row in resolved
    }
    settled = await _settled_days(session, user_id, monday)
    settled_targets = await _settled_targets(session, user_id, monday)
    candidates = [
        lesson
        for lesson in await lessons_service.scheduleable_lessons(session, user_id)
        if int(lesson["id"]) not in settled_targets
    ]
    items, unscheduled = _schedule(
        candidates, dates, daily_minutes, level_labels, monday, settled
    )

    # R12 必须排在 R10 之前：复习优先于新练习。
    # 曾经的顺序（课程 -> 练习 -> 复习）实测导致 review 恒为 0：每天 30 分钟课
    # 加 15 分钟练习正好等于 45 分钟额度，复习永远抢不到余量。而「把答错的题
    # 过几天再考一次」对新手的价值高于再做一道新题，所以先排复习、再由新练习占剩余额度。
    week_end = monday + timedelta(days=WEEK_LENGTH_DAYS - 1)
    items += _schedule_reviews(
        items,
        dates,
        daily_minutes,
        level_labels,
        monday,
        settled,
        await _due_reviews(session, user_id, today, week_end),
        await _week_reviews(session, user_id, monday),
    )

    # R10: exercises are the second pass over the same days, so a lesson (and now a
    # due review) is never displaced. The cap comes from the learner's own levels.
    daily_exercise_cap = exercise_cap_for_levels(
        [int(row["level"]) for row in resolved]
    )
    exercises_by_lesson: dict[int, list[dict[str, object]]] = {}
    for exercise in await scheduleable_exercises(session, user_id):
        exercises_by_lesson.setdefault(int(exercise["lesson_id"]), []).append(exercise)
    exercise_items = _schedule_exercises(
        items,
        dates,
        daily_minutes,
        level_labels,
        monday,
        settled,
        await _settled_exercise_days(session, user_id, monday),
        await _settled_exercise_targets(session, user_id, monday),
        await _taken_lesson_days(session, user_id, monday),
        exercises_by_lesson,
        daily_exercise_cap,
    )
    items += exercise_items

    # R11: refuse a batch with a dangling target before a single row is written.
    await ensure_targets_exist(session, items)

    params = [{**item, "user_id": user_id} for item in items]
    try:
        if params:
            await session.execute(UPSERT_PLAN_ITEM, params)
        # Retire tasks that are no longer part of this week (past day, non-study day,
        # lesson already completed, smaller budget). keep_keys is exactly this run's
        # target set - a stale 'expired' key is never kept alive - and done/skipped
        # rows are not touched at all.
        await session.execute(
            EXPIRE_STALE_ITEMS,
            {
                "user_id": user_id,
                "week_start": monday,
                "keep_keys": [str(item["dedupe_key"]) for item in items],
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    rows = await _load_rows(session, user_id, monday)
    payload = _plan_payload(monday, timezone_name, study_days, daily_minutes, rows, today)
    payload["generated"] = True
    payload["unscheduled"] = unscheduled
    return payload


SELECT_LESSON_LABEL = text(
    "SELECT code AS lesson_code, title AS lesson_title FROM lessons WHERE id = :target_id"
)


async def _target_label(
    session: AsyncSession, kind: str, target_id: int
) -> dict[str, object]:
    """The title/code of one item's target, read by kind (Sprint 6).

    A missing row is not an error here: the row is history and its label is
    simply absent - the item itself is still returned to the client.
    """
    label: dict[str, object] = {
        "lesson_code": None,
        "lesson_title": None,
        "exercise_title": None,
    }
    if kind == PLAN_KIND_LESSON:
        row = (
            (await session.execute(SELECT_LESSON_LABEL, {"target_id": target_id}))
            .mappings()
            .first()
        )
    elif kind in (PLAN_KIND_EXERCISE, PLAN_KIND_REVIEW):
        row = (
            (await session.execute(SELECT_EXERCISE_TITLE, {"target_id": target_id}))
            .mappings()
            .first()
        )
    else:
        row = None
    if row is not None:
        label.update(dict(row))
    return label


def _item_payload(
    row: dict[str, object], target: dict[str, object]
) -> dict[str, object]:
    return {
        "id": int(row["id"]),
        "week_start": row["week_start"],
        "plan_date": row["plan_date"],
        "kind": str(row["kind"]),
        "target_id": int(row["target_id"]),
        "lesson_code": target.get("lesson_code"),
        "lesson_title": target.get("lesson_title"),
        **_target_fields(
            str(row["kind"]),
            int(row["target_id"]),
            target.get("lesson_title"),
            target.get("exercise_title"),
        ),
        "planned_minutes": int(row["planned_minutes"]),
        "status": str(row["status"]),
        "rationale": str(row["rationale"]),
        "dedupe_key": str(row["dedupe_key"]),
        "updated_at": row["updated_at"],
    }


async def update_plan_item(
    session: AsyncSession, *, user_id: int, item_id: int, status: str
) -> dict[str, object]:
    """PATCH one plan item: scheduled -> done|skipped, and nothing else.

    A row that is already done, skipped or expired is final: a second PATCH is a
    409 PLAN_ITEM_LOCKED rather than a silent rewrite, so a finished day cannot
    be flipped by a stale tab. planned_minutes, plan_date, rationale and
    dedupe_key are never part of the SET list.
    """
    if status not in PLAN_STATUS_USER_SETTABLE:
        raise validation_error(
            "status 只允许 done 或 skipped",
            "status",
            "invalid_status",
            allowed=list(PLAN_STATUS_USER_SETTABLE),
            value=status,
        )
    row = (
        (await session.execute(SELECT_ITEM_FOR_UPDATE, {"item_id": item_id, "user_id": user_id}))
        .mappings()
        .first()
    )
    if row is None:
        raise ApiError(404, NOT_FOUND, "计划项不存在，或不属于当前用户")
    if row["status"] != PLAN_STATUS_SCHEDULED:
        raise ApiError(
            409,
            PLAN_ITEM_LOCKED,
            "该计划项已是终态（done/skipped/expired），不允许再次改写",
            {
                "field": "status",
                "reason": "plan_item_locked",
                "current_status": str(row["status"]),
            },
        )
    try:
        updated = (
            (
                await session.execute(
                    UPDATE_ITEM_STATUS,
                    {"item_id": item_id, "user_id": user_id, "status": status},
                )
            )
            .mappings()
            .first()
        )
        if updated is None:
            # Lost the race: another request settled this row first.
            await session.rollback()
            raise ApiError(
                409,
                PLAN_ITEM_LOCKED,
                "该计划项已被其他请求改写，请刷新后重试",
                {"field": "status", "reason": "plan_item_locked"},
            )
        target = await _target_label(session, str(updated["kind"]), int(updated["target_id"]))
        await session.commit()
    except ApiError:
        raise
    except Exception:
        await session.rollback()
        raise
    return _item_payload(dict(updated), target)


__all__ = [
    "build_preview",
    "ensure_targets_exist",
    "exercise_cap_for_levels",
    "generate_plan",
    "read_plan",
    "scheduleable_exercises",
    "update_plan_item",
]
