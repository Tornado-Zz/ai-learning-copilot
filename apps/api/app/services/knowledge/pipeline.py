"""Knowledge pipeline (Sprint 5): whitelist -> fetch -> parse -> chunks -> Postgres,
then a lexical search that can explain every score it returns.

The frozen shape of the feature, in the order the code applies it:

* whitelist - docs.python.org document pages, or repo://lesson/<code>. Every URL
             passes validate_doc_url before anything is fetched, so an arbitrary
             string from a request body can never become an outbound request.
* fetch    - the injected KnowledgeFetcher seam. HttpxFetcher is the production
             implementation; tests always pass a fake, so no suite can reach the
             network. Redirects are not followed: a whitelisted host answering 302
             to an unlisted one would otherwise carry the fetch out of the whitelist.

* parse    - standard library only. Regex strips tags; no bs4, no parser package,
             so the whole feature runs offline and adds no dependency.
* chunk    - split on h2/h3 headings and blank lines, pack blocks up to 1200
             characters, and remember which heading a block belongs to.
* store    - one knowledge_sources row per URL (UNIQUE url) and one
             knowledge_chunks row per block (UNIQUE source_id, chunk_index).
* idempotent - the sha256 of the fetched body is the version key. Same hash =>
             nothing is re-chunked, and the report says skipped: true.
* search   - candidate stage in SQL (content ILIKE ANY(terms) OR keywords && terms,
             capped at 200), scoring in Python: +1 per matched term, +1 when the
             heading matches, +1 when the source title matches, divided by the
             number of query terms. Ties break on everything being equal except
             freshness: fetched_at DESC.

Nothing here is a network call. Fetching is the injected KnowledgeFetcher of
app.services.knowledge.fetcher, so a test cannot reach the internet by accident.
"""

from __future__ import annotations

import hashlib
import html as html_module
import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger("app.services.knowledge")

# Frozen numbers of the retrieval contract.
MAX_CHUNK_CHARS = 1200
SNIPPET_CHARS = 240
KEYWORDS_PER_CHUNK = 12
CANDIDATE_LIMIT = 200
MIN_TERM_LENGTH = 2
SEARCH_QUERY_MIN_LENGTH = 2
SEARCH_QUERY_MAX_LENGTH = 200
SEARCH_LIMIT_DEFAULT = 5
SEARCH_LIMIT_MAX = 50
SOURCES_LIMIT_DEFAULT = 50
SOURCES_LIMIT_MAX = 200
INGEST_URLS_MAX = 20

ERROR_LESSON_NOT_FOUND = "LESSON_NOT_FOUND"
ERROR_EMPTY_CONTENT = "EMPTY_CONTENT"
ERROR_INGEST_FAILED = "INGEST_ERROR"

# Words that carry no retrieval signal. Both lists are frozen on purpose: the
# search must not change behaviour because someone edited a dependency's list.
STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "your", "with", "how",
        "what", "why", "does", "did", "this", "that", "from", "can", "use",
        "using", "when", "where", "which", "who", "will", "was", "were", "has",
        "have", "had", "into", "its", "his", "her", "him", "she", "them", "they",
        "there", "then", "than", "also", "about", "because", "would", "could",
        "should", "more", "most", "some", "such", "only", "just", "very", "all",
        "any", "our", "out", "one", "two", "get", "got", "let", "may", "via",
        "am", "an", "as", "at", "be", "by", "do", "if", "in", "is", "it", "me",
        "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    }
)

# A heading is marked in the intermediate text so chunking can attach it; the
# marker uses NUL, which cannot occur in HTML text or in a lesson body.
HEADING_MARK = "\x00h\x00"

_TERM_RE = re.compile(r"[^\W_]+", re.UNICODE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S)
# <head> carries the document title, which becomes the source title - not body text.
_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head\s*>", re.I | re.S)
_HEADING_RE = re.compile(r"<(h[1-6])\b[^>]*>(.*?)</\1\s*>", re.I | re.S)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.I | re.S)
_BREAK_RE = re.compile(
    r"</(?:p|div|li|tr|section|article|h[1-6]|pre|table|dd|dt|blockquote)\s*>"
    r"|<br\s*/?>",
    re.I,
)
_TAG_RE = re.compile(r"<[^>]+>", re.S)
_BLANK_RUN_RE = re.compile(r"\n{3,}")
_VERSION_RE = re.compile(r"/(\d+(?:\.\d+)*)/")


# ---------------------------------------------------------------------------
# whitelist and the injectable fetcher
#
# The whitelist is a security boundary, not a convenience: every URL passes
# validate_doc_url before anything is fetched, so an arbitrary string from a
# request body can never become an outbound request. Repo lessons have their own
# shape (repo://lesson/<code>) and never leave the database.
#
# Redirects are not followed on purpose: a whitelisted host answering 302 to an
# unlisted one would otherwise carry the fetch out of the whitelist, so the 3xx is
# reported as a failure like any other non-200.
# ---------------------------------------------------------------------------
ALLOWED_DOC_HOST = "docs.python.org"
ALLOWED_DOC_HOST_SUFFIX = ".docs.python.org"
ALLOWED_DOC_SCHEMES = frozenset({"http", "https"})
REPO_LESSON_PREFIX = "repo://lesson/"

