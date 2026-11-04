"""统一错误体（契约 6.6）与数据库不可用降级；不需要数据库。"""

from __future__ import annotations

import httpx


async def test_users_me_returns_503_envelope_when_database_is_down(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"error", "request_id"}
    assert body["error"]["code"] == "DB_UNAVAILABLE"
    assert body["error"]["message"]
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert len(body["request_id"]) == 12


async def test_skills_returns_503_envelope_when_database_is_down(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/skills")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_UNAVAILABLE"


async def test_profile_validation_runs_before_any_database_access(
    client: httpx.AsyncClient,
) -> None:
    response = await client.put(
        "/api/v1/users/me/profile",
        json={
            "study_days": [1, 1],
            "daily_minutes": 60,
            "timezone": "Asia/Shanghai",
            "timezone_confirmed": True,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"] == {
        "field": "study_days",
        "reason": "duplicate_element",
        "value": [1, 1],
    }
    assert body["request_id"]


async def test_daily_minutes_out_of_range_reports_bounds(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/users/me/profile",
        json={
            "study_days": [1, 3, 5],
            "daily_minutes": 10,
            "timezone": "Asia/Shanghai",
            "timezone_confirmed": True,
        },
    )
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["field"] == "daily_minutes"
    assert details["reason"] == "out_of_range"
    assert (details["min"], details["max"]) == (15, 480)


async def test_structurally_invalid_timezone_is_rejected_without_database(
    client: httpx.AsyncClient,
) -> None:
    # 形状校验先于任何数据库访问；是否存在由 pg_timezone_names 在集成测试里验证
    response = await client.put(
        "/api/v1/users/me/profile",
        json={
            "study_days": [1],
            "daily_minutes": 60,
            "timezone": "Asia Shanghai",
            "timezone_confirmed": True,
        },
    )
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["field"] == "timezone"
    assert details["reason"] == "invalid_timezone"


async def test_body_shape_errors_use_the_same_envelope(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/diagnostics",
        json={"question_set_version": "v1", "rule_version": "r1", "answers": "not-an-object"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["field"]
    assert body["request_id"]


async def test_unknown_route_uses_the_same_envelope(client: httpx.AsyncClient) -> None:
    # /lessons（S2）与 /exercises（S3 阶段 B）都已是真实路由，
    # 因此这里用一个仍然不存在的路径（项目功能尚未实现）
    response = await client.get("/api/v1/projects")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["request_id"] == response.headers["X-Request-ID"]
