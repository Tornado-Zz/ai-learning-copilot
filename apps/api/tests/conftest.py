"""Shared fixtures. The default suite must pass with PostgreSQL stopped.

Integration tests are repeatable on a database that already holds real product
data. Two mechanisms, no deletes:

1. Every test runs inside one outer transaction that is rolled back at teardown,
   so committed rows are never modified permanently.
2. State-sensitive assertions never lean on the seeded single user: each such
   test creates its own users row (fixture `test_user`) and filters every query
   by that user_id. Endpoint-level tests that must use the single-user API assert
   only what this test created (this attempt's evidence_ref, row deltas) and
   never a whole-table count or a default profile value.

The suite issues no DELETE / TRUNCATE / DROP against the product database and
never runs a downgrade. The only databases it drops are throwaway ones it created
itself (`copilot_test_probe_<pid>_<random>`), so the product data is never touched.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import date
from pathlib import Path

import asyncpg
import httpx
import pytest
from sqlalchemy import pool, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core import db
from app.core.config import get_settings
from app.services.question_set import CHOICES, DOMAIN_CODES, QUESTIONS_V1

# alembic is run as a subprocess from the directory its alembic.ini lives in.
API_DIR = Path(__file__).resolve().parents[1]

# Nothing listens on this port: the readiness probe must answer 503, not crash.
UNREACHABLE_DATABASE_URL = (
    "postgresql+asyncpg://copilot:copilot_dev_password@127.0.0.1:59999/copilot"
)

MakeClient = Callable[..., Awaitable[httpx.AsyncClient]]
RowCounter = Callable[[AsyncSession, str], Awaitable[int]]
AnswerFactory = Callable[[dict[str, int]], dict[str, dict[str, str]]]
TokenFactory = Callable[[str], str]
FlattenAnswers = Callable[[dict[str, dict[str, str]]], dict[str, str]]

INSERT_TEST_USER = text("INSERT INTO users (display_name) VALUES (:display_name) RETURNING id")
INSERT_TEST_PROFILE = text("INSERT INTO user_profiles (user_id) VALUES (:user_id)")

COUNTS = {
    "users": text("SELECT count(*) FROM users"),
    "user_profiles": text("SELECT count(*) FROM user_profiles"),
    "skills": text("SELECT count(*) FROM skills"),
    "diagnostic_attempts": text("SELECT count(*) FROM diagnostic_attempts"),
    "user_skill_levels": text("SELECT count(*) FROM user_skill_levels"),
    "lessons": text("SELECT count(*) FROM lessons"),
    "learning_progress": text("SELECT count(*) FROM learning_progress"),
    "study_plan_items": text("SELECT count(*) FROM study_plan_items"),
}


def answers_with_correct(per_domain: dict[str, int]) -> dict[str, dict[str, str]]:
    """Payload where the first N questions of each domain are answered correctly."""
    correct_ids: set[str] = set()
    for code, count in per_domain.items():
        ids = [question.id for question in QUESTIONS_V1 if question.skill_code == code]
        correct_ids.update(ids[:count])
    payload: dict[str, dict[str, str]] = {}
    for question in QUESTIONS_V1:
        if question.id in correct_ids:
            payload[question.id] = {"choice": question.answer}
        else:
            payload[question.id] = {
                "choice": next(choice for choice in CHOICES if choice != question.answer)
            }
    return payload


@asynccontextmanager
async def build_client() -> AsyncIterator[httpx.AsyncClient]:
    """Build a fresh app (settings are read at creation time) over ASGI."""
    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture(autouse=True)
async def isolated_settings() -> AsyncIterator[None]:
    """Drop the Settings and engine caches around every test."""
    get_settings.cache_clear()
    await db.dispose_engine()
    try:
        yield
    finally:
        get_settings.cache_clear()
        await db.dispose_engine()


@pytest.fixture
async def make_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MakeClient]:
    """Factory: apply environment overrides, then build a client for that config."""
    stack = AsyncExitStack()
    async with stack:

        async def _make(**env: str) -> httpx.AsyncClient:
            for key, value in env.items():
                monkeypatch.setenv(key, value)
            get_settings.cache_clear()
            await db.dispose_engine()
            return await stack.enter_async_context(build_client())

        yield _make


@pytest.fixture
async def client(make_client: MakeClient) -> httpx.AsyncClient:
    """Client configured the way a developer sees it with PostgreSQL stopped."""
    return await make_client(
        DATABASE_URL=UNREACHABLE_DATABASE_URL,
        DEEPSEEK_API_KEY="",
        APP_ENV="local",
    )


@pytest.fixture
async def live_client(make_client: MakeClient) -> httpx.AsyncClient:
    """Client using the real DATABASE_URL; only for integration tests."""
    return await make_client()


@pytest.fixture
def database_url() -> str:
    """The real DATABASE_URL from the environment or apps/api/.env."""
    return get_settings().database_url


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """One connection inside one outer transaction, rolled back at teardown."""
    engine = create_async_engine(database_url, poolclass=pool.NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # noqa: BLE001 - integration tests need a live database
        await engine.dispose()
        pytest.skip(f"PostgreSQL 不可用，跳过集成测试（{type(exc).__name__}）")
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client whose request session shares the rolled-back test transaction."""
    from app.core.db import get_db
    from app.main import create_app

    application = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    application.dependency_overrides.clear()


