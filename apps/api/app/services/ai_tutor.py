"""AI tutor orchestration (Sprint 4): quota -> configuration -> call -> ledger.

One public entry point per endpoint, and one invariant behind both: every tutor
attempt ends as exactly one ai_interactions row, including the attempts that never
reach the provider. That is what makes the two refusals auditable:

* 'quota'        - today's token sum is already at AI_DAILY_TOKEN_LIMIT. The row
                   carries 0/0 tokens, which is the evidence that no upstream
                   request was made.
* 'unavailable'  - DEEPSEEK_API_KEY is blank. Same evidence, same reason.

The order is frozen: quota first (a spent budget refuses even a configured key),
then configuration, then the call. Both refusals are decided before the transport
is touched, so neither can spend a token.

Privacy boundary: the outbound message is built from the question, the lesson /
exercise *titles*, and - since Sprint 5 - the top KNOWLEDGE_TOP_K knowledge
snippets ([title] snippet). No function in this module reads submissions.code_text,
and the context resolver selects a title column - nothing else.

Sprint 5 adds retrieval to the existing order without changing it: quota, then
configuration, then retrieval, then the call. Retrieval sits after both refusals
so a refused call still costs nothing, and it is wrapped: a search that raises
(as a missing table or a broken query would) degrades to citations: [] and the
answer goes out unchanged. A retrieval problem is never allowed to turn a paid
tutor turn into an error.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AI_QUOTA_EXCEEDED,
    AI_TIMEOUT,
    AI_UNAVAILABLE,
    NOT_FOUND,
    ApiError,
    ai_quota_exceeded,
    ai_timeout,
    ai_unavailable,
    ai_upstream_error,
)
from app.schemas.ai import ANSWER_PREVIEW_LENGTH, TutorRequest
from app.services.ai_client import AiCompletion, AiUpstreamError, AiUpstreamTimeout, DeepSeekClient
from app.services.knowledge import pipeline as knowledge

logger = logging.getLogger("app.services.ai_tutor")


def _citation_url(item: Any) -> str:
    """Citations are dicts from the pipeline; tolerate model objects too."""
    if isinstance(item, dict):
        return str(item.get("url") or "")
    return str(getattr(item, "url", "") or "")


def _dedupe_citations(items: Sequence[Any]) -> list[Any]:
    """One citation per URL, first occurrence wins; items without a URL are kept.

    同一次检索常命中同一页面的多个分块，界面若逐块展示就会出现三条一样的来源卡片。
    """
    seen: set[str] = set()
    out: list[Any] = []
    for item in items:
        url = _citation_url(item)
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        out.append(item)
    return out

# The quota window is one UTC day: created_at is stored as timestamptz, so the sum
# is taken from the UTC midnight boundary of the current day.
SELECT_DAILY_TOKENS = text(
    """
    SELECT COALESCE(sum(prompt_tokens + completion_tokens), 0) AS used_tokens
    FROM ai_interactions
    WHERE user_id = :user_id
      AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
    """
)

SELECT_LESSON_TITLE = text(
    "SELECT title FROM lessons WHERE id = CAST(:lesson_id AS bigint) AND deleted_at IS NULL"
)

SELECT_EXERCISE_TITLE = text(
    "SELECT title FROM exercises WHERE id = CAST(:exercise_id AS bigint) AND deleted_at IS NULL"
)

INSERT_INTERACTION = text(
    """
    INSERT INTO ai_interactions (
        user_id, lesson_id, exercise_id, question, answer, assistance_level,
        model, prompt_tokens, completion_tokens, latency_ms, status, error_code
    ) VALUES (
        :user_id, :lesson_id, :exercise_id, :question, :answer, :assistance_level,
        :model, :prompt_tokens, :completion_tokens, :latency_ms, :status, :error_code
    )
    RETURNING id
    """
)

# answer is never selected here: the list is a log view, and the preview of the
# question is all the learner needs to recognise the exchange.
SELECT_INTERACTIONS = text(
    """
    SELECT id,
           left(question, CAST(:preview_length AS integer)) AS question_preview,
           assistance_level, model, prompt_tokens, completion_tokens,
           prompt_tokens + completion_tokens AS total_tokens,
           status, created_at
    FROM ai_interactions
    WHERE user_id = :user_id
    ORDER BY created_at DESC, id DESC
    LIMIT CAST(:limit AS integer)
    """
)

SELECT_INTERACTIONS_TOTAL = text(
    "SELECT count(*) FROM ai_interactions WHERE user_id = :user_id"
)


async def daily_token_usage(session: AsyncSession, user_id: int) -> int:
    """Tokens this learner spent today (UTC day), successes and failures alike."""
    value = (
        await session.execute(SELECT_DAILY_TOKENS, {"user_id": user_id})
    ).scalar_one()
    return int(value or 0)


async def _resolve_context(
    session: AsyncSession, payload: TutorRequest
) -> tuple[int | None, int | None, str | None, str | None]:
    """Map the context ids to (lesson_id, exercise_id, lesson_title, exercise_title).

    Only the title column is read: the prompt for the model is a name and a goal,
    never the task body and never the learner's code. An unknown id is a 404, like
    every other unknown id in this API, and it is raised before any upstream call.
    """
    context = payload.context
    if context is None:
        return None, None, None, None

    lesson_id = context.lesson_id
    exercise_id = context.exercise_id
    lesson_title: str | None = None
    exercise_title: str | None = None

    if lesson_id is not None:
        row = (
            await session.execute(SELECT_LESSON_TITLE, {"lesson_id": lesson_id})
        ).first()
        if row is None:
            raise ApiError(404, NOT_FOUND, "课程不存在或已下线")
        lesson_title = str(row[0])

    if exercise_id is not None:
        row = (
            await session.execute(SELECT_EXERCISE_TITLE, {"exercise_id": exercise_id})
        ).first()
        if row is None:
            raise ApiError(404, NOT_FOUND, "练习不存在或已下线")
        exercise_title = str(row[0])

    return lesson_id, exercise_id, lesson_title, exercise_title


async def _retrieve_context(
    session: AsyncSession, question: str, top_k: int
) -> list[knowledge.SearchHit]:
    """Top-k knowledge hits, or [] when retrieval is unusable.

    Degrading is the contract: retrieval is an enhancement, never a precondition.
    The rollback exists because a failed statement leaves the session's transaction
    aborted in PostgreSQL, and the ledger row written right after must still land.
    """
    if top_k <= 0:
        return []
    try:
        return await knowledge.search_hits(session, question, limit=top_k)
    except Exception:  # noqa: BLE001 - a retrieval fault must not fail the tutor call
        logger.warning("knowledge retrieval degraded reason=search_failed", exc_info=True)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("knowledge retrieval rollback failed", exc_info=True)
        return []


async def _record(
    session: AsyncSession,
    *,
    user_id: int,
    lesson_id: int | None,
    exercise_id: int | None,
    question: str,
    answer: str | None,
    assistance_level: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    status: str,
    error_code: str | None = None,
) -> int:
    """Write one ledger row and commit it.

    It commits on its own because the refusal paths raise immediately afterwards:
    an uncommitted row would disappear with the request session and the cost
    history would silently lose exactly the rows it exists to keep.
    """
    result = await session.execute(
        INSERT_INTERACTION,
        {
            "user_id": user_id,
            "lesson_id": lesson_id,
            "exercise_id": exercise_id,
            "question": question,
            "answer": answer,
            "assistance_level": assistance_level,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
            "status": status,
            "error_code": error_code,
        },
    )
    interaction_id = int(result.scalar_one())
    await session.commit()
    logger.info(
        "ai_interaction recorded interaction_id=%d status=%s model=%s "
        "prompt_tokens=%d completion_tokens=%d latency_ms=%d error_code=%s",
        interaction_id,
        status,
        model,
        prompt_tokens,
        completion_tokens,
        latency_ms,
        error_code,
    )
    return interaction_id


async def answer_question(
    session: AsyncSession,
    user_id: int,
    payload: TutorRequest,
    client: DeepSeekClient,
) -> dict[str, Any]:
    """Run one tutor turn: refuse, or call, and either way leave one ledger row."""
    settings = get_settings()
    daily_limit = int(settings.ai_daily_token_limit)
    assistance_level = payload.assistance_level
    question = payload.question

    # 1) Quota. A spent budget refuses every call, configured key or not.
    used_tokens = await daily_token_usage(session, user_id)
    if used_tokens >= daily_limit:
        await _record(
            session,
            user_id=user_id,
            lesson_id=None,
            exercise_id=None,
            question=question,
            answer=None,
            assistance_level=assistance_level,
            model=client.model,
            status="quota",
            error_code=AI_QUOTA_EXCEEDED,
        )
        logger.warning(
            "ai_tutor refused reason=quota used_tokens=%d daily_token_limit=%d",
            used_tokens,
            daily_limit,
        )
        raise ai_quota_exceeded(used_tokens, daily_limit)

    lesson_id, exercise_id, lesson_title, exercise_title = await _resolve_context(session, payload)

    # 2) Configuration. A blank key is a refusal, not a failure: nothing is sent.
    if not client.configured:
        await _record(
            session,
            user_id=user_id,
            lesson_id=lesson_id,
            exercise_id=exercise_id,
            question=question,
            answer=None,
            assistance_level=assistance_level,
            model=client.model,
            status="unavailable",
            error_code=AI_UNAVAILABLE,
        )
        logger.warning("ai_tutor refused reason=not_configured")
        raise ai_unavailable()

    # 3) Knowledge retrieval. Local, bounded and degradable: a hit injects
    #    "[title] snippet" lines and produces citations; no hit changes nothing.
    hits = await _retrieve_context(session, question, int(settings.knowledge_top_k_bounded))
    knowledge_context = [hit.as_prompt_line() for hit in hits]
    # 去重：同一页面的多个命中块只保留一条引用（按 url 首次出现），
    # 否则界面上会出现三条一模一样的来源卡片，像重复数据。
    citations = _dedupe_citations([hit.as_citation() for hit in hits])
    logger.info(
        "knowledge retrieval hits=%d top_k=%d",
        len(hits),
        int(settings.knowledge_top_k_bounded),
    )

    # 4) The call. Latency is measured around the transport, not around the HTTP
    #    client's own timing, so a stub transport reports its real elapsed time.
    started = time.perf_counter()
    try:
        completion: AiCompletion = await client.complete(
            question=question,
            assistance_level=assistance_level,
            lesson_title=lesson_title,
            exercise_title=exercise_title,
            knowledge_context=knowledge_context,
        )
    except AiUpstreamTimeout:
        latency_ms = int(round((time.perf_counter() - started) * 1000))
        await _record(
            session,
            user_id=user_id,
            lesson_id=lesson_id,
            exercise_id=exercise_id,
            question=question,
            answer=None,
            assistance_level=assistance_level,
            model=client.model,
            latency_ms=latency_ms,
            status="timeout",
            error_code=AI_TIMEOUT,
        )
        logger.warning("ai_tutor failed status=timeout latency_ms=%d", latency_ms)
        raise ai_timeout(float(settings.ai_timeout_seconds)) from None
    except AiUpstreamError as exc:
        latency_ms = int(round((time.perf_counter() - started) * 1000))
        await _record(
            session,
            user_id=user_id,
            lesson_id=lesson_id,
            exercise_id=exercise_id,
            question=question,
            answer=None,
            assistance_level=assistance_level,
            model=client.model,
            latency_ms=latency_ms,
            status="error",
            error_code=exc.error_code,
        )
        logger.warning(
            "ai_tutor failed status=error error_code=%s latency_ms=%d",
            exc.error_code,
            latency_ms,
        )
        raise ai_upstream_error(exc.error_code) from None

    # 5) Success: the answer is persisted in full, the list endpoint shows a preview.
    interaction_id = await _record(
        session,
        user_id=user_id,
        lesson_id=lesson_id,
        exercise_id=exercise_id,
        question=question,
        answer=completion.answer,
        assistance_level=assistance_level,
        model=completion.model,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        latency_ms=completion.latency_ms,
        status="ok",
    )
    return {
        "interaction_id": interaction_id,
        "answer": completion.answer,
        "model": completion.model,
        "assistance_level": assistance_level,
        "usage": completion.usage(),
        "latency_ms": completion.latency_ms,
        # Sprint 5: where the injected context came from, {} when nothing matched.
        "citations": citations,
    }


async def list_interactions(
    session: AsyncSession, user_id: int, limit: int
) -> dict[str, Any]:
    """Newest first, this learner only, question preview instead of the answer."""
    rows = (
        await session.execute(
            SELECT_INTERACTIONS,
            {
                "user_id": user_id,
                "preview_length": ANSWER_PREVIEW_LENGTH,
                "limit": limit,
            },
        )
    ).mappings().all()
    total = int(
        (await session.execute(SELECT_INTERACTIONS_TOTAL, {"user_id": user_id})).scalar_one()
    )
    return {"items": [dict(row) for row in rows], "total": total}


__all__ = [
    "answer_question",
    "daily_token_usage",
    "list_interactions",
]
