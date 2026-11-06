"""Research column endpoints: list entries, refresh from the catalog, analyse one.

GET  /news                     - 已入库的条目，按发布时间倒序
POST /news/refresh             - 从目录里的源抓一批；NEWS_ENABLED=false 时 403
GET  /news/{id}                - 单条详情
POST /news/{id}/analyze        - 让模型提炼摘要与要点；无 Key 时 503

抓取是显式动作，不是后台魔法：目录是封闭的（不接受客户端传 URL），
开关默认关闭，关闭时这条路由直接 403，不会有人偷偷出网。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.ai import get_ai_client
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.schemas.news import (
    NEWS_LIMIT_DEFAULT,
    NEWS_LIMIT_MAX,
    NewsAskRequest,
    NewsAskResponse,
    NewsItemOut,
    NewsListResponse,
    NewsRefreshResponse,
    NewsRefreshSourceStat,
)
from app.services import news as news_service
from app.services.ai_client import DeepSeekClient

router = APIRouter(tags=["news"])

NEWS_ID_PATH = Path(..., ge=1, description="专栏条目的 id")
NEWS_FETCH_TIMEOUT_SECONDS = 20.0
NEWS_USER_AGENT = "ai-learning-copilot/1.0 (+local research column)"


async def default_fetcher(url: str) -> str:
    """Plain GET for one catalog URL. Overridden in tests; never takes a client URL."""
    async with httpx.AsyncClient(
        timeout=NEWS_FETCH_TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        response = await client.get(url, headers={"User-Agent": NEWS_USER_AGENT})
        response.raise_for_status()
        return response.text


def get_news_fetcher() -> Callable[[str], Awaitable[str]]:
    return default_fetcher


def _require_enabled() -> None:
    if not get_settings().news_enabled:
        raise ApiError(
            status_code=403,
            code="NEWS_DISABLED",
            message="研究专栏抓取未启用：请先在 apps/api/.env 里设置 NEWS_ENABLED=true 并重启后端",
        )


def _to_out(item: dict) -> NewsItemOut:
    return NewsItemOut(**item)


def _not_found() -> ApiError:
    return ApiError(status_code=404, code="NOT_FOUND", message="专栏条目不存在")


@router.get("/news", response_model=NewsListResponse)
async def list_news(
    limit: int = Query(NEWS_LIMIT_DEFAULT, ge=1, le=NEWS_LIMIT_MAX),
    source: str | None = Query(None, description="只看某个源，如 hn / arxiv-ai"),
    session: AsyncSession = Depends(get_db),
) -> NewsListResponse:
    settings = get_settings()
    items = await news_service.list_items(session, limit=limit, source_key=source)
    return NewsListResponse(
        items=[_to_out(item) for item in items],
        total=len(items),
        sources=settings.news_source_key_list,
        enabled=settings.news_enabled,
    )


@router.post("/news/refresh", response_model=NewsRefreshResponse)
async def refresh_news(
    session: AsyncSession = Depends(get_db),
    fetcher: Callable[[str], Awaitable[str]] = Depends(get_news_fetcher),
) -> NewsRefreshResponse:
    _require_enabled()
    settings = get_settings()
    specs = news_service.resolve_sources(settings.news_sources)
    if not specs:
        raise ApiError(
            status_code=400,
            code="NEWS_NO_SOURCES",
            message="NEWS_SOURCES 里没有任何可识别的源",
        )
    result = await news_service.refresh(
        session,
        specs=specs,
        limit_per_source=settings.news_limit_per_source,
        fetcher=fetcher,
    )
    return NewsRefreshResponse(
        sources=[NewsRefreshSourceStat(**stat) for stat in result["sources"]],
        items_before=result["items_before"],
        items_after=result["items_after"],
    )


@router.get("/news/{item_id}", response_model=NewsItemOut)
async def get_news_item(
    item_id: int = NEWS_ID_PATH, session: AsyncSession = Depends(get_db)
) -> NewsItemOut:
    item = await news_service.get_item(session, item_id)
    if item is None:
        raise _not_found()
    return _to_out(item)


@router.post("/news/{item_id}/analyze", response_model=NewsItemOut)
async def analyze_news_item(
    item_id: int = NEWS_ID_PATH,
    session: AsyncSession = Depends(get_db),
    client: DeepSeekClient = Depends(get_ai_client),
    fetcher: Callable[[str], Awaitable[str]] = Depends(get_news_fetcher),
) -> NewsItemOut:
    if not client.configured:
        raise ApiError(
            status_code=503,
            code="AI_UNAVAILABLE",
            message="未配置 DEEPSEEK_API_KEY，无法生成重点解析",
        )
    item = await news_service.get_item(session, item_id)
    if item is None:
        raise _not_found()
    analyzed = await news_service.analyze(
        session,
        item=item,
        client=client,
        article_fetcher=fetcher,
        article_limit=get_settings().news_article_chars,
    )
    return _to_out(analyzed)


@router.post("/news/{item_id}/ask", response_model=NewsAskResponse)
async def ask_news_item(
    payload: NewsAskRequest,
    item_id: int = NEWS_ID_PATH,
    session: AsyncSession = Depends(get_db),
    client: DeepSeekClient = Depends(get_ai_client),
    fetcher: Callable[[str], Awaitable[str]] = Depends(get_news_fetcher),
) -> NewsAskResponse:
    if not client.configured:
        raise ApiError(
            status_code=503,
            code="AI_UNAVAILABLE",
            message="未配置 DEEPSEEK_API_KEY，无法就这条提问",
        )
    item = await news_service.get_item(session, item_id)
    if item is None:
        raise _not_found()
    result = await news_service.ask_about_item(
        item=item,
        question=payload.question,
        client=client,
        article_fetcher=fetcher,
        article_limit=get_settings().news_article_chars,
    )
    return NewsAskResponse(**result)
