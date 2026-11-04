"""Mistake book and spaced repetition (v0.1.2, table review_items).

四条调度规则就是冻结口径，逐条可测：

R1 答错（submissions.is_passed = false）-> upsert（(user_id, exercise_id) 唯一）：
   streak = 0、interval_days = 1、next_review_on = 本地今天 + 1、status = 'pending'、
   last_result = 'failed'。已存在的行同样被重置，包括已经是 done 的行。
R2 答对且存在待复习行（status = 'pending'）-> streak += 1，按新的 streak 取间隔：
   1 -> 3 天、2 -> 7 天、>= 3 -> 14 天并把 status 置 'done'；
   last_result = 'passed'、last_reviewed_at = now()。
R3 答对但没有复习行（或行已是 done）-> 什么都不做：不留行，不噪声。
R4 永不删除行：done 只是一种状态，本模块没有任何 DELETE，也没有软删除列。

"今天"只来自 users.timezone（与周计划 R6 同一口径）：SELECT_USER_TODAY 是唯一的
日期来源，服务器本地时钟从不参与。

last_reviewed_at 只在 R2 写 now()：冻结口径给答错列了五处变更，没有列这一项，因此
答错不擅自改写它（既不清空也不刷新）。

调用约束：schedule_after_submission / record_result 都不 commit。判题成功与错题本
推进必须在同一个事务里落库，提交动作属于调用方（app.services.exercises 与路由）。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NOT_FOUND, ApiError

STATUS_PENDING = "pending"
STATUS_DONE = "done"
LAST_RESULT_PASSED = "passed"
LAST_RESULT_FAILED = "failed"

# R2 的间隔表：新 streak 1 -> 3 天、2 -> 7 天、>= 3 -> 14 天并且结束复习。
INTERVAL_STREAK_1 = 3
INTERVAL_STREAK_2 = 7
INTERVAL_STREAK_MAX = 14
STREAK_FOR_DONE = 3

SELECT_USER_TODAY = text(
    "SELECT (now() AT TIME ZONE timezone)::date AS local_today FROM users WHERE id = :user_id"
)

# R1 的**唯一**分支：一行都没有就建，已经存在就整行重置（ON CONFLICT 覆盖 done）。
UPSERT_FAILED = text(
    """
    INSERT INTO review_items (
        user_id, exercise_id, source_submission_id, streak, interval_days,
        next_review_on, last_result, status
    )
    VALUES (
        :user_id, :exercise_id, :submission_id, 0, 1,
        CAST(:local_today AS date) + 1, 'failed', 'pending'
    )
    ON CONFLICT (user_id, exercise_id) DO UPDATE SET
        streak = 0,
        interval_days = 1,
        next_review_on = EXCLUDED.next_review_on,
        last_result = 'failed',
        status = 'pending',
        source_submission_id = EXCLUDED.source_submission_id,
        updated_at = now()
    RETURNING id, streak, interval_days, next_review_on, status, last_result
    """
)

# R2：SET 的右侧读的是更新前的行，所以 CASE 与算术都以 review_items.streak + 1
# 为准，两处引用同一个表达式，间隔和日期不可能算出不同的数。
_ADVANCE_INTERVAL = (
    f"CASE review_items.streak + 1"
    f" WHEN 1 THEN {INTERVAL_STREAK_1}"
    f" WHEN 2 THEN {INTERVAL_STREAK_2}"
    f" ELSE {INTERVAL_STREAK_MAX} END"
)

ADVANCE_PASSING = text(
    f"""
    UPDATE review_items
    SET streak = review_items.streak + 1,
        interval_days = {_ADVANCE_INTERVAL},
        next_review_on = CAST(:local_today AS date) + {_ADVANCE_INTERVAL},
        status = CASE WHEN review_items.streak + 1 >= {STREAK_FOR_DONE}
                      THEN 'done' ELSE 'pending' END,
        last_result = 'passed',
        last_reviewed_at = now(),
        source_submission_id = COALESCE(
            CAST(:submission_id AS bigint), review_items.source_submission_id
        ),
        updated_at = now()
    WHERE user_id = :user_id AND exercise_id = :exercise_id
      AND status = 'pending'
    RETURNING id, streak, interval_days, next_review_on, status, last_result
    """
)

SELECT_OWN_ITEM = text(
    """
    SELECT id, exercise_id, source_submission_id, streak, interval_days,
           next_review_on, status, last_result
    FROM review_items
    WHERE id = :item_id AND user_id = :user_id
    """
)

# POST /result 的答错分支：与 R1 的五个变更完全一致，只是按 id 命中。
RESET_FAILED = text(
    """
    UPDATE review_items
    SET streak = 0,
        interval_days = 1,
        next_review_on = CAST(:local_today AS date) + 1,
        last_result = 'failed',
        status = 'pending',
        updated_at = now()
    WHERE id = :item_id AND user_id = :user_id
    RETURNING id, streak, interval_days, next_review_on, status
    """
)

SELECT_ITEMS = text(
    """
    SELECT ri.id, ri.exercise_id, e.title AS exercise_title, e.lesson_id,
           ri.streak, ri.interval_days, ri.next_review_on, ri.status, ri.last_result,
           (ri.status = 'pending'
            AND ri.next_review_on <= CAST(:local_today AS date)) AS due
    FROM review_items ri
    JOIN exercises e ON e.id = ri.exercise_id
    WHERE ri.user_id = :user_id
      AND (NOT CAST(:due_only AS boolean)
           OR (ri.status = 'pending'
               AND ri.next_review_on <= CAST(:local_today AS date)))
    ORDER BY ri.next_review_on ASC, ri.id ASC
    LIMIT CAST(:limit AS integer)
    """
)

COUNT_ITEMS = text(
    """
    SELECT count(*)
    FROM review_items ri
    WHERE ri.user_id = :user_id
      AND (NOT CAST(:due_only AS boolean)
           OR (ri.status = 'pending' AND ri.next_review_on <= CAST(:local_today AS date)))
    """
)

COUNT_DUE = text(
    """
    SELECT count(*)
    FROM review_items
    WHERE user_id = :user_id AND status = 'pending'
      AND next_review_on <= CAST(:local_today AS date)
    """
)

SELECT_SUMMARY = text(
    """
    SELECT count(*) FILTER (WHERE status = 'pending') AS pending,
           count(*) FILTER (WHERE status = 'pending'
                             AND next_review_on <= CAST(:local_today AS date)) AS due_today,
           count(*) FILTER (WHERE status = 'done') AS done,
           min(next_review_on) FILTER (WHERE status = 'pending') AS next_due_on
    FROM review_items
    WHERE user_id = :user_id
    """
)


def next_interval_days(streak: int) -> int:
    """R2 的间隔表，纯函数：新 streak -> 距下次复习的天数。"""
    if streak <= 1:
        return INTERVAL_STREAK_1
    if streak == 2:
        return INTERVAL_STREAK_2
    return INTERVAL_STREAK_MAX


def _is_due(status: str, next_review_on: date, today: date) -> bool:
    return status == STATUS_PENDING and next_review_on <= today


async def local_today(session: AsyncSession, user_id: int) -> date:
    """The learner's local calendar day; the only clock this module reads."""
    today = (
        await session.execute(SELECT_USER_TODAY, {"user_id": user_id})
    ).scalar_one_or_none()
    if today is None:
        raise ApiError(404, NOT_FOUND, "用户不存在")
    return today


