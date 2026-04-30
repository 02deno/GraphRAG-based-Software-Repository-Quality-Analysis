from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set


def collect_python_files(repo_path: Path, exclude_dirs: Set[str] | None = None) -> List[Path]:
    """Collect all Python files under the repository path, excluding named folders."""
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
    """Convert a repository file path into a dotted Python module name."""
    relative = file_path.relative_to(repo_path)
    parts = list(relative.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def module_aliases_from_path(file_path: Path, repo_path: Path) -> Set[str]:
    """Generate possible module aliases for repository files for import resolution."""
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
