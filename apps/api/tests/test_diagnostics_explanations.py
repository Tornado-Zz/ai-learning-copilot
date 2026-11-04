"""逐题解析：20 题全有解析、发卷不泄题、明细与题库一致、版本不升。

断言分两层：直接读 QUESTIONS_V1（不依赖数据库），再走 HTTP 确认发卷端点与
批次明细端点的实际形状——解析只在明细出现，题集/规则版本保持 v1 / r1。
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.services.question_set import (
    QUESTION_SET_VERSION,
    QUESTIONS_V1,
    RULE_VERSION,
    TOTAL_QUESTIONS,
    paper_questions,
)

PAPER_PATH = "/api/v1/diagnostics/paper"
DETAIL_PATH = "/api/v1/diagnostics/attempts/{attempt_id}"
# 任务下限：每题解析至少 20 字（实际写的是 40–80 字）
MIN_EXPLANATION_CHARS = 20


def _submit_payload(token: str, answers: dict[str, dict[str, str]]) -> dict[str, object]:
    return {
        "attempt_token": token,
        "question_set_version": "v1",
        "rule_version": "r1",
        "answers": answers,
    }


def test_all_twenty_questions_carry_a_usable_explanation() -> None:
    assert TOTAL_QUESTIONS == len(QUESTIONS_V1) == 20
    for question in QUESTIONS_V1:
        explanation = question.explanation
        assert isinstance(explanation, str), question.id
        assert explanation and explanation.strip() == explanation, question.id
        assert len(explanation) >= MIN_EXPLANATION_CHARS, question.id
        # 解析不是把正确选项原文抄一遍，而要说清机制
        assert explanation != question.options[question.answer], question.id
    # 20 条解析互不重复：复制粘贴的模板解析在这里就会露出来
    assert len({question.explanation for question in QUESTIONS_V1}) == TOTAL_QUESTIONS
    shortest = min(len(question.explanation) for question in QUESTIONS_V1)
    longest = max(len(question.explanation) for question in QUESTIONS_V1)
    print(f"解析条数={TOTAL_QUESTIONS} 最短={shortest} 字 最长={longest} 字")


def test_paper_projection_drops_the_explanation_field() -> None:
    served = paper_questions()
    assert len(served) == TOTAL_QUESTIONS
    for question in served:
        assert "explanation" not in question, question["id"]
    serialized = json.dumps(served, ensure_ascii=False)
    assert "explanation" not in serialized
    leaked = [question.id for question in QUESTIONS_V1 if question.explanation in serialized]
    assert leaked == [], f"发卷视图泄题：{leaked}"


async def test_paper_endpoint_never_returns_explanation(client: AsyncClient) -> None:
    response = await client.get(PAPER_PATH, params={"version": "v1"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question_set_version"] == QUESTION_SET_VERSION == "v1"
    assert body["rule_version"] == RULE_VERSION == "r1"
    for question in body["questions"]:
        assert "explanation" not in question, question["id"]
    assert "explanation" not in response.text
    leaked = [question.id for question in QUESTIONS_V1 if question.explanation in response.text]
    assert leaked == [], f"发卷响应泄题：{leaked}"
    print(f"发卷响应 explanation 键：{'explanation' in response.text}，泄露解析 {len(leaked)} 条")


def test_explanations_do_not_bump_the_question_set_or_rule_version() -> None:
    # 解析是补充说明，不改变评分口径，所以两档版本号都必须原地不动
    assert QUESTION_SET_VERSION == "v1"
    assert RULE_VERSION == "r1"


@pytest.mark.integration
async def test_attempt_detail_repeats_the_question_bank_explanation(
    api, all_correct_answers, unique_token
) -> None:
    created = await api.post(
        "/api/v1/diagnostics",
        json=_submit_payload(unique_token("explanation"), all_correct_answers),
    )
    assert created.status_code == 201, created.text
    attempt_id = int(created.json()["attempt_id"])

    response = await api.get(DETAIL_PATH.format(attempt_id=attempt_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question_set_version"] == "v1"
    assert body["rule_version"] == "r1"
    served = {question["id"]: question["explanation"] for question in body["questions"]}
    assert served == {question.id: question.explanation for question in QUESTIONS_V1}
    assert all(isinstance(value, str) and value.strip() for value in served.values())
    print(f"明细 {len(served)} 条解析与题库一致：{served == {q.id: q.explanation for q in QUESTIONS_V1}}")
