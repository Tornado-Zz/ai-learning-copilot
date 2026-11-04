"""Exercise catalogue, submissions and the static-only judging pipeline (Sprint 3 B).

Four invariants live here:

1. 判题只做文本比对（B2）：本模块没有任何执行用户代码的路径，一次判定就是
   app.services.judging 的一次纯函数调用；那个模块里没有 subprocess、没有
   eval、没有 exec、没有 importlib。
2. 判定永不写 user_skill_levels（B1）：本模块只对 submissions 做 INSERT，
   从不 UPDATE user_skill_levels，也不授予 L3/L4；MVP 的等级上限仍是 L2。
3. 详情不返回答案键：SELECT_EXERCISE_DETAIL 根本不读 required_patterns /
   forbidden_patterns / expected_output；需要它们的只有独立的判题查询
   SELECT_EXERCISE_FOR_JUDGING。详情唯一额外读的是 requirement_labels——题面
   要求的中文清单，它复述要求而不是答案键，正是判分文案「第 N 项」要引用的东西。
   详情里的 review 块只读 review_items，且按 (user_id, exercise_id) 限定，
   别人的错题本进不来。
4. attempt_no 的单调性由数据库唯一约束兜底：一次 INSERT ... SELECT 里算
   max+1，真出现并发时唯一约束报冲突，接口返回 409，而不是覆盖历史。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import CONFLICT, NOT_FOUND, ApiError, validation_error
from app.schemas.exercises import SubmissionCreateRequest
from app.services import judging, review

# The latest submission per exercise plus how many of them passed: both are
# scoped to the calling user, so one learner never sees another's history.
_LATEST_AND_PASSED = """
    latest AS (
        SELECT DISTINCT ON (s.exercise_id)
               s.exercise_id,
               s.id AS last_submission_id,
               s.attempt_no AS last_attempt_no,
               s.is_passed AS last_is_passed,
               s.judging_mode AS last_judging_mode,
               s.verification_method AS last_verification_method,
               s.verification_strength AS last_verification_strength,
               s.created_at AS last_created_at
        FROM submissions s
        WHERE s.user_id = :user_id
        ORDER BY s.exercise_id, s.created_at DESC, s.id DESC
    ),
    passed AS (
        SELECT s.exercise_id, count(*) AS passed_count
        FROM submissions s
        WHERE s.user_id = :user_id AND s.is_passed IS TRUE
        GROUP BY s.exercise_id
    )
