"""Flask and upload configuration (environment overrides where appropriate)."""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Return GraphRAG project root (directory containing ``src/`` and ``templates/``)."""
    return Path(__file__).resolve().parent.parent.parent


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