@pytest.fixture
def answer_factory() -> AnswerFactory:
    return answers_with_correct


@pytest.fixture
def all_correct_answers() -> dict[str, dict[str, str]]:
    return answers_with_correct({code: 99 for code in DOMAIN_CODES})


@pytest.fixture
async def test_user(db_session: AsyncSession) -> dict[str, object]:
    """A user owned by this test, created inside the rolled-back transaction.

    Every assertion about levels, profiles or L0 states is scoped to this id, so
    the result never depends on what the real user already did in the product.
    """
    display_name = f"pytest-user-{uuid.uuid4().hex[:8]}"
    user_id = int(
        (await db_session.execute(INSERT_TEST_USER, {"display_name": display_name})).scalar_one()
    )
    await db_session.execute(INSERT_TEST_PROFILE, {"user_id": user_id})
    return {"id": user_id, "display_name": display_name}


@pytest.fixture
def unique_token() -> TokenFactory:
    """Tokens never collide with a browser's real attempt_token values."""

    def _make(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    return _make


@pytest.fixture
def flatten_answers() -> FlattenAnswers:
    """Service calls take {question_id: choice}; HTTP takes {id: {choice}}."""

    def _flat(answers: dict[str, dict[str, str]]) -> dict[str, str]:
        return {question_id: value["choice"] for question_id, value in answers.items()}

    return _flat


@pytest.fixture
def row_counter() -> RowCounter:
    async def _count(session: AsyncSession, table: str) -> int:
        statement = COUNTS[table]
        return int((await session.execute(statement)).scalar_one())

    return _count


# ---------------------------------------------------------------------------
# Migration replay: one throwaway database, upgraded revision by revision
# ---------------------------------------------------------------------------
# "This migration lost no rows" can only be observed from *before* the
# migration, so the tests that assert it build that state instead of reading it
# out of whatever the developer's database happens to hold: a database of our
# own at the previous revision, one row of our own in every table that already
# existed, then the upgrade. Our rows are the baseline.
PROBE_SENTINELS: dict[str, str] = {
    "diagnostic_attempts": (
        "INSERT INTO diagnostic_attempts (user_id, attempt_token, question_set_version, "
        "rule_version, answers, domain_scores, total_correct, total_questions) "
        "SELECT u.id, 'hermetic-probe', 'v1', 'v1', '{}'::jsonb, '{}'::jsonb, 1, 1 "
        "FROM (SELECT id FROM users ORDER BY id LIMIT 1) AS u"
    ),
    "user_skill_levels": (
        "INSERT INTO user_skill_levels (user_id, skill_id, level, evidence_kind, "
        "verification_method, assessment_state) "
        "SELECT u.id, s.id, 0, 'diagnostic', 'none', 'unassessed' "
        "FROM (SELECT id FROM users ORDER BY id LIMIT 1) AS u "
        "CROSS JOIN (SELECT id FROM skills ORDER BY id LIMIT 1) AS s"
    ),
    "learning_progress": (
        "INSERT INTO learning_progress (user_id, lesson_id, status, progress_pct, "
        "started_at, completed_at) "
        "SELECT u.id, l.id, 'completed', 100, now(), now() "
        "FROM (SELECT id FROM users ORDER BY id LIMIT 1) AS u "
        "CROSS JOIN (SELECT id FROM lessons ORDER BY id LIMIT 1) AS l"
    ),
    "study_plan_items": (
        "INSERT INTO study_plan_items (user_id, week_start, plan_date, kind, target_id, "
        "planned_minutes, status, rationale, dedupe_key) "
        "SELECT u.id, DATE '2026-01-05', DATE '2026-01-05', 'lesson', l.id, 30, "
        "'scheduled', 'hermetic probe row', 'hermetic-probe' "
        "FROM (SELECT id FROM users ORDER BY id LIMIT 1) AS u "
        "CROSS JOIN (SELECT id FROM lessons ORDER BY id LIMIT 1) AS l"
    ),
    "submissions": (
        "INSERT INTO submissions (user_id, exercise_id, attempt_no, code_text, "
        "judging_mode, verification_method, is_passed) "
        "SELECT u.id, e.id, 1, 'print(1)', 'static_rule', 'static_rule', false "
        "FROM (SELECT id FROM users ORDER BY id LIMIT 1) AS u "
        "CROSS JOIN (SELECT id FROM exercises ORDER BY id LIMIT 1) AS e"
    ),
    "ai_interactions": (
        "INSERT INTO ai_interactions (user_id, question, assistance_level, model, status, "
        "answer, error_code) "
        "SELECT u.id, 'hermetic probe question', 'none', 'hermetic-probe', 'unavailable', "
        "NULL, 'unavailable' "
        "FROM (SELECT id FROM users ORDER BY id LIMIT 1) AS u"
    ),
}


class MigrationProbe:
    """A database this test owns, driven through alembic and dropped by its opener."""

    def __init__(self, database_url: str, dsn: str) -> None:
        self._url = database_url
        self._dsn = dsn

    def _alembic(self, *action: str) -> str:
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", *action],
            cwd=API_DIR,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            env={**os.environ, "DATABASE_URL": self._url},
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout

    def upgrade(self, revision: str) -> str:
        return self._alembic("upgrade", revision)

    def current(self) -> str:
        return self._alembic("current")

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[asyncpg.Connection]:
        connection = await asyncpg.connect(self._dsn)
        try:
            yield connection
        finally:
            await connection.close()

    async def insert_sentinels(self, tables: Sequence[str]) -> None:
        """One row of our own per table: unknown tables and not-yet-created ones are skipped."""
        async with self.connect() as connection:
            for table in tables:
                statement = PROBE_SENTINELS.get(table)
                if statement is None:
                    continue
                if await connection.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                    continue
                await connection.execute(statement)

    async def counts(self, tables: Sequence[str]) -> dict[str, int]:
        async with self.connect() as connection:
            return {
                table: int(await connection.fetchval(f'SELECT count(*) FROM "{table}"'))
                for table in tables
            }


@asynccontextmanager
async def _open_probe(database_url: str) -> AsyncIterator[MigrationProbe]:
    name = f"copilot_test_probe_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    url = make_url(database_url)
    probe_url = url.set(database=name).render_as_string(hide_password=False)
    probe_dsn = url.set(drivername="postgresql", database=name).render_as_string(
        hide_password=False
    )
    admin_dsn = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    try:
        admin = await asyncpg.connect(admin_dsn)
    except OSError as exc:
        pytest.skip(f"PostgreSQL 不可用，跳过迁移回放（{type(exc).__name__}）")
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        try:
            yield MigrationProbe(probe_url, probe_dsn)
        finally:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture
def migration_probe(database_url: str):
    """Factory: `async with migration_probe() as probe` opens a throwaway database."""

    def _make():
        return _open_probe(database_url)

    return _make


async def create_isolated_learner(
    session: AsyncSession,
    *,
    study_days: list[int],
    daily_minutes: int,
    level: int = 2,
) -> int:
    """自建一个学习者：已确认时区 + 档案 + 六域等级，全部落在调用方事务里。

    计划相关用例应当用它而不是种子用户：种子用户带着真实学习历史（完成的课程、
    终态的练习行、到期复习），断言会随真实使用漂移。详见 test_study_plan_isolation.py。
    """
    user_id = int(
        (
            await session.execute(
                text("INSERT INTO users (display_name, timezone, timezone_source) "
                     "VALUES (:name, :tz, 'user_confirmed') RETURNING id"),
                {"name": "isolated-" + uuid.uuid4().hex[:8], "tz": "Asia/Shanghai"},
            )
        ).scalar_one()
    )
    await session.execute(
        text("INSERT INTO user_profiles (user_id, study_days, daily_minutes) "
             "VALUES (:user_id, CAST(:days AS smallint[]), :daily)"),
        {"user_id": user_id, "days": study_days, "daily": daily_minutes},
    )
    if level > 0:
        await session.execute(
            text("INSERT INTO user_skill_levels (user_id, skill_id, level, evidence_kind, "
                 "verification_method, assessment_state) "
                 "SELECT :user_id, id, :level, 'diagnostic', 'static_rule', 'established' "
                 "FROM skills WHERE level = 'domain'"),
            {"user_id": user_id, "level": level},
        )
    return user_id
async def calendar_today(session: AsyncSession) -> tuple[date, date]:
    """返回 (本周周一, 该用户时区的今天)。只读，不改任何档案。

    计划相关用例若走 HTTP 触发生成，用的是**真实时钟**；硬编码「周几」的用例会随
    运行日漂移（实测：周三写死 [3]，周四跑就整片变红）。用这两个 helper 从今天推算。
    """
    timezone_name = "Asia/Shanghai"
    monday = (
        await session.execute(
            text("SELECT date_trunc('week', (now() AT TIME ZONE :timezone))::date"),
            {'timezone': timezone_name},
        )
    ).scalar_one()
    today = (
        await session.execute(
            text("SELECT (now() AT TIME ZONE :timezone)::date"),
            {'timezone': timezone_name},
        )
    ).scalar_one()
    return monday, today


def future_weekdays(today: date, count: int) -> list[int]:
    """本周内「今天及以后」的 count 个连续星期号；放不下时返回空列表。"""
    start = today.isoweekday()
    days = [start + offset for offset in range(count)]
    return days if days and days[-1] <= 7 else []
