"""静态规则与自检判题：只做文本比对，绝不执行用户代码（Sprint 3 阶段 B）。

B2 红线：本模块没有任何执行用户代码的能力。没有 subprocess，没有 eval，没有
exec，没有 importlib；code_text 只用正则做模式匹配，claimed_output 只与
expected_output 做归一化后的字符串比较。

B1 证据口径（唯一，不得改写）：

* judging_mode 'static_rule' -> verification_method 'static_rule'
  -> verification_strength 'assessed' -> UI 标「已验证（静态规则）」
* judging_mode 'self_check'  -> verification_method 'self_report'
  -> verification_strength 'self_reported' -> UI 标「未验证（自检）」

两个分支都**不是** verified：它们不写 user_skill_levels，不授予 L3/L4，MVP 的
等级上限仍然是 L2。evidence_strength() 是 method 到 strength 的唯一映射，所以
任何调用路径都不可能产出 verified。

静态规则通过 ≠ 代码可运行：规则只能证明代码文本里出现了期望的字样，不能证明它
跑得起来，也不能证明输出正确。每一个判定结果都带着这句话（JUDGING_NOTICE）。
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

JUDGING_MODE_STATIC_RULE = "static_rule"
JUDGING_MODE_SELF_CHECK = "self_check"

VERIFICATION_METHOD_STATIC_RULE = "static_rule"
VERIFICATION_METHOD_SELF_REPORT = "self_report"
VERIFICATION_METHOD_NONE = "none"

STRENGTH_ASSESSED = "assessed"
STRENGTH_SELF_REPORTED = "self_reported"
STRENGTH_NONE = "none"

# B1：UI 只认这两个标签，第三个只用于「没有任何判定」的兜底，永不标成 verified。
EVIDENCE_LABELS: Mapping[str, str] = {
    STRENGTH_ASSESSED: "已验证（静态规则）",
    STRENGTH_SELF_REPORTED: "未验证（自检）",
    STRENGTH_NONE: "未验证",
}

JUDGING_NOTICE = "静态规则通过 ≠ 代码可运行：系统只做文本比对，没有执行你的代码。"


def evidence_strength(verification_method: str) -> str:
    """B1：method 到 strength 的唯一映射。verified 不在这张表里，因此不可达。"""
    if verification_method == VERIFICATION_METHOD_STATIC_RULE:
        return STRENGTH_ASSESSED
    if verification_method == VERIFICATION_METHOD_SELF_REPORT:
        return STRENGTH_SELF_REPORTED
    return STRENGTH_NONE


def evidence_label(verification_strength: str) -> str:
    return EVIDENCE_LABELS.get(verification_strength, EVIDENCE_LABELS[STRENGTH_NONE])


@dataclass(frozen=True)
class Check:
    """一条可展示的判定证据。detail 永不包含题目答案键（模式本身/期望输出）。"""

    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class Judgment:
    """一次判定的完整结论，字段与 POST 响应的冻结口径一一对应。"""

    judging_mode: str
    verification_method: str
    verification_strength: str
    evidence_label: str
    is_passed: bool | None
    checks: list[Check]

    def as_dict(self) -> dict[str, Any]:
        return {
            "judging_mode": self.judging_mode,
            "verification_method": self.verification_method,
            "verification_strength": self.verification_strength,
            "evidence_label": self.evidence_label,
            "is_passed": self.is_passed,
            "checks": [check.as_dict() for check in self.checks],
        }


def normalize_output(text: str | None) -> str:
    """比较前的归一化：统一换行、去掉每行尾部空白、去掉首尾空行。

    只处理空白，不改写任何字符内容：输出里的错别字仍然算错。
    """
    unified = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in unified.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines)


def code_for_matching(code_text: str) -> str:
    """把注释和「语句位置的字符串」（docstring）抹成空格，剩下的才是真正代码。

    没有这一步时，把要求抄进一行注释就能通过全部规则——实测只写
    `# def error_kind(...) [-1] int(` 一行即可 13/13 通过。docstring 同理。

    只抹这两类：字典里的字符串（如 {"role": "system"}）必须保留，
    否则要求里那些键名规则会反过来判错。抹成空格而不是删除，
    是为了让偏移量不变，方便排查。
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code_text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # 学习者提交的多半是写了一半的代码，tokenize 会失败；
        # 此时退回保守的行级剥离：只在引号之外把 # 之后抹掉。
        return _strip_comments_fallback(code_text)
    # 按行存成二维字符表：token 的位置是 (行, 列)，直接对字符串下标赋值会报错。
    chars = [list(line) for line in code_text.split("\n")]
    source_lines = code_text.split("\n")
    depth = 0  # 括号嵌套深度：>0 说明在表达式里，此时的字符串是数据而不是文档
    for token in tokens:
        if token.type == tokenize.OP:
            if token.string in ("(", "[", "{"):
                depth += 1
            elif token.string in (")", "]", "}"):
                depth = max(0, depth - 1)
        blank = False
        if token.type == tokenize.COMMENT:
            blank = True
        elif token.type == tokenize.STRING:
            # docstring / 裸字符串语句 = 不在任何括号里，且该行字符串之前只有空白。
            # 这两个条件同时成立才算；字典值 {"role": "system"} 虽然也可能独占一行，
            # 但它位于括号内，depth > 0，因此被保留。
            line_index = token.start[0] - 1
            prefix = source_lines[line_index][: token.start[1]] if line_index < len(source_lines) else ""
            blank = depth == 0 and prefix.strip() == ""
        if not blank:
            continue
        for line_no in range(token.start[0], token.end[0] + 1):
            line_index = line_no - 1
            if line_index >= len(chars):
                break
            line = chars[line_index]
            start = token.start[1] if line_no == token.start[0] else 0
            end = token.end[1] if line_no == token.end[0] else len(line)
            for position in range(start, min(end, len(line))):
                line[position] = " "
    return "\n".join("".join(line) for line in chars)


