"""题面要求「打印」时，判题必须真的检查 print。

背景：22 道题里有 12 道在题面写着「打印结果」，但 required_patterns 从来没有
print 规则——学习者一条 print 都不写也能判通过，题目声称的目标从未被检查。
v0.1.29 的迁移 0015 给这 12 道题补上了规则与标签，这条测试守住它不再退化。
"""

from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

SELECT_EXERCISES = text(
    """
    SELECT code, prompt, required_patterns::text AS required, requirement_labels::text AS labels
    FROM exercises
    ORDER BY id
    """
)


async def test_every_exercise_that_asks_for_output_checks_print(
    db_session: AsyncSession,
) -> None:
    """题面提到打印/输出，就必须有一条 print 判题规则。"""
    rows = (await db_session.execute(SELECT_EXERCISES)).mappings().all()
    missing = [
        row['code']
        for row in rows
        if re.search(r'打印|输出', row['prompt'])
        and not any('print' in pattern for pattern in json.loads(row['required']))
    ]
    assert not missing, f'这些题要求打印却不检查 print：{missing}'


async def test_print_rule_has_a_matching_label(
    db_session: AsyncSession,
) -> None:
    """补上的规则必须带标签，否则失败时又会退化成「第 N 项」无从对照。"""
    rows = (await db_session.execute(SELECT_EXERCISES)).mappings().all()
    problems = []
    for row in rows:
        required = json.loads(row['required'])
        labels = json.loads(row['labels'])
        if len(required) != len(labels):
            problems.append(f"{row['code']}: 规则 {len(required)} 条但标签 {len(labels)} 条")
        elif any('print' in pattern for pattern in required) and not any(
            '打印' in label for label in labels
        ):
            problems.append(f"{row['code']}: 有 print 规则但没有「打印」标签")
    assert not problems, '规则与标签不一致:\n' + '\n'.join(problems)