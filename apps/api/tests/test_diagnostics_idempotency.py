"""幂等提交三态：新 token 追加、同 token 同内容回放 200、同 token 不同内容 409。

并发场景用「首次预读返回 None」模拟两个请求同时看不到对方：真正的冲突由数据库的
uq_diagnostic_attempts_token 抛出 IntegrityError，随后走与普通重试完全相同的比对，
因此既不新增行也不是 500。
"""

from __future__ import annotations

import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diagnostics as diagnostics_service
from app.services.question_set import CHOICES, QUESTIONS_V1, score_answers

pytestmark = pytest.mark.integration

COUNT_TOKEN = text(
    "SELECT count(*) FROM diagnostic_attempts WHERE user_id = :user_id AND attempt_token = :token"
)

INSERT_HISTORICAL_ATTEMPT = text(
    """
    INSERT INTO diagnostic_attempts (
        user_id, attempt_token, question_set_version, rule_version,
        answers, domain_scores, total_correct, total_questions
    )
    VALUES (
        :user_id, :attempt_token, :question_set_version, :rule_version,
        :answers, :domain_scores, :total_correct, :total_questions
    )
    RETURNING id
    """
).bindparams(bindparam("answers", type_=JSONB), bindparam("domain_scores", type_=JSONB))

CORRECT_CHOICES: dict[str, str] = {question.id: question.answer for question in QUESTIONS_V1}


def _payload(
    token: str,
    answers: dict[str, dict[str, str]],
    *,
    question_set_version: str = "v1",
    rule_version: str = "r1",
) -> dict[str, object]:
    return {
        "attempt_token": token,
        "question_set_version": question_set_version,
        "rule_version": rule_version,
        "answers": answers,
    }


def _flat(answers: dict[str, dict[str, str]]) -> dict[str, str]:
    return {question_id: value["choice"] for question_id, value in answers.items()}


