"""v0.1.1 后端验收：GET /progress/overview 与 GET /capstone/readiness 只用真实数据。

隔离策略沿用其它集成用例：状态敏感的断言一律用本测试自己创建的 users 行
（fixture test_user）并按该 user_id 过滤；端点级用例走单用户 API，断言值与测试自己
另写的 SQL 交叉核对，不整表依赖产品里既有的学习记录。全程不执行 DELETE / TRUNCATE，
外层事务整体回滚。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import progress

pytestmark = pytest.mark.integration

TIMEZONE = "Asia/Shanghai"
OVERVIEW_URL = "/api/v1/progress/overview"
CAPSTONE_URL = "/api/v1/capstone/readiness"
ACTIVITY_DAYS = 7

LOCAL_TODAY = text("SELECT (now() AT TIME ZONE :timezone)::date")
WEEK_START = text("SELECT (date_trunc('week', now() AT TIME ZONE :timezone))::date")
PUBLISHED_LESSONS = text(
    "SELECT id, estimated_minutes FROM lessons "
    "WHERE status = 'published' AND deleted_at IS NULL ORDER BY id"
)
PUBLISHED_EXERCISES = text(
    "SELECT id FROM exercises WHERE status = 'published' AND deleted_at IS NULL ORDER BY id"
)
DOMAIN_SKILL_IDS = text("SELECT id FROM skills WHERE level = 'domain' ORDER BY id")
SINGLE_USER_ID = text("SELECT id FROM users ORDER BY id LIMIT 1")
LESSON_FACTS = text(
    """
    SELECT
        (SELECT count(*) FROM lessons l
          WHERE l.status = 'published' AND l.deleted_at IS NULL) AS total,
        count(*) FILTER (WHERE p.status = 'completed') AS completed,
        count(*) FILTER (WHERE p.status = 'in_progress') AS in_progress,
        COALESCE(sum(l.estimated_minutes) FILTER (WHERE p.status = 'completed'), 0) AS minutes
    FROM learning_progress p
    JOIN lessons l ON l.id = p.lesson_id
    WHERE p.user_id = :user_id AND l.status = 'published' AND l.deleted_at IS NULL
    """
)
SUBMISSION_COUNT = text("SELECT count(*) FROM submissions WHERE user_id = :user_id")
AVERAGE_LEVEL = text("SELECT avg(level) FROM user_skill_levels WHERE user_id = :user_id")
SKILLS_WITH_LEVELS = text(
    """
    SELECT DISTINCT s.code
    FROM user_skill_levels usl JOIN skills s ON s.id = usl.skill_id
    WHERE usl.user_id = :user_id
    """
)
ROW_COUNTS = text(
    """
    SELECT
        (SELECT count(*) FROM users) AS users,
        (SELECT count(*) FROM lessons) AS lessons,
        (SELECT count(*) FROM exercises) AS exercises,
        (SELECT count(*) FROM learning_progress) AS learning_progress,
        (SELECT count(*) FROM submissions) AS submissions,
        (SELECT count(*) FROM study_plan_items) AS study_plan_items,
        (SELECT count(*) FROM user_skill_levels) AS user_skill_levels,
        (SELECT count(*) FROM ai_interactions) AS ai_interactions
    """
)

INSERT_PROGRESS = text(
    """
    INSERT INTO learning_progress (
        user_id, lesson_id, status, progress_pct, started_at, completed_at
    )
    VALUES (
        :user_id, :lesson_id, :status, :progress_pct, now(),
        CASE WHEN :is_completed THEN now() ELSE NULL END
    )
    """
)
INSERT_SUBMISSION = text(
    """
    INSERT INTO submissions (
        user_id, exercise_id, attempt_no, code_text, judging_mode,
        verification_method, is_passed
    )
    VALUES (
        :user_id, :exercise_id, :attempt_no, 'print(1)', :judging_mode,
        :verification_method, :is_passed
    )
    """
)
INSERT_PLAN_ITEM = text(
    """
    INSERT INTO study_plan_items (
        user_id, week_start, plan_date, kind, target_id, planned_minutes,
        status, rationale, dedupe_key
    )
    VALUES (
        :user_id, :week_start, :plan_date, 'lesson', :target_id, :planned_minutes,
        :status, '进度聚合测试行', :dedupe_key
    )
    """
)
INSERT_LEVEL = text(
    """
    INSERT INTO user_skill_levels (
        user_id, skill_id, level, evidence_kind, verification_method, assessment_state
    )
    VALUES (:user_id, :skill_id, :level, 'diagnostic', 'static_rule', 'established')
    """
)


async def _local_today(session: AsyncSession) -> date:
    return (await session.execute(LOCAL_TODAY, {"timezone": TIMEZONE})).scalar_one()


async def _week_start(session: AsyncSession) -> date:
    return (await session.execute(WEEK_START, {"timezone": TIMEZONE})).scalar_one()


async def _lessons(session: AsyncSession) -> list[tuple[int, int]]:
    rows = (await session.execute(PUBLISHED_LESSONS)).mappings().all()
    return [(int(row["id"]), int(row["estimated_minutes"])) for row in rows]


async def _exercise_ids(session: AsyncSession, wanted: int) -> list[int]:
    ids = [int(value) for value in (await session.execute(PUBLISHED_EXERCISES)).scalars().all()]
    return ids[:wanted]


async def _set_progress(session: AsyncSession, user_id: int, lesson_id: int, status: str) -> None:
    await session.execute(
        INSERT_PROGRESS,
        {
            "user_id": user_id,
            "lesson_id": lesson_id,
            "status": status,
            "progress_pct": 100 if status == "completed" else 40,
            "is_completed": status == "completed",
        },
    )


async def _add_submission(
    session: AsyncSession,
    user_id: int,
    exercise_id: int,
    *,
    verification_method: str,
    is_passed: bool,
    attempt_no: int = 1,
) -> None:
    """verification_method 与 judging_mode 必须成对（ck_submissions_evidence_paired）。"""
    await session.execute(
        INSERT_SUBMISSION,
        {
            "user_id": user_id,
            "exercise_id": exercise_id,
            "attempt_no": attempt_no,
            "judging_mode": "static_rule" if verification_method == "static_rule" else "self_check",
            "verification_method": verification_method,
            "is_passed": is_passed,
        },
    )


async def _add_plan_item(
    session: AsyncSession,
    user_id: int,
    plan_date: date,
    *,
    status: str,
    planned_minutes: int,
    dedupe_key: str,
) -> None:
    lessons = await _lessons(session)
    await session.execute(
        INSERT_PLAN_ITEM,
        {
            "user_id": user_id,
            "week_start": plan_date - timedelta(days=plan_date.weekday()),
            "plan_date": plan_date,
            "target_id": lessons[0][0],
            "planned_minutes": planned_minutes,
            "status": status,
            "dedupe_key": dedupe_key,
        },
    )


async def _meet_every_bar(session: AsyncSession, user_id: int, *, passed_exercises: int) -> None:
    """把四条口径都做到刚好达标，再把练习题数调成调用方要求的值。"""
    lessons = await _lessons(session)
    for lesson_id, _ in lessons:
        await _set_progress(session, user_id, lesson_id, "completed")
    for exercise_id in await _exercise_ids(session, passed_exercises):
        await _add_submission(
            session, user_id, exercise_id, verification_method="static_rule", is_passed=True
        )
    skill_ids = [int(value) for value in (await session.execute(DOMAIN_SKILL_IDS)).scalars().all()]
    for skill_id in skill_ids[: progress.CAPSTONE_REQUIRED_DOMAINS_AT_L2]:
        await session.execute(INSERT_LEVEL, {"user_id": user_id, "skill_id": skill_id, "level": 2})
    monday = await _week_start(session)
    for offset in range(progress.CAPSTONE_REQUIRED_PLAN_ITEMS_DONE):
        await _add_plan_item(
            session,
            user_id,
            monday + timedelta(days=offset),
            status="done",
            planned_minutes=20,
            dedupe_key=f"capstone-{user_id}-{offset}",
        )


async def _row_counts(session: AsyncSession) -> dict[str, int]:
    row = (await session.execute(ROW_COUNTS)).mappings().one()
    return {str(key): int(value) for key, value in row.items()}


async def test_overview_empty_user_returns_zero_structure(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    payload = await progress.read_overview(db_session, user_id, TIMEZONE)
    lessons_total = len(await _lessons(db_session))
    today = await _local_today(db_session)

    assert payload["lessons"] == {
        "total": lessons_total,
        "completed": 0,
        "in_progress": 0,
        "not_started": lessons_total,
        "minutes_completed": 0,
    }
    assert payload["plan"] == {
        "week_start": await _week_start(db_session),
        "scheduled": 0,
        "done": 0,
        "skipped": 0,
        "minutes_done": 0,
        "minutes_scheduled": 0,
    }
    assert payload["practice"]["exercises_attempted"] == 0
    assert payload["practice"]["exercises_passed"] == 0
    assert payload["practice"]["submissions_total"] == 0
    assert payload["practice"]["by_evidence"] == {}
    assert payload["capability"] == {"average_level": 0.0, "domains": []}
    assert [item["minutes"] for item in payload["activity"]] == [0] * ACTIVITY_DAYS
    assert payload["activity"][-1]["date"] == today


async def test_overview_lesson_counts_and_completed_minutes(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    lessons = await _lessons(db_session)
    completed, in_progress = lessons[:2], lessons[2]
    for lesson_id, _ in completed:
        await _set_progress(db_session, user_id, lesson_id, "completed")
    await _set_progress(db_session, user_id, in_progress[0], "in_progress")

    summary = (await progress.read_overview(db_session, user_id, TIMEZONE))["lessons"]

    assert summary["total"] == len(lessons)
    assert summary["completed"] == 2
    assert summary["in_progress"] == 1
    assert summary["not_started"] == len(lessons) - 3
    assert summary["minutes_completed"] == sum(minutes for _, minutes in completed)


async def test_overview_plan_counts_only_this_week(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    monday = await _week_start(db_session)
    await _add_plan_item(
        db_session, user_id, monday, status="done", planned_minutes=20, dedupe_key="this-1"
    )
    await _add_plan_item(
        db_session,
        user_id,
        monday + timedelta(days=1),
        status="done",
        planned_minutes=30,
        dedupe_key="this-2",
    )
    await _add_plan_item(
        db_session,
        user_id,
        monday + timedelta(days=2),
        status="scheduled",
        planned_minutes=45,
        dedupe_key="this-3",
    )
    await _add_plan_item(
        db_session,
        user_id,
        monday + timedelta(days=3),
        status="skipped",
        planned_minutes=25,
        dedupe_key="this-4",
    )
    await _add_plan_item(
        db_session,
        user_id,
        monday - timedelta(days=7),
        status="done",
        planned_minutes=60,
        dedupe_key="previous-week-1",
    )

    plan = (await progress.read_overview(db_session, user_id, TIMEZONE))["plan"]

    assert plan["week_start"] == monday
    assert (plan["scheduled"], plan["done"], plan["skipped"]) == (1, 2, 1)
    assert plan["minutes_done"] == 50
    assert plan["minutes_scheduled"] == 45


async def test_overview_activity_fills_zero_for_seven_days(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    today = await _local_today(db_session)
    await _add_plan_item(
        db_session, user_id, today, status="done", planned_minutes=20, dedupe_key="activity-today"
    )
    await _add_plan_item(
        db_session,
        user_id,
        today - timedelta(days=2),
        status="done",
        planned_minutes=30,
        dedupe_key="activity-two-days-ago",
    )
    await _add_plan_item(
        db_session,
        user_id,
        today - timedelta(days=10),
        status="done",
        planned_minutes=40,
        dedupe_key="activity-out-of-window",
    )

    activity = (await progress.read_overview(db_session, user_id, TIMEZONE))["activity"]

    assert len(activity) == ACTIVITY_DAYS
    assert [item["date"] for item in activity] == [
        today - timedelta(days=offset) for offset in range(ACTIVITY_DAYS - 1, -1, -1)
    ]
    assert [item["minutes"] for item in activity] == [0, 0, 0, 0, 30, 0, 20]


async def test_overview_by_evidence_groups_submissions(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    exercise_ids = await _exercise_ids(db_session, 3)
    await _add_submission(
        db_session, user_id, exercise_ids[0], verification_method="static_rule", is_passed=False
    )
    await _add_submission(
        db_session,
        user_id,
        exercise_ids[0],
        verification_method="static_rule",
        is_passed=True,
        attempt_no=2,
    )
    await _add_submission(
        db_session, user_id, exercise_ids[1], verification_method="self_report", is_passed=False
    )
    await _add_submission(
        db_session, user_id, exercise_ids[2], verification_method="self_report", is_passed=True
    )

    practice = (await progress.read_overview(db_session, user_id, TIMEZONE))["practice"]

    assert practice["exercises_total"] == len(await _exercise_ids(db_session, 99))
    assert practice["submissions_total"] == 4
    assert practice["exercises_attempted"] == 3
    assert practice["exercises_passed"] == 2
    assert practice["by_evidence"] == {"static_rule": 2, "self_report": 2}


async def test_capstone_all_requirements_met_at_the_bar(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    lessons = await _lessons(db_session)
    await _meet_every_bar(
        db_session, user_id, passed_exercises=progress.CAPSTONE_REQUIRED_EXERCISES_PASSED
    )

    readiness = await progress.read_capstone_readiness(db_session, user_id)

    assert [item["key"] for item in readiness["requirements"]] == [
        "lessons_completed",
        "exercises_passed",
        "domains_at_l2",
        "plan_items_done",
    ]
    assert [item["required"] for item in readiness["requirements"]] == [
        len(lessons),
        progress.CAPSTONE_REQUIRED_EXERCISES_PASSED,
        progress.CAPSTONE_REQUIRED_DOMAINS_AT_L2,
        progress.CAPSTONE_REQUIRED_PLAN_ITEMS_DONE,
    ]
    assert [item["actual"] for item in readiness["requirements"]] == [
        len(lessons),
        progress.CAPSTONE_REQUIRED_EXERCISES_PASSED,
        progress.CAPSTONE_REQUIRED_DOMAINS_AT_L2,
        progress.CAPSTONE_REQUIRED_PLAN_ITEMS_DONE,
    ]
    assert [item["met"] for item in readiness["requirements"]] == [True, True, True, True]
    assert readiness["ready"] is True
    assert readiness["note"] == progress.CAPSTONE_NOTE


async def test_capstone_one_short_of_the_bar_keeps_ready_false(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    user_id = int(test_user["id"])
    await _meet_every_bar(
        db_session, user_id, passed_exercises=progress.CAPSTONE_REQUIRED_EXERCISES_PASSED - 1
    )

    readiness = await progress.read_capstone_readiness(db_session, user_id)
    by_key = {str(item["key"]): item for item in readiness["requirements"]}

    assert by_key["exercises_passed"]["actual"] == progress.CAPSTONE_REQUIRED_EXERCISES_PASSED - 1
    assert by_key["exercises_passed"]["met"] is False
    assert by_key["lessons_completed"]["met"] is True
    assert by_key["domains_at_l2"]["met"] is True
    assert by_key["plan_items_done"]["met"] is True
    assert readiness["ready"] is False


async def test_capstone_ready_matches_requirements(
    api, db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    empty = await progress.read_capstone_readiness(db_session, int(test_user["id"]))
    assert [item["met"] for item in empty["requirements"]] == [False, False, False, False]
    assert empty["ready"] == all(item["met"] for item in empty["requirements"])

    response = await api.get(CAPSTONE_URL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ready", "requirements", "note"}
    assert len(body["requirements"]) == 4
    assert body["ready"] == all(item["met"] for item in body["requirements"])
    assert {item["key"] for item in body["requirements"]} == {
        "lessons_completed",
        "exercises_passed",
        "domains_at_l2",
        "plan_items_done",
    }


async def test_overview_endpoint_returns_real_aggregates(
    api, db_session: AsyncSession
) -> None:
    response = await api.get(OVERVIEW_URL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"lessons", "plan", "practice", "capability", "activity"}

    user_id = int((await db_session.execute(SINGLE_USER_ID)).scalar_one())
    facts = (
        (await db_session.execute(LESSON_FACTS, {"user_id": user_id})).mappings().one()
    )
    assert body["lessons"]["total"] == int(facts["total"])
    assert body["lessons"]["completed"] == int(facts["completed"])
    assert body["lessons"]["in_progress"] == int(facts["in_progress"])
    assert (
        body["lessons"]["not_started"]
        == int(facts["total"]) - int(facts["completed"]) - int(facts["in_progress"])
    )
    assert body["lessons"]["minutes_completed"] == int(facts["minutes"])

    submissions = int((await db_session.execute(SUBMISSION_COUNT, {"user_id": user_id})).scalar_one())
    assert body["practice"]["submissions_total"] == submissions
    assert sum(body["practice"]["by_evidence"].values()) == submissions

    assert body["plan"]["week_start"] == (await _week_start(db_session)).isoformat()
    assert len(body["activity"]) == ACTIVITY_DAYS
    assert body["activity"][-1]["date"] == (await _local_today(db_session)).isoformat()

    average = (await db_session.execute(AVERAGE_LEVEL, {"user_id": user_id})).scalar_one()
    expected_average = 0.0 if average is None else round(float(average), 1)
    assert body["capability"]["average_level"] == expected_average
    codes = set((await db_session.execute(SKILLS_WITH_LEVELS, {"user_id": user_id})).scalars().all())
    assert {domain["skill_code"] for domain in body["capability"]["domains"]} == codes


async def test_endpoints_write_no_rows(api, db_session: AsyncSession) -> None:
    before = await _row_counts(db_session)

    assert (await api.get(OVERVIEW_URL)).status_code == 200
    assert (await api.get(CAPSTONE_URL)).status_code == 200

    assert await _row_counts(db_session) == before
