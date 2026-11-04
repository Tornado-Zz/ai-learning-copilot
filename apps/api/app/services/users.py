"""Identity and learning profile service.

Single-user form: the seeded user (lowest id) is "me"; there is no login.
"""

from __future__ import annotations

import re

from sqlalchemy import ARRAY, SmallInteger, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NOT_FOUND, ApiError, validation_error
from app.schemas.users import ProfileUpdateRequest
from app.services import catalog, levels

SELECT_SINGLE_USER = text(
    """
    SELECT id, display_name, timezone, timezone_source
    FROM users
    ORDER BY id
    LIMIT 1
    """
)

SELECT_PROFILE = text(
    """
    SELECT user_id, study_days, daily_minutes, weekly_minutes
    FROM user_profiles
    WHERE user_id = :user_id
    """
)

UPDATE_USER = text(
    """
    UPDATE users
    SET timezone = :timezone,
        timezone_source = CASE WHEN :confirmed THEN 'user_confirmed' ELSE timezone_source END,
        updated_at = now()
    WHERE id = :user_id
    """
)

UPDATE_PROFILE = text(
    """
    UPDATE user_profiles
    SET study_days = :study_days, daily_minutes = :daily_minutes, updated_at = now()
    WHERE user_id = :user_id
    """
).bindparams(bindparam("study_days", type_=ARRAY(SmallInteger)))

INSERT_PROFILE = text(
    """
    INSERT INTO user_profiles (user_id, study_days, daily_minutes)
    VALUES (:user_id, :study_days, :daily_minutes)
    """
).bindparams(bindparam("study_days", type_=ARRAY(SmallInteger)))

SELECT_KNOWN_TIMEZONE = text("SELECT 1 FROM pg_timezone_names WHERE name = :name")

# Structural shape of an IANA zone name; the authoritative check is
# SELECT_KNOWN_TIMEZONE (PostgreSQL ships the tz database, Python on Windows does not).
TIMEZONE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(?:/[A-Za-z0-9_+\-]+)*$")

MIN_STUDY_DAYS = 1
MAX_STUDY_DAYS = 7
MIN_DAILY_MINUTES = 15
MAX_DAILY_MINUTES = 480
MAX_TIMEZONE_LENGTH = 64


async def get_single_user(session: AsyncSession) -> dict[str, object]:
    """The seeded single user; 404 with an initialisation hint when none exists."""
    row = (await session.execute(SELECT_SINGLE_USER)).mappings().first()
    if row is None:
        raise ApiError(
            404,
            NOT_FOUND,
            "还没有可用的用户，请先执行数据库迁移（uv run alembic upgrade head）写入种子用户",
        )
    return dict(row)


async def get_profile(session: AsyncSession, user_id: int) -> dict[str, object]:
    row = (await session.execute(SELECT_PROFILE, {"user_id": user_id})).mappings().first()
    if row is None:
        raise ApiError(404, NOT_FOUND, "学习档案尚未初始化，请先提交一次档案设置")
    return {
        "study_days": [int(day) for day in row["study_days"]],
        "daily_minutes": int(row["daily_minutes"]),
        "weekly_minutes": int(row["weekly_minutes"]),
    }


def validate_profile_update(payload: ProfileUpdateRequest) -> None:
    """Service-side duplicate of the database constraints (both layers are required)."""
    days = list(payload.study_days)
    if len(days) < MIN_STUDY_DAYS or len(days) > MAX_STUDY_DAYS:
        raise validation_error(
            "study_days 需要选择 1–7 天",
            "study_days",
            "out_of_range",
            min=MIN_STUDY_DAYS,
            max=MAX_STUDY_DAYS,
            value=days,
        )
    if len(set(days)) != len(days):
        raise validation_error(
            "study_days 不允许重复元素", "study_days", "duplicate_element", value=days
        )
    if any(day < 1 or day > 7 for day in days):
        raise validation_error(
            "study_days 的每个元素必须在 1–7 之间（1=周一，7=周日）",
            "study_days",
            "out_of_range",
            min=MIN_STUDY_DAYS,
            max=MAX_STUDY_DAYS,
            value=days,
        )
    if not MIN_DAILY_MINUTES <= payload.daily_minutes <= MAX_DAILY_MINUTES:
        raise validation_error(
            "daily_minutes 必须在 15–480 之间",
            "daily_minutes",
            "out_of_range",
            min=MIN_DAILY_MINUTES,
            max=MAX_DAILY_MINUTES,
            value=payload.daily_minutes,
        )
    _validate_timezone_format(payload.timezone)


def _validate_timezone_format(name: str) -> None:
    """Shape check only: runs before any database access so 422 stays cheap."""
    if not name or len(name) > MAX_TIMEZONE_LENGTH or not TIMEZONE_PATTERN.match(name):
        raise validation_error(
            "timezone 必须是合法的 IANA 时区名，例如 Asia/Shanghai",
            "timezone",
            "invalid_timezone",
            value=name,
        )


async def assert_known_timezone(session: AsyncSession, name: str) -> None:
    """Authoritative IANA check against PostgreSQL's tz database."""
    if (await session.execute(SELECT_KNOWN_TIMEZONE, {"name": name})).first() is None:
        raise validation_error(
            "timezone 必须是合法的 IANA 时区名，例如 Asia/Shanghai",
            "timezone",
            "invalid_timezone",
            value=name,
        )


async def update_profile(session: AsyncSession, payload: ProfileUpdateRequest) -> dict[str, object]:
    """Validate, then write users + user_profiles in one transaction."""
    validate_profile_update(payload)
    await assert_known_timezone(session, payload.timezone)
    user = await get_single_user(session)
    user_id = int(user["id"])
    days = sorted(set(int(day) for day in payload.study_days))
    try:
        await session.execute(
            UPDATE_USER,
            {
                "user_id": user_id,
                "timezone": payload.timezone,
                "confirmed": bool(payload.timezone_confirmed),
            },
        )
        result = await session.execute(
            UPDATE_PROFILE,
            {
                "user_id": user_id,
                "study_days": days,
                "daily_minutes": payload.daily_minutes,
            },
        )
        if result.rowcount == 0:
            await session.execute(
                INSERT_PROFILE,
                {
                    "user_id": user_id,
                    "study_days": days,
                    "daily_minutes": payload.daily_minutes,
                },
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return await load_me(session)


async def load_me(session: AsyncSession) -> dict[str, object]:
    """Contract 6.1 payload: user + profile + six resolved domain levels."""
    user = await get_single_user(session)
    user_id = int(user["id"])
    profile = await get_profile(session, user_id)
    resolved = await levels.resolve_current_levels(session, user_id)
    names = await catalog.skill_names(session)
    skills = [
        {
            "code": row["skill_code"],
            "name_zh": names.get(str(row["skill_code"]), str(row["skill_code"])),
            "level": row["level"],
            "state": row["state"],
            "evidence_kind": row["evidence_kind"],
            "evidence_strength": row["evidence_strength"],
        }
        for row in resolved
    ]
    return {
        "user": {
            "id": user_id,
            "display_name": user["display_name"],
            "timezone": user["timezone"],
            "timezone_source": user["timezone_source"],
        },
        "profile": profile,
        "skills": skills,
    }
