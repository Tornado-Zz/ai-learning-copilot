"""CJK 检索回归：中文没有空格，必须用二元组切词才可能召回。"""

from __future__ import annotations

from app.services.knowledge.pipeline import score_terms, tokenize


def test_tokenize_splits_chinese_into_bigrams() -> None:
    terms = tokenize("为什么循环少算")
    assert "循环" in terms, terms
    assert "为什" in terms, terms
    assert all(len(t) >= 2 for t in terms), terms


def test_tokenize_keeps_ascii_and_chinese_together() -> None:
    terms = tokenize("print 为什么报错")
    assert "print" in terms
    assert "为什" in terms


def test_tokenize_dedupes_repeated_bigrams() -> None:
    terms = tokenize("循环循环")
    assert terms.count("循环") == 1, terms


def test_score_terms_matches_chinese_content() -> None:
    terms = tokenize("循环少算")
    score = score_terms(terms, content="for 循环的右端不包含在序列里，常导致少算一次", heading="循环")
    assert score > 0


def test_score_terms_zero_when_nothing_matches() -> None:
    terms = tokenize("机器学习")
    score = score_terms(terms, content="print(type(age)) 输出 <class 'int'>")
    assert score == 0.0