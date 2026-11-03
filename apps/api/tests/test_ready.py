"""Readiness contract tests. The default suite runs with PostgreSQL stopped."""

from __future__ import annotations

import httpx
import pytest

# Local development password from infra/.env.example; it must never be echoed back.
PASSWORD = "copilot_dev_password"


async def test_ready_returns_503_when_database_unreachable(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    check = body["checks"]["database"]
    assert set(check) == {"status", "latency_ms", "detail"}
    assert check["status"] == "disconnected"
    assert check["latency_ms"] is None
    assert isinstance(check["detail"], str)
    assert check["detail"]


async def test_ready_detail_never_leaks_credentials(client: httpx.AsyncClient) -> None:
    detail = (await client.get("/api/v1/ready")).json()["checks"]["database"]["detail"]
    assert PASSWORD not in detail
    assert "@" not in detail or "://" not in detail


async def test_ready_never_raises_a_500(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/ready")).status_code in (200, 503)


@pytest.mark.integration
async def test_ready_returns_200_when_database_available(
    live_client: httpx.AsyncClient,
) -> None:
    response = await live_client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    check = body["checks"]["database"]
    assert check["status"] == "connected"
    assert check["latency_ms"] is not None
    assert isinstance(check["latency_ms"], int)
    assert check["latency_ms"] >= 0
    assert check["detail"] is None