MAX_URL_LENGTH = 2048
# Bounds parsing work per source; a document longer than this is truncated.
MAX_BODY_CHARS = 400_000
DEFAULT_FETCH_TIMEOUT_SECONDS = 10.0
USER_AGENT = "ai-learning-copilot-knowledge/1.0"

ERROR_EMPTY_URL = "EMPTY_URL"
ERROR_URL_TOO_LONG = "URL_TOO_LONG"
ERROR_MALFORMED_URL = "MALFORMED_URL"
ERROR_UNSUPPORTED_SCHEME = "UNSUPPORTED_SCHEME"
ERROR_BLOCKED_HOST = "BLOCKED_HOST"
ERROR_CREDENTIALS_IN_URL = "CREDENTIALS_IN_URL"
ERROR_FETCH_TIMEOUT = "FETCH_TIMEOUT"
ERROR_FETCH_FAILED = "FETCH_FAILED"
ERROR_EMPTY_BODY = "EMPTY_BODY"

SOURCE_TYPE_OFFICIAL_DOC = "official_doc"
SOURCE_TYPE_REPO_LESSON = "repo_lesson"


class KnowledgeUrlError(ValueError):
    """A URL the whitelist refuses. Carries the code the ingest report shows."""

    def __init__(self, error_code: str, message: str, url: str = "") -> None:
        super().__init__(message)
        self.error_code = error_code
        self.url = url
        self.message = message


def normalize_url(raw: str) -> str:
    return str(raw or "").strip()


def is_allowed_doc_host(host: str) -> bool:
    """True for docs.python.org and its subdomains, false for everything else."""
    normalized = str(host or "").strip().lower().rstrip(".")
    if not normalized:
        return False
    return normalized == ALLOWED_DOC_HOST or normalized.endswith(ALLOWED_DOC_HOST_SUFFIX)


def validate_doc_url(raw: str) -> str:
    """Return the cleaned URL, or raise KnowledgeUrlError.

    This is the only gate between a caller supplied string and an outbound GET, so
    it is deliberately strict: absolute URL, http(s) only, no credentials embedded,
    and a host that is docs.python.org or a subdomain of it.
    """
    url = normalize_url(raw)
    if not url:
        raise KnowledgeUrlError(ERROR_EMPTY_URL, "URL 不能为空", url)
    if len(url) > MAX_URL_LENGTH:
        raise KnowledgeUrlError(ERROR_URL_TOO_LONG, f"URL 超过 {MAX_URL_LENGTH} 字符", url)

    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    if not scheme or not parts.netloc:
        raise KnowledgeUrlError(ERROR_MALFORMED_URL, "URL 必须是绝对地址（含协议与主机）", url)
    if scheme not in ALLOWED_DOC_SCHEMES:
        raise KnowledgeUrlError(
            ERROR_UNSUPPORTED_SCHEME, "只抓取 http/https 页面", url
        )
    if parts.username or parts.password:
        raise KnowledgeUrlError(
            ERROR_CREDENTIALS_IN_URL, "URL 不允许携带账号密码", url
        )
    if not is_allowed_doc_host(parts.hostname or ""):
        raise KnowledgeUrlError(
            ERROR_BLOCKED_HOST,
            f"域名不在白名单内：只允许 {ALLOWED_DOC_HOST} 的官方文档页",
            url,
        )
    return url


def is_allowed_doc_url(raw: str) -> bool:
    try:
        validate_doc_url(raw)
    except KnowledgeUrlError:
        return False
    return True


def repo_lesson_url(code: str) -> str:
    """The stable pseudo-URL of one repo lesson. Never fetched over the network."""
    return f"{REPO_LESSON_PREFIX}{str(code).strip()}"


def lesson_code_from_repo_url(url: str) -> str:
    cleaned = normalize_url(url)
    if not cleaned.startswith(REPO_LESSON_PREFIX):
        raise KnowledgeUrlError(ERROR_MALFORMED_URL, "不是 repo://lesson/<code> 形式", cleaned)
    code = cleaned[len(REPO_LESSON_PREFIX) :].strip()
    if not code or "/" in code:
        raise KnowledgeUrlError(ERROR_MALFORMED_URL, "repo lesson 缺少课程 code", cleaned)
    return code


def classify_url(raw: str) -> str:
    """'repo_lesson' or 'official_doc'; raises KnowledgeUrlError for anything else."""
    url = normalize_url(raw)
    if url.startswith(REPO_LESSON_PREFIX):
        lesson_code_from_repo_url(url)
        return SOURCE_TYPE_REPO_LESSON
    validate_doc_url(url)
    return SOURCE_TYPE_OFFICIAL_DOC


@dataclass(frozen=True)
class FetchResult:
    """What one fetch attempt produced. A failure is a value, never an exception."""

    ok: bool
    status_code: int | None = None
    text: str = ""
    error_code: str | None = None
    final_url: str | None = None

    @classmethod
    def success(cls, text: str, *, status_code: int = 200, final_url: str | None = None) -> FetchResult:
        return cls(ok=True, status_code=status_code, text=text, final_url=final_url)

    @classmethod
    def failure(cls, error_code: str, *, status_code: int | None = None) -> FetchResult:
        return cls(ok=False, status_code=status_code, error_code=error_code)


