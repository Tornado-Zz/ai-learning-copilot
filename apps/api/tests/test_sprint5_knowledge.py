"""Sprint 5 acceptance: knowledge ingest, retrieval and the tutor citation path.

Nothing in this module can reach the network, and that is structural rather than a
promise: the fetcher is either a FakeFetcher (a dict of URL -> HTML) injected
through the get_knowledge_fetcher dependency, or HttpxFetcher over an explicit
stub transport. The tutor transport is a stub too, so no suite here can call
api.deepseek.com or docs.python.org.

The default run needs no PostgreSQL. FakeSession below dispatches on the exact SQL
the pipeline issues (the ILIKE patterns and the keywords overlap included), so the
ingest idempotency, the isolation of one failed source and the scoring are all
exercised without a database. The three integration tests at the end run the same
code against the real tables inside the conftest rollback fixture.
"""

from __future__ import annotations

import copy
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ai_client import DeepSeekClient, TransportResponse
from app.services.knowledge import pipeline as knowledge

API_DIR = Path(__file__).resolve().parents[1]
HEAD_REVISION = "0006_sprint5_knowledge"
PREVIOUS_REVISION = "0005_sprint4_ai_interactions"
# Sprint 6 追加 0007、v0.1.2 追加 0008、v0.1.3 追加 0009 后 head 继续前移：
# 0006 仍是链上的一环，但不再是 head。
CURRENT_HEAD = "0010_capstone_review_requires_reviewer"

NOW = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)

DOC_URL = "https://docs.python.org/3/tutorial/introduction.html"
OTHER_DOC_URL = "https://docs.python.org/3/tutorial/controlflow.html"
THIRD_DOC_URL = "https://docs.python.org/3/library/stdtypes.html"
BLOCKED_URL = "https://evil.example.com/steal"
# Unique per process, so an integration run never collides with a row a previous
# manual ingest already committed.
UNIQUE_DOC_URL = f"https://docs.python.org/3/tutorial/introduction.html?pytest=5{uuid.uuid4().hex[:8]}"

DOC_HTML = (
    "<!doctype html><html><head><title>An Informal Introduction to Python</title></head><body>"
    "<h1>3. An Informal Introduction to Python</h1>"
    "<p>Python is a programming language that is easy to learn.</p>"
    "<h2>Using Python as a calculator</h2>"
    "<p>The list comprehension builds a list in one line.</p>"
    "<p>Numbers work as expected.</p>"
    "<h3>List comprehension</h3>"
    "<p>A list comprehension reads left to right.</p>"
    "<script>window.tracker = 'must never be indexed';</script>"
    "</body></html>"
)

DOC_HTML_CHANGED = DOC_HTML.replace(
    "A list comprehension reads left to right.",
    "A list comprehension reads left to right and creates a new list.",
)

DOC_TITLE = "An Informal Introduction to Python"
EXPECTED_HEADINGS = [
    "3. An Informal Introduction to Python",
    "Using Python as a calculator",
    "List comprehension",
]

TUTOR_PATH = "/api/v1/ai/tutor"
INGEST_PATH = "/api/v1/knowledge/ingest"
SEARCH_PATH = "/api/v1/knowledge/search"
SOURCES_PATH = "/api/v1/knowledge/sources"

FAKE_KEY = "sk-sprint5-knowledge-unit-test-never-used-4b1c"
OK_PAYLOAD: dict[str, Any] = {
    "model": "deepseek-flash",
    "choices": [{"message": {"content": "列表推导式会把表达式套在序列上生成新列表。"}}],
    "usage": {"prompt_tokens": 90, "completion_tokens": 20, "total_tokens": 110},
}

KNOWLEDGE_SOURCE_COLUMNS = {
    "id", "url", "title", "source_type", "version_label", "fetched_at",
    "content_hash", "status", "error_code", "created_at", "updated_at",
}
KNOWLEDGE_CHUNK_COLUMNS = {
    "id", "source_id", "chunk_index", "heading", "content", "keywords", "created_at",
}
# Tables that existed before 0006: 0006 must not take a row away from any of them.
# The rows compared against are the test's own, never a snapshot of this database.
PRE_0006_TABLES = (
    "users",
    "lessons",
    "exercises",
    "submissions",
    "user_skill_levels",
    "ai_interactions",
)


# ---------------------------------------------------------------------------
# fakes: a fetcher that never opens a socket, and a session that speaks our SQL
# ---------------------------------------------------------------------------


