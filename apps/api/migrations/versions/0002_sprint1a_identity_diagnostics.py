"""Sprint 1A identity and diagnostics

Revision ID: 0002_sprint1a_identity_diagnostics
Revises: 0001
Create Date: 2026-02-01 00:00:00+00:00

Creates the five Sprint 1 tables (users, user_profiles, skills,
diagnostic_attempts, user_skill_levels), the study_days de-duplication trigger
and the identity/skill seed rows.

Only CREATE / INSERT statements are issued: the Sprint 1 contract forbids any
DROP, DELETE or downgrade path, so no destructive statement exists here.
Constraint names follow SPRINT1A_CONTRACT.md 7.2 (the frozen DDL form).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_sprint1a_identity_diagnostics"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# alembic's default alembic_version.version_num is varchar(32) while the frozen
# revision id is 34 characters: widen the column (non-destructive) before the
# version bump for this revision is written.
WIDEN_VERSION_TABLE = """
ALTER TABLE IF EXISTS alembic_version ALTER COLUMN version_num TYPE varchar(64)
"""

USERS = """
CREATE TABLE users (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  display_name varchar(80) NOT NULL,
  timezone varchar(64) NOT NULL DEFAULT 'Asia/Shanghai',
  timezone_source varchar(16) NOT NULL DEFAULT 'default'
    CONSTRAINT ck_users_timezone_source CHECK (timezone_source IN ('default', 'user_confirmed')),
  locale varchar(16) NOT NULL DEFAULT 'zh-CN',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
)
"""

USER_PROFILES = """
CREATE TABLE user_profiles (
  user_id bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  target_track varchar(32) NOT NULL DEFAULT 'route_a'
    CONSTRAINT ck_up_target_track CHECK (target_track IN ('route_a')),
  study_days smallint[] NOT NULL DEFAULT '{1,3,5}',
  daily_minutes smallint NOT NULL DEFAULT 60
    CONSTRAINT ck_up_daily_minutes CHECK (daily_minutes BETWEEN 15 AND 480),
  weekly_minutes smallint GENERATED ALWAYS AS (cardinality(study_days) * daily_minutes) STORED,
  onboarding_completed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_up_study_days_card CHECK (cardinality(study_days) BETWEEN 1 AND 7),
  CONSTRAINT ck_up_study_days_vals CHECK (study_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[])
)
"""

STUDY_DAYS_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_up_study_days_unique() RETURNS trigger AS $$
BEGIN
  IF cardinality(NEW.study_days) <> (SELECT count(DISTINCT d) FROM unnest(NEW.study_days) AS d) THEN
    RAISE EXCEPTION 'study_days 不允许重复元素: %', NEW.study_days USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql
"""

STUDY_DAYS_TRIGGER = """
CREATE TRIGGER trg_user_profiles_study_days_unique BEFORE INSERT OR UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION fn_up_study_days_unique()
"""

SKILLS = """
CREATE TABLE skills (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code varchar(64) NOT NULL CONSTRAINT uq_skills_code UNIQUE,
  name_zh varchar(80) NOT NULL,
  level varchar(16) NOT NULL DEFAULT 'domain'
    CONSTRAINT ck_skills_level CHECK (level IN ('domain', 'topic')),
  route_code varchar(32) NOT NULL DEFAULT 'route_a',
  order_index smallint NOT NULL,
  description text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
)
"""

DIAGNOSTIC_ATTEMPTS = """
CREATE TABLE diagnostic_attempts (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  attempt_token varchar(64) NOT NULL,
  question_set_version varchar(16) NOT NULL,
  rule_version varchar(16) NOT NULL,
  answers jsonb NOT NULL,
  domain_scores jsonb NOT NULL,
  total_correct smallint NOT NULL CONSTRAINT ck_da_total_correct CHECK (total_correct >= 0),
  total_questions smallint NOT NULL CONSTRAINT ck_da_total_questions CHECK (total_questions > 0),
  submitted_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_diagnostic_attempts_token UNIQUE (user_id, attempt_token),
  CONSTRAINT ck_da_total_within CHECK (total_correct <= total_questions)
)
"""

