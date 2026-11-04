"""AI tutor endpoints (Sprint 4): one call, one log.

The transport seam is mounted as a FastAPI dependency so a test overrides
get_ai_client and no suite can reach the provider: by default the client holds the
configured key and the httpx transport, under test it holds a stub transport.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.schemas.ai import (
    INTERACTIONS_LIMIT_DEFAULT,
    INTERACTIONS_LIMIT_MAX,
    AiInteractionListResponse,
    TutorRequest,
    TutorResponseOut,
)
from app.services import ai_tutor
from app.services import users as users_service
from app.services.ai_client import DeepSeekClient

router = APIRouter(tags=["ai"])


def get_ai_client() -> DeepSeekClient:
    """Per-request client built from settings. Overridden in tests with a stub."""
    settings = get_settings()
    return DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )


@router.post(
    "/ai/tutor",
    response_model=TutorResponseOut,
    summary="向 AI 导师提一个问题：按 assistance_level 控制帮助程度，每次调用都记一行用量",
    responses={
        404: {"description": "context 里的课程 / 练习 id 不存在"},
        422: {"description": "question 为空或超过 2000 字，assistance_level 不在枚举内"},
        429: {"description": "当日累计 token 已达 AI_DAILY_TOKEN_LIMIT，未发起任何上游请求"},
        502: {"description": "上游返回错误或无法解析，已落库 status='error'"},
        503: {"description": "未配置 DEEPSEEK_API_KEY，未发起任何上游请求"},
        504: {"description": "上游超时，已落库 status='timeout'"},
    },
)
async def create_tutor_answer(
    payload: TutorRequest,
    session: AsyncSession = Depends(get_db),
    client: DeepSeekClient = Depends(get_ai_client),
) -> TutorResponseOut:
    user = await users_service.get_single_user(session)
    return TutorResponseOut.model_validate(
        await ai_tutor.answer_question(session, int(user["id"]), payload, client)
    )


@router.get(
    "/ai/interactions",
    response_model=AiInteractionListResponse,
    summary="AI 互动历史（新到旧）：只有问题预览与用量，不含回答全文",
)
async def read_ai_interactions(
    limit: int = Query(
        default=INTERACTIONS_LIMIT_DEFAULT,
        ge=1,
        le=INTERACTIONS_LIMIT_MAX,
        description="返回条数上限",
    ),
    session: AsyncSession = Depends(get_db),
) -> AiInteractionListResponse:
    user = await users_service.get_single_user(session)
    return AiInteractionListResponse.model_validate(
        await ai_tutor.list_interactions(session, int(user["id"]), limit)
    )
