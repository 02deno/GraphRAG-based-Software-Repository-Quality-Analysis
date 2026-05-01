"""Central logging configuration for CLI and web (ISO-8601 UTC, levels, file + stderr)."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final


_CONFIGURED: bool = False

_DEFAULT_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Rotate before single files grow too large for editors / mail attachments.
_FILE_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_FILE_BACKUP_COUNT: Final[int] = 5


class _UtcIsoFormatter(logging.Formatter):
    """Format ``record.created`` as UTC ISO-8601 with millisecond precision."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: ARG002
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z"


def _parse_level(name: str) -> int:
    level = getattr(logging, name.upper(), None)
    return int(level) if level is not None else logging.INFO


def _project_root() -> Path:
    """GraphRAG project root (parent of ``src/``)."""
    return Path(__file__).resolve().parent.parent


def _default_log_file_path() -> Path:
    return _project_root() / "logs" / "graphrag.log"


def _env_flag_false(name: str) -> bool:
    val = os.environ.get(name, "").strip().lower()
    return val in ("0", "false", "no", "off")


def configure_standard_logging() -> None:
    """Configure the root logger once: stderr + optional rotating file, UTC timestamps.

    Environment:
        ``GRAPHRAG_LOG_LEVEL``: ``DEBUG``, ``INFO`` (default), ``WARNING``, ``ERROR``.
        ``GRAPHRAG_LOG_FILE``: Override log file path (UTF-8). If unset, uses
            ``<project_root>/logs/graphrag.log`` unless file logging is disabled.
        ``GRAPHRAG_LOG_TO_FILE``: Set to ``0`` / ``false`` / ``off`` to log only to stderr.

    Idempotent: repeated calls are ignored so tests and reloaders do not duplicate handlers.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = _parse_level(os.environ.get("GRAPHRAG_LOG_LEVEL", "INFO"))
    formatter = _UtcIsoFormatter(_DEFAULT_FORMAT)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(stream_handler)

    if not _env_flag_false("GRAPHRAG_LOG_TO_FILE"):
        raw_path = os.environ.get("GRAPHRAG_LOG_FILE", "").strip()
        if raw_path:
            log_path = Path(raw_path).expanduser()
            if not log_path.is_absolute():
                log_path = (_project_root() / log_path).resolve()
        else:
            log_path = _default_log_file_path()

        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=_FILE_MAX_BYTES,
                backupCount=_FILE_BACKUP_COUNT,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as exc:
            # Keep process usable if logs directory is not writable (e.g. read-only deploy).
            sys.stderr.write(f"[graphrag] Could not open log file {log_path}: {exc}\n")

    # Third-party: reduce matplotlib font spam unless debugging the stack.
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    # Werkzeug access lines stay at INFO; our app uses ``src.*`` for business logs.
    logging.getLogger("werkzeug").setLevel(logging.INFO)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger under the ``src.`` hierarchy (call after :func:`configure_standard_logging`)."""
    return logging.getLogger(name)
