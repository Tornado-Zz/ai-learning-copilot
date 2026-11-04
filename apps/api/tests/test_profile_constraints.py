"""验收 4 与 12：study_days 非法输入、时区确认语义与学习日去重。

隔离策略：约束用例一律在事务内自建 users 行；档案接口按契约是单用户语义，
因此改为"读基线 → 写 → 断言写入值/不变式 → 最后显式复原"，并且外层事务仍会回滚。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import ARRAY, SmallInteger, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

INSERT_PROFILE = text(
    "INSERT INTO user_profiles (user_id, study_days, daily_minutes) VALUES (:user_id, :days, 60)"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))

INSERT_USER = text(
    "INSERT INTO users (display_name) VALUES (:display_name) RETURNING id"
)

UPDATE_STUDY_DAYS = text(
    "UPDATE user_profiles SET study_days = :days WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))

RESTORE_USER = text(
    "UPDATE users SET timezone = :timezone, timezone_source = :source WHERE id = :user_id"
)

RESTORE_PROFILE = text(
    "UPDATE user_profiles SET study_days = :days, daily_minutes = :daily_minutes "
    "WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))

SELECT_PROFILE_ROW = text(
    "SELECT u.timezone, u.timezone_source, p.study_days, p.daily_minutes, p.weekly_minutes "
    "FROM users u JOIN user_profiles p ON p.user_id = u.id WHERE u.id = :user_id"
)

# 验收 4：{}、{1,1}、{8}、{0} 都必须被数据库拒绝
BAD_STUDY_DAYS = [
    ([], "ck_up_study_days_card"),
    ([1, 1], "重复元素"),
    ([8], "ck_up_study_days_vals"),
    ([0], "ck_up_study_days_vals"),
]

BAD_STUDY_DAYS_API = [
    ([], "study_days", "out_of_range"),
    ([1, 1], "study_days", "duplicate_element"),
    ([8], "study_days", "out_of_range"),
    ([0], "study_days", "out_of_range"),
]


async def test_04_study_days_rejected_by_database_constraints(
    db_session: AsyncSession,
) -> None:
    # 自建用户（不含档案），避免依赖库内任何已有行
    user_id = int(
        (
            await db_session.execute(
                INSERT_USER, {"display_name": f"pytest-constraint-{uuid.uuid4().hex[:8]}"}
            )
        ).scalar_one()
    )
    for days, expected in BAD_STUDY_DAYS:
        try:
            async with db_session.begin_nested():
                await db_session.execute(INSERT_PROFILE, {"user_id": user_id, "days": days})
        except IntegrityError as exc:
            message = str(exc)
            assert expected in message, (days, message)
        else:  # pragma: no cover - the insert must fail
            pytest.fail(f"study_days={days} 未被拒绝")


async def test_04b_study_days_rejected_by_api_with_422(api) -> None:
    baseline = (await api.get("/api/v1/users/me")).json()["profile"]
    for days, field, reason in BAD_STUDY_DAYS_API:
        response = await api.put(
            "/api/v1/users/me/profile",
            json={
                "study_days": days,
                "daily_minutes": 60,
                "timezone": "Asia/Shanghai",
                "timezone_confirmed": True,
            },
        )
        assert response.status_code == 422, (days, response.text)
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["details"]["field"] == field
        assert body["error"]["details"]["reason"] == reason
        assert body["request_id"]
    # 拒绝后档案与调用前完全一致（不假设默认值，只比对基线）
    assert (await api.get("/api/v1/users/me")).json()["profile"] == baseline


async def test_12_timezone_confirmation_and_study_days_semantics(
    api, db_session: AsyncSession
) -> None:
    me = (await api.get("/api/v1/users/me")).json()
    user_id = int(me["user"]["id"])
    baseline = {
        "timezone": me["user"]["timezone"],
        "timezone_source": me["user"]["timezone_source"],
        "study_days": me["profile"]["study_days"],
        "daily_minutes": me["profile"]["daily_minutes"],
        "weekly_minutes": me["profile"]["weekly_minutes"],
    }
    try:
        confirmed = await api.put(
            "/api/v1/users/me/profile",
            json={
                "study_days": [2, 4, 7],
                "daily_minutes": 45,
                "timezone": "Asia/Tokyo",
                "timezone_confirmed": True,
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        body = confirmed.json()
        assert body["user"]["timezone"] == "Asia/Tokyo"
        assert body["user"]["timezone_source"] == "user_confirmed"
        assert body["profile"] == {
            "study_days": [2, 4, 7],
            "daily_minutes": 45,
            "weekly_minutes": 135,
        }

        # 只前进不回退：省略 timezone_confirmed 不得清除已确认状态
        relabelled = await api.put(
            "/api/v1/users/me/profile",
            json={"study_days": [1], "daily_minutes": 30, "timezone": "Asia/Tokyo"},
        )
        assert relabelled.status_code == 200, relabelled.text
        assert relabelled.json()["user"]["timezone_source"] == "user_confirmed"
        assert relabelled.json()["profile"] == {
            "study_days": [1],
            "daily_minutes": 30,
            "weekly_minutes": 30,
        }

        # 服务层校验：非法值一律 422 且库内保持上一次成功的值
        for payload, field in (
            ({"study_days": [1, 1], "daily_minutes": 60, "timezone": "Asia/Tokyo"}, "study_days"),
            ({"study_days": [1], "daily_minutes": 10, "timezone": "Asia/Tokyo"}, "daily_minutes"),
            ({"study_days": [1], "daily_minutes": 481, "timezone": "Asia/Tokyo"}, "daily_minutes"),
            ({"study_days": [1], "daily_minutes": 60, "timezone": "Mars/Base"}, "timezone"),
        ):
            rejected = await api.put("/api/v1/users/me/profile", json=payload)
            assert rejected.status_code == 422, (payload, rejected.text)
            assert rejected.json()["error"]["details"]["field"] == field

        current = (await api.get("/api/v1/users/me")).json()
        assert current["profile"] == {
            "study_days": [1],
            "daily_minutes": 30,
            "weekly_minutes": 30,
        }

        stored = (
            await db_session.execute(SELECT_PROFILE_ROW, {"user_id": user_id})
        ).mappings().one()
        assert stored["timezone"] == "Asia/Tokyo"
        assert stored["timezone_source"] == "user_confirmed"
        assert list(stored["study_days"]) == [1]
        assert stored["daily_minutes"] == 30
        assert stored["weekly_minutes"] == 30

        # 数据库触发器是第二层：绕过服务层直接写重复元素仍被拒绝
        with pytest.raises(IntegrityError) as excinfo:
            async with db_session.begin_nested():
                await db_session.execute(
                    UPDATE_STUDY_DAYS, {"user_id": user_id, "days": [1, 1]}
                )
        assert "重复元素" in str(excinfo.value)
        unchanged = (
            await db_session.execute(
                text("SELECT study_days FROM user_profiles WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
        ).scalar_one()
        assert list(unchanged) == [1]
    finally:
        # 显式复原真实档案（外层事务也会回滚），确保本用例改完即恢复
        await db_session.execute(
            RESTORE_USER,
            {
                "user_id": user_id,
                "timezone": baseline["timezone"],
                "source": baseline["timezone_source"],
            },
        )
        await db_session.execute(
            RESTORE_PROFILE,
            {
                "user_id": user_id,
                "days": baseline["study_days"],
                "daily_minutes": baseline["daily_minutes"],
            },
        )
    restored = (
        await db_session.execute(SELECT_PROFILE_ROW, {"user_id": user_id})
    ).mappings().one()
    assert restored["timezone"] == baseline["timezone"]
    assert restored["timezone_source"] == baseline["timezone_source"]
    assert list(restored["study_days"]) == baseline["study_days"]
    assert restored["daily_minutes"] == baseline["daily_minutes"]
    assert restored["weekly_minutes"] == baseline["weekly_minutes"]
