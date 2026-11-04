"""干净库迁移回归：独立临时库上 0001 → head。

隔离策略：临时库名带进程号与随机后缀（并发跑测试不会互删同一个库），运行前后都用
DROP DATABASE ... WITH (FORCE) 清掉；
真实业务库 copilot 只读两件事（连接串与 alembic 版本号），从不写入、不迁移、不删除，
测试结束时还会断言 copilot 库仍在、版本号未被本次运行改动。
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[1]
# 每次运行使用唯一库名：两个 pytest 进程（或 CI 与本机）同时跑时不会互相 DROP 对方的探测库。
PROBE_DATABASE = f"copilot_migration_probe_{os.getpid()}_{uuid.uuid4().hex[:8]}"
BASELINE_REVISION = "0001"
BUSINESS_TABLES = {
    "users",
    "user_profiles",
    "skills",
    "diagnostic_attempts",
    "user_skill_levels",
}
SPRINT2_TABLES = {"lessons", "learning_progress", "study_plan_items"}
SEEDED_LESSONS = 5
SEEDED_SKILL_CODES = [
    "route_a.a1",
    "route_a.a2",
    "route_a.a3",
    "route_a.a4",
    "route_a.a5",
    "route_a.a6",
]


def _probe_database_url(database_url: str) -> str:
    """The alembic connection string for the probe database (same driver and credentials).

    render_as_string keeps the password: str(URL) masks it as *** and the child
    process would then fail authentication instead of migrating.
    """
    url = make_url(database_url).set(database=PROBE_DATABASE)
    return url.render_as_string(hide_password=False)


def _admin_dsn(database_url: str) -> str:
    """asyncpg DSN on the maintenance database: CREATE/DROP DATABASE is cluster-scoped."""
    url = make_url(database_url).set(drivername="postgresql", database="postgres")
    return url.render_as_string(hide_password=False)


def _probe_dsn(database_url: str) -> str:
    url = make_url(database_url).set(drivername="postgresql", database=PROBE_DATABASE)
    return url.render_as_string(hide_password=False)


@asynccontextmanager
async def _admin(database_url: str) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(_admin_dsn(database_url))
    try:
        yield connection
    finally:
        await connection.close()


def _alembic(action: str, database_url: str) -> subprocess.CompletedProcess[str]:
    """Run alembic against exactly one database, passed through DATABASE_URL."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *action.split()],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**os.environ, "DATABASE_URL": database_url},
    )


async def _drop_probe(admin: asyncpg.Connection) -> None:
    # FORCE 只作用于这个临时库：先断开遗留连接再删除，失败也不会静默
    await admin.execute(f'DROP DATABASE IF EXISTS "{PROBE_DATABASE}" WITH (FORCE)')


async def _business_tables(dsn: str) -> set[str]:
    connection = await asyncpg.connect(dsn)
    try:
        return set(
            await connection.fetchval(
                "SELECT array_agg(table_name) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            or []
        )
    finally:
        await connection.close()


async def _copilot_revision(main_dsn: str) -> str | None:
    """Read-only: the business database's alembic version, or None if never migrated."""
    connection = await asyncpg.connect(main_dsn)
    try:
        exists = await connection.fetchval("SELECT to_regclass('public.alembic_version')")
        if exists is None:
            return None
        return await connection.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await connection.close()


async def test_clean_database_upgrades_from_0001_to_head(database_url: str) -> None:
    main_url = make_url(database_url)
    assert PROBE_DATABASE != main_url.database
    main_dsn = main_url.set(drivername="postgresql").render_as_string(hide_password=False)

    try:
        async with _admin(database_url) as admin:
            await _drop_probe(admin)
            await admin.execute(f'CREATE DATABASE "{PROBE_DATABASE}"')
    except OSError as exc:
        pytest.skip(f"PostgreSQL 不可用，跳过干净库迁移回归（{type(exc).__name__}）")

    revision_before = await _copilot_revision(main_dsn)

    try:
        baseline = _alembic(f"upgrade {BASELINE_REVISION}", _probe_database_url(database_url))
        assert baseline.returncode == 0, baseline.stderr
        # 0001 是空基线：只有 alembic_version，没有任何业务表
        assert await _business_tables(_probe_dsn(database_url)) & BUSINESS_TABLES == set()

        upgrade = _alembic("upgrade head", _probe_database_url(database_url))
        assert upgrade.returncode == 0, upgrade.stderr
        current = _alembic("current", _probe_database_url(database_url))
        assert current.returncode == 0, current.stderr
        assert "(head)" in current.stdout, current.stdout

        connection = await asyncpg.connect(_probe_dsn(database_url))
        try:
            revision = await connection.fetchval("SELECT version_num FROM alembic_version")
            tables = set(
                await connection.fetchval(
                    "SELECT array_agg(table_name) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
                or []
            )
            codes = [
                row["code"]
                for row in await connection.fetch(
                    "SELECT code FROM skills WHERE level = 'domain' ORDER BY order_index"
                )
            ]
            skill_rows = await connection.fetchval("SELECT count(*) FROM skills")
            seeded_users = await connection.fetchval("SELECT count(*) FROM users")
            seeded_lessons = await connection.fetchval("SELECT count(*) FROM lessons")
            progress_rows = await connection.fetchval("SELECT count(*) FROM learning_progress")
            plan_rows = await connection.fetchval("SELECT count(*) FROM study_plan_items")
        finally:
            await connection.close()

        assert revision and revision in current.stdout
        assert BUSINESS_TABLES <= tables
        # Sprint 2 的 0003 在干净库上同样建出 3 张表并写入 5 节课程种子
        assert SPRINT2_TABLES <= tables
        assert codes == SEEDED_SKILL_CODES
        assert skill_rows == 6
        assert seeded_users == 1
        assert seeded_lessons == SEEDED_LESSONS
        assert progress_rows == 0
        assert plan_rows == 0
    finally:
        async with _admin(database_url) as admin:
            await _drop_probe(admin)

    # 收尾断言：临时库已删除，真实业务库仍在且版本未被本次运行改动
    async with _admin(database_url) as admin:
        databases = {row["datname"] for row in await admin.fetch("SELECT datname FROM pg_database")}
    assert PROBE_DATABASE not in databases
    assert main_url.database in databases
    assert await _copilot_revision(main_dsn) == revision_before