USER_SKILL_LEVELS = """
CREATE TABLE user_skill_levels (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  skill_id bigint NOT NULL REFERENCES skills(id) ON DELETE RESTRICT,
  level smallint NOT NULL CONSTRAINT ck_usk_level CHECK (level BETWEEN 0 AND 4),
  evidence_kind varchar(16) NOT NULL
    CONSTRAINT ck_usk_evidence_kind
    CHECK (evidence_kind IN ('self_assessment', 'diagnostic', 'practice', 'transfer')),
  verification_method varchar(16) NOT NULL
    CONSTRAINT ck_usk_verification_method
    CHECK (verification_method IN ('none', 'self_report', 'static_rule', 'runtime_test', 'manual_review')),
  evidence_strength varchar(16) GENERATED ALWAYS AS (CASE
    WHEN verification_method IN ('runtime_test', 'manual_review') THEN 'verified'
    WHEN verification_method = 'static_rule' THEN 'assessed'
    WHEN verification_method = 'self_report' THEN 'self_reported'
    ELSE 'none' END) STORED,
  assessment_state varchar(24) NOT NULL
    CONSTRAINT ck_usk_assessment_state
    CHECK (assessment_state IN ('unassessed', 'assessed_below_threshold', 'established', 'requested_verification')),
  evidence_ref varchar(200) NULL,
  evidence_count smallint NOT NULL DEFAULT 0
    CONSTRAINT ck_usk_evidence_count CHECK (evidence_count >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_usk_strength_none_level0 CHECK (evidence_strength <> 'none' OR level = 0),
  CONSTRAINT ck_usk_state_level CHECK (
    (assessment_state IN ('unassessed', 'assessed_below_threshold', 'requested_verification') AND level = 0)
    OR (assessment_state = 'established' AND level BETWEEN 1 AND 4)
  )
)
"""

INDEXES = (
    "CREATE INDEX ix_skills_route_order ON skills (route_code, order_index)",
    "CREATE INDEX ix_diagnostic_attempts_user_time ON diagnostic_attempts (user_id, submitted_at DESC)",
    "CREATE INDEX ix_user_skill_levels_user_skill ON user_skill_levels (user_id, skill_id, created_at DESC)",
)

# seeds: idempotent so a partially applied revision can be re-run safely
SEED_USER = """
INSERT INTO users (display_name, timezone)
SELECT '学习者', 'Asia/Shanghai' WHERE NOT EXISTS (SELECT 1 FROM users)
"""

SEED_PROFILE = """
INSERT INTO user_profiles (user_id, study_days, daily_minutes)
SELECT id, '{1,3,5}'::smallint[], 60 FROM users ORDER BY id LIMIT 1
ON CONFLICT (user_id) DO NOTHING
"""

SEED_SKILLS = """
INSERT INTO skills (code, name_zh, level, route_code, order_index, description) VALUES
  ('route_a.a1', 'Python 基础', 'domain', 'route_a', 1, '能写出含函数、列表、字典、文件读写的脚本'),
  ('route_a.a2', '编程实践', 'domain', 'route_a', 2, '能把需求拆成函数，能读懂报错并自行定位'),
  ('route_a.a3', 'API', 'domain', 'route_a', 3, '能用 requests 调用第三方 HTTP API 并处理错误'),
  ('route_a.a4', 'LLM', 'domain', 'route_a', 4, '理解提示词、上下文、token、流式返回'),
  ('route_a.a5', 'RAG 与 Agent 基础', 'domain', 'route_a', 5, '能把文档切分、检索、拼进提示并解释流程'),
  ('route_a.a6', '简单 AI 项目', 'domain', 'route_a', 6, '交付 1 个可运行、可展示的 AI 应用')
ON CONFLICT (code) DO NOTHING
"""


def upgrade() -> None:
    """Create the five Sprint 1 tables and their seed rows."""
    for statement in (
        WIDEN_VERSION_TABLE,
        USERS,
        USER_PROFILES,
        STUDY_DAYS_FUNCTION,
        STUDY_DAYS_TRIGGER,
        SKILLS,
        DIAGNOSTIC_ATTEMPTS,
        USER_SKILL_LEVELS,
        *INDEXES,
        SEED_USER,
        SEED_PROFILE,
        SEED_SKILLS,
    ):
        op.execute(statement)


def downgrade() -> None:
    """No downgrade path: the Sprint 1 contract forbids every destructive statement."""
    raise RuntimeError(
        "0002_sprint1a_identity_diagnostics 不支持降级：Sprint 1 契约禁止 DROP/DELETE 类语句"
    )