class FakeFetcher:
    """Maps URL -> HTML. Failures and crashes are declared up front."""

    def __init__(
        self,
        pages: dict[str, str] | None = None,
        *,
        failures: dict[str, str] | None = None,
        crash: tuple[str, ...] = (),
    ) -> None:
        self.pages = dict(pages or {})
        self.failures = dict(failures or {})
        self.crash = set(crash)
        self.calls: list[str] = []

    async def fetch(self, url: str) -> knowledge.FetchResult:
        self.calls.append(url)
        if url in self.crash:
            raise RuntimeError("simulated transport crash")
        if url in self.failures:
            return knowledge.FetchResult.failure(self.failures[url])
        page = self.pages.get(url)
        if page is None:
            return knowledge.FetchResult.failure("HTTP_404", status_code=404)
        return knowledge.FetchResult.success(page, status_code=200, final_url=url)


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows = [dict(row) for row in (rows or [])]
        self._scalar = scalar

    def mappings(self) -> _FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return dict(self._rows[0]) if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def scalar_one(self) -> Any:
        if self._scalar is None and not self._rows:
            raise AssertionError("statement was expected to return a scalar")
        return self._scalar


USER_ROW = {
    "id": 1,
    "display_name": "学习者",
    "timezone": "Asia/Shanghai",
    "timezone_source": "seed",
}


class FakeSession:
    """In-memory stand-in for AsyncSession, dispatching on the SQL we issue."""

    def __init__(
        self,
        lessons: list[dict[str, Any]] | None = None,
        *,
        fail_matching: str | None = None,
    ) -> None:
        self.sources: dict[str, dict[str, Any]] = {}
        self.chunks: list[dict[str, Any]] = []
        self.lessons = list(lessons or [])
        self.statements: list[str] = []
        self.commits = 0
        self.rollbacks = 0
        self.interactions: list[dict[str, Any]] = []
        self.fail_matching = fail_matching
        self._next_source_id = 1
        self._next_chunk_id = 1

    # -- direct helpers the tests use to seed a corpus --
    def add_source(
        self,
        url: str,
        *,
        title: str,
        source_type: str = "official_doc",
        fetched_at: datetime | None = None,
        content_hash: str = "seed-hash",
        status: str = "ok",
        error_code: str | None = None,
    ) -> int:
        source_id = self._next_source_id
        self._next_source_id += 1
        self.sources[url] = {
            "id": source_id,
            "url": url,
            "title": title,
            "source_type": source_type,
            "version_label": "",
            "fetched_at": fetched_at or NOW,
            "content_hash": content_hash,
            "status": status,
            "error_code": error_code,
        }
        return source_id

    def add_chunk(
        self,
        source_id: int,
        *,
        content: str,
        chunk_index: int = 0,
        heading: str | None = None,
    ) -> int:
        chunk_id = self._next_chunk_id
        self._next_chunk_id += 1
        self.chunks.append(
            {
                "chunk_id": chunk_id,
                "source_id": source_id,
                "chunk_index": chunk_index,
                "heading": heading,
                "content": content,
                "keywords": knowledge.extract_keywords(heading or "", content),
            }
        )
        return chunk_id

    def chunks_of(self, source_id: int) -> list[dict[str, Any]]:
        return [chunk for chunk in self.chunks if chunk["source_id"] == source_id]

    def source_of(self, source_id: int) -> dict[str, Any] | None:
        for source in self.sources.values():
            if source["id"] == source_id:
                return source
        return None

    # -- the AsyncSession surface the pipeline uses --
    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = " ".join(str(statement).split())
        values = dict(params or {})
        self.statements.append(sql)
        if self.fail_matching and self.fail_matching in sql:
            raise RuntimeError(f"simulated database failure: {self.fail_matching}")

        if "INSERT INTO ai_interactions" in sql:
            self.interactions.append(values)
            return _FakeResult(scalar=len(self.interactions))
        if "sum(prompt_tokens" in sql:
            return _FakeResult(scalar=0)
        if "FROM users" in sql:
            return _FakeResult(rows=[USER_ROW])
        if "SELECT count(*) FROM knowledge_sources" in sql:
            return _FakeResult(scalar=len(self.sources))
        if "SELECT count(*) FROM knowledge_chunks" in sql:
            return _FakeResult(scalar=len(self.chunks))
        if "FROM knowledge_sources WHERE url = :url" in sql:
            source = self.sources.get(values["url"])
            if source is None:
                return _FakeResult(rows=[])
            return _FakeResult(
                rows=[
                    {
                        "id": source["id"],
                        "content_hash": source["content_hash"],
                        "status": source["status"],
                    }
                ]
            )
        if "INSERT INTO knowledge_sources" in sql:
            source_id = self._next_source_id
            self._next_source_id += 1
            self.sources[values["url"]] = {
                "id": source_id,
                "url": values["url"],
                "title": values["title"],
                "source_type": values["source_type"],
                "version_label": values["version_label"],
                "fetched_at": values["fetched_at"],
                "content_hash": values["content_hash"],
                "status": values["status"],
                "error_code": values["error_code"],
            }
            return _FakeResult(scalar=source_id)
        if "UPDATE knowledge_sources" in sql:
            source = self.source_of(int(values["id"]))
            if source is not None:
                for key in (
                    "title",
                    "source_type",
                    "version_label",
                    "fetched_at",
                    "content_hash",
                    "status",
                    "error_code",
                ):
                    source[key] = values[key]
            return _FakeResult()
        if "COALESCE(max(chunk_index)" in sql:
            indexes = [
                chunk["chunk_index"]
                for chunk in self.chunks
                if chunk["source_id"] == int(values["source_id"])
            ]
            return _FakeResult(scalar=max(indexes) if indexes else -1)
        if "DELETE FROM knowledge_chunks" in sql:
            keep = [
                chunk
                for chunk in self.chunks
                if chunk["source_id"] != int(values["source_id"])
            ]
            removed = len(self.chunks) - len(keep)
            self.chunks = keep
            return _FakeResult(scalar=removed)
        if "INSERT INTO knowledge_chunks" in sql:
            chunk_id = self._next_chunk_id
            self._next_chunk_id += 1
            self.chunks.append(
                {
                    "chunk_id": chunk_id,
                    "source_id": int(values["source_id"]),
                    "chunk_index": int(values["chunk_index"]),
                    "heading": values["heading"],
                    "content": values["content"],
                    "keywords": list(values["keywords"]),
                }
            )
            return _FakeResult(scalar=chunk_id)
        if "LEFT JOIN knowledge_chunks c" in sql:
            return _FakeResult(rows=self._source_rows(values))
        if "FROM knowledge_chunks c" in sql:
            return _FakeResult(rows=self._candidate_rows(values))
        if "FROM lessons" in sql:
            if "WHERE code = :code" in sql:
                rows = [lesson for lesson in self.lessons if lesson["code"] == values["code"]]
            else:
                rows = list(self.lessons)
            return _FakeResult(rows=rows)
        raise AssertionError(f"unexpected statement: {sql}")

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    # -- the two read shapes, mirroring the SQL semantics --
    def _candidate_rows(self, values: dict[str, Any]) -> list[dict[str, Any]]:
        terms = list(values["terms"])
        patterns = [str(pattern).lower().strip("%") for pattern in values["patterns"]]
        rows: list[dict[str, Any]] = []
        for chunk in self.chunks:
            source = self.source_of(chunk["source_id"])
            if source is None:
                continue
            content = chunk["content"].lower()
            matched = any(pattern in content for pattern in patterns) or bool(
                set(chunk["keywords"]) & set(terms)
            )
            if not matched:
                continue
            rows.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "source_id": chunk["source_id"],
                    "chunk_index": chunk["chunk_index"],
                    "heading": chunk["heading"],
                    "content": chunk["content"],
                    "title": source["title"],
                    "url": source["url"],
                    "fetched_at": source["fetched_at"],
                }
            )
        rows.sort(key=lambda row: (-row["fetched_at"].timestamp(), -row["chunk_id"]))
        return rows[: int(values["candidate_limit"])]

    def _source_rows(self, values: dict[str, Any]) -> list[dict[str, Any]]:
        sources = sorted(
            self.sources.values(),
            key=lambda source: (-source["fetched_at"].timestamp(), -source["id"]),
        )
        rows = [
            {
                "id": source["id"],
                "url": source["url"],
                "title": source["title"],
                "source_type": source["source_type"],
                "fetched_at": source["fetched_at"],
                "chunks": len(self.chunks_of(source["id"])),
            }
            for source in sources
        ]
        return rows[: int(values["limit"])]


