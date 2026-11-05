"""判题文案可读性：每条必须写法都有一句学习者看得懂的中文要求（0014）。

判题失败时原先只回「第 4 项必须出现的写法没有出现」——题面没有编号，规则本身是
正则又是答案键，学习者无从对照。0014 给 exercises 加了 requirement_labels，与
required_patterns **逐条一一对应、顺序相同、条数相等**，第 N 条标签就是第 N 条规则。

四条不变式，全部由本文件断言：

1. 条数相等是硬约束：当前 26 道题 172 条规则，任何一道题多一条或少一条标签都不许过；
2. 标签是给人看的：非空、≤ 40 字、不含正则记号，也不回显任何一条模式原文；
3. requirements 可以对外：它复述题面要求，不是答案键；required_patterns /
   forbidden_patterns / expected_output 仍然一次都不出现在响应里；
4. 标签只改措辞不改判定：标签缺失或不可用时回退到原来的「第 N 项」文案，绝不报错。

默认档（uv run pytest -q）只跑不连库的用例；连库的用例带 integration 标记。
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.exercises import ExerciseDetailOut
from app.services import judging

LABELS_REVISION = "0014_sprint10_requirement_labels"
ANSWER_KEYS = ("required_patterns", "forbidden_patterns", "expected_output")
# 正则记号：标签是给人看的句子，出现这些字符就说明正则漏到了文案里。
REGEX_MARKS = ("\\s", "\\w", "\\b", "[", "]", "(", ")", "|")
LABEL_MAX_LENGTH = 40
# 三个口径要分开：
#   * 0014 迁移刚跑完时是 124 条规则、22 道题（0011–0013 的种子），幂等用例查的是这个快照；
#   * 0015 给 12 道「要求打印却未检查 print」的题各补一条规则，0016 给 3 道补 return：
#     139 条；
#   * 0017 再补 a3 / a4 两节核心课与 4 道练习，规则 139 + 33 = 172 条、练习 26 道；
#   * 0018 又补 a5 / a6 各一节第二课与 4 道练习，规则 172 + 27 = 199 条、练习 30 道；
#   * 0019 再补 a6 一节「跟着做」实战课与 2 道练习，规则 199 + 14 = 213 条、练习 32 道；
#   * 0020 再给 a1 补字符串与文件两节课与 4 道练习，规则 213 + 31 = 244 条、练习 36 道。
# 改内容时这几个数字都要同步。
TOTAL_RULES_AFTER_0014 = 124
EXERCISES_AT_0014 = 22
TOTAL_RULES = 244
TOTAL_EXERCISES = 36

REQUIRED = [r"def\s+add\s*\(\s*\w+\s*,\s*\w+\s*\)", r"return\s+"]
LABELS = ["定义一个名为 add、接受两个参数的函数", "用 return 把结果返回"]
LEGACY_DETAIL = "第 {index} 项必须出现的写法没有出现，请对照题目要求逐条检查"

# 一道题的失败提交：第 2 条规则（用 return 把结果返回）没有出现。
MISSING_RETURN_CODE = "def add(a, b):\n    print(a + b)\n\nprint(add(2, 3))\n"

SELECT_ALL_LABELS = text(
    """
    SELECT code, required_patterns, requirement_labels
    FROM exercises
    WHERE deleted_at IS NULL
    ORDER BY id
    """
)
SELECT_EXERCISE_ID = text("SELECT id FROM exercises WHERE code = :code")

# 自建一道题来验「标签为空时回退」：不碰任何既有题面，事务结束时随回滚消失。
INSERT_EMPTY_LABEL_EXERCISE = text(
    """
    INSERT INTO exercises (
        lesson_id, code, title, prompt, starter_code, visible_tests,
        required_patterns, forbidden_patterns, requirement_labels,
        estimated_minutes, difficulty, status, order_index, content_version
    )
    SELECT l.id, :code, :title, :prompt, :starter_code,
           CAST(:visible_tests AS jsonb), CAST(:required_patterns AS jsonb),
           '[]'::jsonb, '[]'::jsonb, 10, 1, 'published', 99, 1
    FROM lessons l
    WHERE l.code = 'route_a.py.functions'
    RETURNING id
    """
)


def _as_list(raw: object) -> list[Any]:
    """jsonb 经不同驱动回来可能是 list 也可能是 JSON 文本。"""
    if isinstance(raw, str):
        return list(json.loads(raw))
    return list(raw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 默认档：标签只改措辞，不改判定（不连库）
# ---------------------------------------------------------------------------


def _static(code: str, labels: list[Any] | None) -> judging.Judgment:
    return judging.judge_static_rule(
        code_text=code,
        required_patterns=REQUIRED,
        forbidden_patterns=[],
        expected_output=None,
        claimed_output=None,
        requirement_labels=LABELS if labels is None else labels,
    )


def _failed_required(judgment: judging.Judgment) -> list[judging.Check]:
    """只看必含项：结论项 static_rule 也会 passed=False，它不是规则本身。"""
    return [
        check
        for check in judgment.checks
        if check.name.startswith("required_") and not check.passed
    ]


def test_failed_check_names_the_requirement_in_words() -> None:
    judgment = _static(MISSING_RETURN_CODE, None)
    failed = _failed_required(judgment)
    assert [check.name for check in failed] == ["required_2"]
    assert failed[0].detail == "第 2 项「用 return 把结果返回」没有出现"


def test_labels_never_change_the_verdict() -> None:
    without = _static(MISSING_RETURN_CODE, [])
    with_labels = _static(MISSING_RETURN_CODE, None)
    assert without.is_passed is with_labels.is_passed is False
    assert [c.passed for c in without.checks] == [c.passed for c in with_labels.checks]
    passing = "def add(a, b):\n    return a + b\n"
    assert _static(passing, None).is_passed is _static(passing, []).is_passed is True


@pytest.mark.parametrize(
    "labels",
    [
        [],
        ["只写了第一条"],
        ["", "   "],
        [None, 2],
    ],
)
def test_unusable_labels_fall_back_to_the_original_wording(labels: list[Any]) -> None:
    judgment = _static(MISSING_RETURN_CODE, labels)
    failed = _failed_required(judgment)
    assert [check.name for check in failed] == ["required_2"]
    assert failed[0].detail == LEGACY_DETAIL.format(index=2)


def test_requirement_label_at_is_bounded_and_strips() -> None:
    assert judging.requirement_label_at(["  用 return  ", "第二条"], 1) == "用 return"
    assert judging.requirement_label_at(["只有一条"], 2) == ""
    assert judging.requirement_label_at([], 1) == ""
    assert judging.requirement_label_at(["ok"], 0) == ""
    assert judging.requirement_label_at([None], 1) == ""


def test_labels_do_not_leak_the_pattern_into_the_detail() -> None:
    judgment = _static(MISSING_RETURN_CODE, None)
    rendered = " ".join(check.detail for check in judgment.checks)
    for pattern in REQUIRED:
        assert pattern not in rendered


def test_detail_model_exposes_requirements_but_no_answer_keys() -> None:
    fields = set(ExerciseDetailOut.model_fields)
    assert "requirements" in fields
    for key in ANSWER_KEYS:
        assert key not in fields


# ---------------------------------------------------------------------------
# integration：22 道题 124 条规则，条数、长度、字样逐条对齐
# ---------------------------------------------------------------------------


async def test_every_exercise_has_one_label_per_required_pattern(
    db_session: AsyncSession,
) -> None:
    rows = (await db_session.execute(SELECT_ALL_LABELS)).mappings().all()
    assert len(rows) == TOTAL_EXERCISES
    assert sum(len(_as_list(row["required_patterns"])) for row in rows) == TOTAL_RULES
    for row in rows:
        patterns = _as_list(row["required_patterns"])
        labels = _as_list(row["requirement_labels"])
        # 这是本轮的核心保证：顺序相同、条数相等。
        assert len(labels) == len(patterns), (
            f"{row['code']}: {len(labels)} 条标签 vs {len(patterns)} 条规则"
        )


async def test_labels_are_plain_chinese_and_leak_nothing(db_session: AsyncSession) -> None:
    rows = (await db_session.execute(SELECT_ALL_LABELS)).mappings().all()
    for row in rows:
        patterns = _as_list(row["required_patterns"])
        for index, label in enumerate(_as_list(row["requirement_labels"]), start=1):
            where = f"{row['code']} 第 {index} 条"
            assert isinstance(label, str), where
            assert label.strip(), where
            assert len(label) <= LABEL_MAX_LENGTH, where
            for mark in REGEX_MARKS:
                assert mark not in label, f"{where} 含正则记号 {mark!r}"
            # 标签不是答案键：既不等于某条模式，也不包含任何一条模式原文。
            for pattern in patterns:
                assert label != pattern, where
                assert pattern not in label, where


async def test_detail_endpoint_returns_requirements_and_no_answer_keys(
    api: Any, db_session: AsyncSession
) -> None:
    rows = (await db_session.execute(SELECT_ALL_LABELS)).mappings().all()
    for row in rows:
        exercise_id = int(
            (await db_session.execute(SELECT_EXERCISE_ID, {"code": row["code"]})).scalar_one()
        )
        response = await api.get(f"/api/v1/exercises/{exercise_id}")
        assert response.status_code == 200, row["code"]
        body = response.json()
        assert body["requirements"] == _as_list(row["requirement_labels"]), row["code"]
        for key in ANSWER_KEYS:
            assert key not in body, (row["code"], key)
        # 答案键整体（序列化后的数组原文）也不许出现在响应里。
        rendered = json.dumps(body, ensure_ascii=False)
        assert json.dumps(_as_list(row["required_patterns"]), ensure_ascii=False) not in rendered


async def test_failed_submission_quotes_the_label_in_the_detail(
    api: Any, db_session: AsyncSession
) -> None:
    # route_a.practice.debug.ex1 的第 2 条规则是「定义函数 error_line 读出出错行号」。
    exercise_id = int(
        (await db_session.execute(SELECT_EXERCISE_ID, {"code": "route_a.practice.debug.ex1"}))
        .scalar_one()
    )
    labels = _as_list(
        (
            await db_session.execute(
                text("SELECT requirement_labels FROM exercises WHERE id = :id"),
                {"id": exercise_id},
            )
        ).scalar_one()
    )
    response = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": "def error_kind(text):\n    return text\n"},
    )
    assert response.status_code == 201
    checks = {check["name"]: check for check in response.json()["checks"]}
    assert checks["required_2"]["passed"] is False
    assert checks["required_2"]["detail"] == f"第 2 项「{labels[1]}」没有出现"


async def test_a_blank_label_list_falls_back_without_an_error(
    api: Any, db_session: AsyncSession
) -> None:
    exercise_id = int(
        (
            await db_session.execute(
                INSERT_EMPTY_LABEL_EXERCISE,
                {
                    "code": "test.requirement_labels.empty",
                    "title": "标签为空时的回退用例",
                    "prompt": "这是一道只为回退路径存在的题，事务结束随回滚消失。",
                    "starter_code": "print('hi')\n",
                    "visible_tests": json.dumps(
                        [{"name": "输出 hi", "expect": "hi"}, {"name": "输出 yo", "expect": "yo"}],
                        ensure_ascii=False,
                    ),
                    "required_patterns": json.dumps(
                        [r"def\s+nothing\s*\(", r"return\s+"], ensure_ascii=False
                    ),
                },
            )
        )
        .scalar_one()
    )
    response = await api.post(
        f"/api/v1/exercises/{exercise_id}/submissions",
        json={"code_text": "print('什么都没有')\n"},
    )
    assert response.status_code == 201
    checks = {check["name"]: check for check in response.json()["checks"]}
    assert checks["required_1"]["detail"] == LEGACY_DETAIL.format(index=1)
    assert checks["required_2"]["detail"] == LEGACY_DETAIL.format(index=2)


async def test_0014_backfills_every_exercise_and_is_idempotent(migration_probe) -> None:
    async def snapshot(probe: Any) -> dict[str, tuple[str, ...]]:
        async with probe.connect() as connection:
            rows = await connection.fetch(
                "SELECT code, requirement_labels FROM exercises ORDER BY code"
            )
        return {row["code"]: tuple(json.loads(row["requirement_labels"])) for row in rows}

    async with migration_probe() as probe:
        probe.upgrade(LABELS_REVISION)
        first = await snapshot(probe)
        # 连续第二次 upgrade：列、约束与 124 条标签都必须一模一样。
        probe.upgrade(LABELS_REVISION)
        second = await snapshot(probe)

        assert first == second
        # 探针停在 0014：那时库里只有 0011–0013 播种的 22 道题，0017 的 4 道还没进来。
        assert len(first) == EXERCISES_AT_0014
        assert sum(len(labels) for labels in first.values()) == TOTAL_RULES_AFTER_0014
        assert all(labels for labels in first.values())

        async with probe.connect() as connection:
            default = await connection.fetchval(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'exercises' AND column_name = 'requirement_labels'"
            )
            nullable = await connection.fetchval(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'exercises' AND column_name = 'requirement_labels'"
            )
            checks = await connection.fetchval(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname = 'ck_exercises_requirement_labels'"
            )
        assert "'[]'::jsonb" in str(default)
        assert nullable == "NO"
        assert checks == 1

        # CHECK 真的管用：非数组写不进去。
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            async with probe.connect() as connection:
                await connection.execute(
                    "UPDATE exercises SET requirement_labels = '{}'::jsonb "
                    "WHERE code = 'route_a.py.variables.ex1'"
                )
