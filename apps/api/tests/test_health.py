"""Contract tests for GET /api/v1/health."""

from __future__ import annotations

from datetime import datetime

import httpx

from app import SERVICE_NAME, __version__


async def test_health_returns_200_with_contract_fields(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "status",
        "service",
        "version",
        "environment",
        "timestamp",
        "ai_configured",
    }
    assert body["status"] == "ok"
    assert body["service"] == SERVICE_NAME == "ai-learning-copilot-api"
    assert body["version"] == __version__ == "0.1.0"
    assert body["environment"] == "local"
    assert body["ai_configured"] is False


async def test_health_timestamp_is_iso8601_utc(client: httpx.AsyncClient) -> None:
    timestamp = (await client.get("/api/v1/health")).json()["timestamp"]
    parsed = datetime.fromisoformat(timestamp)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0


async def test_health_environment_follows_app_env(make_client) -> None:
    client = await make_client(APP_ENV="staging")
    body = (await client.get("/api/v1/health")).json()
    assert body["environment"] == "staging"


async def test_health_ai_configured_false_when_key_blank(make_client) -> None:
    client = await make_client(DEEPSEEK_API_KEY="")
    assert (await client.get("/api/v1/health")).json()["ai_configured"] is False


async def test_health_ai_configured_true_when_key_present(make_client) -> None:
    # Not a credential: a plain marker used only to toggle the flag.
    client = await make_client(DEEPSEEK_API_KEY="test-value")
    assert (await client.get("/api/v1/health")).json()["ai_configured"] is True


async def test_health_reachable_when_database_is_down(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_cors_preflight_allows_default_frontend_origin(
    client: httpx.AsyncClient,
) -> None:
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_cors_origins_follow_environment(make_client) -> None:
    client = await make_client(CORS_ORIGINS="http://localhost:4321")
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:4321",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:4321"
