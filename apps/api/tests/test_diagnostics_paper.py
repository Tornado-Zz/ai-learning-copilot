"""题库唯一来源：GET /api/v1/diagnostics/paper 返回无答案键的 20 道题面。"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient, Response

from app.services.question_set import QUESTIONS_V1, TOTAL_QUESTIONS, question_ids

PAPER_PATH = "/api/v1/diagnostics/paper"
# 详情端点才有的字段名，题面端点一个都不许出现
ANSWER_SUBSTRINGS = ("answer", "correct", "explanation", "selected")


@pytest.fixture
async def paper_response(client: AsyncClient) -> Response:
    response = await client.get(PAPER_PATH, params={"version": "v1"})
    assert response.status_code == 200, response.text
    return response


async def test_paper_returns_twenty_questions_and_matching_total(
    paper_response: Response,
) -> None:
    body = paper_response.json()
    assert set(body) == {"question_set_version", "rule_version", "total", "questions"}
    assert body["question_set_version"] == "v1"
    assert body["rule_version"] == "r1"
    assert body["total"] == TOTAL_QUESTIONS == 20
    assert len(body["questions"]) == body["total"]
    assert [question["order"] for question in body["questions"]] == list(range(1, 21))


async def test_question_ids_match_the_scoring_module_exactly(
    paper_response: Response,
) -> None:
    served = [question["id"] for question in paper_response.json()["questions"]]
    scored = question_ids()
    assert served == list(scored)
    assert set(served) == {question.id for question in QUESTIONS_V1}
    print(f"paper ids == scoring ids: {served == list(scored)} ({len(served)} questions)")


async def test_response_carries_no_answer_key(paper_response: Response) -> None:
    body = paper_response.json()
    for question in body["questions"]:
        assert set(question) == {"id", "order", "type", "prompt", "options", "domain_code"}
    serialized = json.dumps(body, ensure_ascii=False)
    leaked = [needle for needle in ANSWER_SUBSTRINGS if needle in serialized]
    assert leaked == [], f"答案键泄露：{leaked}"
    assert "answer" not in paper_response.text
    print(f"answer keys leaked into the serialized body: {leaked}")


async def test_paper_never_carries_a_correct_or_explanation_field(
    paper_response: Response,
) -> None:
    for question in paper_response.json()["questions"]:
        assert "correct" not in question, question["id"]
        assert "explanation" not in question, question["id"]
        assert "selected" not in question, question["id"]
        assert "is_correct" not in question, question["id"]
    # 同一批题目的答案键只能出现在 GET /diagnostics/attempts/{id}
    assert "correct" not in paper_response.text
    assert "explanation" not in paper_response.text


async def test_unknown_version_is_rejected_with_the_unified_envelope(
    client: AsyncClient,
) -> None:
    response = await client.get(PAPER_PATH, params={"version": "v2"})
    assert response.status_code == 422, response.text
    body = response.json()
    assert set(body) == {"error", "request_id"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"] == {
        "field": "version",
        "reason": "unsupported_version",
        "supported": ["v1"],
    }
    assert body["request_id"] == response.headers["X-Request-ID"]


async def test_missing_version_defaults_to_v1(paper_response: Response, client: AsyncClient) -> None:
    response = await client.get(PAPER_PATH)
    assert response.status_code == 200, response.text
    assert response.json() == paper_response.json()


async def test_every_question_has_non_empty_options_with_distinct_keys(
    paper_response: Response,
) -> None:
    for question in paper_response.json()["questions"]:
        keys = [option["key"] for option in question["options"]]
        assert keys, f"{question['id']} 没有选项"
        assert len(keys) == len(set(keys)), f"{question['id']} 选项 key 重复"
        assert all(option["text"] for option in question["options"])


async def test_domain_code_is_returned_for_result_grouping(paper_response: Response) -> None:
    domain_codes = {question["domain_code"] for question in paper_response.json()["questions"]}
    assert domain_codes == {question.skill_code for question in QUESTIONS_V1}
    assert len(domain_codes) == 6
