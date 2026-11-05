"""练习内容质量的可执行检查：题目必须真的需要动手写代码。

三道防线（都在真实题库上跑，不是构造数据）：
  1. 起始代码不能通过判题——否则这道题什么都不用做；
  2. 把题面原文贴进去不能通过——否则照着复述就能过；
  3. 要求标签与判题规则条数必须相等（与 test_requirement_labels 互为呼应）。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.judging import judge_static_rule

pytestmark = pytest.mark.integration

SELECT_EXERCISES = text(
    """
    SELECT code, prompt, starter_code,
           required_patterns::text AS required,
           forbidden_patterns::text AS forbidden,
           expected_output, requirement_labels::text AS labels
    FROM exercises
    ORDER BY id
    """
)


async def _rows(db_session: AsyncSession):
    return (await db_session.execute(SELECT_EXERCISES)).mappings().all()


def _judge(row, code_text: str):
    return judge_static_rule(
        code_text=code_text,
        required_patterns=json.loads(row['required']),
        forbidden_patterns=json.loads(row['forbidden']),
        expected_output=row['expected_output'],
        claimed_output=None,
        requirement_labels=json.loads(row['labels']),
    )


async def test_no_starter_code_passes_its_own_exercise(db_session: AsyncSession) -> None:
    """起始代码必须判失败：否则学习者打开题目就已经「通过」了。"""
    rows = await _rows(db_session)
    passing = [row['code'] for row in rows if _judge(row, row['starter_code']).is_passed]
    assert not passing, f'这些题的起始代码直接就能通过：{passing}'


async def test_pasting_the_prompt_does_not_pass(db_session: AsyncSession) -> None:
    """题面原文贴进编辑器不能通过：判题看的是代码形状，不是复述。"""
    rows = await _rows(db_session)
    passing = [row['code'] for row in rows if _judge(row, row['prompt']).is_passed]
    assert not passing, f'这些题把题面原文贴进去就能通过：{passing}'


async def test_every_requirement_label_has_exactly_one_rule(db_session: AsyncSession) -> None:
    """标签与规则必须一一对应：判题是按下标取标签的，错位会让「第 N 项」指向错的说明。"""
    rows = await _rows(db_session)
    mismatched = [
        (row['code'], len(json.loads(row['labels'])), len(json.loads(row['required'])))
        for row in rows
        if len(json.loads(row['labels'])) != len(json.loads(row['required']))
    ]
    assert not mismatched, f'标签与规则条数不一致（题名, 标签数, 规则数）：{mismatched}'