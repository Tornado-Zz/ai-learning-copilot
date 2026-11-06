"""Research column: parsers are pure, so they are tested without a network."""

from __future__ import annotations

from datetime import UTC

from app.services.news import (
    parse_analysis,
    parse_atom,
    parse_github_releases,
    parse_rss,
    resolve_sources,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>First &amp; one</title><link>https://example.com/a</link>
<description>  spaced   out   text </description>
<pubDate>Fri, 06 Nov 2026 13:22:53 +0000</pubDate></item>
<item><title>Second</title><link>https://example.com/b</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2611.00001v1</id>
    <title>Retrieval Augmented Generation Revisited</title>
    <summary>We study grounding.</summary>
    <published>2026-11-05T18:00:00Z</published>
  </entry>
</feed>"""

RELEASES = """[{"tag_name": "v16.5.0", "name": "v16.5.0",
  "html_url": "https://github.com/vercel/next.js/releases/tag/v16.5.0",
  "published_at": "2026-11-05T23:45:35Z", "body": "Fixes and improvements."}]"""


def test_parse_rss_keeps_title_link_and_collapses_whitespace() -> None:
    items = parse_rss(RSS, 10)
    assert [item.title for item in items] == ["First & one", "Second"]
    assert items[0].url == "https://example.com/a"
    assert items[0].excerpt == "spaced out text"
    assert items[0].published_at is not None
    assert items[0].published_at.tzinfo is not None


def test_parse_rss_respects_the_limit() -> None:
    assert len(parse_rss(RSS, 1)) == 1


def test_parse_atom_reads_arxiv_entries() -> None:
    items = parse_atom(ATOM, 10)
    assert len(items) == 1
    assert items[0].url == "http://arxiv.org/abs/2611.00001v1"
    assert items[0].title.startswith("Retrieval Augmented")
    assert items[0].published_at is not None
    assert items[0].published_at.tzinfo == UTC


def test_parse_github_releases_falls_back_to_tag_name() -> None:
    items = parse_github_releases(RELEASES, 10)
    assert len(items) == 1
    assert items[0].title == "v16.5.0"
    assert items[0].url.endswith("/tag/v16.5.0")


def test_parse_github_releases_ignores_non_list_payloads() -> None:
    assert parse_github_releases('{"message": "Not Found"}', 10) == []


def test_resolve_sources_ignores_unknown_keys() -> None:
    keys = [spec.key for spec in resolve_sources("hn, nope, arxiv-ai")]
    assert keys == ["hn", "arxiv-ai"]


def test_parse_analysis_reads_json_wrapped_in_prose() -> None:
    answer = 'Sure, here it is: {"summary": "一句话", "key_points": ["a", "b"]} hope that helps'
    summary, points = parse_analysis(answer)
    assert summary == "一句话"
    assert points == ["a", "b"]


def test_parse_analysis_degrades_to_plain_text() -> None:
    summary, points = parse_analysis("这不是 JSON，只是一段话")
    assert summary.startswith("这不是 JSON")
    assert points == []


def test_parse_analysis_caps_key_points_at_five() -> None:
    answer = '{"summary": "s", "key_points": ["1", "2", "3", "4", "5", "6", "7"]}'
    _summary, points = parse_analysis(answer)
    assert points == ["1", "2", "3", "4", "5"]


def test_clean_strips_html_from_hacker_news_descriptions() -> None:
    # HN 的 <description> 里带一段 HTML；原样显示会把标签摆到读者面前。
    rss = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>Some post</title><link>https://example.com/x</link>
<description>&lt;p&gt;Article URL: &lt;a href="https://example.com/x"&gt;link&lt;/a&gt;&lt;/p&gt;</description>
</item></channel></rss>"""
    items = parse_rss(rss, 5)
    assert len(items) == 1
    assert "<" not in items[0].excerpt
    assert "Article URL:" in items[0].excerpt

