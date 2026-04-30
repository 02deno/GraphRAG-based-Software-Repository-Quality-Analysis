"""HTTP routes for repository upload, compatibility, and analysis."""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for

from src.web.services.analysis_service import AnalysisService
from src.web.handlers.repository_handler import RepositoryHandler
from src.web.utils.helpers import cleanup_temp_directory, handle_repository_upload

web_bp = Blueprint("web", __name__)


def _repo_handler() -> RepositoryHandler:
    """Return the shared :class:`RepositoryHandler` from app extensions."""
    return current_app.extensions["repo_handler"]


def _analysis_service() -> AnalysisService:
    """Return the shared :class:`AnalysisService` from app extensions."""
    return current_app.extensions["analysis_service"]


@web_bp.route("/")
def index():
    """Render the repository upload landing page."""
    return render_template("index.html")


@web_bp.route("/upload", methods=["POST"])
def upload_repository():
    """Accept ZIP, GitHub URL, or local path; run compatibility check; store session.

    Returns:
        Compatibility results page, or redirect to home with a flash message on error.
    """
    repo_path = None
    cleanup_temp = False

    try:
        repo_path, cleanup_temp = handle_repository_upload(_repo_handler())
        compatibility_result = _analysis_service().run_compatibility_check(repo_path)
        session["analysis_data"] = {
            "repo_path": repo_path,
            "cleanup_temp": cleanup_temp,
            "compatibility": compatibility_result,
        }
        return render_template(
            "compatibility.html",
            score=compatibility_result["score"],
            details=compatibility_result["details"],
            warnings=compatibility_result["warnings"],
        )
    except ValueError as exc:
        flash(str(exc))
        cleanup_temp_directory(repo_path, cleanup_temp)
        return redirect(url_for("web.index"))
    except Exception as exc:
        flash(f"Error processing repository: {exc!s}")
        cleanup_temp_directory(repo_path, cleanup_temp)
        return redirect(url_for("web.index"))


@web_bp.route("/analyze", methods=["POST"])
def analyze_repository():
    """Run the graph pipeline on the repository from session state.

    Returns:
        Results page with graph and report, or redirect home on missing session or failure.
    """
    analysis_data = session.get("analysis_data")
    if not analysis_data:
        flash("Analysis data not found")
        return redirect(url_for("web.index"))

    repo_path = analysis_data["repo_path"]
    cleanup_temp = analysis_data["cleanup_temp"]

    try:
        results = _analysis_service().run_analysis_pipeline(repo_path)
        cleanup_temp_directory(repo_path, cleanup_temp)
        return render_template("results_final.html", results=results)
    except Exception as exc:
        flash(f"Error during analysis: {exc!s}")
        cleanup_temp_directory(repo_path, cleanup_temp)
        return redirect(url_for("web.index"))
