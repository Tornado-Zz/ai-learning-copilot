"""Sprint 16: a research column - tech news and papers, with AI key-point extraction.

Revision ID: 0021_sprint16_news_items
Revises: 0020_sprint15_py_strings_files
Create Date: 2026-11-07 00:00:00+00:00

Why a new table instead of reusing knowledge_sources:

knowledge_* is a read-only SNAPSHOT of documentation used to ground answers - every
chunk is embedded text and the ingest path is opt-in and offline-by-default. The
research column is a different thing: it stores feed entries (title + link + excerpt)
and the AI's reading of them, so the learner can open one, read the key points, and
ask the tutor about it. Mixing the two would make 'where did this claim come from'
ambiguous, which is the one thing the product refuses to be ambiguous about.

Rows are deduplicated by url, because every source re-publishes the same entry on
each refresh: ON CONFLICT (url) DO NOTHING keeps the AI analysis already paid for.

ai_status keeps the three honest states this product uses everywhere: pending (not
analysed yet), ok, error, plus unavailable when no key is configured. Nothing here
is ever reported as analysed when it was not.

Nothing existing is touched: no column changes, no data deletes, no downgrade path
(the project contract forbids DROP/DELETE).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_sprint16_news_items"
down_revision: str | None = "0020_sprint15_py_strings_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE news_items (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_key varchar(32) NOT NULL,
            source_kind varchar(16) NOT NULL,
            title text NOT NULL,
            url text NOT NULL,
            excerpt text NOT NULL DEFAULT '',
            published_at timestamp with time zone,
            fetched_at timestamp with time zone NOT NULL DEFAULT now(),
            ai_status varchar(16) NOT NULL DEFAULT 'pending',
            ai_summary text,
            ai_key_points jsonb NOT NULL DEFAULT '[]'::jsonb,
            ai_model varchar(64),
            ai_tokens integer,
            ai_updated_at timestamp with time zone,
            CONSTRAINT uq_news_items_url UNIQUE (url),
            CONSTRAINT ck_news_items_ai_status CHECK (
                ai_status IN ('pending', 'ok', 'error', 'unavailable')
            ),
            CONSTRAINT ck_news_items_key_points CHECK (jsonb_typeof(ai_key_points) = 'array')
        )
        """,
    )
    op.execute(
        "CREATE INDEX ix_news_items_published ON news_items (published_at DESC NULLS LAST, id DESC)"
    )
    op.execute('CREATE INDEX ix_news_items_source ON news_items (source_key, published_at DESC)')


def downgrade() -> None:
    raise RuntimeError("0021 is not reversible: the project contract forbids DROP")