"""Manual knowledge refresh (Sprint 5): ``uv run python -m app.cli.ingest``.

The CLI is the operator path, not a second implementation: it builds the same
KnowledgeFetcher, calls the same pipeline.ingest and therefore obeys the same
docs.python.org whitelist. Two extra switches keep it safe to run by hand:

* --dry-run validates the whitelist and prints the targets without fetching a page
  or writing a row, so the whitelist can be inspected on a machine with no network;
* --urls narrows the run to explicit URLs (still whitelisted) instead of the
  configured defaults plus every repo lesson.

KNOWLEDGE_INGEST_ENABLED only gates the HTTP endpoint. The CLI does not need it -
and prints a warning when it is off, because then the API cannot be used to
refresh the base and this command is the only way in.

Exit code: 0 when every source succeeded (or was skipped), 1 when at least one
source failed, so a scheduled run can be observed by its exit status.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Sequence

from app.core.config import get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.logging import configure_logging
from app.services.knowledge import DEFAULT_FETCH_TIMEOUT_SECONDS, HttpxFetcher
from app.services.knowledge import pipeline as knowledge


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.ingest",
        description="刷新知识库：默认入库 KNOWLEDGE_DOC_URLS 与仓库内全部课程，按内容 hash 幂等跳过",
    )
    parser.add_argument(
        "--urls",
        default="",
        help="逗号分隔的文档 URL（仍受 docs.python.org 白名单约束）；给了就只处理这些来源",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只做白名单校验并打印目标来源，不抓取、不写库",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_FETCH_TIMEOUT_SECONDS,
        help=f"单次抓取超时秒数（默认 {DEFAULT_FETCH_TIMEOUT_SECONDS:g}）",
    )
    return parser


def _urls(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _dry_run(urls: Sequence[str]) -> int:
    doc_urls, lesson_codes, rejected = knowledge.split_targets(urls or None)
    print("dry-run: 不抓取、不写库")
    for url in doc_urls:
        print(f"  doc      {url}")
    for code in lesson_codes:
        print(f"  lesson   {knowledge.repo_lesson_url(code)}")
    if not urls:
        print("  lesson   repo://lesson/<全部课程>（默认来源，运行时按 lessons 表逐条刷新）")
    for item in rejected:
        print(f"  rejected {item['url']} error_code={item['error_code']}")
    lessons = str(len(lesson_codes)) if urls else "all"
    print(f"targets: docs={len(doc_urls)} lessons={lessons} rejected={len(rejected)}")
    return 1 if rejected else 0


async def _run(urls: Sequence[str], timeout: float) -> int:
    fetcher = HttpxFetcher(timeout_seconds=timeout)
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            summary = await knowledge.ingest(session, urls=urls or None, fetcher=fetcher)
    finally:
        await dispose_engine()

    for item in summary["results"]:
        detail = item.get("error_code") or ("skipped" if item["skipped"] else "ok")
        print(
            f"{item['status']:6} chunks_added={item['chunks_added']:<3} "
            f"{item['url']} ({detail})"
        )
    print(f"sources_total={summary['sources_total']} chunks_total={summary['chunks_total']}")
    failed = [item for item in summary["results"] if item["status"] == "failed"]
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    settings = get_settings()
    configure_logging(settings.log_level)
    urls = _urls(args.urls)
    if not settings.knowledge_ingest_enabled:
        print(
            "提示：KNOWLEDGE_INGEST_ENABLED=false，HTTP 入库端点仍返回 403；",
            "本次命令行刷新不受影响。",
            file=sys.stderr,
        )
    if args.dry_run:
        return _dry_run(urls)
    return asyncio.run(_run(urls, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
