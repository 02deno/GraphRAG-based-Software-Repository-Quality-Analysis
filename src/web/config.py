"""Flask and upload configuration (environment overrides where appropriate)."""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Return GraphRAG project root (directory containing ``src/`` and ``templates/``)."""
    return Path(__file__).resolve().parent.parent.parent


def load_project_dotenv() -> bool:
    """Load project-root ``.env`` into ``os.environ``.

    First pass uses ``override=False`` so values already exported in the shell
    (CI, Windows user environment, IDE-integrated terminals) keep precedence.

    If ``GRAPHRAG_DOTENV_OVERRIDE`` is truthy after that pass — set it in ``.env``
    or export it once in the shell — a second pass loads the same file with
    ``override=True`` so ``GRAPHRAG_OPENAI_BASE_URL`` and other keys from ``.env``
    replace inherited variables (typical fix when a profile pins local Ollama).

    Returns:
        True when the second ``override=True`` pass ran.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    env_path = get_project_root() / ".env"
    if not env_path.is_file():
        return False
    load_dotenv(env_path, override=False)
    flag = os.environ.get("GRAPHRAG_DOTENV_OVERRIDE", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        load_dotenv(env_path, override=True)
        return True
    return False


def load_flask_config() -> dict[str, object]:
    """Build Flask ``app.config`` defaults for the web application.

    Returns:
        Mapping suitable for ``app.config.from_mapping(**...)``.
    """
    secret = os.environ.get("FLASK_SECRET_KEY", "graphrag-secret-key")
    return {
        "SECRET_KEY": secret,
        "MAX_CONTENT_LENGTH": 100 * 1024 * 1024,
        "UPLOAD_FOLDER": "temp_uploads",
    }
