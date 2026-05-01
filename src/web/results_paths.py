"""Resolve on-disk web analysis run directories under ``results/`` safely."""

from __future__ import annotations

import re
from pathlib import Path


_RUN_DIR_PATTERN = re.compile(r"^web_analysis_[a-z0-9_.-]+$", re.IGNORECASE)
_VISUAL_FILE_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+\.png$")


def safe_resolve_results_run_dir(run_dir: str, *, results_root: Path | None = None) -> Path | None:
    """Return a resolved ``Path`` to ``results/<run_dir>`` if it exists and is safe.

    Args:
        run_dir: Basename only (no slashes), e.g. ``web_analysis_myrepo_20260501_120000``.
        results_root: Optional ``results`` directory (defaults to ``Path('results')``).

    Returns:
        Resolved directory, or ``None`` when invalid or outside ``results/``.
    """
    if not run_dir or "/" in run_dir or "\\" in run_dir or run_dir in (".", ".."):
        return None
    if not _RUN_DIR_PATTERN.fullmatch(run_dir.strip()):
        return None
    base = results_root if results_root is not None else Path("results")
    try:
        target = (base / run_dir.strip()).resolve()
        results_abs = base.resolve()
    except OSError:
        return None
    try:
        target.relative_to(results_abs)
    except ValueError:
        return None
    if not target.is_dir():
        return None
    return target


def is_safe_visual_png_filename(filename: str) -> bool:
    """Return True if *filename* is a single-segment PNG name safe to serve."""
    if not filename or "/" in filename or "\\" in filename:
        return False
    return bool(_VISUAL_FILE_PATTERN.fullmatch(filename))
