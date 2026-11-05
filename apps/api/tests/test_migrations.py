"""验收 1–3：S1 的 0002 迁移可升级、五张表结构正确、skills 六条种子正确。

Sprint 2 追加 0003 后 head 变为 0003；本文件仍只校验 0002 建立的那 5 张表结构不变，
3 张新表的结构与约束由 tests/test_sprint2_schema.py 覆盖。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[1]
SPRINT1_REVISION = "0002_sprint1a_identity_diagnostics"
REVISION = "0003_sprint2_lessons_and_plan"
# S3 阶段 B 追加 0004、Sprint 4 追加 0005、Sprint 5 追加 0006、Sprint 6 追加 0007、
# v0.1.2 追加 0008 后 head 变成 0008；0002 -> ... -> 0007 仍然是链上的一环。
SPRINT3_REVISION = "0004_sprint3_exercises"
SPRINT4_REVISION = "0005_sprint4_ai_interactions"
SPRINT5_REVISION = "0006_sprint5_knowledge"
SPRINT6_REVISION = "0007_sprint6_plan_exercise_targets"
# v0.1.2 的 0008 建了 review_items；v0.1.3 的 0009 只建 capstone_submissions。
REVIEW_REVISION = "0008_review_items"
CAPSTONE_REVISION = "0009_capstone_submissions"
# v0.1.11 的 0011 补上 a3/a4 两节 AI 课与 4 道练习；0012 再补 a5/a6 两节与 4 道练习后 head 前移。
CAPSTONE_REVIEW_REVISION = "0010_capstone_review_requires_reviewer"
SPRINT7_REVISION = "0011_sprint7_ai_content"
RAG_REVISION = "0012_sprint8_rag_agent"
# v0.1.13 的 0013 补上 a2 编程实践两节课与 4 道练习：只发 INSERT，head 前移一格。
PRACTICE_REVISION = "0013_sprint9_practice_content"
# v0.1.18 的 0014 给 exercises 加 requirement_labels 并回填 22 题的 124 条中文要求：
# 只发 ADD COLUMN / 一条 CHECK / UPDATE，head 前移一格。
LABELS_REVISION = "0014_sprint10_requirement_labels"
# v0.1.29 / v0.1.30 的 0015 / 0016 只给既有题追加判题规则（print / return），不建表、
# 不加列；v0.1.41 的 0017 再补 a3 / a4 两节核心课与 4 道练习。
PRINT_RULE_REVISION = "0015_sprint11_print_rule"
RETURN_RULE_REVISION = "0016_sprint11_return_rule"
HEAD_REVISION = "0017_sprint12_ai_core_content"
SPRINT2_TABLES = {"lessons", "learning_progress", "study_plan_items"}
SPRINT3_TABLES = {"exercises", "submissions"}

EXPECTED_COLUMNS = {
    "users": {
        "id",
        "display_name",
        "timezone",
        "timezone_source",
        "locale",
        "created_at",
        "updated_at",
    },
    "user_profiles": {
        "user_id",
        "target_track",
        "study_days",
        "daily_minutes",
        "weekly_minutes",
        "onboarding_completed_at",
        "created_at",
        "updated_at",
    },
    "skills": {
        "id",
        "code",
        "name_zh",
        "level",
        "route_code",
        "order_index",
        "description",
        "created_at",
        "updated_at",
    },
    "diagnostic_attempts": {
        "id",
        "user_id",
        "attempt_token",
        "question_set_version",
        "rule_version",
        "answers",
        "domain_scores",
        "total_correct",
        "total_questions",
        "submitted_at",
        "created_at",
    },
    "user_skill_levels": {
        "id",
        "user_id",
        "skill_id",
        "level",
        "evidence_kind",
        "verification_method",
        "evidence_strength",
        "assessment_state",
        "evidence_ref",
        "evidence_count",
        "created_at",
        "updated_at",
    },
}

EXPECTED_CONSTRAINTS = {
    "ck_users_timezone_source",
    "ck_up_target_track",
    "ck_up_daily_minutes",
    "ck_up_study_days_card",
    "ck_up_study_days_vals",
    "ck_skills_level",
    "ck_da_total_correct",
    "ck_da_total_questions",
    "ck_da_total_within",
    "uq_diagnostic_attempts_token",
    "uq_skills_code",
    "ck_usk_level",
    "ck_usk_evidence_kind",
    "ck_usk_verification_method",
    "ck_usk_assessment_state",
    "ck_usk_evidence_count",
    "ck_usk_strength_none_level0",
    "ck_usk_state_level",
}

EXPECTED_INDEXES = {
    "ix_skills_route_order",
    "ix_diagnostic_attempts_user_time",
    "ix_user_skill_levels_user_skill",
}

SKILL_SEED = [
    ("route_a.a1", "Python 基础", 1),
    ("route_a.a2", "编程实践", 2),
    ("route_a.a3", "API", 3),
    ("route_a.a4", "LLM", 4),
    ("route_a.a5", "RAG 与 Agent 基础", 5),
    ("route_a.a6", "简单 AI 项目", 6),
]


async def test_01_alembic_upgrade_head_succeeds_and_reports_head(database_url: str) -> None:
    # head 自 Sprint 2 起是 0003；S1 的 0002 仍是链上已应用的一环。
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    history = subprocess.run(
        [sys.executable, "-m", "alembic", "history"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert history.returncode == 0, history.stderr
    assert f"{SPRINT1_REVISION} -> {REVISION}" in history.stdout
    assert f"{REVISION} -> {SPRINT3_REVISION}" in history.stdout
    assert f"{SPRINT3_REVISION} -> {SPRINT4_REVISION}" in history.stdout
    assert f"{SPRINT4_REVISION} -> {SPRINT5_REVISION}" in history.stdout
    assert f"{SPRINT5_REVISION} -> {SPRINT6_REVISION}" in history.stdout
    assert f"{SPRINT6_REVISION} -> {REVIEW_REVISION}" in history.stdout
    assert f"{REVIEW_REVISION} -> {CAPSTONE_REVISION}" in history.stdout
    assert f"{CAPSTONE_REVISION} -> {CAPSTONE_REVIEW_REVISION}" in history.stdout
    assert f"{CAPSTONE_REVIEW_REVISION} -> {SPRINT7_REVISION}" in history.stdout
    assert f"{SPRINT7_REVISION} -> {RAG_REVISION}" in history.stdout
    assert f"{RAG_REVISION} -> {PRACTICE_REVISION}" in history.stdout
    assert f"{PRACTICE_REVISION} -> {LABELS_REVISION}" in history.stdout
    assert f"{LABELS_REVISION} -> {PRINT_RULE_REVISION}" in history.stdout
    assert f"{PRINT_RULE_REVISION} -> {RETURN_RULE_REVISION}" in history.stdout
    assert f"{RETURN_RULE_REVISION} -> {HEAD_REVISION}" in history.stdout
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

    engine = create_async_engine(database_url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            version = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
    finally:
        await engine.dispose()
    assert version == HEAD_REVISION


async def test_02_five_business_tables_have_the_frozen_structure(
    db_session: AsyncSession,
) -> None:
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
    assert set(EXPECTED_COLUMNS) <= tables
    # 3 张新表由 0003 建立，且不得改动这 5 张表的结构
    assert SPRINT2_TABLES <= tables
    # 2 张新表由 0004 建立，同样不得改动这 5 张表的结构
    assert SPRINT3_TABLES <= tables

    for table, expected in EXPECTED_COLUMNS.items():
        rows = (
            await db_session.execute(
                text(
                    "SELECT column_name, is_nullable, is_generated, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table"
                ),
                {"table": table},
            )
        ).mappings().all()
        assert {row["column_name"] for row in rows} == expected, table

    column_types = {
        (row["table_name"], row["column_name"]): row
        for row in (
            await db_session.execute(
                text(
                    "SELECT table_name, column_name, data_type, udt_name, is_generated "
                    "FROM information_schema.columns WHERE table_schema = 'public'"
                )
            )
        ).mappings()
    }
    assert column_types[("user_profiles", "weekly_minutes")]["is_generated"] == "ALWAYS"
    assert column_types[("user_skill_levels", "evidence_strength")]["is_generated"] == "ALWAYS"
    assert column_types[("user_profiles", "study_days")]["udt_name"] == "_int2"
    assert column_types[("diagnostic_attempts", "answers")]["data_type"] == "jsonb"
    assert column_types[("diagnostic_attempts", "domain_scores")]["data_type"] == "jsonb"
    assert column_types[("users", "created_at")]["data_type"] == "timestamp with time zone"
    assert column_types[("diagnostic_attempts", "attempt_token")]["data_type"] == (
        "character varying"
    )

    constraint_names = set(
        (
            await db_session.execute(
                text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE n.nspname = 'public' AND t.relname IN "
                    "('users','user_profiles','skills','diagnostic_attempts','user_skill_levels')"
                )
            )
        )
        .scalars()
        .all()
    )
    assert EXPECTED_CONSTRAINTS <= constraint_names

    index_names = set(
        (
            await db_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
        )
        .scalars()
        .all()
    )
    assert EXPECTED_INDEXES <= index_names

    triggers = (
        await db_session.execute(
            text(
                "SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE NOT t.tgisinternal AND c.relname = 'user_profiles'"
            )
        )
    ).scalars().all()
    assert "trg_user_profiles_study_days_unique" in triggers


async def test_03_skills_seed_is_exactly_six_domains(db_session: AsyncSession) -> None:
    # 只断言 route_a 的 domain 级种子（skills 是迁移种子，产品使用不会新增行）
    rows = (
        await db_session.execute(
            text(
                "SELECT code, name_zh, level, route_code, order_index "
                "FROM skills WHERE route_code = 'route_a' AND level = 'domain' "
                "ORDER BY order_index"
            )
        )
    ).mappings().all()
    assert [(row["code"], row["name_zh"], row["order_index"]) for row in rows] == SKILL_SEED
    assert {row["level"] for row in rows} == {"domain"}
    assert {row["route_code"] for row in rows} == {"route_a"}
    codes = [row["code"] for row in rows]
    assert len(codes) == len(set(codes)) == 6
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM skills WHERE level <> 'domain'")
        )
    ).scalar_one() == 0


async def test_03b_seeded_identity_rows_exist_for_single_user_mode(
    db_session: AsyncSession,
) -> None:
    # 存在性断言：真实使用会改写档案与时区确认状态，因此只校验"种子身份存在"与生成列不变式
    user = (
        await db_session.execute(
            text(
                "SELECT id, timezone FROM users WHERE display_name = '学习者' "
                "ORDER BY id LIMIT 1"
            )
        )
    ).mappings().first()
    assert user is not None
    assert user["timezone"] == "Asia/Shanghai"
    profile = (
        await db_session.execute(
            text(
                "SELECT study_days, daily_minutes, weekly_minutes, target_track "
                "FROM user_profiles WHERE user_id = :user_id"
            ),
            {"user_id": user["id"]},
        )
    ).mappings().first()
    assert profile is not None
    assert profile["target_track"] == "route_a"
    assert len(profile["study_days"]) >= 1
    assert 15 <= profile["daily_minutes"] <= 480
    # 生成列恒等式：周容量恒为 学习日数 × 每日分钟
    assert profile["weekly_minutes"] == len(profile["study_days"]) * profile["daily_minutes"]


# ---------------------------------------------------------------------------
# v0.1.2: 0008_review_items - 一张表，既有 13 张产品表一行不动
# ---------------------------------------------------------------------------
# 0007 之后存在的全部产品表（alembic_version 由库自己维护，不计入产品表）。
EXISTING_TABLES = (
    "users",
    "user_profiles",
    "skills",
    "diagnostic_attempts",
    "user_skill_levels",
    "lessons",
    "learning_progress",
    "study_plan_items",
    "exercises",
    "submissions",
    "ai_interactions",
    "knowledge_sources",
    "knowledge_chunks",
)
REVIEW_COLUMNS = {
    "id",
    "user_id",
    "exercise_id",
    "source_submission_id",
    "streak",
    "interval_days",
    "next_review_on",
    "last_result",
    "last_reviewed_at",
    "status",
    "created_at",
    "updated_at",
}
REVIEW_NULLABLE = {"source_submission_id", "last_result", "last_reviewed_at"}


async def test_04_review_items_has_the_frozen_structure(db_session: AsyncSession) -> None:
    columns = {
        row["column_name"]: row["is_nullable"]
        for row in (
            await db_session.execute(
                text(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'review_items'"
                )
            )
        ).mappings()
    }
    assert set(columns) == REVIEW_COLUMNS
    assert {name for name, nullable in columns.items() if nullable == "YES"} == REVIEW_NULLABLE

    constraints = {
        row["conname"]: row["contype"]
        for row in (
            await db_session.execute(
                text(
                    "SELECT c.conname, c.contype::text AS contype FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE n.nspname = 'public' AND t.relname = 'review_items'"
                )
            )
        ).mappings()
    }
    checks = {name for name, kind in constraints.items() if kind == "c"}
    assert {
        "ck_review_items_streak",
        "ck_review_items_interval_days",
        "ck_review_items_last_result",
        "ck_review_items_status",
    } <= checks
    # (user_id, exercise_id) 唯一：答错是 upsert，答对是在同一行上推进。
    unique_columns = (
        await db_session.execute(
            text(
                "SELECT array_agg(a.attname ORDER BY a.attname) AS columns "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN unnest(c.conkey) AS k(attnum) ON true "
                "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum "
                "WHERE c.conname = 'uq_review_items_user_exercise'"
            )
        )
    ).scalar_one()
    assert sorted(unique_columns) == ["exercise_id", "user_id"]

    indexes = set(
        (
            await db_session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'review_items'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert "ix_review_items_user_next_review" in indexes

    # 三个外键的删除动作也是冻结口径：用户级联、题目 RESTRICT、来源提交 SET NULL。
    delete_actions = {
        row["column"]: row["confdeltype"]
        for row in (
            await db_session.execute(
                text(
                    "SELECT a.attname AS column, c.confdeltype::text AS confdeltype "
                    "FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[1] "
                    "WHERE c.contype = 'f' AND t.relname = 'review_items'"
                )
            )
        ).mappings()
    }
    assert delete_actions == {
        "user_id": "c",
        "exercise_id": "r",
        "source_submission_id": "n",
    }


async def test_05_upgrade_0008_keeps_every_existing_row(migration_probe) -> None:
    """0007 -> 0008 只多一张空表：既有 13 张产品表逐表行数相等。"""
    async with migration_probe() as probe:
        probe.upgrade(SPRINT6_REVISION)
        await probe.insert_sentinels(EXISTING_TABLES)
        before = await probe.counts(EXISTING_TABLES)
        assert before["users"] >= 1 and before["lessons"] >= 1 and before["exercises"] >= 1

        probe.upgrade(REVIEW_REVISION)

        after = await probe.counts(EXISTING_TABLES)
        assert after == before, {table: (before[table], after[table]) for table in before}
        assert await probe.counts(("review_items",)) == {"review_items": 0}


# ---------------------------------------------------------------------------
# v0.1.3: 0010_capstone_review_requires_reviewer - 一张表，既有 14 张产品表一行不动
# ---------------------------------------------------------------------------
# 0008 之后存在的全部产品表：0009 不得改动其中任何一张的行。
TABLES_BEFORE_0009 = (*EXISTING_TABLES, "review_items")
CAPSTONE_COLUMNS = {
    "id",
    "user_id",
    "title",
    "summary",
    "repo_url",
    "run_instructions",
    "self_checks",
    "readiness_snapshot",
    "status",
    "verdict",
    "reviewer",
    "reviewer_note",
    "submitted_at",
    "reviewed_at",
    "created_at",
    "updated_at",
}
CAPSTONE_NULLABLE = {
    "repo_url",
    "readiness_snapshot",
    "verdict",
    "reviewer",
    "reviewer_note",
    "submitted_at",
    "reviewed_at",
}


async def test_06_capstone_submissions_has_the_frozen_structure(
    db_session: AsyncSession,
) -> None:
    columns = {
        row["column_name"]: row
        for row in (
            await db_session.execute(
                text(
                    "SELECT column_name, is_nullable, data_type, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'capstone_submissions'"
                )
            )
        ).mappings()
    }
    assert set(columns) == CAPSTONE_COLUMNS
    assert {name for name, row in columns.items() if row["is_nullable"] == "YES"} == (
        CAPSTONE_NULLABLE
    )
    # 冻结类型：三段长文本是 text，两个 jsonb，时间戳全是 timestamptz。
    assert columns["title"]["data_type"] == "character varying"
    assert (columns["summary"]["data_type"], columns["run_instructions"]["data_type"]) == (
        "text",
        "text",
    )
    assert (columns["self_checks"]["data_type"], columns["readiness_snapshot"]["data_type"]) == (
        "jsonb",
        "jsonb",
    )
    for name in ("submitted_at", "reviewed_at", "created_at", "updated_at"):
        assert columns[name]["data_type"] == "timestamp with time zone", name
    # 默认值：自检清单是空数组，状态从 draft 开始。
    assert "'[]'::jsonb" in columns["self_checks"]["column_default"]
    assert "'draft'::character varying" in columns["status"]["column_default"]

    constraints = {
        row["conname"]: row["contype"]
        for row in (
            await db_session.execute(
                text(
                    "SELECT c.conname, c.contype::text AS contype FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE n.nspname = 'public' AND t.relname = 'capstone_submissions'"
                )
            )
        ).mappings()
    }
    checks = {name for name, kind in constraints.items() if kind == "c"}
    assert {
        "ck_capstone_submissions_status",
        "ck_capstone_submissions_verdict",
        "ck_capstone_submissions_reviewer",
        "ck_capstone_submissions_reviewed_complete",
    } <= checks

    # 三态与自评都是不可协商的字面量：状态只有三种，结论只有两种，评审者只有 'self'。
    check_definitions = (
        await db_session.execute(
            text(
                "SELECT string_agg(pg_get_constraintdef(oid), ' ') FROM pg_constraint "
                "WHERE conrelid = 'capstone_submissions'::regclass "
                "AND conname LIKE 'ck_capstone_submissions_%'"
            )
        )
    ).scalar_one()
    for literal in ("draft", "submitted", "reviewed", "pass", "needs_work", "self"):
        assert literal in check_definitions, literal

    # 列表与详情的访问路径：(user_id, created_at DESC)。
    index_definitions = {
        row["indexname"]: row["indexdef"]
        for row in (
            await db_session.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'capstone_submissions'"
                )
            )
        ).mappings()
    }
    assert "ix_capstone_submissions_user_created" in index_definitions
    assert "created_at DESC" in index_definitions[
        "ix_capstone_submissions_user_created"
    ]

    # user_id 是 CASCADE：作品是用户私有数据，用户没了它没有独立价值。
    delete_actions = {
        row["column"]: row["confdeltype"]
        for row in (
            await db_session.execute(
                text(
                    "SELECT a.attname AS column, c.confdeltype::text AS confdeltype "
                    "FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[1] "
                    "WHERE c.contype = 'f' AND t.relname = 'capstone_submissions'"
                )
            )
        ).mappings()
    }
    assert delete_actions == {"user_id": "c"}


async def test_07_upgrade_0009_keeps_every_existing_row(migration_probe) -> None:
    """0008 -> 0009 只多一张空表：既有 14 张产品表逐表行数相等。"""
    async with migration_probe() as probe:
        probe.upgrade(REVIEW_REVISION)
        await probe.insert_sentinels(TABLES_BEFORE_0009)
        before = await probe.counts(TABLES_BEFORE_0009)
        assert before["users"] >= 1 and before["lessons"] >= 1 and before["exercises"] >= 1
        # 探针库在 0008 上是全新的：错题本还没有任何行可丢。
        assert before["review_items"] == 0

        # 只升到 0010：0011 会往 lessons / exercises 追加种子行，那是新内容而不是
        # 「丢行」或「改行」，由 tests/test_ai_content.py 单独覆盖。
        probe.upgrade(CAPSTONE_REVIEW_REVISION)

        after = await probe.counts(TABLES_BEFORE_0009)
        assert after == before, {table: (before[table], after[table]) for table in before}
        assert await probe.counts(("capstone_submissions",)) == {"capstone_submissions": 0}
        assert CAPSTONE_REVIEW_REVISION in probe.current()
