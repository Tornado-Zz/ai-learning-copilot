"""Capstone submission endpoints: draft -> submitted -> reviewed (v0.1.3).

POST   /capstone/submissions              - 新建草稿（201）
PATCH  /capstone/submissions/{id}         - 改草稿；非 draft 一律 409
GET    /capstone/submissions              - 列表：created_at DESC, id DESC
GET    /capstone/submissions/{id}         - 详情；别人的行不存在
POST   /capstone/submissions/{id}/submit  - draft -> submitted，同事务写 readiness_snapshot
POST   /capstone/submissions/{id}/review  - submitted -> reviewed，reviewer 恒为 'self'

诚实性口径：本版本是单用户本地应用，不存在第三方评审者。评审永远由本人给出，
请求体必须显式 self_review_confirmed = true，响应里 reviewer 只会是 'self'。

单用户语义与其余接口一致：目标用户永远是种子用户；别人的行一律 404 NOT_FOUND。
状态机与事务内容在 app.services.capstone，这里只做 DI、提交事务与响应模型。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.capstone import (
    CAPSTONE_LIMIT_DEFAULT,
    CAPSTONE_LIMIT_MAX,
    CapstoneReviewRequest,
    CapstoneSubmissionCreateRequest,
    CapstoneSubmissionListResponse,
    CapstoneSubmissionOut,
    CapstoneSubmissionUpdateRequest,
)
from app.services import capstone as capstone_service
from app.services import users as users_service

# 前缀仍是 /api/v1/capstone；GET /capstone/readiness 留在 progress 路由里。
router = APIRouter(prefix="/capstone", tags=["capstone"])

SUBMISSION_ID_PATH = Path(..., ge=1, description="结业作品 id")

SUBMIT_RESPONSES = {
    404: {"description": "作品不存在，或不属于当前用户"},
    409: {"description": "CAPSTONE_INVALID_STATE：只有 draft 可以提交"},
}
REVIEW_RESPONSES = {
    400: {"description": "SELF_REVIEW_NOT_CONFIRMED：self_review_confirmed 不为 true"},
    404: {"description": "作品不存在，或不属于当前用户"},
    409: {"description": "CAPSTONE_INVALID_STATE：只有 submitted 可以评审"},
    422: {"description": "verdict 不是 pass / needs_work"},
}


@router.post(
    "/submissions",
    response_model=CapstoneSubmissionOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建结业作品草稿（self_checks 默认空数组，其余评审字段全为 null）",
    responses={422: {"description": "title / summary / run_instructions 为空或超长，repo_url 不是 http(s) 链接"}},
)
async def create_capstone_submission(
    payload: CapstoneSubmissionCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> CapstoneSubmissionOut:
    user = await users_service.get_single_user(session)
    result = await capstone_service.create_submission(
        session, user_id=int(user["id"]), payload=payload
    )
    await session.commit()
    return CapstoneSubmissionOut.model_validate(result)


@router.get(
    "/submissions",
    response_model=CapstoneSubmissionListResponse,
    summary="结业作品列表：按 created_at DESC, id DESC，total 不受 limit 影响",
)
async def read_capstone_submissions(
    limit: int = Query(
        default=CAPSTONE_LIMIT_DEFAULT,
        ge=1,
        le=CAPSTONE_LIMIT_MAX,
        description="返回条数上限",
    ),
    session: AsyncSession = Depends(get_db),
) -> CapstoneSubmissionListResponse:
    user = await users_service.get_single_user(session)
    return CapstoneSubmissionListResponse.model_validate(
        await capstone_service.list_submissions(
            session, user_id=int(user["id"]), limit=limit
        )
    )


@router.get(
    "/submissions/{submission_id}",
    response_model=CapstoneSubmissionOut,
    summary="结业作品详情（不存在或非本人 -> 404 NOT_FOUND）",
    responses={404: {"description": "作品不存在，或不属于当前用户"}},
)
async def read_capstone_submission(
    submission_id: int = SUBMISSION_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> CapstoneSubmissionOut:
    user = await users_service.get_single_user(session)
    return CapstoneSubmissionOut.model_validate(
        await capstone_service.get_submission(
            session, user_id=int(user["id"]), submission_id=submission_id
        )
    )


@router.patch(
    "/submissions/{submission_id}",
    response_model=CapstoneSubmissionOut,
    summary="修改结业作品：只有 draft 可改，其余状态 409 CAPSTONE_INVALID_STATE（零写入）",
    responses={
        404: {"description": "作品不存在，或不属于当前用户"},
        409: {"description": "CAPSTONE_INVALID_STATE：已提交或已评审的作品不能修改"},
        422: {"description": "字段为空或超长，repo_url 不是 http(s) 链接"},
    },
)
async def update_capstone_submission(
    payload: CapstoneSubmissionUpdateRequest,
    submission_id: int = SUBMISSION_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> CapstoneSubmissionOut:
    user = await users_service.get_single_user(session)
    result = await capstone_service.update_submission(
        session, user_id=int(user["id"]), submission_id=submission_id, payload=payload
    )
    await session.commit()
    return CapstoneSubmissionOut.model_validate(result)


@router.post(
    "/submissions/{submission_id}/submit",
    response_model=CapstoneSubmissionOut,
    summary="提交作品：draft -> submitted，同事务写入 readiness_snapshot 与 submitted_at",
    responses=SUBMIT_RESPONSES,
)
async def submit_capstone_submission(
    submission_id: int = SUBMISSION_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> CapstoneSubmissionOut:
    user = await users_service.get_single_user(session)
    result = await capstone_service.submit_submission(
        session, user_id=int(user["id"]), submission_id=submission_id
    )
    await session.commit()
    return CapstoneSubmissionOut.model_validate(result)


@router.post(
    "/submissions/{submission_id}/review",
    response_model=CapstoneSubmissionOut,
    summary="自评作品：submitted -> reviewed，写 verdict / reviewer='self' / note / reviewed_at",
    responses=REVIEW_RESPONSES,
)
async def review_capstone_submission(
    payload: CapstoneReviewRequest,
    submission_id: int = SUBMISSION_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> CapstoneSubmissionOut:
    user = await users_service.get_single_user(session)
    result = await capstone_service.review_submission(
        session,
        user_id=int(user["id"]),
        submission_id=submission_id,
        payload=payload,
    )
    await session.commit()
    return CapstoneSubmissionOut.model_validate(result)
