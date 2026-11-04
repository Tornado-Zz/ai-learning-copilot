"""Diagnostic submission (single transaction), idempotency and history."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NOT_FOUND, ApiError, idempotency_conflict, validation_error
from app.services import catalog
from app.services.question_set import (
    CHOICES,
    DOMAIN_CODES,
    QUESTION_INDEX,
    QUESTION_SET_VERSION,
    QUESTIONS_V1,
    RULE_VERSION,
    DomainScore,
    score_answers,
)

SUPPORTED_QUESTION_SET_VERSIONS: tuple[str, ...] = (QUESTION_SET_VERSION,)
SUPPORTED_RULE_VERSIONS: tuple[str, ...] = (RULE_VERSION,)

DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 100
MAX_ATTEMPT_TOKEN_LENGTH = 64

# Field names reported by a 409 so the client knows which part of the payload moved.
CONFLICT_QUESTION_SET_VERSION = "question_set_version"
CONFLICT_RULE_VERSION = "rule_version"
CONFLICT_ANSWERS = "answers"

INSERT_ATTEMPT = text(
    """
    INSERT INTO diagnostic_attempts (
        user_id, attempt_token, question_set_version, rule_version,
        answers, domain_scores, total_correct, total_questions
    )
    VALUES (
        :user_id, :attempt_token, :question_set_version, :rule_version,
        :answers, :domain_scores, :total_correct, :total_questions
    )
    RETURNING id
    """
).bindparams(bindparam("answers", type_=JSONB), bindparam("domain_scores", type_=JSONB))

SELECT_ATTEMPT_BY_TOKEN = text(
    """
    SELECT id, submitted_at, question_set_version, rule_version, answers, domain_scores,
           total_correct, total_questions
    FROM diagnostic_attempts
    WHERE user_id = :user_id AND attempt_token = :attempt_token
    """
)

# The user_id predicate is what makes another user's batch a 404 instead of a leak.
SELECT_ATTEMPT_BY_ID = text(
    """
    SELECT id, submitted_at, question_set_version, rule_version, answers, domain_scores,
           total_correct, total_questions
    FROM diagnostic_attempts
    WHERE id = :attempt_id AND user_id = :user_id
    """
)

INSERT_SKILL_LEVEL = text(
    """
    INSERT INTO user_skill_levels (
        user_id, skill_id, level, evidence_kind, verification_method,
        assessment_state, evidence_ref, evidence_count
    )
    VALUES (
        :user_id, :skill_id, :level, :evidence_kind, :verification_method,
        :assessment_state, :evidence_ref, :evidence_count
    )
    """
)

SELECT_HISTORY = text(
    """
    SELECT id, submitted_at, question_set_version, rule_version, domain_scores,
           total_correct, total_questions
    FROM diagnostic_attempts
    WHERE user_id = :user_id AND (CAST(:cursor AS bigint) IS NULL OR id < CAST(:cursor AS bigint))
    ORDER BY id DESC
    LIMIT :limit
    """
)


def _validate_versions(question_set_version: str, rule_version: str) -> None:
    if question_set_version not in SUPPORTED_QUESTION_SET_VERSIONS:
        raise validation_error(
            "不支持的题集版本",
            "question_set_version",
            "unsupported_version",
            supported=list(SUPPORTED_QUESTION_SET_VERSIONS),
        )
    if rule_version not in SUPPORTED_RULE_VERSIONS:
        raise validation_error(
            "不支持的评分规则版本",
            "rule_version",
            "unsupported_version",
            supported=list(SUPPORTED_RULE_VERSIONS),
        )


def _validate_answers(answers: Mapping[str, str]) -> dict[str, str]:
    expected = {question.id for question in QUESTIONS_V1}
    given = set(answers)
    if given != expected:
        raise validation_error(
            "answers 必须恰好覆盖题集的 20 道题",
            "answers",
            "question_set_mismatch",
            expected=len(expected),
            missing=sorted(expected - given),
            unexpected=sorted(given - expected),
        )
    normalized: dict[str, str] = {}
    for question in QUESTIONS_V1:
        choice = str(answers[question.id]).strip().upper()
        if choice not in CHOICES:
            raise validation_error(
                "每道题的 choice 只能是 A、B、C、D",
                f"answers.{question.id}",
                "invalid_choice",
                choices=list(CHOICES),
            )
        normalized[question.id] = choice
    return normalized


def _normalize_token(attempt_token: str | None) -> str:
    """Same token = network retry of one attempt; a missing token always appends."""
    if attempt_token is None:
        return uuid.uuid4().hex
    token = attempt_token.strip()
    if not token or len(token) > MAX_ATTEMPT_TOKEN_LENGTH:
        raise validation_error(
            "attempt_token 必须是 1–64 个字符的非空字符串",
            "attempt_token",
            "invalid_token",
            max_length=MAX_ATTEMPT_TOKEN_LENGTH,
        )
    return token


def _ordered_domains(domain_scores: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
    ordered: list[dict[str, object]] = []
    for code in DOMAIN_CODES:
        if code not in domain_scores:
            continue
        entry = domain_scores[code]
        ordered.append(
            {
                "skill_code": code,
                "correct": int(entry["correct"]),
                "total": int(entry["total"]),
                "rate": float(entry["rate"]),
                "level": int(entry["level"]),
                "state": str(entry["state"]),
            }
        )
    return ordered


def _result_from_row(row: Mapping[str, object], domains: Sequence[dict[str, object]]) -> dict[str, object]:
    return {
        "attempt_id": int(row["id"]),
        "rule_version": str(row["rule_version"]),
        "domains": list(domains),
    }


def normalize_answers(answers: Mapping[str, object]) -> dict[str, str]:
    """Canonical answer map: the only thing two submissions are compared on.

    Pure function, no session and no I/O. Question ids are stripped and
    lower-cased, a mapping value contributes only its "choice" field so extra
    fields cannot fake a difference, choices are stripped and upper-cased, ids
    outside the current question set are dropped (they cannot change a score),
    and the result is ordered by question id so a reordered body compares equal.
    """
    canonical: dict[str, str] = {}
    for raw_id, raw_value in answers.items():
        question_id = str(raw_id).strip().lower()
        if question_id not in QUESTION_INDEX:
            continue
        if isinstance(raw_value, Mapping):
            raw_value = raw_value.get("choice")
        if raw_value is None:
            continue
        choice = str(raw_value).strip().upper()
        if choice:
            canonical[question_id] = choice
    return {question_id: canonical[question_id] for question_id in sorted(canonical)}


def answers_match(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    """True when both answer maps describe the same submission."""
    return normalize_answers(left) == normalize_answers(right)


async def _find_attempt_by_token(
    session: AsyncSession, user_id: int, attempt_token: str
) -> Mapping[str, object] | None:
    return (
        await session.execute(
            SELECT_ATTEMPT_BY_TOKEN, {"user_id": user_id, "attempt_token": attempt_token}
        )
    ).mappings().first()


def _conflicting_fields(
    existing: Mapping[str, object],
    *,
    question_set_version: str,
    rule_version: str,
    answers: Mapping[str, object],
) -> list[str]:
    conflicts: list[str] = []
    if str(existing[CONFLICT_QUESTION_SET_VERSION]) != question_set_version:
        conflicts.append(CONFLICT_QUESTION_SET_VERSION)
    if str(existing[CONFLICT_RULE_VERSION]) != rule_version:
        conflicts.append(CONFLICT_RULE_VERSION)
    if not answers_match(existing["answers"], answers):
        conflicts.append(CONFLICT_ANSWERS)
    return conflicts


def _replay_or_conflict(
    existing: Mapping[str, object],
    *,
    question_set_version: str,
    rule_version: str,
    answers: Mapping[str, object],
) -> dict[str, object]:
    """One token is one attempt: an identical retry replays it, anything else is a 409."""
    conflicts = _conflicting_fields(
        existing,
        question_set_version=question_set_version,
        rule_version=rule_version,
        answers=answers,
    )
    if conflicts:
        raise idempotency_conflict(
            "同一 attempt_token 已经提交过不同的诊断内容，不能覆盖或追加",
            {"attempt_id": int(existing["id"]), "conflicts": conflicts},
        )
    return _result_from_row(existing, _ordered_domains(existing["domain_scores"]))


async def write_skill_levels(
    session: AsyncSession, *, user_id: int, attempt_id: int, domains: Sequence[DomainScore]
) -> None:
    """Six append-only evidence rows sharing one evidence_ref (diag:<attempt_id>)."""
    ids = await catalog.skill_ids(session)
    evidence_ref = f"diag:{attempt_id}"
    rows = [
        {
            "user_id": user_id,
            "skill_id": ids[domain.skill_code],
            "level": domain.level,
            "evidence_kind": "diagnostic",
            "verification_method": "static_rule",
            "assessment_state": domain.state,
            "evidence_ref": evidence_ref,
            "evidence_count": domain.total,
        }
        for domain in domains
    ]
    await session.execute(INSERT_SKILL_LEVEL, rows)


@dataclass(frozen=True)
class SubmitResult:
    """The batch payload, plus whether this call replayed an existing batch."""

    attempt: dict[str, object]
    replayed: bool


async def submit_diagnostic(
    session: AsyncSession,
    *,
    user_id: int,
    attempt_token: str | None,
    question_set_version: str,
    rule_version: str,
    answers: Mapping[str, str],
) -> SubmitResult:
    """Validate, then replay, conflict or write one attempt plus six level rows.

    Three outcomes for an attempt_token: a new token writes one batch, an
    identical retry replays the stored batch with no new rows, and a reused
    token with different versions or answers is a 409 instead of a silent
    overwrite. A concurrent retry that loses the unique-constraint race is
    re-read and compared through exactly the same path, never surfaced as a 500.
    """
    _validate_versions(question_set_version, rule_version)
    normalized = _validate_answers(answers)
    token = _normalize_token(attempt_token)

    existing = await _find_attempt_by_token(session, user_id, token)
    if existing is not None:
        return SubmitResult(
            attempt=_replay_or_conflict(
                existing,
                question_set_version=question_set_version,
                rule_version=rule_version,
                answers=normalized,
            ),
            replayed=True,
        )

    scored = score_answers(normalized)
    try:
        attempt_id = int(
            (
                await session.execute(
                    INSERT_ATTEMPT,
                    {
                        "user_id": user_id,
                        "attempt_token": token,
                        "question_set_version": question_set_version,
                        "rule_version": rule_version,
                        "answers": dict(normalized),
                        "domain_scores": {
                            domain.skill_code: domain.as_json() for domain in scored.domains
                        },
                        "total_correct": scored.total_correct,
                        "total_questions": scored.total_questions,
                    },
                )
            ).scalar_one()
        )
        await write_skill_levels(
            session, user_id=user_id, attempt_id=attempt_id, domains=scored.domains
        )
        await session.commit()
    except IntegrityError:
        # A concurrent retry with the same token won uq_diagnostic_attempts_token.
        # It is committed by now (the insert blocked on the index until it was),
        # so the winner is re-read and compared through the same path as a retry.
        await session.rollback()
        existing = await _find_attempt_by_token(session, user_id, token)
        if existing is None:
            raise
        return SubmitResult(
            attempt=_replay_or_conflict(
                existing,
                question_set_version=question_set_version,
                rule_version=rule_version,
                answers=normalized,
            ),
            replayed=True,
        )
    except Exception:
        await session.rollback()
        raise

    return SubmitResult(
        attempt={
            "attempt_id": attempt_id,
            "rule_version": rule_version,
            "domains": [domain.as_row() for domain in scored.domains],
        },
        replayed=False,
    )


async def list_history(
    session: AsyncSession, user_id: int, *, limit: int, cursor: int | None
) -> dict[str, object]:
    """Append-only attempt history, newest first, cursor = the previous page's smallest id."""
    rows = (
        await session.execute(
            SELECT_HISTORY, {"user_id": user_id, "cursor": cursor, "limit": limit + 1}
        )
    ).mappings().all()
    has_more = len(rows) > limit
    page = rows[:limit]
    items = [
        {
            "attempt_id": int(row["id"]),
            "submitted_at": row["submitted_at"],
            "question_set_version": row["question_set_version"],
            "rule_version": row["rule_version"],
            "total_correct": int(row["total_correct"]),
            "total_questions": int(row["total_questions"]),
            "domains": _ordered_domains(row["domain_scores"]),
        }
        for row in page
    ]
    next_cursor = str(page[-1]["id"]) if has_more and page else None
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


