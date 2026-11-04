"""Current skill level resolution: the single frozen SQL of contract 3.3."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Contract 3.3 is the only authority for this query: tier first, then newest,
# and requested_verification never becomes a displayed level.
CURRENT_LEVELS_SQL = text(
    """
    WITH ev AS (
      SELECT l.id, l.skill_id, l.level, l.assessment_state, l.evidence_kind, l.evidence_strength, l.evidence_ref, l.created_at,
             CASE WHEN l.verification_method IN ('runtime_test','manual_review') THEN 3
                  WHEN l.evidence_kind IN ('practice','transfer') AND l.verification_method = 'static_rule' THEN 2
                  WHEN l.evidence_kind = 'diagnostic' THEN 1 ELSE 0 END AS tier
      FROM user_skill_levels l
      WHERE l.user_id = :user_id AND l.assessment_state = 'established'
    ), cur AS (
      SELECT DISTINCT ON (skill_id) skill_id, level, assessment_state, evidence_kind, evidence_strength, evidence_ref, tier
      FROM ev ORDER BY skill_id, tier DESC, created_at DESC, id DESC
    ), latest_any AS (
      SELECT DISTINCT ON (l.skill_id) l.skill_id, l.assessment_state
      FROM user_skill_levels l WHERE l.user_id = :user_id
      ORDER BY l.skill_id, l.created_at DESC, l.id DESC
    )
    SELECT s.code AS skill_code, COALESCE(cur.level, 0) AS level,
           COALESCE(cur.assessment_state, latest_any.assessment_state, 'unassessed') AS assessment_state,
           cur.evidence_kind, COALESCE(cur.evidence_strength, 'none') AS evidence_strength, cur.evidence_ref
    FROM skills s LEFT JOIN cur ON cur.skill_id = s.id LEFT JOIN latest_any ON latest_any.skill_id = s.id
    WHERE s.level = 'domain' ORDER BY s.order_index
    """
)


async def resolve_current_levels(session: AsyncSession, user_id: int) -> list[dict[str, object]]:
    """One row per domain skill, level 0 and state unassessed when no evidence exists."""
    rows = (await session.execute(CURRENT_LEVELS_SQL, {"user_id": user_id})).mappings().all()
    return [
        {
            "skill_code": row["skill_code"],
            "level": int(row["level"]),
            "state": row["assessment_state"],
            "evidence_kind": row["evidence_kind"],
            "evidence_strength": row["evidence_strength"],
            "evidence_ref": row["evidence_ref"],
        }
        for row in rows
    ]
