"""Application factory for the Flask web app."""

from __future__ import annotations

import os

import atexit

from flask import Flask, request

from src.logging_config import configure_standard_logging, get_logger
from src.graphrag.chat_service import GraphRagChatService
from src.graphrag.neo4j_driver import create_neo4j_driver_from_env
from src.graphrag.openai_compatible_client import load_chat_client_from_env
from src.web.blueprints.graphrag_workspace import graphrag_ws_bp
from src.web.blueprints.web import web_bp
from src.web.config import get_project_root, load_flask_config
from src.web.handlers.repository_handler import RepositoryHandler
from src.web.services.analysis_service import AnalysisService


def create_app() -> Flask:
    """Create and configure the Flask application with blueprints and shared services.

    Services are stored on ``app.extensions`` under ``repo_handler``,
    ``analysis_service``, ``graphrag_chat_service``, and optional ``neo4j_driver``
    so routes stay free of module-level globals.

    Returns:
        A fully wired :class:`flask.Flask` instance (same object ``app`` as in ``app.py``).
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(get_project_root() / ".env", override=False)
    except ImportError:
        pass

    configure_standard_logging()
    get_logger(__name__).info("Flask application factory starting (project_root=%s)", get_project_root())

    project_root = get_project_root()
    app = Flask(__name__, template_folder=str(project_root / "templates"))
    app.config.from_mapping(**load_flask_config())
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.extensions["repo_handler"] = RepositoryHandler(app.config["UPLOAD_FOLDER"])
    app.extensions["analysis_service"] = AnalysisService()
    try:
        _llm = load_chat_client_from_env()
    except ValueError:
        _llm = None
    _neo = create_neo4j_driver_from_env()
    app.extensions["neo4j_driver"] = _neo
    if _neo is not None:

        def _close_neo4j() -> None:
            try:
                _neo.close()
            except Exception:
                get_logger(__name__).debug("Neo4j driver close ignored", exc_info=True)

        atexit.register(_close_neo4j)

    app.extensions["graphrag_chat_service"] = GraphRagChatService(_llm, neo4j_driver=_neo)
    app.register_blueprint(web_bp)
    app.register_blueprint(graphrag_ws_bp)

    @app.after_request
    def _log_request_outcome(response):
        """Emit one structured line per HTTP response for operations debugging."""
        get_logger("src.web.request").info(
            "%s %s -> %s",
            request.method,
            request.path,
            response.status_code,
        )
        return response

    return app
