"""Lesson catalogue and per-lesson progress.

Two invariants of the Sprint 2 contract live here:

1. Reading a lesson never writes. GET builds its payload from two SELECTs, so
   opening a lesson can never flip it to completed; only PUT writes a row.
2. A lesson self-assessment is evidence of reading intent, nothing more. It is
   stored in learning_progress.self_assessment (capped at L2) and no code path
   in this module touches user_skill_levels.
3. Progress is monotonic inside the database, not only inside this module: the
   UPSERT carries the rank guard in its own WHERE, so a request that read a
   stale row still writes nothing and is answered 422
   COURSE_PROGRESS_REGRESSION (A2).
4. Completing a lesson settles its plan items for the current local week only
   (A1). A scheduled row of any other week is that week's work and stays
   exactly as it is.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import COURSE_PROGRESS_REGRESSION, NOT_FOUND, ApiError, validation_error
from app.schemas.lessons import LessonProgressUpdateRequest

MAX_SELF_ASSESSMENT = 2
COMPLETED_PCT = 100
STARTED_PCT = 1
# S4: learning_progress only walks this order, one step at a time and never back.
# A repeated status is idempotent; anything that lowers the rank is a 422.
PROGRESS_RANK = {"not_started": 0, "in_progress": 1, "completed": 2}

_PROGRESS_COLUMNS = """
    p.status AS progress_status,
    p.self_assessment,
    p.progress_pct,
    p.time_spent_seconds,
    p.started_at,
    p.completed_at,
    p.updated_at AS progress_updated_at
