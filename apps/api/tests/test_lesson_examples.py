"""课程的「代码示例」与「期望输出」必须真的对得上。

教学方法论再漂亮，示例输出写错了就是硬伤：学习者照着敲、看到不一样的结果，
会先怀疑自己而不是怀疑材料。

这里**执行仓库自带的课程示例**（不是用户提交，用户代码永远不执行），
把 stdout 与 content.example.output 逐字比对。

注意编码：Windows 控制台默认 GBK，子进程必须显式 PYTHONIOENCODING=utf-8，
否则中文输出会变成空串——第一次做这项验证时就栽在这里，差点误判 10 节课全错。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

SELECT_LESSONS = text('SELECT code, content::text AS content FROM lessons ORDER BY order_index')


def _run_example(code: str, tmp_path) -> subprocess.CompletedProcess[str]:
    path = tmp_path / 'lesson_example.py'
    path.write_text(code, encoding='utf-8')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    return subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=20,
        env=env,
    )


async def test_every_lesson_example_prints_exactly_what_it_promises(
    db_session: AsyncSession, tmp_path
) -> None:
    """逐课执行示例，stdout 必须与文档中的期望输出一致。"""
    rows = (await db_session.execute(SELECT_LESSONS)).mappings().all()
    assert rows, '库里没有课程，这条测试无从判断'
    problems: list[str] = []
    for row in rows:
        content = json.loads(row['content'])
        example = content.get('example') or {}
        code = example.get('code')
        expected = (example.get('output') or '').replace('\r\n', '\n').strip()
        if not code:
            problems.append(f"{row['code']}: 没有示例代码")
            continue
        completed = _run_example(code, tmp_path)
        actual = (completed.stdout or '').replace('\r\n', '\n').strip()
        if completed.returncode != 0:
            tail = (completed.stderr or '').strip().splitlines()[-1:]
            problems.append(f"{row['code']}: 示例代码运行失败 {tail}")
        elif actual != expected:
            problems.append(
                f"{row['code']}: 输出不符\n  期望={expected[:120]!r}\n  实际={actual[:120]!r}"
            )
    assert not problems, '课程示例与文档输出不一致:\n' + '\n'.join(problems)