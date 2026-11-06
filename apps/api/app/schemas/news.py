"""Research column payloads.

Every field the AI fills in carries its own status, so the UI can tell
"not analysed yet" apart from "analysis failed" apart from "no key configured".
"""

from __future__ import annotations

from pydantic import BaseModel, Field

NEWS_LIMIT_DEFAULT = 20
NEWS_LIMIT_MAX = 100


class NewsItemOut(BaseModel):
    id: int
    source_key: str
    source_kind: str
    title: str
    url: str
    excerpt: str
    published_at: str | None = None
    fetched_at: str | None = None
    ai_status: str
    ai_summary: str | None = None
    ai_key_points: list[str] = Field(default_factory=list)
    ai_model: str | None = None
    ai_tokens: int | None = None
    ai_updated_at: str | None = None


class NewsListResponse(BaseModel):
    items: list[NewsItemOut]
    total: int
    sources: list[str]
    enabled: bool


class NewsRefreshSourceStat(BaseModel):
    source: str
    status: str
    fetched: int | None = None
    inserted: int | None = None
    detail: str | None = None


class NewsRefreshResponse(BaseModel):
    sources: list[NewsRefreshSourceStat]
    items_before: int
    items_after: int


class NewsAskRequest(BaseModel):
    """一个问题。长度上限与其它自由文本输入一致，避免把整篇文章塞进来。"""

    question: str = Field(min_length=2, max_length=500)


class NewsAskResponse(BaseModel):
    answer: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    used_article: bool
