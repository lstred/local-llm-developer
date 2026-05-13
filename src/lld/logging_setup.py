"""Centralised structured logging.

The platform writes both:
    * human-readable lines to the console (rich-formatted)
    * line-delimited JSON to ``state/logs/orchestrator.log`` for durable audit

A per-job log is also written by the orchestrator into the project workspace
(`<project>/handoffs/_log.jsonl`) so that resuming or debugging a run never
requires the central log.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.logging import RichHandler


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Attach any structured "extra" passed via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


_CONFIGURED = False


def configure_logging(level: str = "INFO", log_file: Path | None = None,
                      json_console: bool = False) -> None:
    """Idempotently configure root logging."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level.upper())
    # Wipe pre-existing handlers (uvicorn, etc. may have added some).
    for h in list(root.handlers):
        root.removeHandler(h)

    # Console
    if json_console:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(_JsonFormatter())
    else:
        ch = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
    root.addHandler(ch)

    # File
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(_JsonFormatter())
        root.addHandler(fh)

    # Quiet noisy libraries
    for noisy in ("httpx", "httpcore", "asyncio", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
