"""Research column: fetch tech news / papers, and let the AI extract the key points.

Design notes worth keeping:

* Sources are a CLOSED catalog. NEWS_SOURCES picks keys from it; it never accepts a
  URL from the client. A single-user local app that fetches arbitrary URLs on request
  is an SSRF gadget, and this product would rather be boring than clever here.
* Fetching is opt-in (NEWS_ENABLED). With the flag off the endpoints answer 403 and
  nothing leaves the machine - the same posture as knowledge ingest.
* Everything the AI produces is stored with its own status, and 'unavailable' is a
  state, not an error: no key means we cannot analyse, which is different from
  failing to analyse.
* Parsers are pure functions over text so they can be tested without a network.
"""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.errors import ApiError
from app.services.ai_client import AiCallError, AiUpstreamTimeout

ATOM_NS = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    kind: str
    label: str
    url: str


# The catalog. Adding a source is a code change plus a review, on purpose.
SOURCE_CATALOG: dict[str, SourceSpec] = {
    spec.key: spec
    for spec in (
        SourceSpec(
            key="hn",
            kind="rss",
            label="Hacker News 首页",
            url="https://hnrss.org/frontpage",
        ),
        SourceSpec(
            key="arxiv-ai",
            kind="atom",
            label="arXiv cs.AI 最新",
            url=(
                "https://export.arxiv.org/api/query"
                "?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=20"
            ),
        ),
        SourceSpec(
            key="gh-nextjs",
            kind="github_releases",
            label="Next.js Releases",
            url="https://api.github.com/repos/vercel/next.js/releases?per_page=20",
        ),
    )
}


@dataclass(frozen=True)
class FetchedItem:
    title: str
    url: str
    excerpt: str
    published_at: datetime | None


def catalog_keys() -> list[str]:
    return list(SOURCE_CATALOG)


def resolve_sources(raw: str) -> list[SourceSpec]:
    """Map a comma separated key list to specs, ignoring blanks and unknown keys."""
    specs: list[SourceSpec] = []
    for chunk in (raw or "").split(","):
        key = chunk.strip()
        if key and key in SOURCE_CATALOG:
            specs.append(SOURCE_CATALOG[key])
    return specs


_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str | None, limit: int = 600) -> str:
    """Collapse whitespace AND strip HTML.

    HN 的 RSS 把一段 HTML 放在 <description> 里。原样渲染会把 <p> 和 <a href=...>
    直接摆到读者面前；在这里剥掉标签，界面展示的就确实是纯文本。
    """
    if not value:
        return ""
    without_tags = _TAG_RE.sub(" ", value)
    collapsed = " ".join(html.unescape(without_tags).split())
    return collapsed[:limit]


def _parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    candidate = raw.strip()
    # RFC 822 (RSS pubDate) and ISO 8601 (Atom/GitHub) both show up here.
    formats = (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    )
    normalized = candidate.replace("Z", "+0000") if candidate.endswith("Z") else candidate
    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_rss(payload: str, limit: int) -> list[FetchedItem]:
    """RSS 2.0: <item> with title / link / description / pubDate."""
    root = ET.fromstring(payload)
    items: list[FetchedItem] = []
    for node in root.iter("item"):
        title = _clean(node.findtext("title"), 300)
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        items.append(
            FetchedItem(
                title=title,
                url=link,
                excerpt=_clean(node.findtext("description")),
                published_at=_parse_time(node.findtext("pubDate")),
            )
        )
        if len(items) >= limit:
            break
    return items


def parse_atom(payload: str, limit: int) -> list[FetchedItem]:
    """Atom (arXiv): <entry> with title / id / summary / published."""
    root = ET.fromstring(payload)
    items: list[FetchedItem] = []
    for node in root.iter(f"{ATOM_NS}entry"):
        title = _clean(node.findtext(f"{ATOM_NS}title"), 300)
        link = (node.findtext(f"{ATOM_NS}id") or "").strip()
        if not title or not link:
            continue
        items.append(
            FetchedItem(
                title=title,
                url=link,
                excerpt=_clean(node.findtext(f"{ATOM_NS}summary")),
                published_at=_parse_time(node.findtext(f"{ATOM_NS}published")),
            )
        )
        if len(items) >= limit:
            break
    return items


