"""GET /progress/overview and GET /capstone/readiness (v0.1.1: real data).

Both endpoints read only. Neither computes anything the learner has not done: the
aggregation lives in app.services.progress, and a user without rows gets zeros.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.progress import CapstoneReadinessResponse, ProgressOverviewResponse
from app.services import progress as progress_service
from app.services import users as users_service

router = APIRouter(tags=["progress"])


@router.get(
    "/progress/overview",
    response_model=ProgressOverviewResponse,
    summary="学习进度总览：课程 / 本周计划 / 练习 / 能力域 / 最近 7 天活跃（全部为真实聚合）",
)
async def read_overview(session: AsyncSession = Depends(get_db)) -> ProgressOverviewResponse:
    user = await users_service.get_single_user(session)
    return ProgressOverviewResponse.model_validate(
        await progress_service.read_overview(
            session, user_id=int(user["id"]), timezone_name=str(user["timezone"])
        )
    )


@router.get(
    "/capstone/readiness",
    response_model=CapstoneReadinessResponse,
    summary="结业作品达标情况：四条口径全部由真实学习数据推导（ready = 全部 met）",
)
async def read_capstone_readiness(
    session: AsyncSession = Depends(get_db),
) -> CapstoneReadinessResponse:
    user = await users_service.get_single_user(session)
    return CapstoneReadinessResponse.model_validate(
        await progress_service.read_capstone_readiness(session, int(user["id"]))
    )
