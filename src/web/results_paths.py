"""Resolve on-disk web analysis run directories under ``results/`` safely."""

from __future__ import annotations

import re
from pathlib import Path


_RUN_DIR_PATTERN = re.compile(r"^web_analysis_[^\u0000/\u005C]+$")
_VISUAL_SUFFIX = ".png"


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
    if ".." in run_dir:
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
    if not filename or "/" in filename or "\\" in filename or "\x00" in filename:
        return False
    if filename in (".", "..") or ".." in filename:
        return False
    candidate = Path(filename)
    if candidate.name != filename:
        return False
    if len(filename) > 240:
        return False
    if not filename.lower().endswith(_VISUAL_SUFFIX):
        return False
    stem = filename[: -len(_VISUAL_SUFFIX)]
    if not stem or stem in (".", ".."):
        return False
    return True


def resolve_visual_png_file(visuals_dir: Path, filename: str) -> Path | None:
    """Return a resolved PNG path under *visuals_dir*, or ``None`` if missing or unsafe.

    Performs a case-insensitive fallback match for Windows / case-only differences.
    """
    if not is_safe_visual_png_filename(filename):
        return None
    try:
        visuals_resolved = visuals_dir.resolve()
    except OSError:
        return None
    direct = (visuals_dir / filename).resolve()
    try:
        direct.relative_to(visuals_resolved)
    except ValueError:
        return None
    if direct.is_file():
        return direct
    target_lower = filename.lower()
    try:
        for candidate in visuals_dir.iterdir():
            if not candidate.is_file():
                continue
            if candidate.name.lower() == target_lower:
                resolved = candidate.resolve()
                try:
                    resolved.relative_to(visuals_resolved)
                except ValueError:
                    continue
                return resolved
    except OSError:
        return None
    return None
