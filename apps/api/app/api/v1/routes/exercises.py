"""Exercise endpoints: catalogue, detail, submissions, history (Sprint 3 stage B).

B2: submitting code never runs it. The response says what the static rules found
and, if the learner claimed a local result, that the claim is unverified.

B1: every judgement is labelled either 已验证（静态规则） or 未验证（自检）; the
words "verified" and "已通过校验" are deliberately absent from this surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.exercises import (
    RECENT_LIMIT_DEFAULT,
    RECENT_LIMIT_MAX,
    ExerciseDetailOut,
    ExerciseListResponse,
    RecentSubmissionsResponse,
    SubmissionCreateRequest,
    SubmissionHistoryResponse,
    SubmissionJudgedOut,
)
from app.services import exercises as exercises_service
from app.services import users as users_service

router = APIRouter(tags=["exercises"])

EXERCISE_ID_PATH = Path(..., ge=1, description="练习 id")
# One exercise never accumulates more than this many visible history rows in one
# response; total still reports every attempt.
HISTORY_LIMIT = 50


@router.get(
    "/exercises",
    response_model=ExerciseListResponse,
    summary="练习列表：可按 lesson_id 过滤，含当前用户最近一次提交状态与通过数",
)
async def read_exercises(
    lesson_id: int | None = Query(default=None, ge=1, description="只看某一节课的练习"),
    session: AsyncSession = Depends(get_db),
) -> ExerciseListResponse:
    user = await users_service.get_single_user(session)
    return ExerciseListResponse.model_validate(
        await exercises_service.list_exercises(session, int(user["id"]), lesson_id)
    )


@router.get(
    "/exercises/{exercise_id}",
    response_model=ExerciseDetailOut,
    summary="练习详情：题目、起始代码与可见自检用例（不含 required_patterns / expected_output 等答案键）",
    responses={404: {"description": "练习不存在或未发布"}},
)
async def read_exercise(
    exercise_id: int = EXERCISE_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> ExerciseDetailOut:
    user = await users_service.get_single_user(session)
    return ExerciseDetailOut.model_validate(
        await exercises_service.get_exercise(session, int(user["id"]), exercise_id)
    )


@router.post(
    "/exercises/{exercise_id}/submissions",
    response_model=SubmissionJudgedOut,
    status_code=status.HTTP_201_CREATED,
    summary="提交一次练习：静态规则或自检判定，不执行代码，不写 user_skill_levels",
    responses={
        404: {"description": "练习不存在或未发布"},
        409: {"description": "同一题的提交序号并发冲突，重试即可"},
        422: {"description": "code_text 为空或超过长度上限"},
    },
)
async def create_submission(
    payload: SubmissionCreateRequest,
    exercise_id: int = EXERCISE_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> SubmissionJudgedOut:
    user = await users_service.get_single_user(session)
    return SubmissionJudgedOut.model_validate(
        await exercises_service.create_submission(
            session, int(user["id"]), exercise_id, payload
        )
    )


@router.get(
    "/exercises/{exercise_id}/submissions",
    response_model=SubmissionHistoryResponse,
    summary="该题的提交历史（新到旧，含判定方式与证据标签；total 为全部尝试数）",
    responses={404: {"description": "练习不存在或未发布"}},
)
async def read_exercise_submissions(
    exercise_id: int = EXERCISE_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> SubmissionHistoryResponse:
    user = await users_service.get_single_user(session)
    return SubmissionHistoryResponse.model_validate(
        await exercises_service.list_exercise_submissions(
            session, int(user["id"]), exercise_id, HISTORY_LIMIT
        )
    )


@router.get(
    "/submissions/recent",
    response_model=RecentSubmissionsResponse,
    summary="最近提交（跨题，新到旧，默认 20 条）：每条的判定方式与证据标签",
)
async def read_recent_submissions(
    limit: int = Query(
        default=RECENT_LIMIT_DEFAULT,
        ge=1,
        le=RECENT_LIMIT_MAX,
        description="返回条数上限",
    ),
    session: AsyncSession = Depends(get_db),
) -> RecentSubmissionsResponse:
    user = await users_service.get_single_user(session)
    return RecentSubmissionsResponse.model_validate(
        await exercises_service.list_recent_submissions(session, int(user["id"]), limit)
    )
