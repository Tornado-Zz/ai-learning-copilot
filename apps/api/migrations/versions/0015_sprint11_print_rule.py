"""Sprint 11 补一条「必须真的打印」的判题规则

Revision ID: 0015_sprint11_print_rule
Revises: 0014_sprint10_requirement_labels
Create Date: 2026-11-05 00:00:00+00:00

问题：22 道题里有 12 道在题面要求「打印结果」，但 required_patterns 里根本没有
print 规则。学习者可以一条 print 都不写就判通过——题目声称的目标从未被检查。

做法：给这 12 道题各追加一条 print 规则与对应的中文标签（顺序仍是判题顺序）。

* 只追加、不删除：已有规则与标签原样保留，新规则排在末尾；
* 幂等：先判断是否已存在 print 规则，存在则跳过该题；标签同样按条数补齐；
* 没有 DROP / DELETE / TRUNCATE，也没有 downgrade 路径（项目契约禁止破坏性语句）；
* 历史提交的判定是快照，不受影响；只有之后的提交按新规则判。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_sprint11_print_rule"
down_revision: str | None = "0014_sprint10_requirement_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRINT_PATTERN = 'print\\s*\\('
PRINT_LABEL = "用 print 把结果打印出来"

# 题面提到「打印/输出」却没有 print 规则的 12 道题（迁移时刻的实测结果）。
TARGETS: tuple[str, ...] = (
    "route_a.py.variables.ex1",
    "route_a.py.list_dict.ex1",
    "route_a.py.list_dict.ex2",
    "route_a.py.functions.ex1",
    "route_a.py.functions.ex2",
    "route_a.py.debugging.ex1",
    "route_a.py.debugging.ex2",
    "route_a.api.json.ex1",
    "route_a.llm.messages.ex1",
    "route_a.llm.messages.ex2",
    "route_a.agent.tool.ex1",
    "route_a.agent.tool.ex2",
)

# 追加一条模式；已有 print 规则时保持不变（幂等）。
APPEND_PATTERN = sa.text(
    """
    UPDATE exercises
    SET required_patterns = required_patterns || to_jsonb(ARRAY[:pattern]::text[])
    WHERE code = :code
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(required_patterns) AS p
        WHERE p LIKE '%print%'
      )
    """
)

APPEND_LABEL = sa.text(
    """
    UPDATE exercises
    SET requirement_labels = requirement_labels || to_jsonb(ARRAY[:label]::text[])
    WHERE code = :code
      AND jsonb_array_length(requirement_labels) < jsonb_array_length(required_patterns)
    """
)


def upgrade() -> None:
    """给缺 print 规则的题补上规则与标签。"""
    for code in TARGETS:
        op.execute(APPEND_PATTERN.bindparams(sa.bindparam('pattern')).bindparams(sa.bindparam('code')).params(pattern=PRINT_PATTERN, code=code))
        op.execute(APPEND_LABEL.bindparams(sa.bindparam('label')).bindparams(sa.bindparam('code')).params(label=PRINT_LABEL, code=code))


def downgrade() -> None:
    """本项目迁移只向前：破坏性回滚被契约禁止。"""
    raise RuntimeError("本项目的迁移只向前，不提供 downgrade")