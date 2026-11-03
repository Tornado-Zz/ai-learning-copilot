"""Standard library logging, single stdout stream, one line per record."""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

_CONFIGURE_HANDLER_ONCE = False


def configure_logging(level: str = "INFO") -> None:
    """Install one stdout handler on the root logger and apply LOG_LEVEL."""
    global _CONFIGURE_HANDLER_ONCE

    resolved_level = logging.getLevelName(str(level).strip().upper())
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    root = logging.getLogger()
    if not _CONFIGURE_HANDLER_ONCE:
        for existing in list(root.handlers):
            root.removeHandler(existing)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(handler)
        _CONFIGURE_HANDLER_ONCE = True
    root.setLevel(resolved_level)

    # Uvicorn installs its own handlers; route them through the root handler instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        for existing in list(logger.handlers):
            logger.removeHandler(existing)
        logger.propagate = True
