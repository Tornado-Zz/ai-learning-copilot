"""Unified error envelope (Sprint 1A contract 6.6), request ids and handlers."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

REQUEST_ID_HEADER = "X-Request-ID"

VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
CONFLICT = "CONFLICT"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
# A study plan item that is already done/skipped/expired cannot be rewritten.
PLAN_ITEM_LOCKED = "PLAN_ITEM_LOCKED"
# learning_progress only moves forward: a regression is refused with zero writes.
COURSE_PROGRESS_REGRESSION = "COURSE_PROGRESS_REGRESSION"
DB_UNAVAILABLE = "DB_UNAVAILABLE"
INTERNAL_ERROR = "INTERNAL_ERROR"
# Sprint 4 AI tutor. The three contract codes are refusals the learner can act
# on; AI_UPSTREAM_ERROR covers "the provider answered, but not with an answer".
AI_UNAVAILABLE = "AI_UNAVAILABLE"
AI_TIMEOUT = "AI_TIMEOUT"
AI_QUOTA_EXCEEDED = "AI_QUOTA_EXCEEDED"
AI_UPSTREAM_ERROR = "AI_UPSTREAM_ERROR"

_CODE_BY_STATUS = {
    404: NOT_FOUND,
    409: CONFLICT,
    422: VALIDATION_ERROR,
    503: DB_UNAVAILABLE,
}


class ApiError(Exception):
    """A business failure rendered with the frozen unified body."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})


def validation_error(message: str, field: str, reason: str, **extra: Any) -> ApiError:
    """422 with the {field, reason, ...} details shape used by contract 6.7."""
    return ApiError(422, VALIDATION_ERROR, message, {"field": field, "reason": reason, **extra})


def idempotency_conflict(message: str, details: Mapping[str, Any] | None = None) -> ApiError:
    """409 when one attempt_token is reused for a different submission."""
    return ApiError(409, IDEMPOTENCY_CONFLICT, message, details)


def ai_unavailable() -> ApiError:
    """503: no API key configured. No upstream request is ever attempted."""
    return ApiError(
        503,
        AI_UNAVAILABLE,
        "AI 导师暂时不可用：服务端未配置模型密钥",
        {"reason": "not_configured"},
    )


def ai_timeout(timeout_seconds: float) -> ApiError:
    """504: the upstream call exceeded AI_TIMEOUT_SECONDS."""
    return ApiError(
        504,
        AI_TIMEOUT,
        "AI 导师响应超时，请稍后重试",
        {"reason": "upstream_timeout", "timeout_seconds": timeout_seconds},
    )


def ai_quota_exceeded(used_tokens: int, daily_token_limit: int) -> ApiError:
    """429: today's token budget is spent. No upstream request is attempted."""
    return ApiError(
        429,
        AI_QUOTA_EXCEEDED,
        "今日 AI 用量已达上限，请明天再试",
        {"reason": "daily_token_limit", "used_tokens": used_tokens, "daily_token_limit": daily_token_limit},
    )


def ai_upstream_error(reason: str) -> ApiError:
    """502: the provider was reachable but the call did not produce an answer."""
    return ApiError(
        502,
        AI_UPSTREAM_ERROR,
        "AI 导师上游调用失败，请稍后重试",
        {"reason": reason},
    )


def new_request_id() -> str:
    """12 lowercase hex characters, unique per request."""
    return uuid.uuid4().hex[:12]


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) and request_id else new_request_id()


def _envelope(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None,
) -> JSONResponse:
    request_id = get_request_id(request)
    payload = {
        "error": {"code": code, "message": message, "details": dict(details or {})},
        "request_id": request_id,
    }
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={REQUEST_ID_HEADER: request_id},
    )


async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return _envelope(request, exc.status_code, exc.code, exc.message, exc.details)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _CODE_BY_STATUS.get(exc.status_code, INTERNAL_ERROR if exc.status_code >= 500 else NOT_FOUND)
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else "请求无法处理"
    return _envelope(request, exc.status_code, code, message, {})


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details: dict[str, Any] = {}
    errors = exc.errors()
    if errors:
        first = errors[0]
        location = [str(part) for part in first.get("loc", ()) if part != "body"]
        details = {
            "field": location[-1] if location else "body",
            "reason": str(first.get("type", "invalid_value")),
        }
    return _envelope(request, 422, VALIDATION_ERROR, "请求参数不合法", details)


async def _handle_database_error(request: Request, exc: Exception) -> JSONResponse:
    logger.warning(
        "database_unavailable request_id=%s error=%s",
        get_request_id(request),
        type(exc).__name__,
    )
    return _envelope(request, 503, DB_UNAVAILABLE, "数据库暂时不可用，请稍后重试", {})


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error request_id=%s", get_request_id(request))
    return _envelope(request, 500, INTERNAL_ERROR, "服务内部错误，请稍后重试", {})


def install_error_handlers(application: FastAPI) -> None:
    """Every business route answers with the same envelope; health/ready keep theirs."""
    application.add_exception_handler(ApiError, _handle_api_error)
    application.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    application.add_exception_handler(RequestValidationError, _handle_validation_error)
    application.add_exception_handler(SQLAlchemyError, _handle_database_error)
    # A refused connection surfaces as OSError before SQLAlchemy wraps anything,
    # so an unreachable database must be caught here as well to stay a 503.
    application.add_exception_handler(OSError, _handle_database_error)
    application.add_exception_handler(Exception, _handle_unexpected)
