"""Shared fixtures. The default suite must pass with PostgreSQL stopped."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
import pytest

from app.core import db
from app.core.config import get_settings

# Nothing listens on this port: the readiness probe must answer 503, not crash.
UNREACHABLE_DATABASE_URL = (
    "postgresql+asyncpg://copilot:copilot_dev_password@127.0.0.1:59999/copilot"
)

MakeClient = Callable[..., Awaitable[httpx.AsyncClient]]


@asynccontextmanager
async def build_client() -> AsyncIterator[httpx.AsyncClient]:
    """Build a fresh app (settings are read at creation time) over ASGI."""
    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture(autouse=True)
async def isolated_settings() -> AsyncIterator[None]:
    """Drop the Settings and engine caches around every test."""
    get_settings.cache_clear()
    await db.dispose_engine()
    try:
        yield
    finally:
        get_settings.cache_clear()
        await db.dispose_engine()


@pytest.fixture
async def make_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MakeClient]:
    """Factory: apply environment overrides, then build a client for that config."""
    stack = AsyncExitStack()
    async with stack:

        async def _make(**env: str) -> httpx.AsyncClient:
            for key, value in env.items():
                monkeypatch.setenv(key, value)
            get_settings.cache_clear()
            await db.dispose_engine()
            return await stack.enter_async_context(build_client())

        yield _make


@pytest.fixture
async def client(make_client: MakeClient) -> httpx.AsyncClient:
    """Client configured the way a developer sees it with PostgreSQL stopped."""
    return await make_client(
        DATABASE_URL=UNREACHABLE_DATABASE_URL,
        DEEPSEEK_API_KEY="",
        APP_ENV="local",
    )


@pytest.fixture
async def live_client(make_client: MakeClient) -> httpx.AsyncClient:
    """Client using the real DATABASE_URL; only for integration tests."""
    return await make_client()
