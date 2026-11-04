"""Knowledge endpoints (Sprint 5): ingest, search, source freshness.

Three rules this module exists to enforce:

1. Ingestion is a write path, so it is OFF unless KNOWLEDGE_INGEST_ENABLED=true.
   The refusal happens before any database or network work, and it is a 403 with
   a machine readable code (INGEST_DISABLED) rather than a silent no-op.
2. The fetcher is a FastAPI dependency. Tests override get_knowledge_fetcher with
   a fake, which is why no suite in this project can reach the network.
3. Search never mutates: it reads candidates and scores them, so a GET costs one
   SELECT plus the (bounded) Python scoring loop.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.schemas.knowledge import (
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    SEARCH_Q_MAX_LENGTH,
    SEARCH_Q_MIN_LENGTH,
    SOURCES_LIMIT_DEFAULT,
    SOURCES_LIMIT_MAX,
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    KnowledgeSearchResponse,
    KnowledgeSourceListResponse,
)
from app.services.knowledge import HttpxFetcher, KnowledgeFetcher
from app.services.knowledge import pipeline as knowledge

router = APIRouter(tags=["knowledge"])

INGEST_DISABLED = "INGEST_DISABLED"


def get_knowledge_fetcher() -> KnowledgeFetcher:
    """Per-request fetcher. Overridden in tests with a fake."""
    return HttpxFetcher()


@router.post(
    "/knowledge/ingest",
    response_model=KnowledgeIngestResponse,
    summary="把白名单内的知识来源入库：幂等（内容未变则跳过），单个来源失败不影响其他来源",
    responses={
        403: {"description": "KNOWLEDGE_INGEST_ENABLED 未开启，未做任何数据库或网络操作"},
        422: {"description": "urls 为空串、超过 2048 字符或超过条数上限"},
    },
)
async def ingest_knowledge(
    payload: KnowledgeIngestRequest | None = None,
    session: AsyncSession = Depends(get_db),
    fetcher: KnowledgeFetcher = Depends(get_knowledge_fetcher),
) -> KnowledgeIngestResponse:
    settings = get_settings()
    if not settings.knowledge_ingest_enabled:
        raise ApiError(
            403,
            INGEST_DISABLED,
            "知识库入库未启用：需要设置 KNOWLEDGE_INGEST_ENABLED=true",
            {"reason": "ingest_disabled"},
        )
    urls = payload.urls if payload is not None else None
    summary = await knowledge.ingest(session, urls=urls, fetcher=fetcher)
    return KnowledgeIngestResponse.model_validate(summary)


@router.get(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
    summary="关键词检索知识库：score = 命中词数 / 查询词数（heading、标题命中额外加分）",
    responses={422: {"description": "q 缺失、为空或少于 2 个字符"}},
)
async def search_knowledge(
    q: str = Query(
        ...,
        min_length=SEARCH_Q_MIN_LENGTH,
        max_length=SEARCH_Q_MAX_LENGTH,
        description=f"检索词，{SEARCH_Q_MIN_LENGTH}–{SEARCH_Q_MAX_LENGTH} 字符",
    ),
    limit: int = Query(
        default=SEARCH_LIMIT_DEFAULT,
        ge=1,
        le=SEARCH_LIMIT_MAX,
        description="返回条数上限",
    ),
    session: AsyncSession = Depends(get_db),
) -> KnowledgeSearchResponse:
    return KnowledgeSearchResponse.model_validate(
        await knowledge.search(session, q, limit=limit)
    )


@router.get(
    "/knowledge/sources",
    response_model=KnowledgeSourceListResponse,
    summary="知识来源清单：入库时间、age_days、stale 与每个来源的块数",
)
async def read_knowledge_sources(
    limit: int = Query(
        default=SOURCES_LIMIT_DEFAULT,
        ge=1,
        le=SOURCES_LIMIT_MAX,
        description="返回条数上限",
    ),
    session: AsyncSession = Depends(get_db),
) -> KnowledgeSourceListResponse:
    return KnowledgeSourceListResponse.model_validate(
        await knowledge.list_sources(session, limit=limit)
    )


__all__ = ["INGEST_DISABLED", "get_knowledge_fetcher", "router"]
