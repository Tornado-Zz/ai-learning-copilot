"""Async engine, session factory, request dependency and the readiness probe."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

READY_PROBE_TIMEOUT_SECONDS = 2.0
_DETAIL_MAX_LENGTH = 200
# Matches "scheme://user:secret@host" so credentials never reach a response body.
_URL_CREDENTIALS = re.compile(r"://[^:@/\s]+:[^@/\s]*@")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Lazily create the engine: the API must start with the database down."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
        logger.debug("database engine created")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one AsyncSession per request."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def dispose_engine() -> None:
    """Close pooled connections and drop the cached engine/session factory."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@dataclass(frozen=True)
class DatabaseProbe:
    connected: bool
    latency_ms: int | None
    detail: str | None


def _redact(message: str) -> str:
    redacted = _URL_CREDENTIALS.sub("://***:***@", message)
    redacted = " ".join(redacted.split())
    return redacted[:_DETAIL_MAX_LENGTH] or "unknown error"


async def ping_db() -> DatabaseProbe:
    """Run SELECT 1 under a hard timeout. Never raises: /ready must answer 503."""
    started = time.perf_counter()
    try:
        engine = get_engine()
        async with asyncio.timeout(READY_PROBE_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except TimeoutError:
        detail = f"database probe timed out after {READY_PROBE_TIMEOUT_SECONDS:g}s"
        logger.warning("database readiness probe timed out")
        return DatabaseProbe(connected=False, latency_ms=None, detail=detail)
    except Exception as exc:  # noqa: BLE001 - readiness degrades, it never propagates
        message = str(exc).strip()
        detail = _redact(f"{type(exc).__name__}: {message}" if message else type(exc).__name__)
        logger.warning("database readiness probe failed: %s", detail)
        return DatabaseProbe(connected=False, latency_ms=None, detail=detail)

    latency_ms = int(round((time.perf_counter() - started) * 1000))
    return DatabaseProbe(connected=True, latency_ms=latency_ms, detail=None)
