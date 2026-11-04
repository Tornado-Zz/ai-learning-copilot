"""判题前的语法解析门禁：语法不合法的代码不能算通过。

静态规则只做文本比对，所以少一个右括号也能命中「定义了函数」的规则——
v0.1.20 起先过一遍 ast.parse：只解析、不执行，语法不过直接判失败。
"""

from __future__ import annotations

import pytest

from app.services.judging import judge_static_rule, syntax_error


def test_valid_code_has_no_syntax_error() -> None:
    assert syntax_error("def f(x):\n    return x\n") is None


def test_invalid_code_reports_the_line() -> None:
    """错误信息要指到行号，学习者才知道去哪儿改。"""
    message = syntax_error("x = 1\ny = ")
    assert message is not None
    assert "第 2 行" in message


@pytest.mark.parametrize(
    "code",
    [
        "print(" + "(" * 300 + "1" + ")" * 300 + ")",  # 超深嵌套
        "x = 1" * 20000,  # 超长单行
    ],
)
def test_pathological_input_never_raises(code: str) -> None:
    """病态输入可以判失败，但绝不能让判题 500。"""
    assert isinstance(syntax_error(code), (str, type(None)))


def test_patterns_matching_is_not_enough_when_syntax_is_broken() -> None:
    """核心断言：规则全中 + 语法错 = 判失败。"""
    code = "def error_kind(t\n    return [-1]"
    judgment = judge_static_rule(
        code_text=code,
        required_patterns=[r"def\s+error_kind", r"\[-1\]"],
        forbidden_patterns=[],
        expected_output=None,
        claimed_output=None,
    )
    assert judgment.is_passed is False
    assert judgment.checks[0].name == "syntax"
    assert judgment.checks[0].passed is False


def test_valid_code_still_passes_through_the_gate() -> None:
    """反向保证：语法门禁不能误伤正确答案。"""
    code = "def error_kind(t):\n    return t[-1]\n"
    judgment = judge_static_rule(
        code_text=code,
        required_patterns=[r"def\s+error_kind", r"\[-1\]"],
        forbidden_patterns=[],
        expected_output=None,
        claimed_output=None,
    )
    assert judgment.is_passed is True
    assert judgment.checks[0].name == "syntax"
    assert judgment.checks[0].passed is True