class KnowledgeFetcher(Protocol):
    """The injectable fetch seam. Tests pass a fake; production passes HttpxFetcher."""

    async def fetch(self, url: str) -> FetchResult:  # pragma: no cover - protocol
        ...


class HttpxFetcher:
    """Default fetcher: one GET, no redirects, bounded body, failures as values."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        max_body_chars: int = MAX_BODY_CHARS,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self._transport = transport
        self._max_body_chars = int(max_body_chars)

    async def fetch(self, url: str) -> FetchResult:
        try:
            checked = validate_doc_url(url)
        except KnowledgeUrlError as exc:
            # Defensive: ingest validates before fetching. If it ever gets here the
            # whitelist still wins, which is the whole point of the check.
            return FetchResult.failure(exc.error_code)

        try:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=False,
                transport=self._transport,
            )
            async with client:
                response = await client.get(
                    checked,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                )
        except httpx.TimeoutException:
            return FetchResult.failure(ERROR_FETCH_TIMEOUT)
        except (httpx.HTTPError, OSError):
            return FetchResult.failure(ERROR_FETCH_FAILED)

        if response.status_code != 200:
            return FetchResult.failure(
                f"HTTP_{response.status_code}", status_code=response.status_code
            )
        body = response.text[: self._max_body_chars]
        if not body.strip():
            return FetchResult.failure(ERROR_EMPTY_BODY, status_code=200)
        return FetchResult.success(body, status_code=200, final_url=str(response.url))


# ---------------------------------------------------------------------------
# SQL: every statement the pipeline issues, named so a stub session can dispatch
# ---------------------------------------------------------------------------

SELECT_SOURCE_BY_URL = text(
    "SELECT id, content_hash, status FROM knowledge_sources WHERE url = :url"
)

INSERT_SOURCE = text(
    """
    INSERT INTO knowledge_sources (
        url, title, source_type, version_label, fetched_at, content_hash, status, error_code
    ) VALUES (
        :url, :title, :source_type, :version_label, :fetched_at, :content_hash, :status, :error_code
    )
    RETURNING id
    """
)

UPDATE_SOURCE = text(
    """
    UPDATE knowledge_sources
    SET title = :title,
        source_type = :source_type,
        version_label = :version_label,
        fetched_at = :fetched_at,
        content_hash = :content_hash,
        status = :status,
        error_code = :error_code,
        updated_at = now()
    WHERE id = :id
    """
)

SELECT_MAX_CHUNK_INDEX = text(
    "SELECT COALESCE(max(chunk_index), -1) FROM knowledge_chunks WHERE source_id = :source_id"
)

# Scoped to the one source whose content changed: these are derived, regenerable
# rows of that source only. No product table is ever touched and a source row is
# never deleted; the idempotent path issues no DELETE at all.
DELETE_SOURCE_CHUNKS = text("DELETE FROM knowledge_chunks WHERE source_id = :source_id")

INSERT_CHUNK = text(
    """
    INSERT INTO knowledge_chunks (source_id, chunk_index, heading, content, keywords)
    VALUES (:source_id, :chunk_index, :heading, :content, CAST(:keywords AS text[]))
    """
)

SELECT_CANDIDATES = text(
    """
    SELECT c.id AS chunk_id,
           c.source_id,
           c.chunk_index,
           c.heading,
           c.content,
           s.title,
           s.url,
           s.fetched_at
    FROM knowledge_chunks c
    JOIN knowledge_sources s ON s.id = c.source_id
    WHERE c.content ILIKE ANY(CAST(:patterns AS text[]))
       OR c.keywords && CAST(:terms AS text[])
    ORDER BY s.fetched_at DESC, c.id DESC
    LIMIT CAST(:candidate_limit AS integer)
    """
)

SELECT_SOURCES = text(
    """
    SELECT s.id, s.url, s.title, s.source_type, s.fetched_at,
           count(c.id) AS chunks
    FROM knowledge_sources s
    LEFT JOIN knowledge_chunks c ON c.source_id = s.id
    GROUP BY s.id, s.url, s.title, s.source_type, s.fetched_at
    ORDER BY s.fetched_at DESC, s.id DESC
    LIMIT CAST(:limit AS integer)
    """
)

SELECT_SOURCES_TOTAL = text("SELECT count(*) FROM knowledge_sources")
SELECT_CHUNKS_TOTAL = text("SELECT count(*) FROM knowledge_chunks")

SELECT_LESSONS_FOR_INGEST = text(
    """
    SELECT id, code, title, content, content_version
    FROM lessons
    WHERE deleted_at IS NULL
    ORDER BY id
    """
)

SELECT_LESSON_BY_CODE = text(
    """
    SELECT id, code, title, content, content_version
    FROM lessons
    WHERE code = :code AND deleted_at IS NULL
    """
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return utcnow()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# ---------------------------------------------------------------------------
# parse: tags out, headings marked, one blank line between paragraphs
# ---------------------------------------------------------------------------


def _plain(fragment: str) -> str:
    """Tags out, entities decoded, whitespace collapsed - for inline fragments."""
    without_tags = _TAG_RE.sub(" ", fragment or "")
    return " ".join(html_module.unescape(without_tags).split())


def _heading_replacement(match: re.Match[str]) -> str:
    inner = _plain(match.group(2))
    if not inner:
        return "\n\n"
    return f"\n\n{HEADING_MARK}{inner}\n\n"


def html_to_marked_text(raw: str) -> str:
    """Rewrite one HTML document as plain text with HEADING_MARK before each h2..h6.

    Standard library only. Comments and script/style bodies are dropped before the
    generic tag strip so their contents never become searchable text.
    """
    cleaned = _COMMENT_RE.sub(" ", raw or "")
    cleaned = _HEAD_RE.sub(" ", cleaned)
    cleaned = _SCRIPT_RE.sub(" ", cleaned)
    cleaned = _HEADING_RE.sub(_heading_replacement, cleaned)
    cleaned = _BREAK_RE.sub("\n\n", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = html_module.unescape(cleaned)
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    text = "\n".join(lines)
    text = _BLANK_RUN_RE.sub("\n\n", text)
    return text.strip()


def extract_title(raw: str, fallback: str) -> str:
    """<title> first, then the first heading, then the URL."""
    match = _TITLE_RE.search(raw or "")
    if match:
        title = _plain(match.group(1))
        if title:
            return title[:300]
    for chunk in chunk_text(html_to_marked_text(raw)):
        if chunk.heading:
            return chunk.heading[:300]
    return (fallback or "")[:300] or "untitled"


def version_label_for_url(url: str) -> str:
    """'py3.13' for /3.13/..., 'py3' for /3/..., '' when the URL says nothing."""
    match = _VERSION_RE.search(str(url or ""))
    return f"py{match.group(1)}"[:64] if match else ""


# ---------------------------------------------------------------------------
# chunk: h2/h3 headings and blank lines, at most 1200 characters per block
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    heading: str | None
    content: str


def _split_long(segment: str, max_chars: int) -> list[str]:
    """Break one over-long paragraph, preferring a space, hard-slicing when there is none.

    The hard slice is what keeps CJK text (which has no spaces) inside the ceiling.
    """
    if len(segment) <= max_chars:
        return [segment]
    pieces: list[str] = []
    current = ""
    for word in segment.split(" "):
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            pieces.append(current)
            current = word
        while len(current) > max_chars:
            pieces.append(current[:max_chars])
            current = current[max_chars:]
    if current:
        pieces.append(current)
    return [piece for piece in pieces if piece] or [segment[:max_chars]]


def chunk_text(marked_text: str, *, default_heading: str | None = None) -> list[Chunk]:
    """Pack the marked text into blocks of at most MAX_CHUNK_CHARS characters."""
    chunks: list[Chunk] = []
    heading = default_heading
    buffer: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal buffer, size
        if buffer:
            content = " ".join(buffer).strip()
            if content:
                chunks.append(Chunk(heading=heading, content=content[:MAX_CHUNK_CHARS]))
            buffer = []
            size = 0

    for segment in re.split(r"\n\s*\n", marked_text or ""):
        segment = segment.strip()
        if not segment:
            continue
        if segment.startswith(HEADING_MARK):
            flush()
            heading = segment[len(HEADING_MARK) :].strip()[:200] or default_heading
            continue
        for piece in _split_long(segment, MAX_CHUNK_CHARS):
            if size and size + 1 + len(piece) > MAX_CHUNK_CHARS:
                flush()
            buffer.append(piece)
            size += len(piece) + (1 if size else 0)
    flush()
    return chunks


def chunk_html(raw: str, *, default_heading: str | None = None) -> list[Chunk]:
    return chunk_text(html_to_marked_text(raw), default_heading=default_heading)


# ---------------------------------------------------------------------------
# repo lessons: the lessons.content jsonb as headed text, then the same chunker
# ---------------------------------------------------------------------------


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def lesson_marked_text(content: Any, *, title: str) -> str:
    """Render one lesson body as marked text: goal, explanation, example, mistakes, check."""
    data = _loads(content)
    if not isinstance(data, dict):
        return ""
    sections: list[str] = []

    def add(heading: str, lines: Iterable[Any]) -> None:
        body = " ".join(str(line).strip() for line in lines if str(line).strip())
        if body:
            sections.append(f"{HEADING_MARK}{heading}\n\n{body}")

    goal = data.get("goal")
    if isinstance(goal, str) and goal.strip():
        add("本课目标", [goal])

    explanation = data.get("explanation")
    if isinstance(explanation, list):
        add("讲解", explanation)

    example = data.get("example")
    if isinstance(example, dict):
        lines: list[Any] = []
        code = example.get("code")
        if isinstance(code, str) and code.strip():
            lines.append(code)
        output = example.get("output")
        if isinstance(output, str) and output.strip():
            lines.append(f"输出：{output}")
        notes = example.get("notes")
        if isinstance(notes, list):
            lines.extend(notes)
        add(str(example.get("title") or "示例"), lines)

    mistakes = data.get("common_mistakes")
    if isinstance(mistakes, list):
        lines = []
        for item in mistakes:
            if not isinstance(item, dict):
                continue
            parts = [
                str(item.get("mistake") or "").strip(),
                str(item.get("why") or "").strip(),
            ]
            fix = str(item.get("fix") or "").strip()
            if fix:
                parts.append(f"正确做法：{fix}")
            joined = "；".join(part for part in parts if part)
            if joined:
                lines.append(joined)
        add("常见错误", lines)

    checks = data.get("self_check")
    if isinstance(checks, list):
        lines = []
        for item in checks:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            answer = str(item.get("answer") or "").strip()
            joined = f"问：{question} 答：{answer}".strip()
            if question or answer:
                lines.append(joined)
        add("自测", lines)

    del title  # the lesson title is the default heading, not a section
    return "\n\n".join(sections)


def lesson_chunks(content: Any, *, title: str) -> list[Chunk]:
    return chunk_text(lesson_marked_text(content, title=title), default_heading=title or None)


# ---------------------------------------------------------------------------
# terms, keywords and the explainable score
# ---------------------------------------------------------------------------


# 中文没有空格：整句会被 _TERM_RE 当成一个不可切分的长串，导致中文提问召回为 0。
# 这里用 CJK 二元组（bigram）作为索引单位——零依赖、可解释，且对中文检索足够有效。
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def _cjk_bigrams(text: str) -> list[str]:
    """Bigrams of every CJK run: 为什么循环 -> 为什, 什么, 么循, 循环."""
    grams: list[str] = []
    for run in _CJK_RUN_RE.findall(text):
        if len(run) < 2:
            continue
        grams.extend(run[i : i + 2] for i in range(len(run) - 1))
    return grams


def tokenize(raw: str) -> list[str]:
    """Lowercase ASCII terms plus CJK bigrams; stopwords and 1-char terms dropped.

    Duplicates are collapsed in first-seen order: a term is one unit of the query,
    so repeating it in the question must not inflate the denominator or the score.
    """
    lowered = str(raw or "").lower()
    terms: list[str] = []
    seen: set[str] = set()
    for match in _TERM_RE.findall(lowered):
        if len(match) < MIN_TERM_LENGTH or match in STOPWORDS or match in seen:
            continue
        seen.add(match)
        terms.append(match)
    for gram in _cjk_bigrams(lowered):
        if gram in seen:
            continue
        seen.add(gram)
        terms.append(gram)
    return terms


def extract_keywords(*texts: str, limit: int = KEYWORDS_PER_CHUNK) -> list[str]:
    """The most frequent indexable terms of one chunk, most frequent first."""
    counts: dict[str, int] = {}
    for raw in texts:
        text = str(raw or "").lower()
        for term in [*_TERM_RE.findall(text), *_cjk_bigrams(text)]:
            if len(term) < MIN_TERM_LENGTH or term in STOPWORDS:
                continue
            counts[term] = counts.get(term, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _ in ordered[:limit]]


def score_terms(
    terms: Sequence[str], *, content: str, heading: str | None = None, title: str | None = None
) -> float:
    """matched terms / number of query terms, +1 per heading hit, +1 per title hit."""
    if not terms:
        return 0.0
    content_l = str(content or "").lower()
    heading_l = str(heading or "").lower()
    title_l = str(title or "").lower()
    total = 0
    for term in terms:
        if term in content_l:
            total += 1
        if heading_l and term in heading_l:
            total += 1
        if title_l and term in title_l:
            total += 1
    return round(total / len(terms), 4)


def age_days(fetched_at: datetime | None, *, now: datetime | None = None) -> float:
    if fetched_at is None:
        return 0.0
    delta = _as_utc(now) - _as_utc(fetched_at)
    return round(max(delta.total_seconds(), 0.0) / 86400.0, 1)


def is_stale(fetched_at: datetime | None, *, now: datetime | None = None, stale_days: int = 30) -> bool:
    return age_days(fetched_at, now=now) > max(int(stale_days), 1)


def _snippet(content: str) -> str:
    text_value = " ".join(str(content or "").split())
    return text_value[:SNIPPET_CHARS]


def _iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    source_id: int
    title: str
    url: str
    fetched_at: datetime | None
    heading: str | None
    content: str
    score: float
    age_days: float
    stale: bool

    def as_item(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "fetched_at": _iso_z(self.fetched_at),
            "age_days": self.age_days,
            "stale": self.stale,
            "heading": self.heading,
            "snippet": _snippet(self.content),
            "score": self.score,
        }

    def as_citation(self) -> dict[str, Any]:
        """What /ai/tutor returns: where the answer came from, not the whole text."""
        return {
            "title": self.title,
            "url": self.url,
            "fetched_at": _iso_z(self.fetched_at),
            "stale": self.stale,
        }

    def as_prompt_line(self) -> str:
        """'[title] snippet' - the exact shape injected into the tutor message."""
        return f"[{self.title}] {_snippet(self.content)}"


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


async def search_hits(
    session: AsyncSession,
    query: str,
    *,
    limit: int = SEARCH_LIMIT_DEFAULT,
    now: datetime | None = None,
    stale_days: int | None = None,
) -> list[SearchHit]:
    """Lexical search: SQL candidates, Python score, deterministic ordering.

    Returns the hits themselves so the tutor builds citations and prompt lines
    from one retrieval instead of two.
    """
    settings = get_settings()
    response_limit = min(max(int(limit), 1), SEARCH_LIMIT_MAX)
    effective_stale_days = (
        settings.knowledge_stale_days_bounded if stale_days is None else max(int(stale_days), 1)
    )
    terms = tokenize(query)
    if not terms:
        return []

    patterns = [f"%{term}%" for term in terms]
    rows = (
        await session.execute(
            SELECT_CANDIDATES,
            {"patterns": patterns, "terms": terms, "candidate_limit": CANDIDATE_LIMIT},
        )
    ).mappings().all()

    hits: list[SearchHit] = []
    for row in rows:
        content = str(row["content"])
        heading = row["heading"]
        score = score_terms(terms, content=content, heading=heading, title=str(row["title"]))
        if score <= 0:
            continue
        fetched_at = row["fetched_at"]
        hits.append(
            SearchHit(
                chunk_id=int(row["chunk_id"]),
                source_id=int(row["source_id"]),
                title=str(row["title"]),
                url=str(row["url"]),
                fetched_at=fetched_at,
                heading=str(heading) if heading is not None else None,
                content=content,
                score=score,
                age_days=age_days(fetched_at, now=now),
                stale=is_stale(fetched_at, now=now, stale_days=effective_stale_days),
            )
        )

    hits.sort(
        key=lambda hit: (-hit.score, -(_as_utc(hit.fetched_at).timestamp() if hit.fetched_at else 0.0))
    )
    logger.info(
        "knowledge_search query_terms=%d candidates=%d matched=%d returned=%d",
        len(terms),
        len(rows),
        len(hits),
        len(hits[:response_limit]),
    )
    return hits[:response_limit]


async def search(
    session: AsyncSession,
    query: str,
    *,
    limit: int = SEARCH_LIMIT_DEFAULT,
    now: datetime | None = None,
    stale_days: int | None = None,
) -> dict[str, Any]:
    """GET /knowledge/search body: the same hits, already shaped for the response."""
    hits = await search_hits(session, query, limit=limit, now=now, stale_days=stale_days)
    terms = tokenize(query)
    if not terms:
        return {"query": query, "items": [], "total": 0}
    return {
        "query": query,
        "items": [hit.as_item() for hit in hits],
        "total": len(hits),
    }


async def list_sources(
    session: AsyncSession,
    *,
    limit: int = SOURCES_LIMIT_DEFAULT,
    now: datetime | None = None,
    stale_days: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    effective_limit = min(max(int(limit), 1), SOURCES_LIMIT_MAX)
    effective_stale_days = (
        settings.knowledge_stale_days_bounded if stale_days is None else max(int(stale_days), 1)
    )
    rows = (
        await session.execute(SELECT_SOURCES, {"limit": effective_limit})
    ).mappings().all()
    total = int((await session.execute(SELECT_SOURCES_TOTAL)).scalar_one())
    items = []
    for row in rows:
        fetched_at = row["fetched_at"]
        items.append(
            {
                "id": int(row["id"]),
                "url": str(row["url"]),
                "title": str(row["title"]),
                "source_type": str(row["source_type"]),
                "fetched_at": _iso_z(fetched_at),
                "age_days": age_days(fetched_at, now=now),
                "stale": is_stale(fetched_at, now=now, stale_days=effective_stale_days),
                "chunks": int(row["chunks"]),
            }
        )
    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


def content_hash(payload: str) -> str:
    return hashlib.sha256(str(payload or "").encode("utf-8")).hexdigest()


def lesson_content_hash(content: Any) -> str:
    data = _loads(content)
    if data is None:
        return content_hash(str(content or ""))
    return content_hash(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str))


def split_targets(urls: Sequence[str] | None) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """(doc_urls, lesson_codes, rejected results) for one ingest call.

    An empty list means "everything": the configured doc URLs plus every repo
    lesson. A provided list is taken literally, so one bad entry cannot silently
    turn into a fetch of something else.
    """
    doc_urls: list[str] = []
    lesson_codes: list[str] = []
    rejected: list[dict[str, Any]] = []

    def reject(url: str, error_code: str) -> None:
        rejected.append(
            {
                "url": url,
                "status": "failed",
                "chunks_added": 0,
                "skipped": False,
                "error_code": error_code,
            }
        )

    requested = [normalize_url(url) for url in (urls or [])]
    requested = [url for url in requested if url]
    if not requested:
        for url in get_settings().knowledge_doc_url_list:
            try:
                classify_url(url)
            except KnowledgeUrlError as exc:
                reject(url, exc.error_code)
                continue
            doc_urls.append(url)
        return doc_urls, lesson_codes, rejected

    for url in requested:
        try:
            source_type = classify_url(url)
        except KnowledgeUrlError as exc:
            logger.warning("knowledge ingest rejected url=%s error_code=%s", url, exc.error_code)
            reject(url, exc.error_code)
            continue
        if source_type == SOURCE_TYPE_REPO_LESSON:
            lesson_codes.append(lesson_code_from_repo_url(url))
        else:
            doc_urls.append(url)
    return doc_urls, lesson_codes, rejected


def _result(
    url: str,
    *,
    status: str,
    chunks_added: int = 0,
    skipped: bool = False,
    error_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": url,
        "status": status,
        "chunks_added": chunks_added,
        "skipped": skipped,
    }
    if error_code is not None:
        payload["error_code"] = error_code
    return payload


async def _store_source(
    session: AsyncSession,
    *,
    url: str,
    title: str,
    source_type: str,
    version_label: str,
    fetched_at: datetime,
    content_hash_value: str,
    status: str,
    error_code: str | None,
) -> tuple[int, bool]:
    """Upsert the source row. Returns (source_id, content_changed)."""
    existing = (
        await session.execute(SELECT_SOURCE_BY_URL, {"url": url})
    ).mappings().first()
    values = {
        "url": url,
        "title": title[:300] or url[:300],
        "source_type": source_type,
        "version_label": version_label[:64],
        "fetched_at": fetched_at,
        "content_hash": content_hash_value[:64],
        "status": status,
        "error_code": error_code,
    }
    if existing is None:
        source_id = int((await session.execute(INSERT_SOURCE, values)).scalar_one())
        return source_id, True

    source_id = int(existing["id"])
    unchanged = (
        status == "ok"
        and str(existing["content_hash"] or "") == content_hash_value[:64]
        and str(existing["status"]) == "ok"
    )
    if status == "failed" and not values["content_hash"]:
        # A failed refresh must not erase the hash that still describes the chunks
        # we hold: keeping it makes a later identical success a true skip instead of
        # a needless re-chunk, and it keeps hash and chunks telling the same story.
        values = {**values, "content_hash": str(existing["content_hash"] or "")}
    await session.execute(UPDATE_SOURCE, {**values, "id": source_id})
    return source_id, not unchanged


async def _replace_chunks(
    session: AsyncSession, source_id: int, chunks: Sequence[Chunk]
) -> int:
    highest = int(
        (await session.execute(SELECT_MAX_CHUNK_INDEX, {"source_id": source_id})).scalar_one()
    )
    if highest >= 0:
        await session.execute(DELETE_SOURCE_CHUNKS, {"source_id": source_id})
    for index, chunk in enumerate(chunks):
        await session.execute(
            INSERT_CHUNK,
            {
                "source_id": source_id,
                "chunk_index": index,
                "heading": chunk.heading,
                "content": chunk.content,
                "keywords": extract_keywords(chunk.heading or "", chunk.content),
            },
        )
    return len(chunks)


async def _ingest_document(
    session: AsyncSession,
    url: str,
    fetcher: KnowledgeFetcher,
    *,
    now: datetime,
) -> dict[str, Any]:
    try:
        outcome = await fetcher.fetch(url)
    except Exception:  # noqa: BLE001 - a broken fetcher is one failed source
        logger.warning("knowledge fetch raised url=%s", url)
        outcome = FetchResult.failure(ERROR_FETCH_FAILED)

    if not outcome.ok:
        error_code = outcome.error_code or ERROR_FETCH_FAILED
        await _store_source(
            session,
            url=url,
            title=url,
            source_type=SOURCE_TYPE_OFFICIAL_DOC,
            version_label=version_label_for_url(url),
            fetched_at=now,
            content_hash_value="",
            status="failed",
            error_code=error_code,
        )
        await session.commit()
        logger.warning("knowledge ingest failed url=%s error_code=%s", url, error_code)
        return _result(url, status="failed", error_code=error_code)

    title = extract_title(outcome.text, fallback=url)
    chunks = chunk_html(outcome.text, default_heading=title)
    if not chunks:
        await _store_source(
            session,
            url=url,
            title=title,
            source_type=SOURCE_TYPE_OFFICIAL_DOC,
            version_label=version_label_for_url(url),
            fetched_at=now,
            content_hash_value="",
            status="failed",
            error_code=ERROR_EMPTY_CONTENT,
        )
        await session.commit()
        return _result(url, status="failed", error_code=ERROR_EMPTY_CONTENT)

    digest = content_hash(outcome.text)
    source_id, changed = await _store_source(
        session,
        url=url,
        title=title,
        source_type=SOURCE_TYPE_OFFICIAL_DOC,
        version_label=version_label_for_url(url),
        fetched_at=now,
        content_hash_value=digest,
        status="ok",
        error_code=None,
    )
    if not changed:
        await session.commit()
        logger.info("knowledge ingest skipped url=%s reason=content_hash_unchanged", url)
        return _result(url, status="ok", skipped=True)

    added = await _replace_chunks(session, source_id, chunks)
    await session.commit()
    logger.info("knowledge ingest ok url=%s chunks_added=%d", url, added)
    return _result(url, status="ok", chunks_added=added)


async def _ingest_lesson(
    session: AsyncSession, lesson: Any, *, now: datetime
) -> dict[str, Any]:
    code = str(lesson["code"])
    title = str(lesson["title"])
    url = repo_lesson_url(code)
    chunks = lesson_chunks(lesson["content"], title=title)
    if not chunks:
        await _store_source(
            session,
            url=url,
            title=title,
            source_type=SOURCE_TYPE_REPO_LESSON,
            version_label=f"v{lesson['content_version']}",
            fetched_at=now,
            content_hash_value="",
            status="failed",
            error_code=ERROR_EMPTY_CONTENT,
        )
        await session.commit()
        return _result(url, status="failed", error_code=ERROR_EMPTY_CONTENT)

    digest = lesson_content_hash(lesson["content"])
    source_id, changed = await _store_source(
        session,
        url=url,
        title=title,
        source_type=SOURCE_TYPE_REPO_LESSON,
        version_label=f"v{lesson['content_version']}",
        fetched_at=now,
        content_hash_value=digest,
        status="ok",
        error_code=None,
    )
    if not changed:
        await session.commit()
        return _result(url, status="ok", skipped=True)

    added = await _replace_chunks(session, source_id, chunks)
    await session.commit()
    logger.info("knowledge ingest lesson code=%s chunks_added=%d", code, added)
    return _result(url, status="ok", chunks_added=added)


async def _load_lessons(session: AsyncSession) -> list[Any]:
    return (await session.execute(SELECT_LESSONS_FOR_INGEST)).mappings().all()


async def ingest(
    session: AsyncSession,
    *,
    urls: Sequence[str] | None = None,
    fetcher: KnowledgeFetcher | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ingest the whitelisted sources and report one result per source.

    A failure is contained: one unreachable page never stops the others, and the
    caller still gets 200 with a per-source report. Every source commits on its own
    for the same reason.
    """
    started_at = _as_utc(now)
    effective_fetcher: KnowledgeFetcher = fetcher or HttpxFetcher()
    doc_urls, lesson_codes, rejected = split_targets(urls)
    results: list[dict[str, Any]] = list(rejected)

    for url in doc_urls:
        try:
            results.append(await _ingest_document(session, url, effective_fetcher, now=started_at))
        except Exception:  # noqa: BLE001 - isolation is the point of this loop
            await session.rollback()
            logger.exception("knowledge ingest crashed url=%s", url)
            results.append(_result(url, status="failed", error_code=ERROR_INGEST_FAILED))

    lessons: list[Any] = []
    try:
        if lesson_codes:
            for code in lesson_codes:
                row = (
                    await session.execute(SELECT_LESSON_BY_CODE, {"code": code})
                ).mappings().first()
                if row is None:
                    results.append(
                        _result(
                            repo_lesson_url(code),
                            status="failed",
                            error_code=ERROR_LESSON_NOT_FOUND,
                        )
                    )
                else:
                    lessons.append(row)
        elif not (urls and any(normalize_url(url) for url in urls)):
            lessons = await _load_lessons(session)
    except Exception:  # noqa: BLE001
        await session.rollback()
        logger.exception("knowledge ingest could not read lessons")

    for lesson in lessons:
        url = repo_lesson_url(str(lesson["code"]))
        try:
            results.append(await _ingest_lesson(session, lesson, now=started_at))
        except Exception:  # noqa: BLE001
            await session.rollback()
            logger.exception("knowledge ingest crashed lesson=%s", url)
            results.append(_result(url, status="failed", error_code=ERROR_INGEST_FAILED))

    sources_total = int((await session.execute(SELECT_SOURCES_TOTAL)).scalar_one())
    chunks_total = int((await session.execute(SELECT_CHUNKS_TOTAL)).scalar_one())
    logger.info(
        "knowledge ingest finished sources=%d chunks=%d results=%d",
        sources_total,
        chunks_total,
        len(results),
    )
    return {
        "results": results,
        "sources_total": sources_total,
        "chunks_total": chunks_total,
    }


