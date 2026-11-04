"""判题匹配前的剥离：注释与 docstring 不得参与模式匹配。

背景：v0.1.19 之前，把要求抄进一行注释即可让 22 道练习全部通过——
实测 `# def error_kind(...) [-1] int(` 一行就拿到 13/13。静态规则本身不执行代码，
但至少不该被「写在注释里」骗过。
"""

from __future__ import annotations

import pytest

from app.services.judging import code_for_matching, judge_static_rule, pattern_hits


def test_comment_is_blanked_before_matching() -> None:
    """注释里的写法不参与匹配。"""
    code = "# def error_kind(t) [-1] int("
    assert pattern_hits(r"def\s+error_kind", code_for_matching(code)) is False


def test_docstring_is_blanked_before_matching() -> None:
    """docstring 同理：写进文档字符串也不算。"""
    code = '"""def error_kind(t) and [-1] and int("""'
    stripped = code_for_matching(code)
    assert pattern_hits(r"def\s+error_kind", stripped) is False
    assert pattern_hits(r"\[-1\]", stripped) is False


def test_code_inside_a_function_body_is_kept() -> None:
    """只有 docstring 被抹掉，函数体本身必须保留。"""
    code = 'def f():\n    """说明"""\n    return [-1]'
    stripped = code_for_matching(code)
    assert pattern_hits(r"def\s+f\s*\(", stripped) is True
    assert pattern_hits(r"\[-1\]", stripped) is True


@pytest.mark.parametrize(
    ("code", "pattern"),
    [
        ('payload = {"role": "system"}', r"['\"]role['\"]"),
        ('payload = {\n    "role": "system",\n}', r"['\"]role['\"]"),
        ('print("line")', r"['\"]line['\"]"),
    ],
)
def test_strings_inside_expressions_are_kept(code: str, pattern: str) -> None:
    """字典值、参数这类字符串是数据，抹掉会让键名规则反过来判错。"""
    assert pattern_hits(pattern, code_for_matching(code)) is True


def test_unparsable_code_falls_back_without_raising() -> None:
    """学习者常提交写了一半的代码；剥离绝不能因此抛异常。"""
    code = "if x:\n    print(1  # 未闭合"
    stripped = code_for_matching(code)
    assert "print" in stripped
    assert "未闭合" not in stripped


def test_a_comment_only_submission_cannot_pass() -> None:
    """端到端：只写注释的提交必须判失败。"""
    code = "# def error_kind(t) [-1] int( strip( print("
    judgment = judge_static_rule(
        code_text=code,
        required_patterns=[r"def\s+error_kind\s*\(", r"\[-1\]", r"\bint\s*\("],
        forbidden_patterns=[],
        expected_output=None,
        claimed_output=None,
    )
    assert judgment.is_passed is False


def test_a_real_solution_still_passes() -> None:
    """反向保证：真代码不能被这次收紧误伤。"""
    code = "def error_kind(t):\n    lines = t.splitlines()\n    return lines[-1]\n"
    judgment = judge_static_rule(
        code_text=code,
        required_patterns=[r"def\s+error_kind\s*\(", r"\[-1\]"],
        forbidden_patterns=[],
        expected_output=None,
        claimed_output=None,
    )
    assert judgment.is_passed is True