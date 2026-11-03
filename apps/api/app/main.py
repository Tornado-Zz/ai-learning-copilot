"""Application factory, middleware, CORS and router mounting."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app import SERVICE_NAME, __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.logging import configure_logging

logger = logging.getLogger("app.main")
request_logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status_code and duration_ms. Never logs bodies or headers."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int(round((time.perf_counter() - started) * 1000))
            request_logger.exception(
                "method=%s path=%s status_code=500 duration_ms=%d",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = int(round((time.perf_counter() - started) * 1000))
        request_logger.info(
            "method=%s path=%s status_code=%d duration_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "api starting environment=%s api_v1_prefix=%s ai_configured=%s",
        settings.app_env,
        settings.api_v1_prefix,
        settings.ai_configured,
    )
    logger.info(
        "database connection is lazy; readiness is reported by %s/ready",
        settings.api_v1_prefix,
    )
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("api stopped")


def create_app() -> FastAPI:
    """Build a fully configured FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(
        title="AI Learning Copilot API",
        version=__version__,
        description=f"{SERVICE_NAME} - Sprint 0 skeleton",
        lifespan=lifespan,
    )
    # Added first => innermost. CORS is added last so preflight and error
    # responses also carry the CORS headers.
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
