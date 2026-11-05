"""Sprint 4 acceptance: the AI tutor surface, with no network and no live key.

Two halves in one module.

1. Unit tests (no PostgreSQL): every request goes through a stub transport and a
   stub session, so the transport is never httpx's real one and no upstream call
   can happen. These cover the five statuses the ledger records, the two refusals
   that must cost zero upstream calls, the key-never-logged assertion, and the
   shape of the outbound body (titles only, never submitted code).

2. Integration tests (marked individually, need PostgreSQL): the same routes over
   the real database inside the conftest rollback fixture, so the ledger row is
   checked with SQL rather than with a fake.

The empty DEEPSEEK_API_KEY in this environment is not a limitation here: it is the
first scenario. Every other scenario injects a stub client holding a fake key that
authenticates nowhere.
"""

from __future__ import annotations

import copy
import json
import logging
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ai_client import DeepSeekClient, TransportResponse

API_DIR = Path(__file__).resolve().parents[1]
# Sprint 5 追加 0006、Sprint 6 追加 0007 后 head 前移两位；0005 建的这一张表必须保持原样。
HEAD_REVISION = "0005_sprint4_ai_interactions"
LATEST_REVISION = "0006_sprint5_knowledge"
CURRENT_HEAD = "0019_sprint14_project_build"
PREVIOUS_REVISION = "0004_sprint3_exercises"

# A key shaped like a real one, long enough that searching a log line for it means
# something. It authenticates nowhere.
FAKE_KEY = "sk-sprint4-unit-test-key-never-log-me-9f3a"

# The nine tables that existed before 0005. 0005 must not take a row away from any
# of them; the rows the assertion compares against are the test's own, so nothing
# here depends on what the database already held.
PRE_0005_TABLES = (
    "users",
    "skills",
    "diagnostic_attempts",
    "user_skill_levels",
    "lessons",
    "learning_progress",
    "study_plan_items",
    "exercises",
    "submissions",
)

AI_INTERACTION_COLUMNS = {
    "id",
    "user_id",
    "lesson_id",
    "exercise_id",
    "question",
    "answer",
    "assistance_level",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "latency_ms",
    "status",
    "error_code",
    "created_at",
}

TUTOR_PATH = "/api/v1/ai/tutor"
INTERACTIONS_PATH = "/api/v1/ai/interactions"