"""

SELECT_LESSONS = text(
    f"""
    SELECT l.id, l.code, l.title, l.summary, l.stage, l.order_index,
           l.estimated_minutes, l.content_version, l.status,
           s.code AS skill_code,
           {_PROGRESS_COLUMNS}
    FROM lessons l
    LEFT JOIN skills s ON s.id = l.skill_id
    LEFT JOIN learning_progress p ON p.lesson_id = l.id AND p.user_id = :user_id
    WHERE l.status = 'published' AND l.deleted_at IS NULL
    ORDER BY l.stage, l.order_index, l.id
    """
)

SELECT_LESSON = text(
    f"""
    SELECT l.id, l.code, l.title, l.summary, l.stage, l.order_index,
           l.estimated_minutes, l.content_version, l.status, l.content,
           s.code AS skill_code,
           {_PROGRESS_COLUMNS}
    FROM lessons l
    LEFT JOIN skills s ON s.id = l.skill_id
    LEFT JOIN learning_progress p ON p.lesson_id = l.id AND p.user_id = :user_id
    WHERE l.id = :lesson_id AND l.status = 'published' AND l.deleted_at IS NULL
    """
)

SELECT_PROGRESS = text(
    """
    SELECT lesson_id, status, self_assessment, progress_pct, time_spent_seconds,
           started_at, completed_at
    FROM learning_progress
    WHERE user_id = :user_id AND lesson_id = :lesson_id
    """
)

SELECT_USER_TIMEZONE = text("SELECT timezone FROM users WHERE id = :user_id")

UPSERT_PROGRESS = text(
    """
    INSERT INTO learning_progress (
        user_id, lesson_id, status, self_assessment, progress_pct,
        time_spent_seconds, started_at, completed_at
    )
    VALUES (
        :user_id, :lesson_id, :status, :self_assessment, :progress_pct,
        :time_spent_seconds,
        -- The VALUES row must satisfy the CHECK constraints on its own: PostgreSQL
        -- validates them before ON CONFLICT decides between insert and update.
        CASE WHEN :started_now THEN now() END,
        CASE WHEN :completed_now THEN now() END
    )
    ON CONFLICT (user_id, lesson_id) DO UPDATE SET
        status = EXCLUDED.status,
        self_assessment = EXCLUDED.self_assessment,
        -- A2: the rank and both numbers only grow, so two racing requests that
        -- each read a stale row still cannot lower them.
        progress_pct = GREATEST(learning_progress.progress_pct, EXCLUDED.progress_pct),
        time_spent_seconds = GREATEST(
            learning_progress.time_spent_seconds, EXCLUDED.time_spent_seconds
        ),
        -- a timestamp already earned is never erased by a later, weaker status
        started_at = COALESCE(learning_progress.started_at, EXCLUDED.started_at),
        completed_at = COALESCE(learning_progress.completed_at, EXCLUDED.completed_at),
        updated_at = now()
    -- A2: the guard is the statement's own WHERE, not the service check that ran
    -- before it. When it fails PostgreSQL updates nothing, RETURNING yields no
    -- row, and save_progress answers 422 with zero writes.
    WHERE (CASE EXCLUDED.status
               WHEN 'completed' THEN 2 WHEN 'in_progress' THEN 1 ELSE 0 END)
          >= (CASE learning_progress.status
               WHEN 'completed' THEN 2 WHEN 'in_progress' THEN 1 ELSE 0 END)
    RETURNING lesson_id, status, self_assessment, progress_pct, time_spent_seconds,
              started_at, completed_at, updated_at
    """
)

# A1: completing a lesson is the trusted source for its plan items, but only for
# the week the completion happens in. A row of another week is that week's work:
# finishing this lesson now must not settle next week's (or last week's) task.
# Only rows that are still 'scheduled' are touched - done/skipped/expired are
# history and stay exactly as they are. Runs in the same transaction as the
# progress write.
MARK_PLAN_ITEMS_DONE = text(
    """
    UPDATE study_plan_items
    SET status = 'done', updated_at = now()
    WHERE user_id = :user_id AND kind = 'lesson'
      AND target_id = :lesson_id AND status = 'scheduled'
      AND week_start = :current_week_start
    RETURNING id
    """
)

# Lessons a plan may point at: published, not soft-deleted, not already completed
# by this user. Ordered so the plan fills week days in curriculum order.
SELECT_SCHEDULEABLE_LESSONS = text(
    """
    SELECT l.id, l.code, l.title, l.stage, l.order_index, l.estimated_minutes,
           s.code AS skill_code, s.name_zh AS skill_name
    FROM lessons l
    JOIN skills s ON s.id = l.skill_id
    LEFT JOIN learning_progress p ON p.lesson_id = l.id AND p.user_id = :user_id
    WHERE l.status = 'published' AND l.deleted_at IS NULL
      AND COALESCE(p.status, 'not_started') <> 'completed'
    ORDER BY l.stage, l.order_index, l.id
    """
)


def _progress_row(row: dict[str, Any]) -> dict[str, object] | None:
    """Learner-facing progress, or None when this lesson was never written."""
    if row["progress_status"] is None:
        return None
    return {
        "status": row["progress_status"],
        "self_assessment": int(row["self_assessment"]),
        "progress_pct": int(row["progress_pct"]),
        "time_spent_seconds": int(row["time_spent_seconds"]),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "updated_at": row["progress_updated_at"],
    }


def _lesson_row(row: dict[str, Any]) -> dict[str, object]:
    return {
        "id": int(row["id"]),
        "code": str(row["code"]),
        "title": str(row["title"]),
        "summary": row["summary"],
        "stage": int(row["stage"]),
        "order_index": int(row["order_index"]),
        "estimated_minutes": int(row["estimated_minutes"]),
        "content_version": int(row["content_version"]),
        "status": str(row["status"]),
        "skill_code": row["skill_code"],
        "progress": _progress_row(row),
    }


async def list_lessons(session: AsyncSession, user_id: int) -> dict[str, object]:
    """Published lessons in curriculum order, each with this user's progress."""
    rows = (
        (await session.execute(SELECT_LESSONS, {"user_id": user_id})).mappings().all()
    )
    items = [_lesson_row(dict(row)) for row in rows]
    return {"items": items, "total": len(items)}


