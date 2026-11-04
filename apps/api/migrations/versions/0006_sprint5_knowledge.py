"""Sprint 5 knowledge base

Revision ID: 0006_sprint5_knowledge
Revises: 0005_sprint4_ai_interactions
Create Date: 2026-04-01 00:00:00+00:00

Creates exactly two tables - knowledge_sources and knowledge_chunks - and touches
nothing else: 0001-0005 are not modified, the ten existing tables keep their
structure and every row they already hold, and only CREATE statements are issued
(the project contract forbids DROP, DELETE, TRUNCATE and every downgrade path).

Why two tables and not a vector store: the frozen Sprint 5 retrieval is a lexical,
explainable match (content ILIKE + keywords overlap, scored in Python). It needs a
searchable text column and a term array, nothing else - so no dependency is added
and the whole feature works offline.

knowledge_sources is one row per ingested origin. url is UNIQUE because ingestion
is idempotent per URL: the second run of the same page finds this row and compares
content_hash instead of appending a duplicate copy. source_type is a two-value
CHECK on purpose - the whitelist is enforced in code (docs.python.org pages and
repo://lesson/<code> only), and this column records which of the two it was.
status/error_code follow the same rule as ai_interactions: 'failed' always carries
a machine readable code, 'ok' never does, so a failure cannot be read as a success.
content_hash is the sha256 hex of the fetched body (64 characters).

knowledge_chunks is one row per block of one source. UNIQUE(source_id,
chunk_index) is what makes re-ingestion deterministic, and ON DELETE CASCADE means
a chunk can never outlive its source (sources themselves are never deleted here).
keywords is text[] NOT NULL - the array overlap operator (&&) is the candidate
stage of the search, and an empty array is a legitimate value for a chunk whose
text carries no indexable term.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_sprint5_knowledge"
down_revision: str | None = "0005_sprint4_ai_interactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KNOWLEDGE_SOURCES = """
CREATE TABLE knowledge_sources (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  url text NOT NULL CONSTRAINT ck_knowledge_sources_url
    CHECK (length(btrim(url)) > 0 AND length(url) <= 2048),
  title text NOT NULL CONSTRAINT ck_knowledge_sources_title
    CHECK (length(btrim(title)) > 0),
  source_type varchar(16) NOT NULL CONSTRAINT ck_knowledge_sources_source_type
    CHECK (source_type IN ('official_doc', 'repo_lesson')),
  version_label varchar(64) NOT NULL DEFAULT '',
  fetched_at timestamptz NOT NULL DEFAULT now(),
  content_hash varchar(64) NOT NULL DEFAULT '',
  status varchar(16) NOT NULL CONSTRAINT ck_knowledge_sources_status
    CHECK (status IN ('ok', 'failed')),
  error_code varchar(64) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  -- An ok source has no error; a failed source always names its reason.
  CONSTRAINT ck_knowledge_sources_error_code
    CHECK ((status = 'ok') = (error_code IS NULL)),
  -- One row per origin: this is the key ingestion is idempotent on.
  CONSTRAINT uq_knowledge_sources_url UNIQUE (url)
)
"""

KNOWLEDGE_CHUNKS = """
CREATE TABLE knowledge_chunks (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id bigint NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL CONSTRAINT ck_knowledge_chunks_chunk_index
    CHECK (chunk_index >= 0),
  heading text NULL,
  -- The 1200 character ceiling is the frozen chunk size, enforced by the database
  -- as well so no caller can store a block the search would have to truncate.
  content text NOT NULL CONSTRAINT ck_knowledge_chunks_content
    CHECK (length(btrim(content)) > 0 AND length(content) <= 1200),
  keywords text[] NOT NULL DEFAULT '{}'::text[],
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_knowledge_chunks_source_index UNIQUE (source_id, chunk_index)
)
"""

INDEXES = (
    # Candidate stage of the search is keywords && terms; a GIN index keeps that
    # array overlap off a sequential scan once the corpus grows.
    "CREATE INDEX ix_knowledge_chunks_keywords "
    "ON knowledge_chunks USING gin (keywords)",
)


def upgrade() -> None:
    """Create the two Sprint 5 tables."""
    op.execute(KNOWLEDGE_SOURCES)
    op.execute(KNOWLEDGE_CHUNKS)
    for statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0006_sprint5_knowledge 不支持降级：Sprint 5 契约禁止 DROP/DELETE 类语句"
    )
