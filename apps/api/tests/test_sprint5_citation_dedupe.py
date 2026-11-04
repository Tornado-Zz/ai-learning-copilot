"""引用去重回归：同一 URL 的多个命中块只应出现一次。"""

from __future__ import annotations

from app.schemas.ai import KnowledgeCitation
from app.services.ai_tutor import _dedupe_citations


def _c(url: str, title: str) -> KnowledgeCitation:
    return KnowledgeCitation(title=title, url=url, fetched_at="2026-11-04T00:00:00Z", stale=False)


def test_dedupe_keeps_first_occurrence_per_url() -> None:
    items = [_c("https://docs.python.org/a.html", "A"), _c("https://docs.python.org/a.html", "A"), _c("repo://lesson/x", "X")]
    out = _dedupe_citations(items)
    assert [c.url for c in out] == ["https://docs.python.org/a.html", "repo://lesson/x"]


def test_dedupe_keeps_items_without_url() -> None:
    items = [_c("", "A"), _c("", "B")]
    assert len(_dedupe_citations(items)) == 2


def test_dedupe_works_on_plain_dicts_from_the_pipeline() -> None:
    items = [{"url": "https://docs.python.org/a.html"}, {"url": "https://docs.python.org/a.html"}, {"url": "repo://lesson/x"}]
    out = _dedupe_citations(items)
    assert [d["url"] for d in out] == ["https://docs.python.org/a.html", "repo://lesson/x"]