"""

# The list deliberately does not select prompt, starter_code or any answer key:
# a list row is a card, not a task.
SELECT_EXERCISE_LIST = text(
    f"""
    WITH {_LATEST_AND_PASSED}
    SELECT e.id, e.code, e.lesson_id, l.code AS lesson_code, e.title, e.order_index,
           e.difficulty, e.estimated_minutes, e.content_version, e.status,
           jsonb_array_length(e.visible_tests) AS visible_test_count,
           COALESCE(p.passed_count, 0) AS passed_count,
           lat.last_submission_id, lat.last_attempt_no, lat.last_is_passed,
           lat.last_judging_mode, lat.last_verification_method,
           lat.last_verification_strength, lat.last_created_at
    FROM exercises e
    JOIN lessons l ON l.id = e.lesson_id
    LEFT JOIN latest lat ON lat.exercise_id = e.id
    LEFT JOIN passed p ON p.exercise_id = e.id
    WHERE e.status = 'published' AND e.deleted_at IS NULL
      AND (CAST(:lesson_id AS bigint) IS NULL OR e.lesson_id = CAST(:lesson_id AS bigint))
    ORDER BY e.lesson_id, e.order_index, e.id
    """
)

# Detail reads the task text and the visible self-check cases only. The answer
# keys are absent from this statement by design, not by a serializer filter.
#
# The lateral join answers "does this learner owe a review of this task": it reads
# review_items for this user and this exercise and nothing else, so one learner's
# mistake book never reaches another's detail. review_items is unique on
# (user_id, exercise_id) and has no soft-delete column (rows are never deleted,
# review R4), so the pair already yields at most one row; ORDER BY id DESC keeps
# the "newest row wins" wording true if a second source ever inserts one.
# due is compared against :local_today, which get_exercise fills from
# review.local_today - the same users.timezone clock the mistake book uses.
SELECT_EXERCISE_DETAIL = text(
    f"""
    WITH {_LATEST_AND_PASSED}
    SELECT e.id, e.code, e.lesson_id, l.code AS lesson_code, e.title, e.order_index,
           e.difficulty, e.estimated_minutes, e.content_version, e.status,
           e.prompt, e.starter_code, e.visible_tests, e.requirement_labels,
           jsonb_array_length(e.visible_tests) AS visible_test_count,
           COALESCE(p.passed_count, 0) AS passed_count,
           lat.last_submission_id, lat.last_attempt_no, lat.last_is_passed,
           lat.last_judging_mode, lat.last_verification_method,
           lat.last_verification_strength, lat.last_created_at,
           rv.id AS review_item_id, rv.status AS review_status,
           rv.streak AS review_streak, rv.interval_days AS review_interval_days,
           rv.next_review_on AS review_next_review_on,
           rv.last_result AS review_last_result,
           rv.last_reviewed_at AS review_last_reviewed_at,
           (rv.status = 'pending'
            AND rv.next_review_on <= CAST(:local_today AS date)) AS review_due
    FROM exercises e
    JOIN lessons l ON l.id = e.lesson_id
    LEFT JOIN latest lat ON lat.exercise_id = e.id
    LEFT JOIN passed p ON p.exercise_id = e.id
    LEFT JOIN LATERAL (
        SELECT ri.id, ri.status, ri.streak, ri.interval_days, ri.next_review_on,
               ri.last_result, ri.last_reviewed_at
        FROM review_items ri
        WHERE ri.user_id = :user_id AND ri.exercise_id = e.id
        ORDER BY ri.id DESC
        LIMIT 1
    ) rv ON TRUE
    WHERE e.id = :exercise_id AND e.status = 'published' AND e.deleted_at IS NULL
    """
)

# Judge-time read: this is the only statement that returns the answer keys and
# its result never leaves the service (the response model has no such fields).
SELECT_EXERCISE_FOR_JUDGING = text(
    """
    SELECT e.id, e.code, e.required_patterns, e.forbidden_patterns, e.expected_output,
           e.requirement_labels
    FROM exercises e
    WHERE e.id = :exercise_id AND e.status = 'published' AND e.deleted_at IS NULL
    """
)

# attempt_no = max+1 inside the statement that inserts it. An empty history
# yields one row with a NULL max, so COALESCE makes the first attempt 1.
INSERT_SUBMISSION = text(
    """
    INSERT INTO submissions (
        user_id, exercise_id, attempt_no, code_text, claimed_output,
        judging_mode, verification_method, is_passed, ai_assistance_level
    )
    SELECT :user_id, :exercise_id, COALESCE(max(s.attempt_no), 0) + 1,
           :code_text, :claimed_output, :judging_mode, :verification_method,
           :is_passed, 'none'
    FROM submissions s
    WHERE s.user_id = :user_id AND s.exercise_id = :exercise_id
    RETURNING id, attempt_no, is_passed, verification_strength, created_at
    """
)

# now() is the transaction timestamp, so two submissions of one transaction can
# share created_at. The id tiebreaker keeps the order total: a listing is always
# "newest first" even when the clock cannot tell the rows apart.
SELECT_EXERCISE_SUBMISSIONS = text(
    """
    SELECT id, attempt_no, is_passed, judging_mode, verification_method,
           verification_strength, created_at
    FROM submissions
    WHERE user_id = :user_id AND exercise_id = :exercise_id
    ORDER BY created_at DESC, id DESC
    LIMIT CAST(:limit AS integer)
    """
)

COUNT_EXERCISE_SUBMISSIONS = text(
    "SELECT count(*) FROM submissions WHERE user_id = :user_id AND exercise_id = :exercise_id"
)

SELECT_RECENT_SUBMISSIONS = text(
    """
    SELECT s.id, s.attempt_no, s.is_passed, s.judging_mode, s.verification_method,
           s.verification_strength, s.created_at,
           e.id AS exercise_id, e.code AS exercise_code, e.title AS exercise_title,
           e.lesson_id
    FROM submissions s
    JOIN exercises e ON e.id = s.exercise_id
    WHERE s.user_id = :user_id
    ORDER BY s.created_at DESC, s.id DESC
    LIMIT CAST(:limit AS integer)
    """
)

COUNT_USER_SUBMISSIONS = text("SELECT count(*) FROM submissions WHERE user_id = :user_id")


def _json_array(raw: object) -> list[object]:
    """Read a JSONB array defensively: a driver may hand back a str or a list."""
    value: object = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return list(value) if isinstance(value, (list, tuple)) else []


def _patterns(raw: object) -> list[str]:
    return [str(item) for item in _json_array(raw)]


def _visible_tests(raw: object) -> list[dict[str, str]]:
    """Self-check cases plus the input/expected aliases the web client reads."""
    cases: list[dict[str, str]] = []
    for item in _json_array(raw):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        expect = str(item.get("expect", ""))
        cases.append(
            {"name": name, "expect": expect, "input": name, "expected": expect}
        )
    return cases


def _evidence(
    *,
    submission_id: object,
    attempt_no: object,
    is_passed: object,
    judging_mode: object,
    verification_method: object,
    verification_strength: object,
    created_at: object,
) -> dict[str, object]:
    """Build the B1 evidence block; the label always comes from the strength."""
    strength = str(verification_strength)
    return {
        "submission_id": int(submission_id),  # type: ignore[arg-type]
        "attempt_no": int(attempt_no),  # type: ignore[arg-type]
        "is_passed": None if is_passed is None else bool(is_passed),
        "judging_mode": str(judging_mode),
        "verification_method": str(verification_method),
        "verification_strength": strength,
        "evidence_label": judging.evidence_label(strength),
        "created_at": created_at,
    }


def _last_submission(row: dict[str, Any]) -> dict[str, object] | None:
    if row["last_submission_id"] is None:
        return None
    return _evidence(
        submission_id=row["last_submission_id"],
        attempt_no=row["last_attempt_no"],
        is_passed=row["last_is_passed"],
        judging_mode=row["last_judging_mode"],
        verification_method=row["last_verification_method"],
        verification_strength=row["last_verification_strength"],
        created_at=row["last_created_at"],
    )


def _review_block(row: dict[str, Any]) -> dict[str, object] | None:
    """This user's review row for the exercise, or None when there is no row.

    None is the honest answer for "not in the mistake book": an empty object would
    claim a review exists with no status. A row whose status is 'done' still
    returns a block, because the learner may want to see the finished streak.
    """
    if row["review_item_id"] is None:
        return None
    last_result = row["review_last_result"]
    return {
        "status": str(row["review_status"]),
        "due": bool(row["review_due"]),
        "streak": int(row["review_streak"]),
        "interval_days": int(row["review_interval_days"]),
        "next_review_on": row["review_next_review_on"],
        "last_result": None if last_result is None else str(last_result),
        "last_reviewed_at": row["review_last_reviewed_at"],
    }


def _list_row(row: dict[str, Any]) -> dict[str, object]:
    return {
        "id": int(row["id"]),
        "code": str(row["code"]),
        "lesson_id": int(row["lesson_id"]),
        "lesson_code": str(row["lesson_code"]),
        "title": str(row["title"]),
        "order_index": int(row["order_index"]),
        "difficulty": int(row["difficulty"]),
        "estimated_minutes": int(row["estimated_minutes"]),
        "content_version": int(row["content_version"]),
        "status": str(row["status"]),
        "visible_test_count": int(row["visible_test_count"]),
        "passed_count": int(row["passed_count"]),
        "last_submission": _last_submission(row),
    }


async def list_exercises(
    session: AsyncSession, user_id: int, lesson_id: int | None = None
) -> dict[str, object]:
    """Published exercises in curriculum order, optionally one lesson only."""
    rows = (
        (
            await session.execute(
                SELECT_EXERCISE_LIST, {"user_id": user_id, "lesson_id": lesson_id}
            )
        )
        .mappings()
        .all()
    )
    items = [_list_row(dict(row)) for row in rows]
    return {"items": items, "total": len(items)}


async def get_exercise(
    session: AsyncSession, user_id: int, exercise_id: int
) -> dict[str, object]:
    """One published exercise with its task text and this user's review context.

    404 when the exercise does not exist. The review block is null unless the
    mistake book holds a row for this (user, exercise) pair.
    """
    # 今天只来自 users.timezone：review.local_today 是唯一的日期来源，UTC 不参与。
    # 直接用 now()::date 会在东八区凌晨把「今天到期」错算成明天。
    today = await review.local_today(session, user_id)
    row = (
        (
            await session.execute(
                SELECT_EXERCISE_DETAIL,
                {"user_id": user_id, "exercise_id": exercise_id, "local_today": today},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ApiError(404, NOT_FOUND, "练习不存在或未发布")
    values = dict(row)
    detail = _list_row(values)
    detail["prompt"] = str(values["prompt"])
    detail["starter_code"] = str(values["starter_code"])
    detail["visible_tests"] = _visible_tests(values["visible_tests"])
    # 标签复述题面要求，不是答案键：判题失败时它就是「第 N 项」的内容，
    # 顺序与 required_patterns 一致，因此可以直接给学习者看。
    detail["requirements"] = _patterns(values["requirement_labels"])
    detail["review"] = _review_block(values)
    return detail


async def _exercise_for_judging(session: AsyncSession, exercise_id: int) -> dict[str, object]:
    row = (
        (
            await session.execute(SELECT_EXERCISE_FOR_JUDGING, {"exercise_id": exercise_id})
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ApiError(404, NOT_FOUND, "练习不存在或未发布")
    return {
        "id": int(row["id"]),
        "code": str(row["code"]),
        "required_patterns": _patterns(row["required_patterns"]),
        "forbidden_patterns": _patterns(row["forbidden_patterns"]),
        "expected_output": None if row["expected_output"] is None else str(row["expected_output"]),
        "requirement_labels": _patterns(row["requirement_labels"]),
    }


async def create_submission(
    session: AsyncSession,
    user_id: int,
    exercise_id: int,
    payload: SubmissionCreateRequest,
) -> dict[str, object]:
    """Judge one submission with static rules or a self check, never by running it.

    The judgement is computed in memory and then stored: judging_mode,
    verification_method and is_passed are the only evidence columns written, and
    verification_strength is derived by the generated column in the database, so
    the response can quote what was really recorded.

    v0.1.2: 判题结论同时驱动错题本，且与提交行共用同一个事务（下面那次 commit 之前
    调用），所以"提交成功但复习计划没动"或"复习计划动了但提交没落库"都不会发生。
    判题逻辑本身（app.services.judging）不因这次接入改动一行。
    """
    if not payload.code_text.strip():
        raise validation_error("code_text 不能为空", "code_text", "empty")

    exercise = await _exercise_for_judging(session, exercise_id)
    judgment = judging.judge_submission(
        code_text=payload.code_text,
        required_patterns=exercise["required_patterns"],  # type: ignore[arg-type]
        forbidden_patterns=exercise["forbidden_patterns"],  # type: ignore[arg-type]
        expected_output=exercise["expected_output"],  # type: ignore[arg-type]
        claimed_output=payload.claimed_output,
        self_reported_passed=payload.self_reported_passed,
        requirement_labels=exercise["requirement_labels"],  # type: ignore[arg-type]
    )

    try:
        row = (
            (
                await session.execute(
                    INSERT_SUBMISSION,
                    {
                        "user_id": user_id,
                        "exercise_id": exercise_id,
                        "code_text": payload.code_text,
                        "claimed_output": payload.claimed_output,
                        "judging_mode": judgment.judging_mode,
                        "verification_method": judgment.verification_method,
                        "is_passed": judgment.is_passed,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiError(404, NOT_FOUND, "练习不存在或未发布")
        # 答错建/重置、答对推进，无复习行时什么都不做；这里不 commit，
        # 与提交行一起在下面那次 commit 落库。
        await review.schedule_after_submission(
            session,
            user_id=user_id,
            exercise_id=exercise_id,
            submission_id=int(row["id"]),
            is_passed=None if row["is_passed"] is None else bool(row["is_passed"]),
        )
        await session.commit()
    except IntegrityError as exc:
        # uq_submissions_user_exercise_attempt fired: a concurrent submission
        # took this attempt_no. Nothing was written; the caller may retry.
        await session.rollback()
        raise ApiError(409, CONFLICT, "该题的提交序号发生并发冲突，请重试") from exc
    except Exception:
        await session.rollback()
        raise

    strength = str(row["verification_strength"])
    return {
        "submission_id": int(row["id"]),
        "judging_mode": judgment.judging_mode,
        "verification_method": judgment.verification_method,
        "verification_strength": strength,
        "evidence_label": judging.evidence_label(strength),
        "is_passed": None if row["is_passed"] is None else bool(row["is_passed"]),
        "checks": [check.as_dict() for check in judgment.checks],
    }


async def list_exercise_submissions(
    session: AsyncSession, user_id: int, exercise_id: int, limit: int = 50
) -> dict[str, object]:
    """Newest-first history for one exercise; total counts every attempt."""
    await _exercise_for_judging(session, exercise_id)
    rows = (
        (
            await session.execute(
                SELECT_EXERCISE_SUBMISSIONS,
                {"user_id": user_id, "exercise_id": exercise_id, "limit": limit},
            )
        )
        .mappings()
        .all()
    )
    items = [
        _evidence(
            submission_id=row["id"],
            attempt_no=row["attempt_no"],
            is_passed=row["is_passed"],
            judging_mode=row["judging_mode"],
            verification_method=row["verification_method"],
            verification_strength=row["verification_strength"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    total = (
        await session.execute(
            COUNT_EXERCISE_SUBMISSIONS, {"user_id": user_id, "exercise_id": exercise_id}
        )
    ).scalar_one()
    return {"items": items, "total": int(total)}


async def list_recent_submissions(
    session: AsyncSession, user_id: int, limit: int
) -> dict[str, object]:
    """Newest-first submissions across every exercise, for the /practice dashboard."""
    rows = (
        (await session.execute(SELECT_RECENT_SUBMISSIONS, {"user_id": user_id, "limit": limit}))
        .mappings()
        .all()
    )
    items = [
        {
            **_evidence(
                submission_id=row["id"],
                attempt_no=row["attempt_no"],
                is_passed=row["is_passed"],
                judging_mode=row["judging_mode"],
                verification_method=row["verification_method"],
                verification_strength=row["verification_strength"],
                created_at=row["created_at"],
            ),
            "exercise_id": int(row["exercise_id"]),
            "exercise_code": str(row["exercise_code"]),
            "exercise_title": str(row["exercise_title"]),
            "lesson_id": int(row["lesson_id"]),
        }
        for row in rows
    ]
    total = (await session.execute(COUNT_USER_SUBMISSIONS, {"user_id": user_id})).scalar_one()
    return {"items": items, "total": int(total)}


__all__ = [
    "create_submission",
    "get_exercise",
    "list_exercise_submissions",
    "list_exercises",
    "list_recent_submissions",
]
