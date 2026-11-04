"""Sprint 3 阶段 B 的判题口径单元用例（不连数据库，默认档 uv run pytest -q 即执行）。

这些用例锁住 B1/B2 的冻结语义：

* 证据标签只有「已验证（静态规则）」与「未验证（自检）」，任何分支都不可能产出
  verified；
* 判题只做文本比对，判题模块里不存在执行用户代码的能力；
* 判题的 detail 不回显答案键（模式本身、期望输出）；
* 详情响应模型没有答案键字段。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.schemas.exercises import (
    ExerciseDetailOut,
    SubmissionCreateRequest,
    SubmissionJudgedOut,
)
from app.services import judging

SERVICES_DIR = Path(__file__).resolve().parents[1] / "app" / "services"

REQUIRED = [r"print\s*\(", r"def\s+greet\s*\("]
FORBIDDEN = [r"\beval\s*\(", r"\bexec\s*\("]
EXPECTED = "你好，同学"
GOOD_CODE = 'def greet(name="同学"):\n    return "你好，" + name\n\nprint(greet())\n'


def _static(code: str = GOOD_CODE, claimed: str | None = None) -> judging.Judgment:
    return judging.judge_static_rule(
        code_text=code,
        required_patterns=REQUIRED,
        forbidden_patterns=FORBIDDEN,
        expected_output=EXPECTED,
        claimed_output=claimed,
    )


def _module_tree(filename: str) -> ast.Module:
    return ast.parse((SERVICES_DIR / filename).read_text(encoding="utf-8"))


def test_static_rule_passes_when_required_hit_and_forbidden_absent() -> None:
    judgment = _static()
    assert judgment.judging_mode == "static_rule"
    assert judgment.verification_method == "static_rule"
    assert judgment.verification_strength == "assessed"
    assert judgment.evidence_label == "已验证（静态规则）"
    assert judgment.is_passed is True


def test_static_rule_fails_when_a_required_pattern_is_missing() -> None:
    judgment = _static(code='print("只写了一句话")\n')
    assert judgment.is_passed is False
    failed = [check.name for check in judgment.checks if not check.passed]
    assert "required_2" in failed
    # 结论仍然是 assessed，不是 verified
    assert judgment.verification_strength == "assessed"


def test_static_rule_fails_when_a_forbidden_pattern_appears() -> None:
    judgment = _static(code=GOOD_CODE + "\neval(\"1 + 1\")\n")
    assert judgment.is_passed is False
    assert "forbidden_1" in [check.name for check in judgment.checks if not check.passed]


def test_static_rule_output_comparison_ignores_whitespace_only() -> None:
    # 契约：只忽略每行尾部空白与首尾空行，行内的前导空格（缩进）仍然算差异。
    judgment = _static(claimed="你好，同学  \n\n")
    assert judgment.is_passed is True
    output_checks = [check for check in judgment.checks if check.name == "claimed_output"]
    assert len(output_checks) == 1 and output_checks[0].passed is True


def test_static_rule_output_mismatch_fails_even_when_patterns_match() -> None:
    judgment = _static(claimed="你好，小明")
    assert judgment.is_passed is False
    output_checks = [check for check in judgment.checks if check.name == "claimed_output"]
    assert len(output_checks) == 1 and output_checks[0].passed is False


def test_output_check_is_skipped_when_user_reports_no_output() -> None:
    # 冻结口径：只有在「题目有期望输出 且 用户填了自报输出」时才做输出比对。
    judgment = _static(claimed=None)
    assert [check.name for check in judgment.checks].count("claimed_output") == 0
    assert judgment.is_passed is True


@pytest.mark.parametrize("claimed", [None, EXPECTED, "错的输出"])
@pytest.mark.parametrize("extra", ["", "\neval(1)\n"])
def test_no_static_rule_branch_reports_verified(claimed: str | None, extra: str) -> None:
    judgment = _static(code=GOOD_CODE + extra, claimed=claimed)
    assert judgment.verification_strength in {"assessed", "self_reported", "none"}
    assert judgment.verification_strength != "verified"
    assert judgment.evidence_label != "verified"


def test_self_check_is_labelled_unverified_and_keeps_the_user_claim() -> None:
    passed = judging.judge_self_check(self_reported_passed=True)
    failed = judging.judge_self_check(self_reported_passed=False)
    assert passed.is_passed is True and failed.is_passed is False
    for judgment in (passed, failed):
        assert judgment.judging_mode == "self_check"
        assert judgment.verification_method == "self_report"
        assert judgment.verification_strength == "self_reported"
        assert judgment.evidence_label == "未验证（自检）"


def test_self_report_presence_switches_the_mode() -> None:
    assert judging.judge_submission(
        code_text=GOOD_CODE,
        required_patterns=REQUIRED,
        forbidden_patterns=FORBIDDEN,
        expected_output=None,
        claimed_output=None,
        self_reported_passed=None,
    ).judging_mode == "static_rule"
    assert judging.judge_submission(
        code_text=GOOD_CODE,
        required_patterns=REQUIRED,
        forbidden_patterns=FORBIDDEN,
        expected_output=None,
        claimed_output=None,
        self_reported_passed=False,
    ).judging_mode == "self_check"


def test_checks_never_echo_answer_keys() -> None:
    secret_pattern = r"SECRET_REQUIRED_XYZ"
    secret_output = "SECRET_OUTPUT_XYZ"
    judgment = judging.judge_static_rule(
        code_text="print('无关代码')",
        required_patterns=[secret_pattern],
        forbidden_patterns=[r"SECRET_FORBIDDEN_XYZ"],
        expected_output=secret_output,
        claimed_output="别的内容",
    )
    rendered = " ".join(
        [check.name + check.detail for check in judgment.checks]
        + [judgment.evidence_label, judgment.judging_mode]
    )
    for secret in ("SECRET_REQUIRED_XYZ", "SECRET_FORBIDDEN_XYZ", "SECRET_OUTPUT_XYZ"):
        assert secret not in rendered


def test_invalid_regex_pattern_falls_back_to_a_literal_match() -> None:
    # 种子里写坏的正则不该让接口 500：退化成字面包含即可。
    assert judging.pattern_hits("(未闭合", "这里有(未闭合的括号") is True
    assert judging.pattern_hits("(未闭合", "没有那个东西") is False


def test_normalize_output_only_touches_whitespace() -> None:
    assert judging.normalize_output("a  \r\n\r\nb\r\n\n") == "a\n\nb"
    assert judging.normalize_output("a\n\nb") != judging.normalize_output("a\nb")


@pytest.mark.parametrize("filename", ["judging.py", "exercises.py"])
def test_judging_code_path_has_no_execution_primitives(filename: str) -> None:
    """B2 的结构性证明：判题代码里没有执行用户代码的能力。"""
    banned_modules = {"subprocess", "importlib", "os", "shutil", "multiprocessing", "pty"}
    banned_calls = {"eval", "exec", "compile", "__import__", "system"}
    for node in ast.walk(_module_tree(filename)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned_modules, node.lineno
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned_modules, node.lineno
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in banned_calls, (node.func.id, node.lineno)


def test_detail_response_model_carries_no_answer_keys() -> None:
    fields = set(ExerciseDetailOut.model_fields)
    for key in ("required_patterns", "forbidden_patterns", "expected_output"):
        assert key not in fields
    assert {"prompt", "starter_code", "visible_tests"} <= fields


def test_judged_response_model_is_exactly_the_frozen_seven_keys() -> None:
    assert set(SubmissionJudgedOut.model_fields) == {
        "submission_id",
        "judging_mode",
        "verification_method",
        "verification_strength",
        "evidence_label",
        "is_passed",
        "checks",
    }


def test_submission_request_defaults_to_self_check_absent() -> None:
    payload = SubmissionCreateRequest(code_text="print(1)")
    assert payload.claimed_output is None and payload.self_reported_passed is None
    with pytest.raises(Exception):
        SubmissionCreateRequest()  # code_text 是必填
