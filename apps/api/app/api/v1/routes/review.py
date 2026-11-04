"""Review endpoints: the mistake book, one result per attempt and the summary.

GET  /review/items              - 错题本列表，默认 next_review_on ASC, id ASC；due=1 只看今天及逾期
POST /review/items/{id}/result  - 一次复习结果：passed=false 走答错规则、true 走答对规则
GET  /review/summary            - pending / due_today / done / next_due_on（无数据全 0）

单用户语义与其余接口一致：目标用户永远是种子用户；别人的行一律 404 NOT_FOUND。
调度规则本身在 app.services.review，这里只做 DI、提交事务与响应模型。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.review import (
    REVIEW_LIMIT_DEFAULT,
    REVIEW_LIMIT_MAX,
    ReviewItemsResponse,
    ReviewResultOut,
    ReviewResultRequest,
    ReviewSummaryOut,
)
from app.services import review as review_service
from app.services import users as users_service

router = APIRouter(tags=["review"])

REVIEW_ID_PATH = Path(..., ge=1, description="复习项 id")


@router.get(
    "/review/items",
    response_model=ReviewItemsResponse,
    summary="错题本（默认按 next_review_on, id 升序；due=1 只看今天及逾期）",
)
async def read_review_items(
    due: bool = Query(default=False, description="true/1 时只返回到期待复习的条目"),
    limit: int = Query(
        default=REVIEW_LIMIT_DEFAULT,
        ge=1,
        le=REVIEW_LIMIT_MAX,
        description="返回条数上限",
    ),
    session: AsyncSession = Depends(get_db),
) -> ReviewItemsResponse:
    user = await users_service.get_single_user(session)
    return ReviewItemsResponse.model_validate(
        await review_service.list_items(
            session, user_id=int(user["id"]), due_only=due, limit=limit
        )
    )


@router.get(
    "/review/summary",
    response_model=ReviewSummaryOut,
    summary="错题本汇总：pending / due_today / done / next_due_on（无数据时全 0、next_due_on=null）",
)
async def read_review_summary(session: AsyncSession = Depends(get_db)) -> ReviewSummaryOut:
    user = await users_service.get_single_user(session)
    return ReviewSummaryOut.model_validate(
        await review_service.summary(session, user_id=int(user["id"]))
    )


@router.post(
    "/review/items/{item_id}/result",
    response_model=ReviewResultOut,
    summary="记录一次复习结果：passed=false 重置（明天再复习），true 推进（3/7/14 天）",
    responses={404: {"description": "复习项不存在，或不属于当前用户"}},
)
async def record_review_result(
    payload: ReviewResultRequest,
    item_id: int = REVIEW_ID_PATH,
    session: AsyncSession = Depends(get_db),
) -> ReviewResultOut:
    user = await users_service.get_single_user(session)
    # 服务层不提交；这里提交这一条独立写操作。失败时不显式回滚：依赖在请求结束时
    # 关闭会话即回滚，而显式 rollback 会连带丢弃同一事务里已经完成的写操作。
    result = await review_service.record_result(
        session, user_id=int(user["id"]), item_id=item_id, passed=payload.passed
    )
    await session.commit()
    return ReviewResultOut.model_validate(result)
