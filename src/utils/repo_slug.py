"""Sanitize repository identifiers for filesystem paths (temp dirs, results folders)."""

from __future__ import annotations

import re
from pathlib import Path


def filesystem_slug(label: str, max_len: int = 48) -> str:
    """Turn an arbitrary label into a single path segment safe on common filesystems.

    Args:
        label: Raw name (e.g. ZIP stem, ``owner_repo`` fragment, directory basename).
        max_len: Maximum length of the returned slug (truncated on the right).

    Returns:
        Non-empty slug; falls back to ``repo`` when nothing usable remains.
    """
    text = (label or "").strip().lower()
    if not text:
        return "repo"
    text = text.replace("\\", "_").replace("/", "_")
    text = re.sub(r"[^\w\-.]+", "_", text, flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("._-")
    if not text:
        return "repo"
    return text[:max_len]


def slug_from_github_clone_url(url: str, max_len: int = 56) -> str:
    """Derive ``owner_repo`` style slug from an HTTPS or SSH GitHub clone URL.

    Args:
        url: ``https://github.com/org/name`` or ``git@github.com:org/name.git``.
        max_len: Passed to :func:`filesystem_slug`.

    Returns:
        Sanitized slug such as ``fastapi_full-stack-fastapi-template``.
    """
    u = url.strip().rstrip("/")
    if u.startswith("git@github.com:"):
        rest = u.split(":", 1)[1]
    elif "github.com/" in u:
        rest = u.split("github.com/", 1)[1]
    else:
        return filesystem_slug("repo", max_len=max_len)
    rest = rest.removesuffix(".git").strip("/")
    parts = [p for p in rest.split("/") if p]
    if len(parts) >= 2:
        combined = f"{parts[0]}_{parts[1]}"
    elif len(parts) == 1:
        combined = parts[0]
    else:
        combined = "repo"
    return filesystem_slug(combined, max_len=max_len)


def slug_from_local_repo_path(repo_path: str, max_len: int = 48) -> str:
    """Use the last path segment of a local repository root as the slug."""
    return filesystem_slug(Path(repo_path).name, max_len=max_len)