async def schedule_after_submission(
    session: AsyncSession,
    *,
    user_id: int,
    exercise_id: int,
    submission_id: int,
    is_passed: bool | None,
) -> dict[str, object] | None:
    """R1/R2/R3: advance the mistake book for one judged submission.

    Never commits: the caller's transaction holds both the submission row and
    this row, so a failure rolls the judgement back as well.
    """
    today = await local_today(session, user_id)
    if is_passed is False:
        row = (
            (
                await session.execute(
                    UPSERT_FAILED,
                    {
                        "user_id": user_id,
                        "exercise_id": exercise_id,
                        "submission_id": submission_id,
                        "local_today": today,
                    },
                )
            )
            .mappings()
            .first()
        )
    elif is_passed is True:
        row = (
            (
                await session.execute(
                    ADVANCE_PASSING,
                    {
                        "user_id": user_id,
                        "exercise_id": exercise_id,
                        "submission_id": submission_id,
                        "local_today": today,
                    },
                )
            )
            .mappings()
            .first()
        )
    else:
        # R3: 判定为空（当前判题路径不会产生）不动错题本。
        return None
    if row is None:
        # R3: 答对但没有 pending 行 —— 不建行，不噪声。
        return None
    return {
        "id": int(row["id"]),
        "streak": int(row["streak"]),
        "interval_days": int(row["interval_days"]),
        "next_review_on": row["next_review_on"],
        "status": str(row["status"]),
        "last_result": row["last_result"],
    }


