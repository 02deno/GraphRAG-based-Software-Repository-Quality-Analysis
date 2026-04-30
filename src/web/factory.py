"""Application factory for the Flask web app."""

from __future__ import annotations

import os

from flask import Flask

from src.web.blueprints.web import web_bp
from src.web.config import get_project_root, load_flask_config
from src.web.handlers.repository_handler import RepositoryHandler
from src.web.services.analysis_service import AnalysisService


def create_app() -> Flask:
    """Create and configure the Flask application with blueprints and shared services.

    Services are stored on ``app.extensions`` under ``repo_handler`` and
    ``analysis_service`` so routes stay free of module-level globals.

    Returns:
        A fully wired :class:`flask.Flask` instance (same object ``app`` as in ``app.py``).
    """
    project_root = get_project_root()
    app = Flask(__name__, template_folder=str(project_root / "templates"))
    app.config.from_mapping(**load_flask_config())
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.extensions["repo_handler"] = RepositoryHandler(app.config["UPLOAD_FOLDER"])
    app.extensions["analysis_service"] = AnalysisService()
    app.register_blueprint(web_bp)
    return app
