"""Knowledge base (Sprint 5): whitelisted ingest plus explainable lexical retrieval.

Two modules, one surface:

* pipeline     - the whitelist and the injectable fetcher, the HTML parser, the
                 chunker, the search and the ingest orchestration.
* this package - re-exports, so callers write `from app.services.knowledge import
                 pipeline, HttpxFetcher` and never depend on internal names.

Import the fetcher as a value (HttpxFetcher in production, a fake under test) and
pass it in: that seam is what keeps the test suite off the network.
"""

from __future__ import annotations

from app.services.knowledge import pipeline
from app.services.knowledge.pipeline import (
    ALLOWED_DOC_HOST,
    DEFAULT_FETCH_TIMEOUT_SECONDS,
    ERROR_BLOCKED_HOST,
    SOURCE_TYPE_OFFICIAL_DOC,
    SOURCE_TYPE_REPO_LESSON,
    FetchResult,
    HttpxFetcher,
    KnowledgeFetcher,
    KnowledgeUrlError,
    classify_url,
    is_allowed_doc_host,
    is_allowed_doc_url,
    lesson_code_from_repo_url,
    repo_lesson_url,
    validate_doc_url,
)

__all__ = [
    "ALLOWED_DOC_HOST",
    "DEFAULT_FETCH_TIMEOUT_SECONDS",
    "ERROR_BLOCKED_HOST",
    "FetchResult",
    "HttpxFetcher",
    "KnowledgeFetcher",
    "KnowledgeUrlError",
    "SOURCE_TYPE_OFFICIAL_DOC",
    "SOURCE_TYPE_REPO_LESSON",
    "classify_url",
    "is_allowed_doc_host",
    "is_allowed_doc_url",
    "lesson_code_from_repo_url",
    "pipeline",
    "repo_lesson_url",
    "validate_doc_url",
]