class StubAiTransport:
    """Answers from a fixed payload and records what would have been sent."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._payload = copy.deepcopy(OK_PAYLOAD if payload is None else payload)

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> TransportResponse:
        self.calls.append(
            {
                "url": url,
                "body": copy.deepcopy(json),
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        return TransportResponse(status_code=200, payload=copy.deepcopy(self._payload))


def _ai_client(transport: StubAiTransport, api_key: str = FAKE_KEY) -> DeepSeekClient:
    return DeepSeekClient(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=30.0,
        transport=transport,
    )


@asynccontextmanager
async def _app_client(
    session: Any,
    *,
    fetcher: Any = None,
    ai_client: DeepSeekClient | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    """App with the session, the knowledge fetcher and the AI client all replaced."""
    from app.api.v1.routes import ai as ai_routes
    from app.api.v1.routes import knowledge as knowledge_routes
    from app.core.db import get_db
    from app.main import create_app

    application = create_app()

    async def _override_db() -> AsyncIterator[Any]:
        yield session

    application.dependency_overrides[get_db] = _override_db
    if fetcher is not None:
        application.dependency_overrides[knowledge_routes.get_knowledge_fetcher] = lambda: fetcher
    if ai_client is not None:
        application.dependency_overrides[ai_routes.get_ai_client] = lambda: ai_client

    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    application.dependency_overrides.clear()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    """Apply environment overrides, then rebuild the cached Settings."""

    def _apply(**values: str) -> None:
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    return _apply


def _expected_chunks(html: str) -> int:
    return len(knowledge.chunk_html(html, default_heading=DOC_TITLE))


# ---------------------------------------------------------------------------
# 1) the whitelist: the gate between a request and a socket
# ---------------------------------------------------------------------------


def test_01_whitelist_accepts_docs_python_org_only() -> None:
    assert (
        knowledge.validate_doc_url("  " + DOC_URL + " ")
        == DOC_URL
    )
    assert knowledge.is_allowed_doc_url(DOC_URL)
    assert knowledge.is_allowed_doc_url("https://www.docs.python.org/3/library/stdtypes.html")

    cases = {
        "https://example.com/x": "BLOCKED_HOST",
        "https://docs.python.org.evil.example/x": "BLOCKED_HOST",
        "https://python.org/3/tutorial/": "BLOCKED_HOST",
        "http://127.0.0.1:8000/admin": "BLOCKED_HOST",
        "file://docs.python.org/etc/passwd": "UNSUPPORTED_SCHEME",
        "repo://lesson/route_a.py.variables": "UNSUPPORTED_SCHEME",
        "/3/tutorial/introduction.html": "MALFORMED_URL",
        "": "EMPTY_URL",
        "https://user:secret@docs.python.org/3/": "CREDENTIALS_IN_URL",
        "https://docs.python.org/3/" + "a" * 2100: "URL_TOO_LONG",
    }
    for url, expected in cases.items():
        with pytest.raises(knowledge.KnowledgeUrlError) as caught:
            knowledge.validate_doc_url(url)
        assert caught.value.error_code == expected, url


def test_02_repo_lessons_have_their_own_url_shape() -> None:
    url = knowledge.repo_lesson_url("route_a.py.variables")
    assert url == "repo://lesson/route_a.py.variables"
    assert knowledge.classify_url(url) == "repo_lesson"
    assert knowledge.classify_url(DOC_URL) == "official_doc"
    assert knowledge.lesson_code_from_repo_url(url) == "route_a.py.variables"

    with pytest.raises(knowledge.KnowledgeUrlError):
        knowledge.lesson_code_from_repo_url(DOC_URL)
    with pytest.raises(knowledge.KnowledgeUrlError):
        knowledge.classify_url("https://example.com/x")


# ---------------------------------------------------------------------------
# 2) parse and chunk: standard library only, h2/h3 aware, 1200 characters max
# ---------------------------------------------------------------------------


def test_03_html_is_stripped_and_split_on_headings() -> None:
    chunks = knowledge.chunk_html(DOC_HTML, default_heading=DOC_TITLE)
    assert [chunk.heading for chunk in chunks] == EXPECTED_HEADINGS

    rendered = " ".join(chunk.content for chunk in chunks)
    assert "<" not in rendered and ">" not in rendered
    assert "window.tracker" not in rendered, "script bodies must never be indexed"
    assert "The list comprehension builds a list in one line." in rendered
    assert all(len(chunk.content) <= knowledge.MAX_CHUNK_CHARS for chunk in chunks)
    assert knowledge.extract_title(DOC_HTML, DOC_URL) == DOC_TITLE


def test_04_over_long_blocks_are_split_under_the_ceiling() -> None:
    spaced = " ".join(["token"] * 700)
    chunks = knowledge.chunk_html("<h2>Long section</h2><p>" + spaced + "</p>")
    assert len(chunks) >= 3
    assert all(len(chunk.content) <= knowledge.MAX_CHUNK_CHARS for chunk in chunks)
    assert all(chunk.heading == "Long section" for chunk in chunks)

    cjk = "循" * 3000  # no spaces: the hard slice has to do the work
    cjk_chunks = knowledge.chunk_html("<h2>中文</h2><p>" + cjk + "</p>")
    assert len(cjk_chunks) >= 3
    assert all(len(chunk.content) <= knowledge.MAX_CHUNK_CHARS for chunk in cjk_chunks)


# ---------------------------------------------------------------------------
# 3) terms and score: every number in a search result is reproducible
# ---------------------------------------------------------------------------


def test_05_tokenizer_drops_stopwords_and_short_terms() -> None:
    assert knowledge.tokenize("How do I use the LIST and list_comprehension?") == [
        "list",
        "comprehension",
    ]
    assert "typeerror" in knowledge.tokenize("为什么 a + b 会报 TypeError？")
    assert knowledge.tokenize("a b ?!") == []
    assert knowledge.extract_keywords(
        "List comprehension", "a list comprehension builds a list"
    )[:2] == ["list", "comprehension"]


def test_06_score_adds_the_heading_and_title_bonus() -> None:
    terms = ["list", "comprehension"]
    assert knowledge.score_terms(terms, content="a list comprehension") == 1.0
    assert (
        knowledge.score_terms(terms, content="a list comprehension", heading="List comprehension")
        == 2.0
    )
    assert (
        knowledge.score_terms(terms, content="a list comprehension", title="List comprehension")
        == 2.0
    )
    assert knowledge.score_terms(terms, content="nothing here", heading="List comprehension") == 1.0
    assert knowledge.score_terms([], content="anything") == 0.0


def test_07_age_days_and_the_stale_threshold() -> None:
    half_day = NOW - timedelta(hours=12)
    old = NOW - timedelta(days=45)
    assert knowledge.age_days(half_day, now=NOW) == 0.5
    assert knowledge.age_days(old, now=NOW) == 45.0
    assert knowledge.is_stale(half_day, now=NOW, stale_days=30) is False
    assert knowledge.is_stale(old, now=NOW, stale_days=30) is True
    assert knowledge.is_stale(NOW - timedelta(days=2), now=NOW, stale_days=1) is True


# ---------------------------------------------------------------------------
# 4) ingest: idempotent, isolated, and refused before any fetch
# ---------------------------------------------------------------------------


async def test_08_ingest_is_idempotent_when_the_content_hash_is_unchanged() -> None:
    session = FakeSession()
    fetcher = FakeFetcher({DOC_URL: DOC_HTML})
    expected = _expected_chunks(DOC_HTML)

    first = await knowledge.ingest(session, urls=[DOC_URL], fetcher=fetcher, now=NOW)
    assert first["results"] == [
        {"url": DOC_URL, "status": "ok", "chunks_added": expected, "skipped": False}
    ]
    assert first["sources_total"] == 1
    assert first["chunks_total"] == expected

    second = await knowledge.ingest(session, urls=[DOC_URL], fetcher=fetcher, now=NOW)
    assert second["results"] == [
        {"url": DOC_URL, "status": "ok", "chunks_added": 0, "skipped": True}
    ]
    assert second["sources_total"] == 1
    assert second["chunks_total"] == expected, "a skipped ingest must not add a chunk"
    assert not [sql for sql in session.statements if sql.startswith("DELETE")]
    assert fetcher.calls == [DOC_URL, DOC_URL]


async def test_09_changed_content_replaces_the_chunk_set() -> None:
    session = FakeSession()
    await knowledge.ingest(session, urls=[DOC_URL], fetcher=FakeFetcher({DOC_URL: DOC_HTML}), now=NOW)
    before = len(session.chunks)
    digest_before = session.sources[DOC_URL]["content_hash"]

    changed = await knowledge.ingest(
        session, urls=[DOC_URL], fetcher=FakeFetcher({DOC_URL: DOC_HTML_CHANGED}), now=NOW
    )
    assert changed["results"][0]["skipped"] is False
    assert changed["results"][0]["chunks_added"] == before
    assert len(session.chunks) == before, "the old chunk set is replaced, not appended to"
    assert session.sources[DOC_URL]["content_hash"] != digest_before
    assert [chunk["chunk_index"] for chunk in session.chunks] == list(range(before))


async def test_10_one_failed_source_does_not_stop_the_others() -> None:
    session = FakeSession()
    fetcher = FakeFetcher(
        {DOC_URL: DOC_HTML},
        failures={OTHER_DOC_URL: "HTTP_503"},
        crash=(THIRD_DOC_URL,),
    )
    summary = await knowledge.ingest(
        session, urls=[OTHER_DOC_URL, THIRD_DOC_URL, DOC_URL], fetcher=fetcher, now=NOW
    )

    results = summary["results"]
    assert results[0] == {
        "url": OTHER_DOC_URL,
        "status": "failed",
        "chunks_added": 0,
        "skipped": False,
        "error_code": "HTTP_503",
    }
    assert results[1]["status"] == "failed"
    assert results[1]["error_code"] == "FETCH_FAILED"
    assert results[2]["status"] == "ok"
    assert results[2]["chunks_added"] == _expected_chunks(DOC_HTML)
    assert summary["sources_total"] == 3
    assert summary["chunks_total"] == results[2]["chunks_added"]
    assert session.sources[OTHER_DOC_URL]["status"] == "failed"
    assert session.sources[OTHER_DOC_URL]["error_code"] == "HTTP_503"
    assert session.chunks_of(session.sources[OTHER_DOC_URL]["id"]) == []

    # A refresh that fails afterwards keeps the chunks and the hash of the last
    # good ingest, so the next identical success is still a skip.
    digest = session.sources[DOC_URL]["content_hash"]
    kept = len(session.chunks)
    await knowledge.ingest(
        session, urls=[DOC_URL], fetcher=FakeFetcher(failures={DOC_URL: "HTTP_500"}), now=NOW
    )
    assert session.sources[DOC_URL]["status"] == "failed"
    assert session.sources[DOC_URL]["content_hash"] == digest
    assert len(session.chunks) == kept


async def test_11_a_non_whitelisted_url_is_rejected_before_any_fetch() -> None:
    session = FakeSession()
    fetcher = FakeFetcher({DOC_URL: DOC_HTML})
    summary = await knowledge.ingest(session, urls=[BLOCKED_URL, DOC_URL], fetcher=fetcher, now=NOW)

    assert summary["results"][0] == {
        "url": BLOCKED_URL,
        "status": "failed",
        "chunks_added": 0,
        "skipped": False,
        "error_code": "BLOCKED_HOST",
    }
    assert fetcher.calls == [DOC_URL], "a rejected URL must never reach the fetcher"
    assert BLOCKED_URL not in session.sources
    assert summary["results"][1]["status"] == "ok"


# ---------------------------------------------------------------------------
# 5) search: score first, freshness second, staleness always reported
# ---------------------------------------------------------------------------


async def test_12_search_ranks_by_score_then_freshness_and_flags_stale() -> None:
    session = FakeSession()
    fresh_id = session.add_source(
        DOC_URL, title=DOC_TITLE, fetched_at=NOW - timedelta(days=1)
    )
    session.add_chunk(
        fresh_id, heading="List comprehension", content="a list comprehension builds a new list"
    )
    recent_id = session.add_source(THIRD_DOC_URL, title="Built-in Types", fetched_at=NOW - timedelta(days=2))
    session.add_chunk(recent_id, content="the list type keeps insertion order")
    old_id = session.add_source(OTHER_DOC_URL, title="Control Flow", fetched_at=NOW - timedelta(days=45))
    session.add_chunk(old_id, content="a list of examples")

    result = await knowledge.search(session, "list comprehension", limit=5, now=NOW)
    items = result["items"]

    assert result["query"] == "list comprehension"
    assert result["total"] == 3
    assert [item["score"] for item in items] == [2.0, 0.5, 0.5]
    assert items[0]["heading"] == "List comprehension"
    assert items[0]["stale"] is False
    assert items[0]["age_days"] == 1.0
    assert items[0]["url"] == DOC_URL
    assert items[0]["fetched_at"].endswith("Z")
    assert items[1]["age_days"] == 2.0, "equal scores break on fetched_at DESC"
    assert items[2]["age_days"] == 45.0
    assert items[2]["stale"] is True
    assert items[0]["snippet"].startswith("a list comprehension")


async def test_13_search_without_usable_terms_issues_no_query() -> None:
    session = FakeSession()
    result = await knowledge.search(session, "a b ?!", limit=5)
    assert result == {"query": "a b ?!", "items": [], "total": 0}
    assert session.statements == []


# ---------------------------------------------------------------------------
# 6) endpoints: the switch, the 422 and the report shape
# ---------------------------------------------------------------------------


async def test_14_search_endpoint_rejects_a_query_shorter_than_two() -> None:
    session = FakeSession()
    async with _app_client(session) as http:
        empty = await http.get(SEARCH_PATH + "?q=")
        short = await http.get(SEARCH_PATH + "?q=a")
        missing = await http.get(SEARCH_PATH)

    for response in (empty, short, missing):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert session.statements == [], "a rejected query must not reach the database"


async def test_15_ingest_endpoint_is_403_when_the_switch_is_off(env) -> None:
    env(KNOWLEDGE_INGEST_ENABLED="false")
    session = FakeSession()
    fetcher = FakeFetcher({DOC_URL: DOC_HTML})
    async with _app_client(session, fetcher=fetcher) as http:
        response = await http.post(INGEST_PATH, json={"urls": [DOC_URL]})

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "INGEST_DISABLED"
    assert body["error"]["details"]["reason"] == "ingest_disabled"
    assert fetcher.calls == []
    assert session.statements == []


async def test_16_ingest_endpoint_reports_every_source(env) -> None:
    env(KNOWLEDGE_INGEST_ENABLED="true")
    session = FakeSession()
    fetcher = FakeFetcher({DOC_URL: DOC_HTML}, failures={OTHER_DOC_URL: "HTTP_500"})
    async with _app_client(session, fetcher=fetcher) as http:
        response = await http.post(INGEST_PATH, json={"urls": [DOC_URL, OTHER_DOC_URL]})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"results", "sources_total", "chunks_total"}
    assert [item["status"] for item in body["results"]] == ["ok", "failed"]
    assert set(body["results"][0]) == {"url", "status", "chunks_added", "skipped", "error_code"}
    assert body["results"][0]["error_code"] is None
    assert body["results"][0]["chunks_added"] == _expected_chunks(DOC_HTML)
    assert body["results"][1]["error_code"] == "HTTP_500"
    assert body["sources_total"] == 2
    assert body["chunks_total"] == body["results"][0]["chunks_added"]


async def test_17_sources_endpoint_reports_freshness_and_chunk_counts() -> None:
    session = FakeSession()
    fresh_id = session.add_source(
        DOC_URL, title=DOC_TITLE, fetched_at=datetime.now(timezone.utc)
    )
    session.add_chunk(fresh_id, content="a list comprehension builds a new list")
    session.add_source(
        OTHER_DOC_URL, title="Control Flow", fetched_at=datetime.now(timezone.utc) - timedelta(days=40)
    )

    async with _app_client(session) as http:
        response = await http.get(SOURCES_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    first = body["items"][0]
    assert set(first) == {
        "id", "url", "title", "source_type", "fetched_at", "age_days", "stale", "chunks",
    }
    assert first["url"] == DOC_URL
    assert first["source_type"] == "official_doc"
    assert first["chunks"] == 1
    assert first["stale"] is False
    assert body["items"][1]["stale"] is True
    assert body["items"][1]["chunks"] == 0


def test_17b_openapi_document_exposes_the_three_knowledge_paths() -> None:
    """The schema is built once per process: a field whose description is not a
    string (a tuple, say) makes /openapi.json a 500 while every ASGI test stays
    green, so the document itself is asserted here.
    """
    from app.main import create_app

    schema = create_app().openapi()
    assert {SEARCH_PATH, INGEST_PATH, SOURCES_PATH} <= set(schema["paths"])
    citations = schema["components"]["schemas"]["TutorResponseOut"]["properties"]["citations"]
    assert citations["items"]["$ref"].endswith("KnowledgeCitation")
    assert (
        schema["components"]["schemas"]["KnowledgeCitation"]["properties"]["stale"]["type"]
        == "boolean"
    )

# ---------------------------------------------------------------------------
# 7) the tutor: citations on a hit, nothing on a miss, 200 on a broken search
# ---------------------------------------------------------------------------


def _matching_session() -> FakeSession:
    # The tutor retrieves with the real clock, so the seeded freshness is relative
    # to it: two days old, comfortably inside the 30-day stale threshold.
    session = FakeSession()
    source_id = session.add_source(
        DOC_URL, title=DOC_TITLE, fetched_at=datetime.now(timezone.utc) - timedelta(days=2)
    )
    session.add_chunk(
        source_id, heading="List comprehension", content="a list comprehension builds a new list"
    )
    return session


async def test_18_tutor_hit_returns_citations_and_injects_the_snippet(env) -> None:
    env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000", KNOWLEDGE_TOP_K="3")
    session = _matching_session()
    transport = StubAiTransport()
    question = "How does a list comprehension work?"

    async with _app_client(session, ai_client=_ai_client(transport)) as http:
        response = await http.post(
            TUTOR_PATH, json={"question": question, "assistance_level": "hint"}
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["citations"]) == 1
    assert set(body["citations"][0]) == {"title", "url", "fetched_at", "stale"}
    assert body["citations"][0]["url"] == DOC_URL
    assert body["citations"][0]["stale"] is False

    outbound = transport.calls[0]["body"]
    prompt = outbound["messages"][1]["content"]
    assert "[" + DOC_TITLE + "] a list comprehension builds a new list" in prompt
    assert question in prompt
    assert session.interactions[0]["status"] == "ok"


async def test_19_tutor_miss_keeps_citations_empty_and_the_prompt_unchanged(env) -> None:
    env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000", KNOWLEDGE_TOP_K="3")
    session = FakeSession()
    transport = StubAiTransport()

    async with _app_client(session, ai_client=_ai_client(transport)) as http:
        response = await http.post(
            TUTOR_PATH, json={"question": "为什么缩进会报错？", "assistance_level": "hint"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert set(body) == {
        "interaction_id", "answer", "model", "assistance_level", "usage", "latency_ms", "citations",
    }
    prompt = transport.calls[0]["body"]["messages"][1]["content"]
    assert "参考资料" not in prompt
    assert "为什么缩进会报错？" in prompt
    assert session.interactions[0]["status"] == "ok"


async def test_20_tutor_answers_even_when_retrieval_raises(env) -> None:
    env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000", KNOWLEDGE_TOP_K="3")
    session = FakeSession(fail_matching="FROM knowledge_chunks c")
    transport = StubAiTransport()

    async with _app_client(session, ai_client=_ai_client(transport)) as http:
        response = await http.post(
            TUTOR_PATH, json={"question": "什么是列表推导式？", "assistance_level": "hint"}
        )

    assert response.status_code == 200, "a retrieval fault must not fail the tutor call"
    assert response.json()["citations"] == []
    assert transport.calls, "the upstream call must still happen"
    assert session.interactions[0]["status"] == "ok"
    assert session.rollbacks >= 1, "the aborted transaction is cleared before the ledger write"


# ---------------------------------------------------------------------------
# 8) integration: the same code against the real tables
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_21_0006_is_on_the_chain_and_creates_exactly_two_tables(
    db_session: AsyncSession, migration_probe
) -> None:
    current = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert current.returncode == 0, current.stderr
    assert CURRENT_HEAD + " (head)" in current.stdout

    history = subprocess.run(
        [sys.executable, "-m", "alembic", "history"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert history.returncode == 0, history.stderr
    assert PREVIOUS_REVISION + " -> " + HEAD_REVISION in history.stdout

    rows = (
        await db_session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name IN ('knowledge_sources', 'knowledge_chunks')"
            )
        )
    ).mappings().all()
    by_table: dict[str, set[str]] = {}
    for row in rows:
        by_table.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    assert by_table["knowledge_sources"] == KNOWLEDGE_SOURCE_COLUMNS
    assert by_table["knowledge_chunks"] == KNOWLEDGE_CHUNK_COLUMNS

    constraints = set(
        (
            await db_session.execute(
                text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE n.nspname = 'public' "
                    "AND t.relname IN ('knowledge_sources', 'knowledge_chunks')"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {
        "uq_knowledge_sources_url",
        "ck_knowledge_sources_source_type",
        "ck_knowledge_sources_status",
        "ck_knowledge_sources_error_code",
        "uq_knowledge_chunks_source_index",
        "ck_knowledge_chunks_content",
    } <= constraints

    index_names = set(
        (
            await db_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
        )
        .scalars()
        .all()
    )
    assert "ix_knowledge_chunks_keywords" in index_names

    # Every pre-existing table still holds at least what it held before 0006: the
    # "before" side is a throwaway database at 0005 with one row of ours in each.
    tables = list(PRE_0006_TABLES)
    async with migration_probe() as probe:
        probe.upgrade(PREVIOUS_REVISION)
        await probe.insert_sentinels(tables)
        before = await probe.counts(tables)
        assert all(count >= 1 for count in before.values()), before

        probe.upgrade("head")
        assert "(head)" in probe.current()
        after = await probe.counts(tables)

    for table in tables:
        assert after[table] >= before[table], (table, before[table], after[table])


@pytest.mark.integration
async def test_22_real_ingest_search_and_idempotent_rerun(db_session: AsyncSession) -> None:
    fetcher = FakeFetcher({UNIQUE_DOC_URL: DOC_HTML})
    first = await knowledge.ingest(
        db_session, urls=[UNIQUE_DOC_URL], fetcher=fetcher, now=datetime.now(timezone.utc)
    )
    added = first["results"][0]["chunks_added"]
    assert first["results"][0]["status"] == "ok"
    assert added == _expected_chunks(DOC_HTML)

    result = await knowledge.search(db_session, "list comprehension", limit=5)
    assert result["items"], "the freshly ingested page must be searchable"
    top = result["items"][0]
    assert top["url"] == UNIQUE_DOC_URL
    assert top["score"] >= 1.0
    assert top["stale"] is False
    assert top["age_days"] == 0.0
    assert top["fetched_at"].endswith("Z")

    second = await knowledge.ingest(
        db_session, urls=[UNIQUE_DOC_URL], fetcher=fetcher, now=datetime.now(timezone.utc)
    )
    assert second["results"][0] == {
        "url": UNIQUE_DOC_URL,
        "status": "ok",
        "chunks_added": 0,
        "skipped": True,
    }
    stored = int(
        (
            await db_session.execute(
                text(
                    "SELECT count(*) FROM knowledge_chunks WHERE source_id = "
                    "(SELECT id FROM knowledge_sources WHERE url = :url)"
                ),
                {"url": UNIQUE_DOC_URL},
            )
        ).scalar_one()
    )
    assert stored == added

    sources = await knowledge.list_sources(db_session, limit=50)
    assert any(
        item["url"] == UNIQUE_DOC_URL and item["chunks"] == added
        for item in sources["items"]
    )


@pytest.mark.integration
async def test_23_real_tutor_call_cites_a_real_chunk(db_session: AsyncSession) -> None:
    get_settings.cache_clear()
    await knowledge.ingest(
        db_session,
        urls=[UNIQUE_DOC_URL],
        fetcher=FakeFetcher({UNIQUE_DOC_URL: DOC_HTML}),
        now=datetime.now(timezone.utc),
    )
    transport = StubAiTransport()
    async with _app_client(db_session, ai_client=_ai_client(transport)) as http:
        response = await http.post(
            TUTOR_PATH,
            json={"question": "How does a list comprehension work?", "assistance_level": "hint"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"], "a real chunk in the real tables must produce a citation"
    assert body["citations"][0]["url"] == UNIQUE_DOC_URL
    prompt = transport.calls[0]["body"]["messages"][1]["content"]
    assert "[" + DOC_TITLE + "]" in prompt
