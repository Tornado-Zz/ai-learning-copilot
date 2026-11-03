"""empty baseline

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00+00:00

Sprint 0 baseline: proves the migration chain works without creating business tables.
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No business tables are created by the baseline revision."""


def downgrade() -> None:
    """Nothing to drop: the baseline creates no business tables."""