__all__ = [
    "age_days",
    "ALLOWED_DOC_HOST",
    "CANDIDATE_LIMIT",
    "Chunk",
    "chunk_html",
    "chunk_text",
    "classify_url",
    "content_hash",
    "DEFAULT_FETCH_TIMEOUT_SECONDS",
    "ERROR_BLOCKED_HOST",
    "extract_keywords",
    "extract_title",
    "FetchResult",
    "html_to_marked_text",
    "HttpxFetcher",
    "ingest",
    "is_allowed_doc_host",
    "is_allowed_doc_url",
    "is_stale",
    "KnowledgeFetcher",
    "KnowledgeUrlError",
    "lesson_chunks",
    "lesson_code_from_repo_url",
    "list_sources",
    "MAX_CHUNK_CHARS",
    "normalize_url",
    "REPO_LESSON_PREFIX",
    "repo_lesson_url",
    "score_terms",
    "search",
    "search_hits",
    "SEARCH_LIMIT_DEFAULT",
    "SEARCH_LIMIT_MAX",
    "SEARCH_QUERY_MAX_LENGTH",
    "SEARCH_QUERY_MIN_LENGTH",
    "SearchHit",
    "SOURCE_TYPE_OFFICIAL_DOC",
    "SOURCE_TYPE_REPO_LESSON",
    "SOURCES_LIMIT_DEFAULT",
    "split_targets",
    "STOPWORDS",
    "tokenize",
    "utcnow",
    "validate_doc_url",
]
