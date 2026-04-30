from __future__ import annotations

from pathlib import Path
from typing import List, Set


def collect_python_files(repo_path: Path, exclude_dirs: Set[str] | None = None) -> List[Path]:
    """List every ``*.py`` file under *repo_path*, skipping configured directory segments.

    Args:
        repo_path: Repository root to scan recursively.
        exclude_dirs: Directory name fragments (case-insensitive) to skip when any
            path component matches (e.g. ``venv``, ``__pycache__``).

    Returns:
        Sorted list of absolute-or-repo-relative paths to Python source files.
    """
    if exclude_dirs is None:
        exclude_dirs = set()
    exclude_dirs = {directory.lower() for directory in exclude_dirs}

    python_files: List[Path] = []
    for path in repo_path.rglob("*.py"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo_path).parts
        if any(part.lower() in exclude_dirs for part in rel_parts):
            continue
        python_files.append(path)
    return python_files


def module_name_from_path(file_path: Path, repo_path: Path) -> str:
    """Map a file path to the dotted module name relative to *repo_path*.

    Args:
        file_path: Absolute or repo-relative path to ``*.py``.
        repo_path: Repository root used as package root.

    Returns:
        Dotted module string (``__init__`` segments are omitted from the tail).
    """
    relative = file_path.relative_to(repo_path)
    parts = list(relative.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def module_aliases_from_path(file_path: Path, repo_path: Path) -> Set[str]:
    """Produce dotted aliases that might resolve imports to this file.

    For nested packages, every suffix of the module path is included so that
    imports like ``from pkg.sub import mod`` can match internal heuristics.

    Args:
        file_path: Path to a Python module under *repo_path*.
        repo_path: Repository root.

    Returns:
        Non-empty set of possible import strings for this file.
    """
    relative = file_path.relative_to(repo_path)
    parts = list(relative.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    aliases: Set[str] = set()
    for index in range(len(parts)):
        alias = ".".join(parts[index:])
        if alias:
            aliases.add(alias)
    return aliases
