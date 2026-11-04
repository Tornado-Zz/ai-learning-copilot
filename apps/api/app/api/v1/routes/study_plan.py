"""Study plan endpoints: preview (in memory), persisted week plan and generation.

GET /study-plan/preview   - computed in memory, persisted=false, writes nothing (contract 6.5)
GET /study-plan           - this week's persisted plan, grouped by date
POST /study-plan/generate - generate/refresh this week's plan and persist it (R1-R6)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.study_plan import (
    PlanItemResponse,
    PlanItemUpdateRequest,
    StudyPlanGeneratedResponse,
    StudyPlanPreviewResponse,
    StudyPlanResponse,
)
from app.services import users as users_service


async def _current_user_id(session: AsyncSession) -> int:
    """单用户语义：计划生成需要显式 user_id，路由在这里解析一次。"""
    return int((await users_service.get_single_user(session))["id"])
from app.services import study_plan as study_plan_service

router = APIRouter(tags=["study-plan"])

TIMEZONE_NOT_CONFIRMED = {409: {"description": "时区未确认，不得展示或生成今日/本周推导"}}


@router.get(
    "/study-plan/preview",
    response_model=StudyPlanPreviewResponse,
    summary="本周计划预览（内存计算，persisted 恒为 false）",
    responses=TIMEZONE_NOT_CONFIRMED,
)
async def read_preview(session: AsyncSession = Depends(get_db)) -> StudyPlanPreviewResponse:
    return StudyPlanPreviewResponse.model_validate(
        await study_plan_service.build_preview(session)
    )


@router.get(
    "/study-plan",
    response_model=StudyPlanResponse,
    summary="本周已落库计划（按日期分组，含 rationale；读取不生成）",
    responses=TIMEZONE_NOT_CONFIRMED,
)
async def read_plan(session: AsyncSession = Depends(get_db)) -> StudyPlanResponse:
    return StudyPlanResponse.model_validate(await study_plan_service.read_plan(session))


@router.post(
    "/study-plan/generate",
    response_model=StudyPlanGeneratedResponse,
    summary="生成/刷新本周计划并落库（同周重复生成行数不变，done/skipped 行不被改写）",
    responses=TIMEZONE_NOT_CONFIRMED,
)
async def generate_plan(
    session: AsyncSession = Depends(get_db),
) -> StudyPlanGeneratedResponse:
    return StudyPlanGeneratedResponse.model_validate(
        await study_plan_service.generate_plan(session, user_id=await _current_user_id(session))
    )


@router.patch(
    "/study-plan/items/{item_id}",
    response_model=PlanItemResponse,
    summary="把一条计划项标记为 done / skipped（scheduled 之外的状态一律 409 PLAN_ITEM_LOCKED）",
    responses={
        404: {"description": "计划项不存在，或不属于当前用户"},
        409: {"description": "该计划项已是终态，不允许改写"},
        422: {"description": "status 只能是 done 或 skipped"},
    },
)
async def patch_plan_item(
    payload: PlanItemUpdateRequest,
    item_id: int = Path(..., ge=1, description="计划项 id"),
    session: AsyncSession = Depends(get_db),
) -> PlanItemResponse:
    user = await users_service.get_single_user(session)
    return PlanItemResponse.model_validate(
        await study_plan_service.update_plan_item(
            session, user_id=int(user["id"]), item_id=item_id, status=payload.status
        )
    )