OK_PAYLOAD: dict[str, Any] = {
    "model": "deepseek-flash",
    "choices": [{"message": {"content": "先看第 3 行：a 是文本，b 是整数。"}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 34, "total_tokens": 154},
}

BASE_BODY: dict[str, Any] = {
    "question": "为什么 a + b 会报 TypeError？",
    "assistance_level": "hint",
}


# ---------------------------------------------------------------------------
# stub transport: the only object that would speak HTTP
# ---------------------------------------------------------------------------


class StubTransport:
    """Records every attempt and answers from a queue. Never opens a socket."""

    def __init__(
        self,
        responses: list[Any] | None = None,
        *,
        status_code: int = 200,
        payload: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._queue = list(responses or [])
        self._status_code = status_code
        self._payload = copy.deepcopy(OK_PAYLOAD if payload is None else payload)
        self._error = error

    @property
    def call_count(self) -> int:
        return len(self.calls)

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
        if self._error is not None:
            raise self._error
        if self._queue:
            item = self._queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return TransportResponse(
            status_code=self._status_code, payload=copy.deepcopy(self._payload)
        )

    def outbound_text(self) -> str:
        return json.dumps([call["body"] for call in self.calls], ensure_ascii=False)


# ---------------------------------------------------------------------------
# stub session: dispatch on the statement, so the real SQL is still exercised
# ---------------------------------------------------------------------------


class _StubMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return dict(self._rows[0]) if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]


class _StubResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows = [dict(row) for row in (rows or [])]
        self._scalar = scalar

    def mappings(self) -> _StubMappings:
        return _StubMappings(self._rows)

    def first(self) -> tuple[Any, ...] | None:
        return tuple(self._rows[0].values()) if self._rows else None

    def all(self) -> list[tuple[Any, ...]]:
        return [tuple(row.values()) for row in self._rows]

    def scalar_one(self) -> Any:
        assert self._scalar is not None, "statement was expected to return a scalar"
        return self._scalar


class StubSession:
    """Just enough AsyncSession for the tutor service; refuses unknown SQL."""

    def __init__(
        self,
        *,
        user_id: int = 1,
        used_tokens: int = 0,
        lesson_title: str | None = "变量与数据类型",
        exercise_title: str | None = "用变量记住四种类型并打印",
        list_rows: list[dict[str, Any]] | None = None,
        list_total: int = 0,
    ) -> None:
        self.user_id = user_id
        self.used_tokens = used_tokens
        self.lesson_title = lesson_title
        self.exercise_title = exercise_title
        self.list_rows = list_rows or []
        self.list_total = list_total
        self.statements: list[str] = []
        self.inserts: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _StubResult:
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        values = dict(params or {})
        if "INSERT INTO ai_interactions" in sql:
            self.inserts.append(values)
            return _StubResult(scalar=len(self.inserts))
        if "sum(prompt_tokens" in sql:
            return _StubResult(scalar=self.used_tokens)
        if "FROM users" in sql:
            return _StubResult(
                rows=[
                    {
                        "id": self.user_id,
                        "display_name": "学习者",
                        "timezone": "Asia/Shanghai",
                        "timezone_source": "seed",
                    }
                ]
            )
        if "FROM lessons" in sql:
            if self.lesson_title is None:
                return _StubResult(rows=[])
            return _StubResult(rows=[{"title": self.lesson_title}])
        if "FROM exercises" in sql:
            if self.exercise_title is None:
                return _StubResult(rows=[])
            return _StubResult(rows=[{"title": self.exercise_title}])
        if "count(*)" in sql:
            return _StubResult(scalar=self.list_total)
        if "FROM ai_interactions" in sql:
            return _StubResult(rows=self.list_rows)
        raise AssertionError(f"unexpected statement: {sql}")

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _client_for(session: Any, client: DeepSeekClient) -> AsyncIterator[httpx.AsyncClient]:
    """App with the database session and the AI client both replaced."""
    from app.api.v1.routes import ai as ai_routes
    from app.core.db import get_db
    from app.main import create_app

    application = create_app()

    async def _override_db() -> AsyncIterator[Any]:
        yield session

    application.dependency_overrides[get_db] = _override_db
    application.dependency_overrides[ai_routes.get_ai_client] = lambda: client
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    application.dependency_overrides.clear()


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Attach a handler after the app exists.

    create_app() installs its own root handler and drops the existing ones, so a
    capture attached before the app is built would silently see nothing - and a
    "the key is not in the log" assertion that sees nothing proves nothing.
    """
    handler = _ListHandler()
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler.messages
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


@pytest.fixture
def ai_env(monkeypatch: pytest.MonkeyPatch):
    """Apply environment overrides, then rebuild the cached Settings."""

    def _apply(**env: str) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    return _apply


def _client(transport: StubTransport, api_key: str = FAKE_KEY) -> DeepSeekClient:
    return DeepSeekClient(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=30.0,
        transport=transport,
    )


async def _single_user_id(session: AsyncSession) -> int:
    return int((await session.execute(text("SELECT min(id) FROM users"))).scalar_one())


# ---------------------------------------------------------------------------
# 1) refusals that must cost nothing
# ---------------------------------------------------------------------------


async def test_01_no_api_key_returns_503_and_never_calls_upstream(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY="", AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport()
    session = StubSession()
    async with _client_for(session, _client(transport, api_key="")) as http:
        response = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert transport.call_count == 0, "no key configured must not reach the provider"
    assert [row["status"] for row in session.inserts] == ["unavailable"]
    assert session.inserts[0]["error_code"] == "AI_UNAVAILABLE"
    assert session.inserts[0]["answer"] is None
    assert session.commits == 1
    assert FAKE_KEY not in response.text


async def test_02_quota_exceeded_returns_429_and_never_calls_upstream(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="1000")
    transport = StubTransport()
    session = StubSession(used_tokens=1000)
    async with _client_for(session, _client(transport)) as http:
        response = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "AI_QUOTA_EXCEEDED"
    assert body["error"]["details"]["used_tokens"] == 1000
    assert body["error"]["details"]["daily_token_limit"] == 1000
    assert transport.call_count == 0, "a spent budget must not reach the provider"
    assert [row["status"] for row in session.inserts] == ["quota"]
    assert session.inserts[0]["error_code"] == "AI_QUOTA_EXCEEDED"
    assert session.inserts[0]["prompt_tokens"] == 0


# ---------------------------------------------------------------------------
# 2) the three outcomes of a real attempt
# ---------------------------------------------------------------------------


async def test_03_success_returns_200_and_records_usage(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport()
    session = StubSession()
    async with _client_for(session, _client(transport)) as http:
        response = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "interaction_id",
        "answer",
        "model",
        "assistance_level",
        "usage",
        "latency_ms",
        "citations",
    }
    assert body["answer"] == "先看第 3 行：a 是文本，b 是整数。"
    assert body["model"] == "deepseek-flash"
    assert body["assistance_level"] == "hint"
    assert body["usage"] == {
        "prompt_tokens": 120,
        "completion_tokens": 34,
        "total_tokens": 154,
    }
    assert body["citations"] == []
    assert body["interaction_id"] == 1
    assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0

    assert transport.call_count == 1
    call = transport.calls[0]
    assert call["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert call["timeout"] == 30.0
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in json.dumps(call["body"], ensure_ascii=False)

    row = session.inserts[0]
    assert row["status"] == "ok"
    assert row["error_code"] is None
    assert row["answer"] == body["answer"]
    assert (row["prompt_tokens"], row["completion_tokens"]) == (120, 34)
    assert row["user_id"] == 1
    assert session.commits == 1


async def test_04_upstream_timeout_returns_504_and_records_timeout(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport(error=httpx.TimeoutException("simulated timeout"))
    session = StubSession()
    async with _client_for(session, _client(transport)) as http:
        response = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "AI_TIMEOUT"
    assert transport.call_count == 1
    row = session.inserts[0]
    assert row["status"] == "timeout"
    assert row["error_code"] == "AI_TIMEOUT"
    assert row["answer"] is None
    assert row["latency_ms"] >= 0


async def test_05_upstream_500_returns_502_and_records_error(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport(status_code=500, payload={"error": {"message": "boom"}})
    session = StubSession()
    async with _client_for(session, _client(transport)) as http:
        response = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_UPSTREAM_ERROR"
    assert transport.call_count == 1
    row = session.inserts[0]
    assert row["status"] == "error"
    assert row["error_code"] == "AI_UPSTREAM_STATUS_500"
    assert row["answer"] is None


# ---------------------------------------------------------------------------
# 3) the key and the code text never leave their boxes
# ---------------------------------------------------------------------------


async def test_06_logs_and_responses_never_contain_the_api_key(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    # The transport error text carries the key, so a passthrough would leak it.
    transport = StubTransport(error=httpx.ConnectError(f"connection refused, key={FAKE_KEY}"))
    session = StubSession()
    async with _client_for(session, _client(transport)) as http:
        with _captured_logs() as messages:
            response = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert response.status_code == 502
    assert messages, "the failure must produce at least one log line"
    assert all(FAKE_KEY not in message for message in messages)
    assert FAKE_KEY not in response.text
    assert FAKE_KEY not in json.dumps(session.inserts, ensure_ascii=False, default=str)
    assert session.inserts[0]["error_code"] == "AI_TRANSPORT_ERROR"


async def test_07_outbound_body_carries_titles_only_and_never_user_code(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport()
    session = StubSession(lesson_title="变量与数据类型", exercise_title="用变量记住四种类型并打印")
    body = {
        "question": "为什么报 TypeError？",
        "assistance_level": "partial_code",
        "context": {"lesson_id": 1, "exercise_id": 2},
    }
    async with _client_for(session, _client(transport)) as http:
        response = await http.post(TUTOR_PATH, json=body)

    assert response.status_code == 200
    outbound = transport.calls[0]["body"]
    assert set(outbound) == {"model", "messages", "stream", "temperature"}
    user_text = outbound["messages"][1]["content"]
    assert "变量与数据类型" in user_text
    assert "用变量记住四种类型并打印" in user_text
    assert "为什么报 TypeError？" in user_text
    assert outbound["stream"] is False
    # Structural proof: the tutor never reads a submission, so no code can travel.
    assert all("submissions" not in sql.lower() for sql in session.statements)
    assert "starter_code" not in transport.outbound_text()


# ---------------------------------------------------------------------------
# 4) the log view and the 422 contract
# ---------------------------------------------------------------------------


async def test_08_interactions_list_is_newest_first_without_full_answer(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY="", AI_DAILY_TOKEN_LIMIT="50000")
    newer = {
        "id": 12,
        "question_preview": "第二个问题",
        "assistance_level": "hint",
        "model": "deepseek-flash",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "status": "ok",
        "created_at": "2026-03-15T10:00:00Z",
    }
    older = {**newer, "id": 11, "question_preview": "第一个问题"}
    transport = StubTransport()
    session = StubSession(list_rows=[newer, older], list_total=2)
    async with _client_for(session, _client(transport, api_key="")) as http:
        response = await http.get(f"{INTERACTIONS_PATH}?limit=20")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [12, 11]
    assert body["total"] == 2
    assert set(body["items"][0]) == {
        "id",
        "question_preview",
        "assistance_level",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "status",
        "created_at",
    }
    assert "answer" not in body["items"][0]

    list_sql = next(sql for sql in session.statements if "left(question" in sql.lower())
    assert "answer" not in list_sql.lower(), "the list statement must not select the answer"
    assert "ORDER BY created_at DESC, id DESC" in list_sql
    assert transport.call_count == 0


@pytest.mark.parametrize(
    "body",
    [
        {"question": "正常问题", "assistance_level": "expert"},
        {"question": "正常问题", "assistance_level": ""},
        {"question": "   ", "assistance_level": "hint"},
        {"question": "x" * 2001, "assistance_level": "hint"},
        {"assistance_level": "hint"},
        {"question": "正常问题"},
    ],
    ids=[
        "bad-level",
        "empty-level",
        "blank-question",
        "question-too-long",
        "missing-question",
        "missing-level",
    ],
)
async def test_09_invalid_request_returns_422_without_cost(
    ai_env, body: dict[str, Any]
) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport()
    session = StubSession()
    async with _client_for(session, _client(transport)) as http:
        response = await http.post(TUTOR_PATH, json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert transport.call_count == 0
    assert session.inserts == []


async def test_10_unknown_context_returns_404_without_cost(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport()
    session = StubSession(exercise_title=None)  # the exercises lookup finds no row
    async with _client_for(session, _client(transport)) as http:
        response = await http.post(
            TUTOR_PATH, json={**BASE_BODY, "context": {"exercise_id": 99999}}
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert transport.call_count == 0
    assert session.inserts == []


async def test_10b_limit_parameter_is_bounded(ai_env) -> None:
    ai_env(DEEPSEEK_API_KEY="", AI_DAILY_TOKEN_LIMIT="50000")
    transport = StubTransport()
    session = StubSession(list_rows=[], list_total=0)
    async with _client_for(session, _client(transport, api_key="")) as http:
        too_many = await http.get(f"{INTERACTIONS_PATH}?limit=51")
        zero = await http.get(f"{INTERACTIONS_PATH}?limit=0")

    assert too_many.status_code == 422
    assert zero.status_code == 422
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# 5) integration: the same routes over the real database
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_11_0005_is_head_and_creates_only_ai_interactions(
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
    assert f"{CURRENT_HEAD} (head)" in current.stdout

    history = subprocess.run(
        [sys.executable, "-m", "alembic", "history"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert history.returncode == 0, history.stderr
    assert f"{PREVIOUS_REVISION} -> {HEAD_REVISION}" in history.stdout
    assert f"{HEAD_REVISION} -> {LATEST_REVISION}" in history.stdout

    columns = {
        str(row["column_name"])
        for row in (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'ai_interactions'"
                )
            )
        )
        .mappings()
        .all()
    }
    assert columns == AI_INTERACTION_COLUMNS

    # Every pre-existing table still holds at least what it held before 0005.
    # The "before" side is built here: a throwaway database at 0004, one row of our
    # own per table, then the upgrade to head.
    tables = list(PRE_0005_TABLES)
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
async def test_12_unavailable_call_is_persisted_in_postgres(
    db_session: AsyncSession, ai_env
) -> None:
    ai_env(DEEPSEEK_API_KEY="", AI_DAILY_TOKEN_LIMIT="50000")
    user_id = await _single_user_id(db_session)
    transport = StubTransport()
    async with _client_for(db_session, _client(transport, api_key="")) as http:
        response = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert response.status_code == 503
    assert transport.call_count == 0
    row = (
        await db_session.execute(
            text(
                "SELECT user_id, status, error_code, answer, prompt_tokens, "
                "completion_tokens, assistance_level, model, lesson_id, exercise_id "
                "FROM ai_interactions ORDER BY id DESC LIMIT 1"
            )
        )
    ).mappings().first()
    assert row is not None
    assert int(row["user_id"]) == user_id
    assert row["status"] == "unavailable"
    assert row["error_code"] == "AI_UNAVAILABLE"
    assert row["answer"] is None
    assert (row["prompt_tokens"], row["completion_tokens"]) == (0, 0)
    assert row["assistance_level"] == "hint"
    assert row["model"] == "deepseek-flash"
    assert row["lesson_id"] is None and row["exercise_id"] is None


@pytest.mark.integration
async def test_13_ok_call_is_persisted_and_listed_newest_first(
    db_session: AsyncSession, ai_env
) -> None:
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT="50000")
    long_question = "长问题：" + "为什么我的循环少算了一个数？" * 20
    transport = StubTransport(
        responses=[
            TransportResponse(status_code=200, payload=copy.deepcopy(OK_PAYLOAD)),
            TransportResponse(status_code=200, payload=copy.deepcopy(OK_PAYLOAD)),
        ]
    )
    async with _client_for(db_session, _client(transport)) as http:
        first = await http.post(TUTOR_PATH, json={**BASE_BODY, "question": long_question})
        second = await http.post(TUTOR_PATH, json={**BASE_BODY, "question": "第二个问题"})
        listing = await http.get(f"{INTERACTIONS_PATH}?limit=5")

    assert first.status_code == 200 and second.status_code == 200
    assert transport.call_count == 2
    assert second.json()["interaction_id"] == first.json()["interaction_id"] + 1

    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) >= 2
    # Both rows were written in one transaction, so created_at ties; the id
    # tiebreaker is what keeps "newest first" true.
    assert items[0]["id"] > items[1]["id"]
    assert items[0]["question_preview"] == "第二个问题"
    assert len(items[1]["question_preview"]) == 120
    assert all("answer" not in item for item in items)
    assert items[1]["total_tokens"] == 154
    assert listing.json()["total"] >= 2

    stored = (
        await db_session.execute(
            text(
                "SELECT answer, status, prompt_tokens, completion_tokens "
                "FROM ai_interactions WHERE id = :id"
            ),
            {"id": first.json()["interaction_id"]},
        )
    ).mappings().first()
    assert stored["status"] == "ok"
    assert stored["answer"] == "先看第 3 行：a 是文本，b 是整数。"
    assert (stored["prompt_tokens"], stored["completion_tokens"]) == (120, 34)


@pytest.mark.integration
async def test_14_quota_counts_only_todays_tokens(db_session: AsyncSession, ai_env) -> None:
    user_id = await _single_user_id(db_session)
    # 本用例必须与「今天真实用过多少次 AI」无关：先量出今天已消耗的 token，
    # 再把预算设成「已用 + 1000」，否则开发库里有真实调用时首调就会 429。
    baseline_used = int(
        (
            await db_session.execute(
                text(
                    "SELECT coalesce(sum(prompt_tokens + completion_tokens), 0) "
                    "FROM ai_interactions WHERE user_id = :user_id "
                    "AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
                ),
                {"user_id": user_id},
            )
        ).scalar_one()
        or 0
    )
    ai_env(DEEPSEEK_API_KEY=FAKE_KEY, AI_DAILY_TOKEN_LIMIT=str(baseline_used + 1000))
    insert_row = text(
        "INSERT INTO ai_interactions (user_id, question, answer, assistance_level, model, "
        "prompt_tokens, completion_tokens, status, created_at) "
        "VALUES (:user_id, :question, :answer, 'hint', 'deepseek-flash', "
        ":prompt_tokens, :completion_tokens, 'ok', :created_at)"
    )
    # A large spend from two days ago must not consume today's budget.
    await db_session.execute(
        insert_row,
        {
            "user_id": user_id,
            "question": "前天的问题",
            "answer": "前天的回答",
            "prompt_tokens": 900000,
            "completion_tokens": 0,
            "created_at": (await db_session.execute(text("SELECT now() - interval '2 days'"))).scalar_one(),
        },
    )
    transport = StubTransport()
    async with _client_for(db_session, _client(transport)) as http:
        allowed = await http.post(TUTOR_PATH, json=BASE_BODY)
        assert allowed.status_code == 200
        assert transport.call_count == 1

        # Now today's budget is spent and the next call must be refused for free.
        await db_session.execute(
            insert_row,
            {
                "user_id": user_id,
                "question": "今天的问题",
                "answer": "今天的回答",
                "prompt_tokens": 400,
                "completion_tokens": 600,
                "created_at": (await db_session.execute(text("SELECT now()"))).scalar_one(),
            },
        )
        refused = await http.post(TUTOR_PATH, json=BASE_BODY)

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
    assert refused.json()["error"]["details"]["used_tokens"] >= baseline_used + 1000
    assert transport.call_count == 1, "the refused call must not reach the provider"

    row = (
        await db_session.execute(
            text(
                "SELECT status, error_code, prompt_tokens, completion_tokens "
                "FROM ai_interactions ORDER BY id DESC LIMIT 1"
            )
        )
    ).mappings().first()
    assert row["status"] == "quota"
    assert row["error_code"] == "AI_QUOTA_EXCEEDED"
    assert (row["prompt_tokens"], row["completion_tokens"]) == (0, 0)
