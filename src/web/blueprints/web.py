"""HTTP routes for repository upload, compatibility, and analysis."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.compatibility.check_item import CheckItem
from src.web.handlers.repository_handler import RepositoryHandler
from src.web.services.analysis_service import AnalysisService
from src.web.utils.helpers import cleanup_temp_directory, handle_repository_upload

web_bp = Blueprint("web", __name__)

_PROGRESS_UI_HEADER = "X-GraphRAG-Progressive-UI"


def _repo_handler() -> RepositoryHandler:
    """Return the shared :class:`RepositoryHandler` from app extensions."""
    return current_app.extensions["repo_handler"]


def _analysis_service() -> AnalysisService:
    """Return the shared :class:`AnalysisService` from app extensions."""
    return current_app.extensions["analysis_service"]


def _wants_progressive_ui() -> bool:
    """Return True when the client opted into fetch + JSON errors (see templates)."""
    return request.headers.get(_PROGRESS_UI_HEADER, "").strip().lower() in ("1", "true", "yes")


def _serialize_compatibility_for_session(result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert checker output (with ``CheckItem`` objects) to a JSON-serializable dict."""
    details_out: list[Dict[str, Any]] = []
    for item in result["details"]:
        if isinstance(item, CheckItem):
            details_out.append(dataclasses.asdict(item))
        elif isinstance(item, dict):
            details_out.append(dict(item))
        else:
            raise TypeError(f"Unexpected compatibility detail type: {type(item)!r}")
    return {
        "score": result["score"],
        "passed": result["passed"],
        "details": details_out,
        "warnings": list(result["warnings"]),
        "repo_path": result["repo_path"],
    }


@web_bp.route("/")
def index():
    """Render the repository upload landing page."""
    return render_template("index.html")


@web_bp.route("/compatibility")
def compatibility_results():
    """Show the latest compatibility outcome from the session (after upload redirect)."""
    analysis_data = session.get("analysis_data")
    if not analysis_data or "compatibility" not in analysis_data:
        flash("No compatibility results. Upload a repository first.")
        return redirect(url_for("web.index"))
    compat = analysis_data["compatibility"]
    return render_template(
        "compatibility.html",
        score=compat["score"],
        details=compat["details"],
        warnings=compat.get("warnings", []),
    )


@web_bp.route("/upload", methods=["POST"])
def upload_repository():
    """Accept ZIP, GitHub URL, or local path; run compatibility check; store session.

    Returns:
        Redirect to :func:`compatibility_results` on success, or redirect home with flash
        on error. When ``X-GraphRAG-Progressive-UI`` is set, validation errors return JSON
        instead of redirect so the landing page can show a message without navigation.
    """
    repo_path = None
    cleanup_temp = False

    try:
        repo_path, cleanup_temp, results_folder_slug = handle_repository_upload(_repo_handler())
        compatibility_result = _analysis_service().run_compatibility_check(repo_path)
        session["analysis_data"] = {
            "repo_path": repo_path,
            "cleanup_temp": cleanup_temp,
            "results_folder_slug": results_folder_slug,
            "compatibility": _serialize_compatibility_for_session(compatibility_result),
        }
        return redirect(url_for("web.compatibility_results"))
    except ValueError as exc:
        cleanup_temp_directory(repo_path, cleanup_temp)
        if _wants_progressive_ui():
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc))
        return redirect(url_for("web.index"))
    except Exception as exc:
        cleanup_temp_directory(repo_path, cleanup_temp)
        if _wants_progressive_ui():
            return jsonify({"ok": False, "error": f"Error processing repository: {exc!s}"}), 500
        flash(f"Error processing repository: {exc!s}")
        return redirect(url_for("web.index"))


@web_bp.route("/analyze", methods=["POST"])
def analyze_repository():
    """Run the graph pipeline on the repository from session state.

    Returns:
        Rendered results HTML on success, or redirect home on missing session or failure.
    """
    analysis_data = session.get("analysis_data")
    if not analysis_data:
        flash("Analysis data not found")
        return redirect(url_for("web.index"))

    repo_path = analysis_data["repo_path"]
    cleanup_temp = analysis_data["cleanup_temp"]
    results_folder_slug = analysis_data.get("results_folder_slug")

    try:
        results = _analysis_service().run_analysis_pipeline(
            repo_path, results_folder_slug=results_folder_slug
        )
        cleanup_temp_directory(repo_path, cleanup_temp)
        session.pop("analysis_data", None)
        return render_template("results_final.html", results=results)
    except Exception as exc:
        cleanup_temp_directory(repo_path, cleanup_temp)
        if _wants_progressive_ui():
            return jsonify({"ok": False, "error": f"Error during analysis: {exc!s}"}), 500
        flash(f"Error during analysis: {exc!s}")
        return redirect(url_for("web.index"))