def _with_one_answer_changed(answers: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    changed = dict(answers)
    changed["q01"] = {"choice": next(c for c in CHOICES if c != CORRECT_CHOICES["q01"])}
    return changed


async def _api_user_id(api) -> int:
    return int((await api.get("/api/v1/users/me")).json()["user"]["id"])


async def _token_rows(db_session: AsyncSession, user_id: int, token: str) -> int:
    return int(
        (await db_session.execute(COUNT_TOKEN, {"user_id": user_id, "token": token})).scalar_one()
    )


async def _insert_historical_attempt(
    db_session: AsyncSession,
    *,
    user_id: int,
    token: str,
    answers: dict[str, str],
    question_set_version: str = "v1",
    rule_version: str = "r1",
) -> int:
    """A stored batch as it would look after a question-set version bump."""
    scored = score_answers(answers)
    return int(
        (
            await db_session.execute(
                INSERT_HISTORICAL_ATTEMPT,
                {
                    "user_id": user_id,
                    "attempt_token": token,
                    "question_set_version": question_set_version,
                    "rule_version": rule_version,
                    "answers": dict(answers),
                    "domain_scores": {
                        domain.skill_code: domain.as_json() for domain in scored.domains
                    },
                    "total_correct": scored.total_correct,
                    "total_questions": scored.total_questions,
                },
            )
        ).scalar_one()
    )


async def test_identical_retry_replays_200_and_appends_no_rows(
    api, db_session: AsyncSession, all_correct_answers, row_counter, unique_token
) -> None:
    user_id = await _api_user_id(api)
    token = unique_token("idem")

    first = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert first.status_code == 201, first.text
    attempt_id = first.json()["attempt_id"]
    attempts_after_first = await row_counter(db_session, "diagnostic_attempts")
    levels_after_first = await row_counter(db_session, "user_skill_levels")

    second = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert second.json()["attempt_id"] == attempt_id
    assert await row_counter(db_session, "diagnostic_attempts") == attempts_after_first
    assert await row_counter(db_session, "user_skill_levels") == levels_after_first
    assert await _token_rows(db_session, user_id, token) == 1

    # 第三次仍回放同一批次，行数不动
    third = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert third.status_code == 200, third.text
    assert third.json() == first.json()
    assert await row_counter(db_session, "diagnostic_attempts") == attempts_after_first


async def test_same_token_with_different_answers_is_409(
    api, db_session: AsyncSession, all_correct_answers, row_counter, unique_token
) -> None:
    user_id = await _api_user_id(api)
    token = unique_token("idem-ans")
    first = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert first.status_code == 201, first.text
    attempt_id = first.json()["attempt_id"]
    attempts_after_first = await row_counter(db_session, "diagnostic_attempts")
    levels_after_first = await row_counter(db_session, "user_skill_levels")

    conflict = await api.post(
        "/api/v1/diagnostics", json=_payload(token, _with_one_answer_changed(all_correct_answers))
    )
    assert conflict.status_code == 409, conflict.text
    body = conflict.json()
    assert set(body) == {"error", "request_id"}
    assert body["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert body["error"]["details"] == {"attempt_id": attempt_id, "conflicts": ["answers"]}
    assert body["request_id"] == conflict.headers["X-Request-ID"]

    # 冲突不写任何行，原批次也不被覆盖
    assert await row_counter(db_session, "diagnostic_attempts") == attempts_after_first
    assert await row_counter(db_session, "user_skill_levels") == levels_after_first
    assert await _token_rows(db_session, user_id, token) == 1

    # 相同 token + 原样答案仍然回放（409 不会污染这个 token）
    replay = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()


async def test_same_token_with_a_different_stored_version_is_409(
    api, db_session: AsyncSession, all_correct_answers, row_counter, unique_token
) -> None:
    user_id = await _api_user_id(api)
    attempts_before = await row_counter(db_session, "diagnostic_attempts")

    # 题集/规则版本升级后，旧批次以旧版本存库；同 token 用新版本提交必须 409
    version_token = unique_token("idem-qs")
    version_attempt_id = await _insert_historical_attempt(
        db_session,
        user_id=user_id,
        token=version_token,
        answers=_flat(all_correct_answers),
        question_set_version="v0",
    )
    version_conflict = await api.post(
        "/api/v1/diagnostics", json=_payload(version_token, all_correct_answers)
    )
    assert version_conflict.status_code == 409, version_conflict.text
    assert version_conflict.json()["error"]["details"] == {
        "attempt_id": version_attempt_id,
        "conflicts": ["question_set_version"],
    }

    rule_token = unique_token("idem-rv")
    rule_attempt_id = await _insert_historical_attempt(
        db_session,
        user_id=user_id,
        token=rule_token,
        answers=_flat(all_correct_answers),
        rule_version="r0",
    )
    rule_conflict = await api.post(
        "/api/v1/diagnostics", json=_payload(rule_token, all_correct_answers)
    )
    assert rule_conflict.status_code == 409, rule_conflict.text
    assert rule_conflict.json()["error"]["details"] == {
        "attempt_id": rule_attempt_id,
        "conflicts": ["rule_version"],
    }

    assert await row_counter(db_session, "diagnostic_attempts") == attempts_before + 2


async def test_concurrent_same_token_never_500_and_keeps_one_batch(
    api,
    db_session: AsyncSession,
    all_correct_answers,
    row_counter,
    unique_token,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _api_user_id(api)
    token = unique_token("idem-race")
    first = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert first.status_code == 201, first.text
    attempt_id = first.json()["attempt_id"]
    attempts_after_first = await row_counter(db_session, "diagnostic_attempts")
    levels_after_first = await row_counter(db_session, "user_skill_levels")

    real_find = diagnostics_service._find_attempt_by_token
    calls = {"count": 0}

    async def racing_find(session, user_id, attempt_token):
        """First look returns None: both requests read before either committed."""
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return await real_find(session, user_id, attempt_token)

    monkeypatch.setattr(diagnostics_service, "_find_attempt_by_token", racing_find)

    # 竞争 + 相同内容：唯一约束冲突被捕获后重新读取并回放，不是 500
    raced = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert raced.status_code == 200, raced.text
    assert raced.json()["attempt_id"] == attempt_id
    assert calls["count"] == 2

    # 同一条捕获路径 + 不同内容：重新读取后比对，落到 409 而不是 500
    calls["count"] = 0
    raced_conflict = await api.post(
        "/api/v1/diagnostics", json=_payload(token, _with_one_answer_changed(all_correct_answers))
    )
    assert raced_conflict.status_code == 409, raced_conflict.text
    assert raced_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert raced_conflict.json()["error"]["details"] == {
        "attempt_id": attempt_id,
        "conflicts": ["answers"],
    }

    assert await row_counter(db_session, "diagnostic_attempts") == attempts_after_first
    assert await row_counter(db_session, "user_skill_levels") == levels_after_first
    assert await _token_rows(db_session, user_id, token) == 1
