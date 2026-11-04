"""v0.1.3 修正：reviewed 行必须有 reviewer（修 SQL 三值逻辑漏洞）。

0009 的 ck_capstone_submissions_reviewed_complete 写的是
`verdict IS NOT NULL AND reviewer = 'self' AND reviewed_at IS NOT NULL`。
当 reviewer 为 NULL 时，`reviewer = 'self'` 求值为 NULL，整个 CHECK 变成 NULL；
而 PostgreSQL 把 NULL 当作**通过**，于是「已评审但没有评审者」的行可以写进去。

实测：`UPDATE capstone_submissions SET reviewer = NULL WHERE status = 'reviewed'` 当时未被拒绝。
本迁移把条件改成显式的 `reviewer IS NOT NULL AND reviewer = 'self'`，堵住这个洞。

只重建这一条约束，不动表结构与数据。
"""

from __future__ import annotations

from alembic import op

revision = "0010_capstone_review_requires_reviewer"
down_revision = "0009_capstone_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_capstone_submissions_reviewed_complete",
        "capstone_submissions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_capstone_submissions_reviewed_complete",
        "capstone_submissions",
        # reviewer IS NOT NULL 不能省：缺了它，NULL 会让整条 CHECK 变成 NULL，
        # 而 PostgreSQL 认为 NULL 不违反约束。
        "status <> 'reviewed' OR (verdict IS NOT NULL AND reviewer IS NOT NULL "
        "AND reviewer = 'self' AND reviewed_at IS NOT NULL)",
    )


def downgrade() -> None:
    raise RuntimeError("本项目的迁移不提供降级路径；请前滚修复。")