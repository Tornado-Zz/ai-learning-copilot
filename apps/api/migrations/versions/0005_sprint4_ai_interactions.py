"""Sprint 4 AI tutor interaction log

Revision ID: 0005_sprint4_ai_interactions
Revises: 0004_sprint3_exercises
Create Date: 2026-03-15 00:00:00+00:00

Creates exactly one table - ai_interactions - and touches nothing else: 0001-0004
are not modified, the nine existing tables keep their structure and every row they
already hold, and only CREATE statements are issued (the project contract forbids
DROP, DELETE, TRUNCATE and every downgrade path).

Why a row per call, including the failures: the Sprint 4 cost question is "how
many tokens did the tutor spend, and how often did it fail", and a log that only
stores successes answers neither half. This is why status is a five-value CHECK
('ok', 'error', 'timeout', 'unavailable', 'quota'): the two refusals that never
reach the upstream provider ('unavailable' = no key configured, 'quota' = daily
token budget spent) are recorded with prompt_tokens = completion_tokens = 0, which
is exactly the evidence that no upstream request was made.

Scalar columns cannot carry the API key: the key lives only in the outbound
Authorization header and there is no column that would hold it.

answer is NULL for every non-ok row by constraint, so a failed call cannot be
mistaken for an answered one; ck_ai_interactions_status_answer makes that a
database rule rather than a service convention. error_code is required for a
non-ok row for the same reason: a failure without a code is not traceable.

lesson_id / exercise_id are nullable and ON DELETE SET NULL: a context link is
provenance, not curriculum membership, so archiving a lesson must not delete the
spend history. user_id cascades like every other user-owned row.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_sprint4_ai_interactions"
down_revision: str | None = "0004_sprint3_exercises"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_INTERACTIONS = """
CREATE TABLE ai_interactions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_id bigint NULL REFERENCES lessons(id) ON DELETE SET NULL,
  exercise_id bigint NULL REFERENCES exercises(id) ON DELETE SET NULL,
  question text NOT NULL CONSTRAINT ck_ai_interactions_question
    CHECK (length(btrim(question)) > 0 AND length(question) <= 2000),
  answer text NULL,
  assistance_level varchar(16) NOT NULL CONSTRAINT ck_ai_interactions_assistance_level
    CHECK (assistance_level IN ('none', 'hint', 'partial_code', 'full_answer')),
  model varchar(64) NOT NULL CONSTRAINT ck_ai_interactions_model
    CHECK (length(btrim(model)) > 0),
  prompt_tokens integer NOT NULL DEFAULT 0 CONSTRAINT ck_ai_interactions_prompt_tokens
    CHECK (prompt_tokens >= 0),
  completion_tokens integer NOT NULL DEFAULT 0
    CONSTRAINT ck_ai_interactions_completion_tokens CHECK (completion_tokens >= 0),
  latency_ms integer NOT NULL DEFAULT 0 CONSTRAINT ck_ai_interactions_latency_ms
    CHECK (latency_ms >= 0),
  status varchar(16) NOT NULL CONSTRAINT ck_ai_interactions_status
    CHECK (status IN ('ok', 'error', 'timeout', 'unavailable', 'quota')),
  error_code varchar(64) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  -- ok <=> an answer exists; a failed call can never be read as an answered one.
  CONSTRAINT ck_ai_interactions_status_answer
    CHECK ((status = 'ok') = (answer IS NOT NULL)),
  -- A recorded failure always carries the machine readable reason.
  CONSTRAINT ck_ai_interactions_error_code
    CHECK ((status = 'ok') = (error_code IS NULL))
)
"""

INDEXES = (
    # Serves both the reverse-chronological list and the UTC-day token sum: one
    # index, two reads, no scan of another learner's rows.
    "CREATE INDEX ix_ai_interactions_user_created "
    "ON ai_interactions (user_id, created_at DESC, id DESC)",
)


def upgrade() -> None:
    """Create the single Sprint 4 table."""
    op.execute(AI_INTERACTIONS)
    for statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0005_sprint4_ai_interactions 不支持降级：Sprint 4 契约禁止 DROP/DELETE 类语句"
    )