async def get_lesson(session: AsyncSession, user_id: int, lesson_id: int) -> dict[str, object]:
    """One published lesson with its body and this user's progress; 404 otherwise."""
    row = (
        (await session.execute(SELECT_LESSON, {"user_id": user_id, "lesson_id": lesson_id}))
        .mappings()
        .first()
    )
    if row is None:
        raise ApiError(404, NOT_FOUND, "课程不存在或未发布")
    lesson = _lesson_row(dict(row))
    lesson["content"] = _normalize_content(row["content"])
    return lesson


def _normalize_content(raw: object) -> dict[str, object]:
    """Read the stored JSONB defensively: never trust the payload shape."""
    content = dict(raw) if isinstance(raw, dict) else {}
    return {
        "schema_version": int(content.get("schema_version", 1)),
        "goal": str(content.get("goal", "")),
        "explanation": [str(part) for part in content.get("explanation", [])],
        "example": content.get("example") or {},
        "common_mistakes": list(content.get("common_mistakes", [])),
        "self_check": list(content.get("self_check", [])),
    }


async def scheduleable_lessons(session: AsyncSession, user_id: int) -> list[dict[str, object]]:
    """Lessons the weekly plan may schedule (published, not completed yet)."""
    rows = (
        (await session.execute(SELECT_SCHEDULEABLE_LESSONS, {"user_id": user_id}))
        .mappings()
        .all()
    )
    return [
        {
            "id": int(row["id"]),
            "code": str(row["code"]),
            "title": str(row["title"]),
            "stage": int(row["stage"]),
            "order_index": int(row["order_index"]),
            "estimated_minutes": int(row["estimated_minutes"]),
            "skill_code": str(row["skill_code"]),
            "skill_name": str(row["skill_name"]),
        }
        for row in rows
    ]


def validate_progress(payload: LessonProgressUpdateRequest) -> None:
    """Service-layer duplicate of the schema and the CHECK constraints."""
    if payload.self_assessment is not None and payload.self_assessment > MAX_SELF_ASSESSMENT:
        raise validation_error(
            "self_assessment 上限为 L2：课程自评不授予 L3/L4",
            "self_assessment",
            "out_of_range",
            min=0,
            max=MAX_SELF_ASSESSMENT,
            value=payload.self_assessment,
        )
    if payload.time_spent_seconds is not None and payload.time_spent_seconds < 0:
        raise validation_error(
            "time_spent_seconds 不能为负数",
            "time_spent_seconds",
            "out_of_range",
            min=0,
            value=payload.time_spent_seconds,
        )


def _regression(current: object, requested: str) -> ApiError:
    """The one 422 body for a backward status, whichever layer caught it."""
    return ApiError(
        422,
        COURSE_PROGRESS_REGRESSION,
        "课程进度只允许前进（not_started → in_progress → completed），不允许回退",
        {
            "field": "status",
            "reason": "course_progress_regression",
            "current_status": current,
            "requested_status": requested,
        },
    )


def _ensure_forward_transition(current: object, requested: str) -> None:
    """S4: refuse a status that would move a lesson backwards, writing nothing.

    completed -> in_progress / completed -> not_started / in_progress ->
    not_started all raise 422 COURSE_PROGRESS_REGRESSION before any write runs, so
    a stale tab or a duplicated request can never undo a finished lesson. This is
    the fast path; A2 repeats the same rule inside the UPSERT for the window
    between this read and the write.
    """
    if not isinstance(current, str) or current not in PROGRESS_RANK:
        return
    if PROGRESS_RANK[requested] < PROGRESS_RANK[current]:
        raise _regression(current, requested)


