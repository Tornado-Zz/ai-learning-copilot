"""Sprint 15: the capability average must use one level per domain.

Why this test exists: user_skill_levels is an evidence HISTORY - a domain can carry
several rows (a diagnostic row at L0, then a practice row at L2). The resolver
(levels.resolve_current_levels) understands that and reports L2. But the capability
mean used to be a row-level sum/count, so the same user showed an average diluted by
the stale diagnostic row. This pins the mean to the resolved level per domain.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import progress

pytestmark = pytest.mark.integration

TIMEZONE = "Asia/Shanghai"


async def test_capability_average_uses_resolved_level_per_domain(
    db_session: AsyncSession, test_user
) -> None:
    user_id = int(test_user["id"])
    skill_id = (
        await db_session.execute(text("SELECT id FROM skills WHERE code = 'route_a.a4'"))
    ).scalar_one()

    # Two rows for the same domain, exactly the shape the writer produces over time:
    # an early diagnostic at L0 and a later practice row at L2.
    # ck_usk_state_level: only 'established' rows may carry a level >= 1, so the stale
    # diagnostic row is 'assessed_below_threshold' at L0 - exactly what the writer emits.
    for level, kind, method, ref, state in (
        (0, "diagnostic", "static_rule", "diag:1", "assessed_below_threshold"),
        (2, "practice", "static_rule", "sub:1", "established"),
    ):
        await db_session.execute(
            text(
                "INSERT INTO user_skill_levels (user_id, skill_id, level, evidence_kind, "
                "verification_method, assessment_state, evidence_ref, evidence_count) "
                "VALUES (:user_id, :skill_id, :level, :kind, :method, :state, :ref, 1)"
            ),
            {
                "user_id": user_id,
                "skill_id": skill_id,
                "level": level,
                "kind": kind,
                "method": method,
                "ref": ref,
                "state": state,
            },
        )

    capability = await progress._capability(db_session, user_id)

    resolved = {d["skill_code"]: d["level"] for d in capability["domains"]}
    assert resolved["route_a.a4"] == 2, f"resolver must keep the stronger row: {resolved}"

    # One row per domain, so the mean is 2 / 6 domains, not 2 / 7 rows.
    expected = round(sum(resolved.values()) / len(resolved), 1)
    assert capability["average_level"] == expected, (
        f"average {capability['average_level']} should divide by {len(resolved)} domains, "
        "not by the number of evidence rows"
    )