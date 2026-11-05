"""Sprint 11 补一条「函数必须真的返回值」的判题规则

Revision ID: 0016_sprint11_return_rule
Revises: 0015_sprint11_print_rule
Create Date: 2026-11-05 00:00:00+00:00

问题：3 道题要求写函数并「返回值」，required_patterns 里有 def 规则却没有 return 规则。
学习者写个只 print 不 return 的函数照样判通过——题面要的返回值从未被检查。
（上一轮 0015 修的是同一类问题，只是那个动词是 print。）

做法：给这 3 道题各追加一条 return 规则与对应标签，顺序仍是判题顺序。

* 只追加、不删除，已有 return 规则的题自动跳过（幂等）；
* 没有 DROP / DELETE / TRUNCATE，也没有 downgrade 路径（项目契约禁止破坏性语句）；
* 历史提交是快照，不受影响。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_sprint11_return_rule"
down_revision: str | None = "0015_sprint11_print_rule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETURN_PATTERN = r'return\s+'
RETURN_LABEL = "用 return 把结果返回给调用方"

# 题面要求函数返回、却没有 return 规则的题（迁移时刻的实测结果）。
TARGETS: tuple[str, ...] = (
    "route_a.rag.retrieval.ex1",
    "route_a.rag.retrieval.ex2",
    "route_a.practice.debug.ex1",
)

APPEND_PATTERN = sa.text(
    """
    UPDATE exercises
    SET required_patterns = required_patterns || to_jsonb(ARRAY[:pattern]::text[])
    WHERE code = :code
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(required_patterns) AS p
        WHERE p LIKE '%return%'
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
    """给缺 return 规则的题补上规则与标签。"""
    for code in TARGETS:
        op.execute(
            APPEND_PATTERN.bindparams(sa.bindparam('pattern')).bindparams(sa.bindparam('code'))
            .params(pattern=RETURN_PATTERN, code=code)
        )
        op.execute(
            APPEND_LABEL.bindparams(sa.bindparam('label')).bindparams(sa.bindparam('code'))
            .params(label=RETURN_LABEL, code=code)
        )


def downgrade() -> None:
    """本项目迁移只向前：破坏性回滚被契约禁止。"""
    raise RuntimeError("本项目的迁移只向前，不提供 downgrade")