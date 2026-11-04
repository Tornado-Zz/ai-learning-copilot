"""normalize_answers() 纯函数：幂等比对只看规范化后的答案（无数据库、无 I/O）。"""

from __future__ import annotations

from app.services.diagnostics import answers_match, normalize_answers
from app.services.question_set import CHOICES, QUESTIONS_V1

ALL_CORRECT: dict[str, str] = {question.id: question.answer for question in QUESTIONS_V1}


def test_keys_are_lowercased_and_stripped() -> None:
    assert normalize_answers({" Q01 ": "B", "Q02": "C"}) == {"q01": "B", "q02": "C"}


def test_choices_are_uppercased_and_stripped() -> None:
    assert normalize_answers({"q01": " b ", "q02": "c"}) == {"q01": "B", "q02": "C"}


def test_mapping_values_contribute_only_the_choice_field() -> None:
    normalized = normalize_answers(
        {"q01": {"choice": "B", "time_spent_ms": 1200, "confidence": "high"}}
    )
    assert normalized == {"q01": "B"}


def test_payload_order_does_not_matter() -> None:
    forwards = normalize_answers(ALL_CORRECT)
    backwards = normalize_answers(dict(reversed(list(ALL_CORRECT.items()))))
    assert forwards == backwards
    assert list(forwards) == sorted(forwards) == list(ALL_CORRECT)


def test_ids_outside_the_question_set_are_dropped() -> None:
    normalized = normalize_answers({**ALL_CORRECT, "q99": "A", "unrelated": "B"})
    assert normalized == ALL_CORRECT
    assert "q99" not in normalized


def test_missing_or_blank_choices_are_dropped() -> None:
    assert normalize_answers({"q01": None, "q02": "", "q03": "   ", "q04": {}}) == {}


def test_input_is_not_mutated() -> None:
    payload = {"Q01": "b"}
    normalize_answers(payload)
    assert payload == {"Q01": "b"}


def test_answers_match_ignores_field_and_order_noise() -> None:
    noisy = {
        question.id: {"choice": question.answer.lower(), "extra": 1} for question in QUESTIONS_V1
    }
    assert answers_match(ALL_CORRECT, noisy) is True
    assert answers_match(ALL_CORRECT, dict(reversed(list(ALL_CORRECT.items())))) is True


def test_answers_match_detects_a_single_changed_choice() -> None:
    changed = dict(ALL_CORRECT)
    changed["q01"] = next(choice for choice in CHOICES if choice != ALL_CORRECT["q01"])
    assert answers_match(ALL_CORRECT, changed) is False


def test_answers_match_detects_a_missing_answer() -> None:
    partial = dict(ALL_CORRECT)
    partial.pop("q20")
    assert answers_match(ALL_CORRECT, partial) is False
