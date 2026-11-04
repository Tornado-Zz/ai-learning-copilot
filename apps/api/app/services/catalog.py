"""Skill domain catalog read model (skills table, six domain rows)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SELECT_DOMAIN_SKILLS = text(
    """
    SELECT id, code, name_zh, level, route_code, order_index
    FROM skills
    WHERE level = 'domain'
    ORDER BY order_index
    """
)


async def list_domain_skills(session: AsyncSession) -> list[dict[str, object]]:
    rows = (await session.execute(SELECT_DOMAIN_SKILLS)).mappings().all()
    return [dict(row) for row in rows]


async def skill_names(session: AsyncSession) -> dict[str, str]:
    return {str(row["code"]): str(row["name_zh"]) for row in await list_domain_skills(session)}


async def skill_ids(session: AsyncSession) -> dict[str, int]:
    rows = (await session.execute(SELECT_DOMAIN_SKILLS)).mappings().all()
    return {str(row["code"]): int(row["id"]) for row in rows}