def _strip_comments_fallback(code_text: str) -> str:
    """tokenize 失败时的保守剥离：引号之外的 # 之后一律抹掉。"""
    out_lines: list[str] = []
    for line in code_text.split("\n"):
        in_single = in_double = False
        cut = len(line)
        escaped = False
        for position, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            elif char == "#" and not in_single and not in_double:
                cut = position
                break
        out_lines.append(line[:cut])
    return "\n".join(out_lines)


def pattern_hits(pattern: str, code_text: str) -> bool:
    """正则优先；题目种子里写坏正则时退化成字面包含，绝不因为一条模式而 500。

    code_text 应当已经过 code_for_matching 处理：注释与 docstring 不参与匹配。
    """
    try:
        return re.search(pattern, code_text) is not None
    except re.error:
        return pattern in code_text


def _build_judgment(
    *,
    judging_mode: str,
    verification_method: str,
    is_passed: bool | None,
    checks: list[Check],
) -> Judgment:
    strength = evidence_strength(verification_method)
    return Judgment(
        judging_mode=judging_mode,
        verification_method=verification_method,
        verification_strength=strength,
        evidence_label=evidence_label(strength),
        is_passed=is_passed,
        checks=checks,
    )


def requirement_label_at(labels: Sequence[str], index: int) -> str:
    """第 index 条（从 1 开始）中文要求；缺失或不可用时返回空串。

    空串是「没有可展示的标签」的唯一表示，调用方据此回退旧文案。标签顺序与
    required_patterns 一致，所以第 index 条标签说的就是第 index 条规则。
    """
    position = index - 1
    if position < 0 or position >= len(labels):
        return ""
    value = labels[position]
    if not isinstance(value, str):
        return ""
    return value.strip()


