"""POST /diagnostics, GET /diagnostics/paper|history|attempts (contract 6.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import validation_error
from app.schemas.diagnostics import (
    DiagnosticAttemptDetailResponse,
    DiagnosticHistoryResponse,
    DiagnosticPaperResponse,
    DiagnosticSubmitRequest,
    DiagnosticSubmitResponse,
)
from app.services import diagnostics as diagnostics_service
from app.services import users as users_service
from app.services.question_set import (
    QUESTION_SET_VERSION,
    RULE_VERSION,
    TOTAL_QUESTIONS,
    paper_questions,
)

router = APIRouter(tags=["diagnostics"])


@router.post(
    "/diagnostics",
    response_model=DiagnosticSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交 20 题诊断：201 新批次 / 200 同 token 同内容回放 / 409 内容冲突",
)
async def submit_diagnostics(
    payload: DiagnosticSubmitRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> DiagnosticSubmitResponse:
    user = await users_service.get_single_user(session)
    outcome = await diagnostics_service.submit_diagnostic(
        session,
        user_id=int(user["id"]),
        attempt_token=payload.attempt_token,
        question_set_version=payload.question_set_version,
        rule_version=payload.rule_version,
        answers={question_id: answer.choice for question_id, answer in payload.answers.items()},
    )
    if outcome.replayed:
        # Same token, same content: the stored batch is replayed as-is.
        response.status_code = status.HTTP_200_OK
    return DiagnosticSubmitResponse.model_validate(outcome.attempt)


@router.get(
    "/diagnostics/paper",
    response_model=DiagnosticPaperResponse,
    summary="20 题题面：后端是题集的唯一来源，响应不含任何答案键",
)
async def read_paper(
    version: str = Query(QUESTION_SET_VERSION, description="题集版本，当前仅支持 v1"),
) -> DiagnosticPaperResponse:
    if version not in diagnostics_service.SUPPORTED_QUESTION_SET_VERSIONS:
        raise validation_error(
            "不支持的题集版本",
            "version",
            "unsupported_version",
            supported=list(diagnostics_service.SUPPORTED_QUESTION_SET_VERSIONS),
        )
    return DiagnosticPaperResponse.model_validate(
        {
            "question_set_version": QUESTION_SET_VERSION,
            "rule_version": RULE_VERSION,
            "total": TOTAL_QUESTIONS,
            "questions": list(paper_questions()),
        }
    )


@router.get(
    "/diagnostics/attempts/{attempt_id}",
    response_model=DiagnosticAttemptDetailResponse,
    summary="已提交批次的逐题判定依据：题库现取题面，答案键只在这里出现",
)
async def read_attempt(
    attempt_id: int,
    session: AsyncSession = Depends(get_db),
) -> DiagnosticAttemptDetailResponse:
    user = await users_service.get_single_user(session)
    detail = await diagnostics_service.attempt_detail(
        session, user_id=int(user["id"]), attempt_id=attempt_id
    )
    return DiagnosticAttemptDetailResponse.model_validate(detail)


@router.get(
    "/diagnostics/history",
    response_model=DiagnosticHistoryResponse,
    summary="该用户的诊断批次历史（追加式，最新在前）",
)
async def read_history(
    limit: int = Query(diagnostics_service.DEFAULT_HISTORY_LIMIT, description="每页条数，1–100"),
    cursor: int | None = Query(None, description="上一页最后一条的 attempt id"),
    session: AsyncSession = Depends(get_db),
) -> DiagnosticHistoryResponse:
    diagnostics_service.validate_history_query(limit, cursor)
    user = await users_service.get_single_user(session)
    result = await diagnostics_service.list_history(
        session, int(user["id"]), limit=limit, cursor=cursor
    )
    return DiagnosticHistoryResponse.model_validate(result)
