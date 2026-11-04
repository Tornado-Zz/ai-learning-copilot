"""GET /diagnostics/attempts/{id}：逐题判定依据；答案键只在这个端点出现。

隔离策略与其余集成用例一致：走单用户 HTTP 的用例只断言本测试新建的批次，
越权用例自建 users 行，不依赖库内既有数据。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diagnostics as diagnostics_service
from app.services.question_set import DOMAIN_CODES, QUESTIONS_V1

pytestmark = pytest.mark.integration

DETAIL_PATH = "/api/v1/diagnostics/attempts/{attempt_id}"

SELECT_STORED_ANSWERS = text(
    "SELECT answers FROM diagnostic_attempts WHERE id = :attempt_id"
)

QUESTION_FIELDS = {
    "id",
    "order",
    # Sprint 2 补的题型字段：取自题库（single_choice / code_reading / bug_fix）
    "type",
    "domain_code",
    "prompt",
    "options",
    "selected",
    "correct",
    "is_correct",
    "explanation",
}
DOMAIN_FIELDS = {"skill_code", "level", "state", "correct", "total", "rate"}


def _payload(token: str, answers: dict[str, dict[str, str]]) -> dict[str, object]:
    return {
        "attempt_token": token,
        "question_set_version": "v1",
        "rule_version": "r1",
        "answers": answers,
    }


async def _submit(api, token: str, answers: dict[str, dict[str, str]]) -> int:
    response = await api.post("/api/v1/diagnostics", json=_payload(token, answers))
    assert response.status_code == 201, response.text
    return int(response.json()["attempt_id"])


async def test_detail_returns_per_question_verdicts_from_the_live_question_set(
    api, db_session: AsyncSession, all_correct_answers, unique_token
) -> None:
    attempt_id = await _submit(api, unique_token("detail"), all_correct_answers)

    response = await api.get(DETAIL_PATH.format(attempt_id=attempt_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "attempt_id",
        "submitted_at",
        "question_set_version",
        "rule_version",
        "total_correct",
        "total_questions",
        "domains",
        "questions",
    }
    assert body["attempt_id"] == attempt_id
    assert body["submitted_at"].endswith("Z")
    assert body["question_set_version"] == "v1"
    assert body["rule_version"] == "r1"
    assert body["total_correct"] == body["total_questions"] == 20
    assert [domain["skill_code"] for domain in body["domains"]] == list(DOMAIN_CODES)
    assert all(set(domain) == DOMAIN_FIELDS for domain in body["domains"])

    questions = body["questions"]
    assert len(questions) == 20
    assert [question["order"] for question in questions] == list(range(1, 21))
    assert [question["id"] for question in questions] == [q.id for q in QUESTIONS_V1]
    for served, source in zip(questions, QUESTIONS_V1, strict=True):
        assert set(served) == QUESTION_FIELDS
        # 题面与选项在请求时从题库模块现取，不来自数据库
        assert served["prompt"] == source.prompt
        assert served["options"] == [
            {"key": key, "text": text} for key, text in source.options.items()
        ]
        assert served["type"] == source.kind
        assert served["domain_code"] == source.skill_code
        assert served["correct"] == source.answer
        assert served["selected"] == source.answer
        assert served["is_correct"] is True
        assert served["explanation"] is None
    # 三种题型都真实出现在 20 题里（前端不再显示"题型未提供"）
    assert {question["type"] for question in questions} == {
        "single_choice",
        "code_reading",
        "bug_fix",
    }


async def test_detail_marks_wrong_choices_and_the_database_stores_answers_only(
    api, db_session: AsyncSession, answer_factory, unique_token
) -> None:
    answers = answer_factory({"route_a.a1": 2})
    attempt_id = await _submit(api, unique_token("detail-wrong"), answers)

    body = (await api.get(DETAIL_PATH.format(attempt_id=attempt_id))).json()
    submitted = {question_id: value["choice"] for question_id, value in answers.items()}
    answer_key = {question.id: question.answer for question in QUESTIONS_V1}
    flagged = {question["id"]: question["is_correct"] for question in body["questions"]}
    assert flagged == {
        question_id: submitted[question_id] == answer_key[question_id] for question_id in answer_key
    }
    assert sum(flagged.values()) == body["total_correct"] == 2
    assert {
        question["id"]: question["selected"] for question in body["questions"]
    } == submitted

    # 数据库里只有「题号 → 选项」，没有题面、选项文本或答案的副本
    stored = (
        await db_session.execute(SELECT_STORED_ANSWERS, {"attempt_id": attempt_id})
    ).scalar_one()
    assert stored == submitted
    assert all(isinstance(value, str) for value in stored.values())


async def test_another_users_batch_is_404_and_never_leaks_verdicts(
    api,
    db_session: AsyncSession,
    all_correct_answers,
    test_user,
    flatten_answers,
    unique_token,
) -> None:
    foreign = await diagnostics_service.submit_diagnostic(
        db_session,
        user_id=int(test_user["id"]),
        attempt_token=unique_token("foreign"),
        question_set_version="v1",
        rule_version="r1",
        answers=flatten_answers(all_correct_answers),
    )
    foreign_id = int(foreign.attempt["attempt_id"])

    forbidden = await api.get(DETAIL_PATH.format(attempt_id=foreign_id))
    assert forbidden.status_code == 404, forbidden.text
    body = forbidden.json()
    assert set(body) == {"error", "request_id"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert body["request_id"] == forbidden.headers["X-Request-ID"]
    assert "questions" not in body and "correct" not in forbidden.text
    assert "selected" not in forbidden.text

    # 不存在的批次与非法 id 都不确认「这个 id 是否存在」
    unknown = await api.get(DETAIL_PATH.format(attempt_id=10**9))
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "NOT_FOUND"

    invalid = await api.get("/api/v1/diagnostics/attempts/not-a-number")
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