def judge_static_rule(
    *,
    code_text: str,
    required_patterns: Sequence[str],
    forbidden_patterns: Sequence[str],
    expected_output: str | None,
    claimed_output: str | None,
    requirement_labels: Sequence[str] = (),
) -> Judgment:
    """B1 static_rule：必含全命中 + 禁止全不命中 +（可选）输出文本相等。

    输出比对只在「题目有期望输出 + 用户填了自报输出」时进行（冻结口径）。
    detail 只给序号、标签与结论，不回显模式本身，避免把答案键泄漏给客户端。

    requirement_labels 是第 N 条规则的中文要求（顺序与 required_patterns 一致）；
    标签缺失、为空或不是字符串时回退到原来的序号文案——标签只影响措辞，绝不参与
    判定，也绝不会让判题报错。
    """
    # 匹配用的文本先抹掉注释与 docstring：否则把要求抄进注释即可通过。
    matchable = code_for_matching(code_text)
    checks: list[Check] = []
    missing_required = 0
    for index, pattern in enumerate(required_patterns, start=1):
        hit = pattern_hits(pattern, matchable)
        if not hit:
            missing_required += 1
        label = requirement_label_at(requirement_labels, index)
        checks.append(
            Check(
                name=f"required_{index}",
                passed=hit,
                detail=(
                    f"第 {index} 项必须出现的写法已出现"
                    if hit
                    else (
                        f"第 {index} 项「{label}」没有出现"
                        if label
                        else f"第 {index} 项必须出现的写法没有出现，请对照题目要求逐条检查"
                    )
                ),
            )
        )

    hit_forbidden = 0
    for index, pattern in enumerate(forbidden_patterns, start=1):
        hit = pattern_hits(pattern, matchable)
        if hit:
            hit_forbidden += 1
        checks.append(
            Check(
                name=f"forbidden_{index}",
                passed=not hit,
                detail=(
                    f"第 {index} 项禁止出现的写法出现了，请删掉它"
                    if hit
                    else f"第 {index} 项禁止出现的写法没有出现"
                ),
            )
        )

    output_ok = True
    if expected_output is not None and claimed_output is not None:
        output_ok = normalize_output(expected_output) == normalize_output(claimed_output)
        checks.append(
            Check(
                name="claimed_output",
                passed=output_ok,
                detail=(
                    "自报的运行结果与期望输出一致（已忽略每行尾部空白与首尾空行，缩进仍然算差异）"
                    if output_ok
                    else "自报的运行结果与期望输出不一致（已忽略每行尾部空白与首尾空行，缩进仍然算差异）"
                ),
            )
        )

    is_passed = missing_required == 0 and hit_forbidden == 0 and output_ok
    checks.append(
        Check(
            name=JUDGING_MODE_STATIC_RULE,
            passed=is_passed,
            detail=(
                JUDGING_NOTICE
                if is_passed
                else f"静态规则未全部通过（缺 {missing_required} 项必须写法，"
                f"命中 {hit_forbidden} 项禁止写法）。{JUDGING_NOTICE}"
            ),
        )
    )

    return _build_judgment(
        judging_mode=JUDGING_MODE_STATIC_RULE,
        verification_method=VERIFICATION_METHOD_STATIC_RULE,
        is_passed=is_passed,
        checks=checks,
    )


def judge_self_check(*, self_reported_passed: bool) -> Judgment:
    """B1 self_check：结论完全来自用户自述，所以只能标「未验证（自检）」。"""
    passed = bool(self_reported_passed)
    checks = [
        Check(
            name="self_reported",
            passed=passed,
            detail=(
                "你在本地自述运行通过；系统没有执行代码，这条结论未经验证。"
                if passed
                else "你自述本地运行未通过；系统没有执行代码，这条结论未经验证。"
            ),
        ),
        Check(
            name="code_execution",
            passed=False,
            detail="系统不执行任何用户代码：自检结论无法由系统复核。",
        ),
    ]
    return _build_judgment(
        judging_mode=JUDGING_MODE_SELF_CHECK,
        verification_method=VERIFICATION_METHOD_SELF_REPORT,
        is_passed=passed,
        checks=checks,
    )


def judge_submission(
    *,
    code_text: str,
    required_patterns: Sequence[str],
    forbidden_patterns: Sequence[str],
    expected_output: str | None,
    claimed_output: str | None,
    self_reported_passed: bool | None,
    requirement_labels: Sequence[str] = (),
) -> Judgment:
    """入口：填了 self_reported_passed 就是自检，否则走静态规则（口径冻结）。"""
    if self_reported_passed is not None:
        return judge_self_check(self_reported_passed=self_reported_passed)
    return judge_static_rule(
        code_text=code_text,
        required_patterns=required_patterns,
        forbidden_patterns=forbidden_patterns,
        expected_output=expected_output,
        claimed_output=claimed_output,
        requirement_labels=requirement_labels,
    )


__all__ = [
    "Check",
    "EVIDENCE_LABELS",
    "JUDGING_MODE_SELF_CHECK",
    "JUDGING_MODE_STATIC_RULE",
    "JUDGING_NOTICE",
    "Judgment",
    "VERIFICATION_METHOD_SELF_REPORT",
    "VERIFICATION_METHOD_STATIC_RULE",
    "evidence_label",
    "evidence_strength",
    "judge_self_check",
    "judge_static_rule",
    "judge_submission",
    "normalize_output",
    "pattern_hits",
    "requirement_label_at",
]
