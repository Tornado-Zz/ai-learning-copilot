"""GET /lessons, GET /lessons/{id}, PUT /lessons/{id}/progress (Sprint 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.lessons import (
    LessonDetailOut,
    LessonListResponse,
    LessonProgressResponse,
    LessonProgressUpdateRequest,
)
from app.services import lessons as lessons_service
from app.services import users as users_service

router = APIRouter(tags=["lessons"])

LESSON_ID_PATH = Path(..., ge=1, description="课程 id")


@router.get(
    "/lessons",
    response_model=LessonListResponse,
    summary="课程列表：元数据与当前用户进度，不含正文",
)
async def read_lessons(session: AsyncSession = Depends(get_db)) -> LessonListResponse:
    user = await users_service.get_single_user(session)
    return LessonListResponse.model_validate(
        await lessons_service.list_lessons(session, int(user["id"]))
    )


@router.get(
    "/lessons/{lesson_id}",
    response_model=LessonDetailOut,
    summary="课程详情：正文五块内容 + 当前用户进度（读取不写库）",
    responses={404: {"description": "课程不存在或未发布"}},
)
async def read_lesson(
    lesson_id: int = LESSON_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> LessonDetailOut:
    user = await users_service.get_single_user(session)
    return LessonDetailOut.model_validate(
        await lessons_service.get_lesson(session, int(user["id"]), lesson_id)
    )


@router.put(
    "/lessons/{lesson_id}/progress",
    response_model=LessonProgressResponse,
    summary="写课程进度：status 必填，self_assessment 上限 L2，不写 user_skill_levels",
    responses={
        404: {"description": "课程不存在或未发布"},
        422: {
            "description": "参数不合法（含 self_assessment > 2），"
            "或进度回退 COURSE_PROGRESS_REGRESSION（completed→in_progress 等，零写入）"
        },
    },
)
async def put_lesson_progress(
    payload: LessonProgressUpdateRequest,
    lesson_id: int = LESSON_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> LessonProgressResponse:
    user = await users_service.get_single_user(session)
    return LessonProgressResponse.model_validate(
        await lessons_service.save_progress(session, int(user["id"]), lesson_id, payload)
    )