def parse_github_releases(payload: str, limit: int) -> list[FetchedItem]:
    """GitHub releases JSON: tag_name / name / html_url / published_at / body."""
    data = json.loads(payload)
    if not isinstance(data, list):
        return []
    items: list[FetchedItem] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("html_url") or "")
        title = _clean(str(entry.get("name") or entry.get("tag_name") or ""), 300)
        if not url or not title:
            continue
        items.append(
            FetchedItem(
                title=title,
                url=url,
                excerpt=_clean(str(entry.get("body") or "")),
                published_at=_parse_time(entry.get("published_at")),
            )
        )
        if len(items) >= limit:
            break
    return items


PARSERS: dict[str, Callable[[str, int], list[FetchedItem]]] = {
    "rss": parse_rss,
    "atom": parse_atom,
    "github_releases": parse_github_releases,
}

Fetcher = Callable[[str], Awaitable[str]]


# --- persistence -----------------------------------------------------------

INSERT_ITEM = text(
    """
    INSERT INTO news_items (source_key, source_kind, title, url, excerpt, published_at)
    VALUES (:source_key, :source_kind, :title, :url, :excerpt, :published_at)
    ON CONFLICT (url) DO NOTHING
    """
)

SELECT_COLUMNS = (
    "id, source_key, source_kind, title, url, excerpt, published_at, fetched_at, "
    "ai_status, ai_summary, ai_key_points, ai_model, ai_tokens, ai_updated_at"
)

SELECT_LIST = text(
    "SELECT " + SELECT_COLUMNS + " FROM news_items "
    "WHERE (CAST(:source_key AS varchar) IS NULL "
    "OR source_key = CAST(:source_key AS varchar)) "
    "ORDER BY published_at DESC NULLS LAST, id DESC LIMIT :limit"
)

SELECT_ITEM = text("SELECT " + SELECT_COLUMNS + " FROM news_items WHERE id = :item_id")

UPDATE_ANALYSIS = text(
    """
    UPDATE news_items SET
        ai_status = :ai_status,
        ai_summary = :ai_summary,
        ai_key_points = CAST(:ai_key_points AS jsonb),
        ai_model = :ai_model,
        ai_tokens = :ai_tokens,
        ai_updated_at = now()
    WHERE id = :item_id
    """
)

COUNT_ITEMS = text("SELECT count(*) FROM news_items")