async def record_result(
    session: AsyncSession, *, user_id: int, item_id: int, passed: bool
) -> dict[str, object]:
    """POST /review/items/{id}/result: the learner's own verdict on one attempt.

    passed=false resets exactly like R1; passed=true advances exactly like R2 and
    leaves an already-done row untouched (R3: no pending row, nothing to advance).
    A row that does not exist or belongs to someone else is a 404 NOT_FOUND.
    """
    today = await local_today(session, user_id)
    current = (
        (await session.execute(SELECT_OWN_ITEM, {"item_id": item_id, "user_id": user_id}))
        .mappings()
        .first()
    )
    if current is None:
        raise ApiError(404, NOT_FOUND, "复习项不存在，或不属于当前用户")
    if passed:
        row = (
            (
                await session.execute(
                    ADVANCE_PASSING,
                    {
                        "user_id": user_id,
                        "exercise_id": int(current["exercise_id"]),
                        "submission_id": current["source_submission_id"],
                        "local_today": today,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            row = current
    else:
        row = (
            (
                await session.execute(
                    RESET_FAILED, {"item_id": item_id, "user_id": user_id, "local_today": today}
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiError(404, NOT_FOUND, "复习项不存在，或不属于当前用户")
    return {
        "id": int(row["id"]),
        "streak": int(row["streak"]),
        "interval_days": int(row["interval_days"]),
        "next_review_on": row["next_review_on"],
        "status": str(row["status"]),
        "due": _is_due(str(row["status"]), row["next_review_on"], today),
    }


async def list_items(
    session: AsyncSession, *, user_id: int, due_only: bool, limit: int
) -> dict[str, object]:
    """GET /review/items: next_review_on ASC, id ASC; due=1 filters to due rows."""
    today = await local_today(session, user_id)
    params = {"user_id": user_id, "local_today": today, "due_only": due_only, "limit": limit}
    rows = (await session.execute(SELECT_ITEMS, params)).mappings().all()
    return {
        "items": [
            {
                "id": int(row["id"]),
                "exercise_id": int(row["exercise_id"]),
                "exercise_title": str(row["exercise_title"]),
                "lesson_id": int(row["lesson_id"]),
                "streak": int(row["streak"]),
                "interval_days": int(row["interval_days"]),
                "next_review_on": row["next_review_on"],
                "status": str(row["status"]),
                "due": bool(row["due"]),
                "last_result": row["last_result"],
            }
            for row in rows
        ],
        "total": int((await session.execute(COUNT_ITEMS, params)).scalar_one()),
        "due_total": int((await session.execute(COUNT_DUE, params)).scalar_one()),
    }


async def summary(session: AsyncSession, *, user_id: int) -> dict[str, object]:
    """GET /review/summary: all-zero and next_due_on=null when the book is empty."""
    today = await local_today(session, user_id)
    row = (
        (await session.execute(SELECT_SUMMARY, {"user_id": user_id, "local_today": today}))
        .mappings()
        .one()
    )
    return {
        "pending": int(row["pending"]),
        "due_today": int(row["due_today"]),
        "done": int(row["done"]),
        "next_due_on": row["next_due_on"],
    }


__all__ = [
    "INTERVAL_STREAK_1",
    "INTERVAL_STREAK_2",
    "INTERVAL_STREAK_MAX",
    "LAST_RESULT_FAILED",
    "LAST_RESULT_PASSED",
    "STATUS_DONE",
    "STATUS_PENDING",
    "STREAK_FOR_DONE",
    "list_items",
    "local_today",
    "next_interval_days",
    "record_result",
    "schedule_after_submission",
    "summary",
]
