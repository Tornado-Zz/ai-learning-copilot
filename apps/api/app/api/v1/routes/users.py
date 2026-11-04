"""GET /users/me and PUT /users/me/profile (contract 6.1, 6.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.users import MeResponse, ProfileUpdateRequest
from app.services import users as users_service

router = APIRouter(tags=["users"])


@router.get(
    "/users/me",
    response_model=MeResponse,
    summary="当前用户、学习档案与六域等级快照",
)
async def read_me(session: AsyncSession = Depends(get_db)) -> MeResponse:
    return MeResponse.model_validate(await users_service.load_me(session))


@router.put(
    "/users/me/profile",
    response_model=MeResponse,
    summary="更新学习档案（study_days / daily_minutes / timezone）",
)
async def put_profile(
    payload: ProfileUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> MeResponse:
    return MeResponse.model_validate(await users_service.update_profile(session, payload))
