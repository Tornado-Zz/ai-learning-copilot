"""Liveness and readiness endpoints. Field names are a frozen contract."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import SERVICE_NAME, __version__
from app.core.config import get_settings
from app.core.db import ping_db

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str = Field(examples=[SERVICE_NAME])
    version: str = Field(examples=[__version__])
    environment: str = Field(examples=["local"])
    timestamp: datetime = Field(description="ISO 8601 timestamp in UTC")
    ai_configured: bool = Field(description="True only when DEEPSEEK_API_KEY is set")


class DatabaseCheck(BaseModel):
    status: str = Field(examples=["connected", "disconnected"])
    latency_ms: int | None
    detail: str | None


class ReadyChecks(BaseModel):
    database: DatabaseCheck


class ReadyResponse(BaseModel):
    status: str = Field(examples=["ready", "not_ready"])
    checks: ReadyChecks


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    """Always 200: it reports configuration, not dependency health."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=__version__,
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
        ai_configured=settings.ai_configured,
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness probe",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
async def ready() -> ReadyResponse | JSONResponse:
    """200 when SELECT 1 succeeds within the probe timeout, 503 otherwise."""
    probe = await ping_db()
    if probe.connected:
        return ReadyResponse(
            status="ready",
            checks=ReadyChecks(
                database=DatabaseCheck(
                    status="connected",
                    latency_ms=probe.latency_ms,
                    detail=None,
                )
            ),
        )
    payload = ReadyResponse(
        status="not_ready",
        checks=ReadyChecks(
            database=DatabaseCheck(
                status="disconnected",
                latency_ms=None,
                detail=probe.detail,
            )
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload.model_dump(mode="json"),
    )
