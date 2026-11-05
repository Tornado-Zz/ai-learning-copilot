"""Sprint 2 验收 ① 与 ②：0003 迁移、既有 5 表零变化、3 张新表结构与约束。

隔离策略：约束用例一律在事务用 begin_nested() 里制造预期失败，外层事务整体回滚，
因此既不需要也不产生任何 DELETE。「既有 5 表一行未少」用临时库回放证明：升到 0002、
自己写入一行、再升到 head，断言行数不下降，因此不依赖产品库里已有什么数据。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[1]
REVISION = "0003_sprint2_lessons_and_plan"
BASELINE_REVISION = "0002_sprint1a_identity_diagnostics"
# S3 阶段 B 追加 0004、Sprint 4 追加 0005、Sprint 5 追加 0006、Sprint 6 追加 0007、
# v0.1.2 追加 0008、v0.1.3 追加 0009 后 head 继续前移；本文件仍只校验 0003 建的 3 张表。
SPRINT3_REVISION = "0004_sprint3_exercises"
# 0011 追加 a3/a4、0012 追加 a5/a6 四节 AI 课，0013 补 a2 编程实践两节，0014 给
# exercises 加 requirement_labels 后 head 前移；0003 建的 3 张表不受影响。
HEAD_REVISION = "0015_sprint11_print_rule"

# 0003 之前就已存在的 5 张表：迁移只许加表，不许让这些表少行。
PRE_MIGRATION_TABLES = (
    "users",
    "user_profiles",
    "skills",
    "diagnostic_attempts",
    "user_skill_levels",
)

EXPECTED_NEW_COLUMNS = {
    "lessons": {
        "id",
        "code",
        "skill_id",
        "route_code",
        "stage",
        "title",
        "summary",
        "content",
        "content_version",
        "estimated_minutes",
        "order_index",
        "difficulty",
        "status",
        "created_at",
        "updated_at",
        "deleted_at",
    },
    "learning_progress": {
        "id",
        "user_id",
        "lesson_id",
        "status",
        "self_assessment",
        "progress_pct",
        "time_spent_seconds",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    },
    "study_plan_items": {
        "id",
        "user_id",
        "week_start",
        "plan_date",
        "kind",
        "target_id",
        "planned_minutes",
        "status",
        "rationale",
        "dedupe_key",
        "created_at",
        "updated_at",
    },
}

EXPECTED_NEW_CONSTRAINTS = {
    "uq_lessons_code",
    "ck_lessons_stage",
    "ck_lessons_status",
    "ck_lessons_estimated_minutes",
    "ck_lessons_content_version",
    "ck_lessons_difficulty",
    "uq_learning_progress_user_lesson",
    "ck_learning_progress_status",
    "ck_learning_progress_self_assessment",
    "ck_learning_progress_progress_pct",
    "ck_learning_progress_time_spent",
    "ck_learning_progress_started_present",
    "ck_learning_progress_completed_present",
    "uq_study_plan_items_dedupe",
    "ck_spi_kind",
    "ck_spi_status",
    "ck_spi_planned_minutes",
    "ck_spi_plan_date_in_week",
}

EXPECTED_NEW_INDEXES = {
    "uq_lessons_code",
    "ix_lessons_stage_order",
    "ix_lessons_status",
    "uq_learning_progress_user_lesson",
    "ix_learning_progress_user_status",
    "uq_study_plan_items_dedupe",
    "ix_study_plan_items_user_week",
}

# 0003 只允许新增 3 张表。exercises 与 submissions 在 S3 阶段 B 由 0004 建立，
# 已由 tests/test_sprint3_exercises.py 覆盖；ai_interactions 在 Sprint 4 由 0005
# 建立，由 tests/test_sprint4_ai.py 覆盖；本文件继续审核其余尚不存在的表。
FORBIDDEN_TABLES = {
    "exercise_test_cases",
    "mistakes",
    "review_tasks",
    "projects",
}

INSERT_LESSON = text(
    """
    INSERT INTO lessons (code, skill_id, stage, title, content, estimated_minutes, order_index, status)
    VALUES (:code, (SELECT id FROM skills WHERE code = 'route_a.a1'), :stage, :title,
            '{"schema_version": 1}'::jsonb, :minutes, 1, :status)
    """
)

INSERT_PROGRESS = text(
    """
    INSERT INTO learning_progress (user_id, lesson_id, status, self_assessment, started_at, completed_at)
    VALUES (:user_id, :lesson_id, :status, :self_assessment, :started_at, :completed_at)
    """
)

INSERT_PLAN_ITEM = text(
    """
    INSERT INTO study_plan_items (
        user_id, week_start, plan_date, kind, target_id, planned_minutes, rationale, dedupe_key
    )
    VALUES (
        :user_id, :week_start, :plan_date, :kind, :target_id, :planned_minutes, '测试', :dedupe_key
    )
    """
)


async def _first_lesson_id(session: AsyncSession) -> int:
    return int(
        (await session.execute(text("SELECT min(id) FROM lessons"))).scalar_one()
    )


async def test_01_head_is_single_and_upgrade_is_idempotent(database_url: str) -> None:
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    current = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert current.returncode == 0, current.stderr
    assert f"{HEAD_REVISION} (head)" in current.stdout

    history = subprocess.run(
        [sys.executable, "-m", "alembic", "history"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert history.returncode == 0, history.stderr
    assert REVISION in history.stdout
    assert f"{BASELINE_REVISION} -> {REVISION}" in history.stdout


async def test_01b_existing_five_tables_lost_no_rows(
    db_session: AsyncSession, migration_probe
) -> None:
    """既有 5 表在 0003 → head 的升级里一行未少。

    基线由本用例自建：临时库升到 0002，往每张既有表写一行，再升到 head，断言每张表
    的行数不低于升级前。干净库与开发库上的断言完全相同。
    """
    version = (
        await db_session.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one()
    assert version == HEAD_REVISION

    tables = list(PRE_MIGRATION_TABLES)
    async with migration_probe() as probe:
        probe.upgrade(BASELINE_REVISION)
        await probe.insert_sentinels(tables)
        before = await probe.counts(tables)
        # 非空才是有意义的基线：5 张表都必须真的承载行
        assert all(count >= 1 for count in before.values()), before

        probe.upgrade("head")
        assert "(head)" in probe.current()
        after = await probe.counts(tables)

    for table in tables:
        assert after[table] >= before[table], (table, before[table], after[table])


async def test_02_the_three_new_tables_have_the_frozen_structure(
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT table_name, column_name, data_type, udt_name, is_nullable, is_generated "
                "FROM information_schema.columns WHERE table_schema = 'public'"
            )
        )
    ).mappings().all()
    columns: dict[str, dict[str, dict[str, object]]] = {}
    for row in rows:
        columns.setdefault(str(row["table_name"]), {})[str(row["column_name"])] = dict(row)

    for table, expected in EXPECTED_NEW_COLUMNS.items():
        assert table in columns, table
        assert set(columns[table]) == expected, (table, set(columns[table]) ^ expected)

    assert columns["lessons"]["content"]["data_type"] == "jsonb"
    assert columns["lessons"]["content_version"]["data_type"] == "smallint"
    assert columns["lessons"]["deleted_at"]["is_nullable"] == "YES"
    assert columns["learning_progress"]["started_at"]["is_nullable"] == "YES"
    assert columns["learning_progress"]["completed_at"]["is_nullable"] == "YES"
    assert columns["learning_progress"]["time_spent_seconds"]["data_type"] == "integer"
    assert columns["study_plan_items"]["week_start"]["data_type"] == "date"
    assert columns["study_plan_items"]["plan_date"]["data_type"] == "date"

    constraint_names = set(
        (
            await db_session.execute(
                text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE n.nspname = 'public' AND t.relname IN "
                    "('lessons','learning_progress','study_plan_items')"
                )
            )
        )
        .scalars()
        .all()
    )
    assert EXPECTED_NEW_CONSTRAINTS <= constraint_names

    index_names = set(
        (
            await db_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
        )
        .scalars()
        .all()
    )
    assert EXPECTED_NEW_INDEXES <= index_names

    triggers = set(
        (
            await db_session.execute(
                text(
                    "SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                    "WHERE NOT t.tgisinternal AND c.relname = 'study_plan_items'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert "trg_spi_lesson_target_exists" in triggers

    tables = set(
        (
            await db_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        )
        .scalars()
        .all()
    )
    # 本文件审核的那批表仍需不存在（S3 阶段 B 只开了 exercises / submissions）
    assert FORBIDDEN_TABLES & tables == set()


async def test_02b_lesson_and_progress_constraints_reject_bad_rows(
    db_session: AsyncSession, test_user
) -> None:
    lesson_id = await _first_lesson_id(db_session)
    suffix = uuid.uuid4().hex[:8]
    cases = [
        ({"code": f"pytest.bad.stage.{suffix}", "stage": 7, "title": "x", "minutes": 20, "status": "published"}, "ck_lessons_stage"),
        ({"code": f"pytest.bad.minutes.{suffix}", "stage": 1, "title": "x", "minutes": 241, "status": "published"}, "ck_lessons_estimated_minutes"),
        ({"code": f"pytest.bad.status.{suffix}", "stage": 1, "title": "x", "minutes": 20, "status": "live"}, "ck_lessons_status"),
        ({"code": "route_a.py.variables", "stage": 1, "title": "dup", "minutes": 20, "status": "published"}, "uq_lessons_code"),
    ]
    for params, expected in cases:
        with pytest.raises(IntegrityError) as error:
            async with db_session.begin_nested():
                await db_session.execute(INSERT_LESSON, params)
        assert expected in str(error.value), (params, str(error.value))

    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(
                INSERT_PROGRESS,
                {
                    "user_id": int(test_user["id"]),
                    "lesson_id": lesson_id,
                    "status": "in_progress",
                    "self_assessment": 3,
                    "started_at": None,
                    "completed_at": None,
                },
            )
    assert "ck_learning_progress_self_assessment" in str(error.value)

    # 已开始/已完成都必须有开始时间
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(
                INSERT_PROGRESS,
                {
                    "user_id": int(test_user["id"]),
                    "lesson_id": lesson_id,
                    "status": "in_progress",
                    "self_assessment": 2,
                    "started_at": None,
                    "completed_at": None,
                },
            )
    assert "ck_learning_progress_started_present" in str(error.value)

    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(
                INSERT_PROGRESS,
                {
                    "user_id": int(test_user["id"]),
                    "lesson_id": lesson_id,
                    "status": "completed",
                    "self_assessment": 2,
                    "started_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "completed_at": None,
                },
            )
    assert "ck_learning_progress_completed_present" in str(error.value)

    # 同一用户同一课程只能一行（当前状态表，不是历史表）
    async with db_session.begin_nested():
        await db_session.execute(
            INSERT_PROGRESS,
            {
                "user_id": int(test_user["id"]),
                "lesson_id": lesson_id,
                "status": "in_progress",
                "self_assessment": 1,
                "started_at": datetime(2026, 1, 1, tzinfo=UTC),
                "completed_at": None,
            },
        )
    with pytest.raises(IntegrityError) as error:
        async with db_session.begin_nested():
            await db_session.execute(
                INSERT_PROGRESS,
                {
                    "user_id": int(test_user["id"]),
                    "lesson_id": lesson_id,
                    "status": "not_started",
                    "self_assessment": 0,
                    "started_at": None,
                    "completed_at": None,
                },
            )
    assert "uq_learning_progress_user_lesson" in str(error.value)


async def test_02c_plan_item_constraints_and_target_trigger(
    db_session: AsyncSession, test_user
) -> None:
    lesson_id = await _first_lesson_id(db_session)
    # DATE 列必须绑定真正的 date 对象：asyncpg 不接受字符串
    base = {
        "user_id": int(test_user["id"]),
        "week_start": date(2026, 3, 2),
        "plan_date": date(2026, 3, 2),
        "kind": "lesson",
        "target_id": lesson_id,
        "planned_minutes": 20,
        "dedupe_key": f"2026-03-02|2026-03-02|lesson|{lesson_id}",
    }

    async with db_session.begin_nested():
        await db_session.execute(INSERT_PLAN_ITEM, base)

    bad_rows = [
        ({**base, "planned_minutes": 10, "dedupe_key": f"k1-{uuid.uuid4().hex[:6]}"}, "ck_spi_planned_minutes"),
        ({**base, "planned_minutes": 481, "dedupe_key": f"k2-{uuid.uuid4().hex[:6]}"}, "ck_spi_planned_minutes"),
        ({**base, "kind": "video", "dedupe_key": f"k3-{uuid.uuid4().hex[:6]}"}, "ck_spi_kind"),
        ({**base, "plan_date": date(2026, 3, 10), "dedupe_key": f"k4-{uuid.uuid4().hex[:6]}"}, "ck_spi_plan_date_in_week"),
        ({**base, "target_id": 999999999, "dedupe_key": f"k5-{uuid.uuid4().hex[:6]}"}, "lessons.id"),
        (base, "uq_study_plan_items_dedupe"),
    ]
    for params, expected in bad_rows:
        with pytest.raises(IntegrityError) as error:
            async with db_session.begin_nested():
                await db_session.execute(INSERT_PLAN_ITEM, params)
        assert expected in str(error.value), (params, str(error.value))