async def attempt_detail(
    session: AsyncSession, *, user_id: int, attempt_id: int
) -> dict[str, object]:
    """Per-question verdicts of one committed batch.

    Only a batch that was actually submitted exists as a row, so "read a
    submitted batch only" is the row being there at all. The lookup is scoped to
    the current user, so another user's batch is a 404 rather than a leak.
    Prompt and options are projected from the live question set at request time:
    the database stores answers only, never a copy of the question bank.
    """
    row = (
        await session.execute(
            SELECT_ATTEMPT_BY_ID, {"attempt_id": attempt_id, "user_id": user_id}
        )
    ).mappings().first()
    if row is None:
        raise ApiError(404, NOT_FOUND, "诊断批次不存在，或不属于当前用户")

    selected = normalize_answers(row["answers"])
    questions = [
        {
            "id": question.id,
            "order": order,
            # The type comes from the live question bank, not from the stored snapshot.
            "type": question.kind,
            "domain_code": question.skill_code,
            "prompt": question.prompt,
            "options": [{"key": key, "text": text} for key, text in question.options.items()],
            "selected": selected.get(question.id),
            "correct": question.answer,
            "is_correct": selected.get(question.id) == question.answer,
            # 解析来自题库，与 correct 同源，因此不会和题面版本漂移。
            "explanation": question.explanation,
        }
        for order, question in enumerate(QUESTIONS_V1, start=1)
    ]
    return {
        "attempt_id": int(row["id"]),
        "submitted_at": row["submitted_at"],
        "question_set_version": str(row["question_set_version"]),
        "rule_version": str(row["rule_version"]),
        "total_correct": int(row["total_correct"]),
        "total_questions": int(row["total_questions"]),
        # The stored scoring snapshot, not a re-score: this is what was assessed.
        "domains": _ordered_domains(row["domain_scores"]),
        "questions": questions,
    }


def validate_history_query(limit: int, cursor: int | None) -> None:
    if limit < 1 or limit > MAX_HISTORY_LIMIT:
        raise validation_error(
            "limit 必须在 1–100 之间",
            "limit",
            "out_of_range",
            min=1,
            max=MAX_HISTORY_LIMIT,
            value=limit,
        )
    if cursor is not None and cursor < 1:
        raise validation_error("cursor 必须是正整数", "cursor", "invalid_cursor", value=cursor)


__all__ = [
    "SubmitResult",
    "answers_match",
    "attempt_detail",
    "list_history",
    "normalize_answers",
    "submit_diagnostic",
    "validate_history_query",
    "write_skill_levels",
]
