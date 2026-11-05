"""题面要求的动作，判题必须真的检查（print / return 两例）。

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


async def test_every_exercise_that_asks_for_a_return_checks_return(
    db_session: AsyncSession,
) -> None:
    """题面要求函数返回值，就必须有一条 return 规则（0016 之前这里有 3 道题漏判）。"""
    rows = (await db_session.execute(SELECT_EXERCISES)).mappings().all()
    missing = [
        row['code']
        for row in rows
        if '返回' in row['prompt']
        and any('def' in pattern for pattern in json.loads(row['required']))
        and not any('return' in pattern for pattern in json.loads(row['required']))
    ]
    assert not missing, f'这些题要求返回值却不检查 return：{missing}'


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