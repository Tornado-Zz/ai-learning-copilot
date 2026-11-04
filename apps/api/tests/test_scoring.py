"""验收 6（规则部分）：题集分布与 60% / 85% 阈值边界，纯函数、不连库。"""

from __future__ import annotations

import pytest

from app.services.question_set import (
    BUG_FIX,
    CODE_READING,
    DOMAIN_CODES,
    QUESTIONS_V1,
    SINGLE_CHOICE,
    TOTAL_QUESTIONS,
    kind_distribution,
    level_for,
    score_answers,
    state_for,
)


def test_question_set_is_20_items_split_12_5_3() -> None:
    assert TOTAL_QUESTIONS == 20
    assert kind_distribution() == {SINGLE_CHOICE: 12, CODE_READING: 5, BUG_FIX: 3}
    assert [question.id for question in QUESTIONS_V1] == [f"q{index:02d}" for index in range(1, 21)]


def test_question_set_covers_all_six_domains_and_sums_to_20() -> None:
    totals = {code: 0 for code in DOMAIN_CODES}
    for question in QUESTIONS_V1:
        totals[question.skill_code] += 1
    assert totals == {
        "route_a.a1": 4,
        "route_a.a2": 4,
        "route_a.a3": 3,
        "route_a.a4": 3,
        "route_a.a5": 3,
        "route_a.a6": 3,
    }
    assert sum(totals.values()) == TOTAL_QUESTIONS
    assert all(question.answer in {"A", "B", "C", "D"} for question in QUESTIONS_V1)
    assert all(len(question.options) == 4 for question in QUESTIONS_V1)


@pytest.mark.parametrize(
    ("correct", "total", "expected"),
    [
        (20, 20, 2),
        (17, 20, 2),
        (16, 20, 1),
        (12, 20, 1),
        (11, 20, 0),
        (85, 100, 2),
        (84, 100, 1),
        (60, 100, 1),
        (59, 100, 0),
        (4, 4, 2),
        (3, 4, 1),
        (2, 4, 0),
        (3, 5, 1),
        (2, 5, 0),
        (0, 3, 0),
    ],
)
def test_level_for_threshold_boundaries(correct: int, total: int, expected: int) -> None:
    assert level_for(correct, total) == expected


def test_level_for_never_returns_l3_or_l4() -> None:
    assert {level_for(correct, 20) for correct in range(0, 21)} == {0, 1, 2}


def test_state_for_maps_level_zero_to_assessed_below_threshold() -> None:
    assert state_for(2) == "established"
    assert state_for(1) == "established"
    assert state_for(0) == "assessed_below_threshold"


def test_score_answers_is_deterministic_and_caps_at_l2() -> None:
    answers = {question.id: question.answer for question in QUESTIONS_V1}
    first = score_answers(answers)
    second = score_answers(answers)
    assert first == second
    assert first.total_correct == 20
    assert first.total_questions == 20
    assert sum(domain.total for domain in first.domains) == 20
    assert {domain.level for domain in first.domains} == {2}
    assert {domain.state for domain in first.domains} == {"established"}
    assert all(domain.rate == 1.0 for domain in first.domains)


def test_score_answers_zero_correct_is_below_threshold() -> None:
    answers = {
        question.id: next(choice for choice in "ABCD" if choice != question.answer)
        for question in QUESTIONS_V1
    }
    result = score_answers(answers)
    assert result.total_correct == 0
    assert {domain.level for domain in result.domains} == {0}
    assert {domain.state for domain in result.domains} == {"assessed_below_threshold"}
    assert all(domain.rate == 0.0 for domain in result.domains)


def test_rate_is_rounded_to_two_decimals() -> None:
    answers = {question.id: next(choice for choice in "ABCD" if choice != question.answer) for question in QUESTIONS_V1}
    a3 = [question for question in QUESTIONS_V1 if question.skill_code == "route_a.a3"]
    answers[a3[0].id] = a3[0].answer
    result = score_answers(answers)
    a3_domain = next(domain for domain in result.domains if domain.skill_code == "route_a.a3")
    assert a3_domain.correct == 1
    assert a3_domain.total == 3
    assert a3_domain.rate == 0.33
    assert a3_domain.level == 0
