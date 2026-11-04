"""Schemas for the Sprint 5 knowledge surface.

The shapes are frozen: ingestion reports one result per source and never fails the
whole call for one bad page; search reports why each hit scored what it scored
(score, age_days, stale) so the retrieval stays explainable without a vector
store; the source list is the freshness view of what is actually indexed.

fetched_at is serialised as an ISO-8601 UTC string ending in Z, the same
convention /ai/interactions already uses, so no client has to guess a timezone.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.knowledge.pipeline import (
    INGEST_URLS_MAX,
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    SEARCH_QUERY_MAX_LENGTH,
    SEARCH_QUERY_MIN_LENGTH,
    SOURCES_LIMIT_DEFAULT,
    SOURCES_LIMIT_MAX,
)

MAX_URL_LENGTH = 2048
IngestStatus = Literal["ok", "failed"]


class KnowledgeIngestRequest(BaseModel):
    """POST /knowledge/ingest body. An omitted or empty list means every default source."""

    urls: list[str] | None = Field(
        default=None,
        max_length=INGEST_URLS_MAX,
        description=(
            "要入库的 URL 列表；省略则入库默认的 python 官方文档页与仓库内全部课程。 "
            "只接受 docs.python.org 域名与 repo://lesson/<code>， "
            f"最多 {INGEST_URLS_MAX} 条"
        ),
    )

    @field_validator("urls")
    @classmethod
    def _urls_must_not_be_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            text_value = item.strip()
            if not text_value:
                raise ValueError("urls 里不能有空字符串")
            if len(text_value) > MAX_URL_LENGTH:
                raise ValueError(f"url 超过 {MAX_URL_LENGTH} 字符")
            cleaned.append(text_value)
        return cleaned


class KnowledgeIngestResultItem(BaseModel):
    url: str
    status: IngestStatus
    chunks_added: int
    skipped: bool
    error_code: str | None = None


class KnowledgeIngestResponse(BaseModel):
    results: list[KnowledgeIngestResultItem]
    sources_total: int
    chunks_total: int


class KnowledgeSearchItem(BaseModel):
    chunk_id: int
    source_id: int
    title: str
    url: str
    fetched_at: str | None
    age_days: float
    stale: bool
    heading: str | None
    snippet: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    query: str
    items: list[KnowledgeSearchItem]
    total: int


class KnowledgeSourceItem(BaseModel):
    id: int
    url: str
    title: str
    source_type: str
    fetched_at: str | None
    age_days: float
    stale: bool
    chunks: int


class KnowledgeSourceListResponse(BaseModel):
    items: list[KnowledgeSourceItem]
    total: int


class KnowledgeCitation(BaseModel):
    """One citation on a tutor answer: where the context came from and how fresh it is."""

    title: str
    url: str
    fetched_at: str | None = None
    stale: bool = False


SEARCH_Q_MIN_LENGTH = SEARCH_QUERY_MIN_LENGTH
SEARCH_Q_MAX_LENGTH = SEARCH_QUERY_MAX_LENGTH

__all__ = [
    "KnowledgeCitation",
    "KnowledgeIngestRequest",
    "KnowledgeIngestResponse",
    "KnowledgeIngestResultItem",
    "KnowledgeSearchItem",
    "KnowledgeSearchResponse",
    "KnowledgeSourceItem",
    "KnowledgeSourceListResponse",
    "MAX_URL_LENGTH",
    "SEARCH_LIMIT_DEFAULT",
    "SEARCH_LIMIT_MAX",
    "SEARCH_Q_MAX_LENGTH",
    "SEARCH_Q_MIN_LENGTH",
    "SOURCES_LIMIT_DEFAULT",
    "SOURCES_LIMIT_MAX",
]