def _next_progress_pct(
    current: int | None, payload: LessonProgressUpdateRequest
) -> int:
    """Reading progress only grows; completing a lesson always ends at 100."""
    value = max(int(current or 0), int(payload.progress_pct or 0))
    if payload.status == "completed":
        return COMPLETED_PCT
    if payload.status == "in_progress":
        return max(value, STARTED_PCT)
    return value


async def _current_week_start(session: AsyncSession, user_id: int) -> date:
    """This week's Monday on the user's own calendar (A1).

    users.timezone is the only clock this module trusts. The Monday itself comes
    from the study-plan helper so both modules read the same week; the import is
    deferred because app.services.study_plan imports this module at import time.
    """
    from app.services.study_plan import _week_start

    timezone_name = (
        await session.execute(SELECT_USER_TIMEZONE, {"user_id": user_id})
    ).scalar_one()
    return await _week_start(session, timezone_name)


async def _stored_status(
    session: AsyncSession, user_id: int, lesson_id: int
) -> str | None:
    """Read the stored status back; only the A2 refusal path needs it."""
    row = (
        (
            await session.execute(
                SELECT_PROGRESS, {"user_id": user_id, "lesson_id": lesson_id}
            )
        )
        .mappings()
        .first()
    )
    return None if row is None else str(row["status"])


async def save_progress(
    session: AsyncSession, user_id: int, lesson_id: int, payload: LessonProgressUpdateRequest
) -> dict[str, object]:
    """Write learning_progress in one UPSERT. Never touches user_skill_levels.

    A2: the write is granted by the statement itself. If the row already holds a
    higher rank than this request asks for - the race the service-level check
    cannot see - the ON CONFLICT WHERE matches nothing, RETURNING is empty and
    the answer is 422 COURSE_PROGRESS_REGRESSION with zero writes.
    """
    validate_progress(payload)
    lesson = await get_lesson(session, user_id, lesson_id)
    existing = lesson["progress"] or {}
    _ensure_forward_transition(existing.get("status"), payload.status)
    params = {
        "user_id": user_id,
        "lesson_id": lesson_id,
        "status": payload.status,
        "self_assessment": (
            payload.self_assessment
            if payload.self_assessment is not None
            else int(existing.get("self_assessment", 0))
        ),
        "progress_pct": _next_progress_pct(existing.get("progress_pct"), payload),
        "time_spent_seconds": max(
            int(existing.get("time_spent_seconds", 0)), int(payload.time_spent_seconds or 0)
        ),
        "started_now": payload.status != "not_started",
        "completed_now": payload.status == "completed",
    }
    try:
        row = (await session.execute(UPSERT_PROGRESS, params)).mappings().first()
        if row is None:
            # A2: the WHERE refused the update, so a concurrent request already
            # holds a higher rank and this transaction wrote nothing. Re-read the
            # stored status for the details and refuse without committing.
            raise _regression(
                await _stored_status(session, user_id, lesson_id), payload.status
            )
        plan_items_completed = 0
        if payload.status == "completed":
            # S3 + A1: the lesson becomes the trusted source for the plan items of
            # the week it was completed in, in the same transaction - a failed sync
            # rolls the progress write back too.
            plan_items_completed = len(
                (
                    await session.execute(
                        MARK_PLAN_ITEMS_DONE,
                        {
                            "user_id": user_id,
                            "lesson_id": lesson_id,
                            "current_week_start": await _current_week_start(
                                session, user_id
                            ),
                        },
                    )
                )
                .scalars()
                .all()
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return {
        "lesson_id": int(row["lesson_id"]),
        "status": str(row["status"]),
        "plan_items_completed": plan_items_completed,
        "self_assessment": int(row["self_assessment"]),
        "progress_pct": int(row["progress_pct"]),
        "time_spent_seconds": int(row["time_spent_seconds"]),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "updated_at": row["updated_at"],
    }


__all__ = [
    "get_lesson",
    "list_lessons",
    "save_progress",
    "scheduleable_lessons",
    "validate_progress",
]