def _row_to_dict(row) -> dict:
    payload = dict(row._mapping)
    points = payload.get("ai_key_points")
    if isinstance(points, str):
        try:
            points = json.loads(points)
        except json.JSONDecodeError:
            points = []
    payload["ai_key_points"] = points or []
    for key in ("published_at", "fetched_at", "ai_updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if value is not None else None
    return payload


async def list_items(session, *, limit: int, source_key: str | None = None) -> list:
    rows = (await session.execute(SELECT_LIST, {"limit": limit, "source_key": source_key})).all()
    return [_row_to_dict(row) for row in rows]


async def get_item(session, item_id: int):
    row = (await session.execute(SELECT_ITEM, {"item_id": item_id})).first()
    return _row_to_dict(row) if row else None


async def refresh(session, *, specs, limit_per_source: int, fetcher):
    """Fetch every configured source and store new entries; existing rows are kept."""
    stats = []
    before = int((await session.execute(COUNT_ITEMS)).scalar_one())
    for spec in specs:
        try:
            payload = await fetcher(spec.url)
            parsed = PARSERS[spec.kind](payload, limit_per_source)
        except (OSError, TimeoutError) as exc:
            stats.append({"source": spec.key, "status": "network_error", "detail": str(exc)[:120]})
            continue
        except (ET.ParseError, json.JSONDecodeError) as exc:
            stats.append({"source": spec.key, "status": "parse_error", "detail": str(exc)[:120]})
            continue
        inserted = 0
        for item in parsed:
            result = await session.execute(
                INSERT_ITEM,
                {
                    "source_key": spec.key,
                    "source_kind": spec.kind,
                    "title": item.title,
                    "url": item.url,
                    "excerpt": item.excerpt,
                    "published_at": item.published_at,
                },
            )
            inserted += result.rowcount or 0
        stats.append(
            {"source": spec.key, "status": "ok", "fetched": len(parsed), "inserted": inserted}
        )
    await session.commit()
    after = int((await session.execute(COUNT_ITEMS)).scalar_one())
    return {"sources": stats, "items_before": before, "items_after": after}


ANALYSIS_SYSTEM_PROMPT = (
    "你是一个严谨的技术研究助理，读者是刚学完 Python 与 API 基础的初学者。"
    "只根据用户给出的标题与摘要作答，不要补充摘要里没有的事实。"
    "输出必须是 JSON，且只有 JSON，形如 "
    '{"summary": "一句话说清这条在讲什么", "key_points": ["要点1", "要点2"]}。'
    "key_points 给 3 到 5 条，每条不超过 40 字。"
)


def build_analysis_messages(title: str, excerpt: str, source_label: str) -> list:
    fallback = "（没有摘要；只能根据标题判断，请在 summary 里说明）"
    lines = [
        "来源：" + source_label,
        "标题：" + title,
        "摘要：" + (excerpt or fallback),
    ]
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": chr(10).join(lines)},
    ]


def parse_analysis(answer: str):
    """Lenient JSON extraction: models wrap JSON in prose or fences often enough."""
    raw = answer.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _clean(answer, 400), []
    summary = _clean(str(data.get("summary") or ""), 400)
    points = []
    raw_points = data.get("key_points")
    if isinstance(raw_points, list):
        for entry in raw_points:
            point = _clean(str(entry), 120)
            if point:
                points.append(point)
    return summary, points[:5]


async def _store_failure(session, item_id: int) -> None:
    await session.execute(
        UPDATE_ANALYSIS,
        {
            "item_id": item_id,
            "ai_status": "error",
            "ai_summary": None,
            "ai_key_points": json.dumps([], ensure_ascii=False),
            "ai_model": None,
            "ai_tokens": None,
        },
    )
    await session.commit()


async def analyze(session, *, item, client):
    """Ask the model for a summary plus key points and store the result."""
    spec = SOURCE_CATALOG.get(str(item["source_key"]))
    label = spec.label if spec else str(item["source_key"])
    messages = build_analysis_messages(str(item["title"]), str(item.get("excerpt") or ""), label)
    try:
        completion = await client.complete_chat(messages=messages, temperature=0.2)
    except AiUpstreamTimeout:
        await _store_failure(session, int(item["id"]))
        raise ApiError(
            status_code=504, code="AI_TIMEOUT", message="模型调用超时，这条分析没有生成"
        ) from None
    except AiCallError as exc:
        await _store_failure(session, int(item["id"]))
        raise ApiError(
            status_code=502,
            code=getattr(exc, "code", "AI_UPSTREAM_ERROR"),
            message="模型调用失败，这条分析没有生成",
        ) from exc
    summary, points = parse_analysis(completion.answer)
    await session.execute(
        UPDATE_ANALYSIS,
        {
            "item_id": int(item["id"]),
            "ai_status": "ok",
            "ai_summary": summary,
            "ai_key_points": json.dumps(points, ensure_ascii=False),
            "ai_model": completion.model,
            "ai_tokens": int(completion.prompt_tokens) + int(completion.completion_tokens),
        },
    )
    await session.commit()
    return await get_item(session, int(item["id"])) or item
