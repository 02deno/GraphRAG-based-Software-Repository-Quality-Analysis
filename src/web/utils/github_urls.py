"""Detect GitHub URLs suitable for ``git clone``."""

from __future__ import annotations


def is_github_clone_url(url: str) -> bool:
    """Return True if *url* looks like an https or SSH GitHub repository URL.

    Args:
        url: Non-empty trimmed URL string.

    Returns:
        True when the host is GitHub in a form accepted by the upload handler.
    """
    return url.startswith("https://github.com/") or url.startswith("git@github.com:")
