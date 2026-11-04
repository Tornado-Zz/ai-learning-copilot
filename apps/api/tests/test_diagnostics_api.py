"""验收 5–11：诊断提交、评分、幂等、追加历史、L0 两态、证据分层与事务回滚。

隔离策略：凡是断言"展示等级/状态"的用例都走服务层并把作用域限定为本测试
自建的 users 行（fixture test_user）；凡是走单用户 HTTP 接口的用例只断言
"本次请求造成的行"（按 evidence_ref 或行数增量），不依赖库的初始状态。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diagnostics as diagnostics_service
from app.services import levels as levels_service
from app.services.question_set import DOMAIN_CODES, QUESTIONS_V1

pytestmark = pytest.mark.integration

SELECT_ATTEMPT = text(
    "SELECT id, user_id, attempt_token, question_set_version, rule_version, answers, "
    "domain_scores, total_correct, total_questions, submitted_at FROM diagnostic_attempts "
    "WHERE id = :attempt_id"
)

SELECT_LEVELS_BY_REF = text(
    "SELECT id, skill_id, level, evidence_kind, verification_method, evidence_strength, "
    "assessment_state, evidence_ref, evidence_count, created_at FROM user_skill_levels "
    "WHERE user_id = :user_id AND evidence_ref = :evidence_ref ORDER BY id"
)

SELECT_LEVELS_BY_USER = text(
    "SELECT id, skill_id, level, evidence_kind, verification_method, evidence_strength, "
    "assessment_state, evidence_ref, evidence_count, created_at FROM user_skill_levels "
    "WHERE user_id = :user_id ORDER BY id"
)

COUNT_TOKEN = text(
    "SELECT count(*) FROM diagnostic_attempts WHERE user_id = :user_id AND attempt_token = :token"
)

COUNT_AT_LEAST_L3 = text(
    "SELECT count(*) FROM user_skill_levels WHERE user_id = :user_id AND level >= 3"
)

COUNT_VERIFIED = text(
    "SELECT count(*) FROM user_skill_levels WHERE user_id = :user_id AND evidence_strength = 'verified'"
)

COUNT_REF_OUTSIDE_USER = text(
    "SELECT count(*) FROM user_skill_levels WHERE evidence_ref = :evidence_ref AND user_id <> :user_id"
)


def _payload(token: str, answers: dict[str, dict[str, str]]) -> dict[str, object]:
    return {
        "attempt_token": token,
        "question_set_version": "v1",
        "rule_version": "r1",
        "answers": answers,
    }


async def _api_user_id(api) -> int:
    return int((await api.get("/api/v1/users/me")).json()["user"]["id"])


async def test_05_submit_writes_one_attempt_and_six_evidence_rows(
    api, db_session: AsyncSession, all_correct_answers, row_counter, unique_token
) -> None:
    user_id = await _api_user_id(api)
    token = unique_token("t05")
    attempts_before = await row_counter(db_session, "diagnostic_attempts")

    response = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"attempt_id", "rule_version", "domains"}
    assert body["rule_version"] == "r1"
    assert [domain["skill_code"] for domain in body["domains"]] == list(DOMAIN_CODES)
    assert all(domain["level"] == 2 for domain in body["domains"])
    assert all(domain["state"] == "established" for domain in body["domains"])
    attempt_id = body["attempt_id"]

    # 本次提交只新增 1 个批次（增量断言，与库内已有批次无关）
    assert await row_counter(db_session, "diagnostic_attempts") == attempts_before + 1

    attempt = (
        await db_session.execute(SELECT_ATTEMPT, {"attempt_id": attempt_id})
    ).mappings().one()
    assert attempt["user_id"] == user_id
    assert attempt["attempt_token"] == token
    assert set(attempt["answers"]) == {question.id for question in QUESTIONS_V1}
    assert attempt["total_questions"] == 20
    assert attempt["total_correct"] == 20
    assert attempt["question_set_version"] == "v1"
    assert attempt["rule_version"] == "r1"
    assert set(attempt["domain_scores"]) == set(DOMAIN_CODES)
    assert sum(entry["total"] for entry in attempt["domain_scores"].values()) == 20
    assert sum(entry["correct"] for entry in attempt["domain_scores"].values()) == 20

    # 只按本次批次的 evidence_ref 作用域断言，不数全表
    evidence_ref = f"diag:{attempt_id}"
    levels = (
        await db_session.execute(
            SELECT_LEVELS_BY_REF, {"user_id": user_id, "evidence_ref": evidence_ref}
        )
    ).mappings().all()
    assert len(levels) == 6
    assert {row["evidence_kind"] for row in levels} == {"diagnostic"}
    assert {row["verification_method"] for row in levels} == {"static_rule"}
    assert {row["evidence_strength"] for row in levels} == {"assessed"}
    assert {row["assessment_state"] for row in levels} == {"established"}
    assert {row["level"] for row in levels} == {2}
    assert sum(row["evidence_count"] for row in levels) == 20
    assert (
        await db_session.execute(
            COUNT_REF_OUTSIDE_USER, {"evidence_ref": evidence_ref, "user_id": user_id}
        )
    ).scalar_one() == 0

    # I5/I6：本用户不得出现 L3/L4，也不得出现 verified
    assert (
        await db_session.execute(COUNT_AT_LEAST_L3, {"user_id": user_id})
    ).scalar_one() == 0
    assert (
        await db_session.execute(COUNT_VERIFIED, {"user_id": user_id})
    ).scalar_one() == 0

    # 同 tier 取最新：本次全对是 tier 1 的最新证据，六域展示都为 L2
    refreshed = (await api.get("/api/v1/users/me")).json()
    assert [skill["level"] for skill in refreshed["skills"]] == [2, 2, 2, 2, 2, 2]
    assert [skill["state"] for skill in refreshed["skills"]] == ["established"] * 6
    assert [skill["evidence_strength"] for skill in refreshed["skills"]] == ["assessed"] * 6


async def test_06_domain_levels_follow_thresholds(
    api, db_session: AsyncSession, answer_factory, test_user, unique_token, flatten_answers
) -> None:
    answers = answer_factory({"route_a.a1": 3, "route_a.a3": 2, "route_a.a4": 3})

    # (a) 响应中的 domains 是本次判分快照，与历史无关
    response = await api.post("/api/v1/diagnostics", json=_payload(unique_token("t06"), answers))
    assert response.status_code == 201, response.text
    domains = {domain["skill_code"]: domain for domain in response.json()["domains"]}
    assert domains["route_a.a1"]["correct"] == 3
    assert domains["route_a.a1"]["rate"] == 0.75
    assert domains["route_a.a1"]["level"] == 1
    assert domains["route_a.a1"]["state"] == "established"
    assert domains["route_a.a2"]["level"] == 0
    assert domains["route_a.a2"]["state"] == "assessed_below_threshold"
    assert domains["route_a.a3"]["rate"] == 0.67
    assert domains["route_a.a3"]["level"] == 1
    assert domains["route_a.a4"]["rate"] == 1.0
    assert domains["route_a.a4"]["level"] == 2
    assert {domain["level"] for domain in response.json()["domains"]} <= {0, 1, 2}

    # (b) 展示等级用本测试自建用户验证，不受真实历史影响
    user_id = int(test_user["id"])
    await diagnostics_service.submit_diagnostic(
        db_session,
        user_id=user_id,
        attempt_token=unique_token("t06-user"),
        question_set_version="v1",
        rule_version="r1",
        answers=flatten_answers(answers),
    )
    resolved = {
        row["skill_code"]: row
        for row in await levels_service.resolve_current_levels(db_session, user_id)
    }
    assert resolved["route_a.a1"]["level"] == 1
    assert resolved["route_a.a1"]["state"] == "established"
    assert resolved["route_a.a1"]["evidence_strength"] == "assessed"
    assert resolved["route_a.a2"]["level"] == 0
    assert resolved["route_a.a2"]["state"] == "assessed_below_threshold"
    assert resolved["route_a.a2"]["evidence_kind"] is None
    assert resolved["route_a.a2"]["evidence_strength"] == "none"
    assert resolved["route_a.a4"]["level"] == 2
    assert resolved["route_a.a4"]["state"] == "established"


async def test_07_same_attempt_token_is_idempotent(
    api, db_session: AsyncSession, all_correct_answers, row_counter, unique_token
) -> None:
    user_id = await _api_user_id(api)
    token = unique_token("t07")

    first = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert first.status_code == 201, first.text
    attempts_after_first = await row_counter(db_session, "diagnostic_attempts")
    evidence_ref = f"diag:{first.json()['attempt_id']}"
    levels_after_first = (
        await db_session.execute(
            SELECT_LEVELS_BY_REF, {"user_id": user_id, "evidence_ref": evidence_ref}
        )
    ).mappings().all()
    assert len(levels_after_first) == 6

    # 回放是 200，不是第二次创建（201 只给真正写入的新批次）
    second = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert await row_counter(db_session, "diagnostic_attempts") == attempts_after_first
    levels_after_second = (
        await db_session.execute(
            SELECT_LEVELS_BY_REF, {"user_id": user_id, "evidence_ref": evidence_ref}
        )
    ).mappings().all()
    assert len(levels_after_second) == 6
    assert [row["id"] for row in levels_after_second] == [row["id"] for row in levels_after_first]
    assert (
        await db_session.execute(COUNT_TOKEN, {"user_id": user_id, "token": token})
    ).scalar_one() == 1


async def test_08_new_token_appends_history_without_rewriting(
    api, db_session: AsyncSession, all_correct_answers, answer_factory, row_counter, unique_token
) -> None:
    user_id = await _api_user_id(api)
    token_a = unique_token("t08a")
    first = await api.post("/api/v1/diagnostics", json=_payload(token_a, all_correct_answers))
    assert first.status_code == 201, first.text
    ref_a = f"diag:{first.json()['attempt_id']}"
    snapshot = [
        dict(row)
        for row in (
            await db_session.execute(SELECT_LEVELS_BY_REF, {"user_id": user_id, "evidence_ref": ref_a})
        ).mappings().all()
    ]
    assert len(snapshot) == 6
    attempts_after_first = await row_counter(db_session, "diagnostic_attempts")

    second = await api.post(
        "/api/v1/diagnostics",
        json=_payload(unique_token("t08b"), answer_factory({"route_a.a1": 1})),
    )
    assert second.status_code == 201, second.text
    assert second.json()["attempt_id"] > first.json()["attempt_id"]
    assert await row_counter(db_session, "diagnostic_attempts") == attempts_after_first + 1

    # 旧批次的六行原封不动（按 evidence_ref 作用域比对，不数全表）
    after = (
        await db_session.execute(SELECT_LEVELS_BY_REF, {"user_id": user_id, "evidence_ref": ref_a})
    ).mappings().all()
    assert [dict(row) for row in after] == snapshot
    ref_b = f"diag:{second.json()['attempt_id']}"
    assert len(
        (
            await db_session.execute(
                SELECT_LEVELS_BY_REF, {"user_id": user_id, "evidence_ref": ref_b}
            )
        ).mappings().all()
    ) == 6

    history = await api.get("/api/v1/diagnostics/history")
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["has_more"] is False
    assert body["next_cursor"] is None
    attempt_ids = [item["attempt_id"] for item in body["items"]]
    assert attempt_ids[:2] == [second.json()["attempt_id"], first.json()["attempt_id"]]
    newest = body["items"][0]
    assert set(newest) == {
        "attempt_id",
        "submitted_at",
        "question_set_version",
        "rule_version",
        "total_correct",
        "total_questions",
        "domains",
    }
    assert newest["question_set_version"] == "v1"
    assert newest["rule_version"] == "r1"
    assert newest["total_questions"] == 20
    assert [domain["skill_code"] for domain in newest["domains"]] == list(DOMAIN_CODES)
    assert newest["submitted_at"].endswith("Z")


async def test_09_two_kinds_of_l0_are_distinguishable(
    db_session: AsyncSession, answer_factory, test_user, unique_token
) -> None:
    user_id = int(test_user["id"])
    initial = await levels_service.resolve_current_levels(db_session, user_id)
    assert len(initial) == 6
    assert [row["level"] for row in initial] == [0] * 6
    assert [row["state"] for row in initial] == ["unassessed"] * 6
    assert [row["evidence_kind"] for row in initial] == [None] * 6
    assert [row["evidence_strength"] for row in initial] == ["none"] * 6
    assert (
        await db_session.execute(SELECT_LEVELS_BY_USER, {"user_id": user_id})
    ).mappings().all() == []

    result = await diagnostics_service.submit_diagnostic(
        db_session,
        user_id=user_id,
        attempt_token=unique_token("t09"),
        question_set_version="v1",
        rule_version="r1",
        answers={question_id: value["choice"] for question_id, value in answer_factory({}).items()},
    )
    attempt_id = int(result.attempt["attempt_id"])

    after = await levels_service.resolve_current_levels(db_session, user_id)
    assert [row["state"] for row in after] == ["assessed_below_threshold"] * 6
    assert [row["level"] for row in after] == [0] * 6
    assert [row["evidence_kind"] for row in after] == [None] * 6
    assert [row["evidence_strength"] for row in after] == ["none"] * 6

    rows = (
        await db_session.execute(SELECT_LEVELS_BY_USER, {"user_id": user_id})
    ).mappings().all()
    assert len(rows) == 6
    assert {row["assessment_state"] for row in rows} == {"assessed_below_threshold"}
    assert {row["level"] for row in rows} == {0}
    assert {row["evidence_strength"] for row in rows} == {"assessed"}
    assert {row["evidence_ref"] for row in rows} == {f"diag:{attempt_id}"}


async def test_10_higher_tier_evidence_is_not_overwritten(
    db_session: AsyncSession, answer_factory, test_user, unique_token
) -> None:
    user_id = int(test_user["id"])
    skill_id = (
        await db_session.execute(text("SELECT id FROM skills WHERE code = 'route_a.a1'"))
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO user_skill_levels (user_id, skill_id, level, evidence_kind, "
            "verification_method, assessment_state, evidence_ref, evidence_count) "
            "VALUES (:user_id, :skill_id, 2, 'practice', 'static_rule', 'established', 'sub:1', 1)"
        ),
        {"user_id": user_id, "skill_id": skill_id},
    )

    # 后到的诊断在该域只到 L1（tier 1），不得覆盖已建立的 tier 2 练习证据
    await diagnostics_service.submit_diagnostic(
        db_session,
        user_id=user_id,
        attempt_token=unique_token("t10"),
        question_set_version="v1",
        rule_version="r1",
        answers={
            question_id: value["choice"]
            for question_id, value in answer_factory({"route_a.a1": 3}).items()
        },
    )

    resolved = {
        row["skill_code"]: row
        for row in await levels_service.resolve_current_levels(db_session, user_id)
    }
    assert resolved["route_a.a1"]["level"] == 2
    assert resolved["route_a.a1"]["state"] == "established"
    assert resolved["route_a.a1"]["evidence_kind"] == "practice"
    assert resolved["route_a.a1"]["evidence_strength"] == "assessed"

    rows = (
        await db_session.execute(
            text(
                "SELECT evidence_kind, level, assessment_state FROM user_skill_levels "
                "WHERE user_id = :user_id AND skill_id = :skill_id ORDER BY id"
            ),
            {"user_id": user_id, "skill_id": skill_id},
        )
    ).mappings().all()
    assert [(row["evidence_kind"], row["level"], row["assessment_state"]) for row in rows] == [
        ("practice", 2, "established"),
        ("diagnostic", 1, "established"),
    ]


async def test_11_failed_submit_rolls_back_attempt_and_levels(
    api, db_session: AsyncSession, all_correct_answers, row_counter, monkeypatch, unique_token
) -> None:
    user_id = await _api_user_id(api)
    token = unique_token("t11")
    attempts_before = await row_counter(db_session, "diagnostic_attempts")
    levels_before = await row_counter(db_session, "user_skill_levels")
    calls = {"count": 0}
    original = diagnostics_service.write_skill_levels

    async def failing_write(session, *, user_id, attempt_id, domains):
        calls["count"] += 1
        raise RuntimeError("注入的写库故障：等级行写入失败")

    monkeypatch.setattr(diagnostics_service, "write_skill_levels", failing_write)
    response = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert response.status_code == 500, response.text
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert calls["count"] == 1

    monkeypatch.setattr(diagnostics_service, "write_skill_levels", original)
    assert await row_counter(db_session, "diagnostic_attempts") == attempts_before
    assert await row_counter(db_session, "user_skill_levels") == levels_before
    assert (
        await db_session.execute(COUNT_TOKEN, {"user_id": user_id, "token": token})
    ).scalar_one() == 0


async def test_11b_same_token_after_rollback_can_be_resubmitted(
    api, db_session: AsyncSession, all_correct_answers, monkeypatch, unique_token
) -> None:
    user_id = await _api_user_id(api)
    token = unique_token("t11b")
    original = diagnostics_service.write_skill_levels

    async def failing_write(session, *, user_id, attempt_id, domains):
        raise RuntimeError("注入故障")

    monkeypatch.setattr(diagnostics_service, "write_skill_levels", failing_write)
    failed = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert failed.status_code == 500, failed.text

    monkeypatch.setattr(diagnostics_service, "write_skill_levels", original)
    retried = await api.post("/api/v1/diagnostics", json=_payload(token, all_correct_answers))
    assert retried.status_code == 201, retried.text
    assert (
        await db_session.execute(COUNT_TOKEN, {"user_id": user_id, "token": token})
    ).scalar_one() == 1
    ref = f"diag:{retried.json()['attempt_id']}"
    assert len(
        (
            await db_session.execute(SELECT_LEVELS_BY_REF, {"user_id": user_id, "evidence_ref": ref})
        ).mappings().all()
    ) == 6
