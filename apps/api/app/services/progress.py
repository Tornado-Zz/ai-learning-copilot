"""Progress overview and capstone readiness: real aggregation, no demo numbers.

v0.1.1 replaces the presentation placeholders with data, so nothing here carries
a hard-coded progress figure: every value is computed from this user's own rows,
and a user without rows gets an all-zero structure instead of an error.

Capstone readiness - the four frozen judgment criteria (v0.1.1):

1. lessons_completed: required = the published lesson total; actual =
   learning_progress rows of this user with status='completed' on a published
   lesson (a lesson outside the published catalogue is not a finished lesson).
2. exercises_passed: required = CAPSTONE_REQUIRED_EXERCISES_PASSED; actual =
   count(DISTINCT exercise_id) over this user's submissions where is_passed is
   true - the same exercise counts once, however many attempts it took.
3. domains_at_l2: required = CAPSTONE_REQUIRED_DOMAINS_AT_L2; actual = the domains
   whose resolved current level is >= 2 (the contract 3.3 resolution, so this
   number is the one the profile page shows, not a second opinion).
4. plan_items_done: required = CAPSTONE_REQUIRED_PLAN_ITEMS_DONE; actual =
   study_plan_items rows of this user with status='done', any week.

ready = every one of the four is met. A criterion that cannot be derived from a
real row does not exist here: the endpoint never invents progress.

Week semantics for GET /progress/overview: "this week" is the Monday of
users.timezone and comes from study_plan._week_start - the single definition the
plan generator already uses, so the dashboard and the plan cannot disagree.
plan.minutes_done sums planned_minutes of the done rows; plan.minutes_scheduled
sums planned_minutes of the rows still scheduled. A skipped or expired row was
planned and then not done, so it belongs to neither minute total.

activity is the last ACTIVITY_WINDOW_DAYS local days including today, one entry
per day in ascending order, missing days filled with 0 so the client can plot a
fixed-width window without filling gaps itself.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import levels, study_plan

# Frozen v0.1.1 thresholds - the contract's numbers, named instead of sprinkled.
CAPSTONE_REQUIRED_EXERCISES_PASSED = 6
CAPSTONE_REQUIRED_DOMAINS_AT_L2 = 3
CAPSTONE_REQUIRED_PLAN_ITEMS_DONE = 5
CAPSTONE_L2_LEVEL = 2
ACTIVITY_WINDOW_DAYS = 7
CAPSTONE_NOTE = (
    "作品提交与人工评审流程尚未实现（v0.1.x）；本页只展示由真实学习数据推导出的达标情况。"
)

# Lessons: the catalogue total is a scalar subquery, the rest is this user's own
# progress joined to the published catalogue only.
SELECT_LESSONS = text(
    """
    SELECT
        (SELECT count(*) FROM lessons l
          WHERE l.status = 'published' AND l.deleted_at IS NULL) AS total,
        count(*) FILTER (WHERE p.status = 'completed') AS completed,
        count(*) FILTER (WHERE p.status = 'in_progress') AS in_progress,
        COALESCE(sum(l.estimated_minutes) FILTER (WHERE p.status = 'completed'), 0)
            AS minutes_completed
    FROM learning_progress p
    JOIN lessons l ON l.id = p.lesson_id
    WHERE p.user_id = :user_id
      AND l.status = 'published' AND l.deleted_at IS NULL
    """
)

SELECT_PLAN = text(
    """
    SELECT
        count(*) FILTER (WHERE status = 'scheduled') AS scheduled,
        count(*) FILTER (WHERE status = 'done') AS done,
        count(*) FILTER (WHERE status = 'skipped') AS skipped,
        COALESCE(sum(planned_minutes) FILTER (WHERE status = 'done'), 0) AS minutes_done,
        COALESCE(sum(planned_minutes) FILTER (WHERE status = 'scheduled'), 0)
            AS minutes_scheduled
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
    """
)

SELECT_PRACTICE = text(
    """
    SELECT
        (SELECT count(*) FROM exercises e
          WHERE e.status = 'published' AND e.deleted_at IS NULL) AS exercises_total,
        count(*) AS submissions_total,
        count(DISTINCT exercise_id) AS exercises_attempted,
        count(DISTINCT exercise_id) FILTER (WHERE is_passed IS TRUE) AS exercises_passed
    FROM submissions
    WHERE user_id = :user_id
    """
)

SELECT_BY_EVIDENCE = text(
    """
    SELECT verification_method, count(*) AS submissions
    FROM submissions
    WHERE user_id = :user_id
    GROUP BY verification_method
    ORDER BY verification_method
    """
)

# One row per domain the user has any evidence for, carrying the row count and
# the level sum: the arithmetic mean of user_skill_levels.level is rebuilt from
# these two columns, so the whole capability block costs a single query plus the
# contract 3.3 resolution.
SELECT_CAPABILITY_ROWS = text(
    """
    SELECT s.code AS skill_code, s.name_zh AS name,
           sum(usl.level) AS level_sum, count(*) AS row_count
    FROM user_skill_levels usl
    JOIN skills s ON s.id = usl.skill_id
    WHERE usl.user_id = :user_id
    GROUP BY s.code, s.name_zh
    ORDER BY s.code
    """
)

SELECT_ACTIVITY = text(
    """
    SELECT plan_date, sum(planned_minutes) AS minutes
    FROM study_plan_items
    WHERE user_id = :user_id AND status = 'done'
      AND plan_date >= CAST(:since AS date) AND plan_date <= CAST(:today AS date)
    GROUP BY plan_date
    """
)

SELECT_PASSED_EXERCISES = text(
    """
    SELECT count(DISTINCT exercise_id)
    FROM submissions
    WHERE user_id = :user_id AND is_passed IS TRUE
    """
)

SELECT_PLAN_ITEMS_DONE = text(
    "SELECT count(*) FROM study_plan_items WHERE user_id = :user_id AND status = 'done'"
)


def average_level(level_sum: int, row_count: int) -> float:
    """Arithmetic mean of user_skill_levels.level, one decimal; 0.0 without rows."""
    if row_count <= 0:
        return 0.0
    return round(level_sum / row_count, 1)


def activity_window(today: date, minutes_by_date: dict[date, int]) -> list[dict[str, object]]:
    """Seven local days ending today, ascending, a missing day filled with 0."""
    start = today - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)
    return [
        {"date": start + timedelta(days=offset), "minutes": int(minutes_by_date.get(start + timedelta(days=offset), 0))}
        for offset in range(ACTIVITY_WINDOW_DAYS)
    ]


def requirement(key: str, label: str, required: int, actual: int) -> dict[str, object]:
    """One capstone criterion: met exactly when the real count reaches the bar."""
    return {
        "key": key,
        "label": label,
        "required": int(required),
        "actual": int(actual),
        "met": int(actual) >= int(required),
    }


async def _lessons(session: AsyncSession, user_id: int) -> dict[str, int]:
    row = (await session.execute(SELECT_LESSONS, {"user_id": user_id})).mappings().one()
    total = int(row["total"])
    completed = int(row["completed"])
    in_progress = int(row["in_progress"])
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        # The remainder is what the learner has not opened yet; never negative.
        "not_started": max(total - completed - in_progress, 0),
        "minutes_completed": int(row["minutes_completed"]),
    }


async def _plan(session: AsyncSession, user_id: int, monday: date) -> dict[str, object]:
    row = (
        (await session.execute(SELECT_PLAN, {"user_id": user_id, "week_start": monday}))
        .mappings()
        .one()
    )
    return {
        "week_start": monday,
        "scheduled": int(row["scheduled"]),
        "done": int(row["done"]),
        "skipped": int(row["skipped"]),
        "minutes_done": int(row["minutes_done"]),
        "minutes_scheduled": int(row["minutes_scheduled"]),
    }


async def _practice(session: AsyncSession, user_id: int) -> dict[str, object]:
    row = (await session.execute(SELECT_PRACTICE, {"user_id": user_id})).mappings().one()
    evidence = (await session.execute(SELECT_BY_EVIDENCE, {"user_id": user_id})).mappings().all()
    return {
        "exercises_total": int(row["exercises_total"]),
        "exercises_attempted": int(row["exercises_attempted"]),
        "exercises_passed": int(row["exercises_passed"]),
        "submissions_total": int(row["submissions_total"]),
        # Grouped by what actually occurred: a method with no submission is
        # absent, exactly like the frozen payload, and the sum matches
        # submissions_total.
        "by_evidence": {str(item["verification_method"]): int(item["submissions"]) for item in evidence},
    }


async def _capability(session: AsyncSession, user_id: int) -> dict[str, object]:
    """Row-level mean plus one entry per domain the user has evidence for."""
    rows = (await session.execute(SELECT_CAPABILITY_ROWS, {"user_id": user_id})).mappings().all()
    names = {str(row["skill_code"]): str(row["name"]) for row in rows}
    level_sum = sum(int(row["level_sum"]) for row in rows)
    row_count = sum(int(row["row_count"]) for row in rows)
    domains: list[dict[str, object]] = []
    for resolved in await levels.resolve_current_levels(session, user_id):
        code = str(resolved["skill_code"])
        if code not in names:
            # No user_skill_levels row for this domain: nothing to report, so the
            # empty-data answer stays an empty list.
            continue
        domains.append(
            {
                "skill_code": code,
                "name": names[code],
                "level": int(resolved["level"]),
                "source": resolved["evidence_kind"],
            }
        )
    return {"average_level": average_level(level_sum, row_count), "domains": domains}


async def _activity(session: AsyncSession, user_id: int, today: date) -> list[dict[str, object]]:
    rows = (
        (
            await session.execute(
                SELECT_ACTIVITY,
                {
                    "user_id": user_id,
                    "since": today - timedelta(days=ACTIVITY_WINDOW_DAYS - 1),
                    "today": today,
                },
            )
        )
        .mappings()
        .all()
    )
    return activity_window(today, {row["plan_date"]: int(row["minutes"]) for row in rows})


async def read_overview(
    session: AsyncSession, user_id: int, timezone_name: str
) -> dict[str, object]:
    """GET /progress/overview: real aggregates, a zero structure when empty."""
    # One definition of the week boundary and of "today" (Sprint 2 R1/R6): both
    # come from users.timezone through study_plan, never from a second copy.
    monday = await study_plan._week_start(session, timezone_name)
    today = await study_plan._local_today(session, timezone_name)
    return {
        "lessons": await _lessons(session, user_id),
        "plan": await _plan(session, user_id, monday),
        "practice": await _practice(session, user_id),
        "capability": await _capability(session, user_id),
        "activity": await _activity(session, user_id, today),
    }


async def read_capstone_readiness(session: AsyncSession, user_id: int) -> dict[str, object]:
    """GET /capstone/readiness: the four frozen criteria, derived from real rows."""
    lessons = await _lessons(session, user_id)
    capability = await _capability(session, user_id)
    passed = int(
        (await session.execute(SELECT_PASSED_EXERCISES, {"user_id": user_id})).scalar_one()
    )
    plan_done = int(
        (await session.execute(SELECT_PLAN_ITEMS_DONE, {"user_id": user_id})).scalar_one()
    )
    domains_at_l2 = sum(
        1 for domain in capability["domains"] if int(domain["level"]) >= CAPSTONE_L2_LEVEL
    )
    requirements = [
        requirement(
            "lessons_completed",
            f"完成全部 {lessons['total']} 节课程",
            lessons["total"],
            lessons["completed"],
        ),
        requirement(
            "exercises_passed",
            f"通过至少 {CAPSTONE_REQUIRED_EXERCISES_PASSED} 道练习",
            CAPSTONE_REQUIRED_EXERCISES_PASSED,
            passed,
        ),
        requirement(
            "domains_at_l2",
            f"至少 {CAPSTONE_REQUIRED_DOMAINS_AT_L2} 个能力域达到 L2",
            CAPSTONE_REQUIRED_DOMAINS_AT_L2,
            domains_at_l2,
        ),
        requirement(
            "plan_items_done",
            f"完成至少 {CAPSTONE_REQUIRED_PLAN_ITEMS_DONE} 个计划任务",
            CAPSTONE_REQUIRED_PLAN_ITEMS_DONE,
            plan_done,
        ),
    ]
    return {
        "ready": all(bool(item["met"]) for item in requirements),
        "requirements": requirements,
        "note": CAPSTONE_NOTE,
    }


__all__ = [
    "CAPSTONE_NOTE",
    "read_capstone_readiness",
    "read_overview",
]
