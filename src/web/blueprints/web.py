"""HTTP routes for repository upload, compatibility, and analysis."""

from __future__ import annotations

import dataclasses
import json
import logging
import queue
import threading
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterator

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    stream_with_context,
    url_for,
)

from src.compatibility.check_item import CheckItem
from src.graph.json_document import load_graph_document
from src.graphrag.analysis_llm_insights import generate_and_save_llm_insights
from src.graphrag.neo4j_property_graph_export import export_graphrag_run_for_visualization
from src.graphrag.neo4j_subgraph import Neo4jSubgraphExpander
from src.web.handlers.repository_handler import RepositoryHandler
from src.web.report_docx import build_analysis_docx_bytes
from src.web.results_paths import (
    is_safe_visual_png_filename,
    resolve_visual_png_file,
    safe_resolve_results_run_dir,
)
from src.web.services.analysis_service import AnalysisService, load_results_from_run_directory
from src.web.utils.helpers import cleanup_temp_directory, handle_repository_upload

web_bp = Blueprint("web", __name__)
logger = logging.getLogger(__name__)


def _results_final_template_kwargs(results: Dict[str, Any]) -> Dict[str, Any]:
    """Shared context for ``results_final.html`` (GraphRAG + Neo4j UI flags)."""
    return {
        "results": results,
        "neo4j_property_graph_available": current_app.extensions.get("neo4j_driver") is not None,
    }

_PROGRESS_UI_HEADER = "X-GraphRAG-Progressive-UI"
_ANALYZE_STREAM_HEADER = "X-GraphRAG-Analyze-Stream"


def _repo_handler() -> RepositoryHandler:
    """Return the shared :class:`RepositoryHandler` from app extensions."""
    return current_app.extensions["repo_handler"]


def _analysis_service() -> AnalysisService:
    """Return the shared :class:`AnalysisService` from app extensions."""
    return current_app.extensions["analysis_service"]


def _wants_progressive_ui() -> bool:
    """Return True when the client opted into fetch + JSON errors (see templates)."""
    return request.headers.get(_PROGRESS_UI_HEADER, "").strip().lower() in ("1", "true", "yes")


def _wants_analyze_event_stream() -> bool:
    """Return True when the client expects SSE progress events for ``POST /analyze``."""
    return request.headers.get(_ANALYZE_STREAM_HEADER, "").strip().lower() in ("1", "true", "yes")


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


@web_bp.route("/favicon.ico")
def favicon() -> tuple[str, int]:
    """Return empty favicon response to avoid browser 404 noise."""
    return ("", 204)


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
        if _wants_progressive_ui():
            return jsonify({"ok": True, "redirect": url_for("web.compatibility_results")})
        return redirect(url_for("web.compatibility_results"))
    except ValueError as exc:
        cleanup_temp_directory(repo_path, cleanup_temp)
        if _wants_progressive_ui():
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc))
        return redirect(url_for("web.index"))
    except Exception as exc:
        logger.exception("upload_repository failed")
        cleanup_temp_directory(repo_path, cleanup_temp)
        if _wants_progressive_ui():
            return jsonify({"ok": False, "error": f"Error processing repository: {exc!s}"}), 500
        flash(f"Error processing repository: {exc!s}")
        return redirect(url_for("web.index"))


@web_bp.route("/analyze", methods=["POST"])
def analyze_repository():
    """Run the graph pipeline on the repository from session state.

    Returns:
        Rendered results HTML on success, ``text/event-stream`` when the client requests
        SSE progress (see ``X-GraphRAG-Analyze-Stream``), or JSON errors for progressive UI.
    """
    analysis_data = session.get("analysis_data")
    if not analysis_data:
        flash("Analysis data not found")
        return redirect(url_for("web.index"))

    repo_path = analysis_data["repo_path"]
    cleanup_temp = analysis_data["cleanup_temp"]
    results_folder_slug = analysis_data.get("results_folder_slug")

    if _wants_progressive_ui() and _wants_analyze_event_stream():
        # Resolve service in the request/app context; the worker thread must not call
        # ``current_app`` (Flask raises "Working outside of application context").
        analysis_svc: AnalysisService = current_app.extensions["analysis_service"]

        def _sse_bytes(obj: Dict[str, Any]) -> bytes:
            return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")

        @stream_with_context
        def event_stream() -> Iterator[bytes]:
            events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
            yield _sse_bytes({"type": "progress", "percent": 1, "message": "Starting graph pipeline…"})

            def progress_cb(percent: int, message: str) -> None:
                events.put(("progress", (percent, message)))

            def worker() -> None:
                try:
                    done = analysis_svc.run_analysis_pipeline(
                        repo_path,
                        results_folder_slug=results_folder_slug,
                        progress_callback=progress_cb,
                    )
                    events.put(("ok", done))
                except Exception as exc:  # noqa: BLE001 — surfaced to client as SSE
                    events.put(("err", str(exc)))

            threading.Thread(target=worker, daemon=True).start()
            while True:
                kind, payload = events.get()
                if kind == "progress":
                    pct, msg = payload
                    yield _sse_bytes({"type": "progress", "percent": pct, "message": msg})
                elif kind == "err":
                    logger.error("analyze_repository SSE pipeline error: %s", payload)
                    cleanup_temp_directory(repo_path, cleanup_temp)
                    yield _sse_bytes({"type": "error", "error": payload})
                    return
                elif kind == "ok":
                    cleanup_temp_directory(repo_path, cleanup_temp)
                    session.pop("analysis_data", None)
                    run_dir = payload.get("results_run_dir", "")
                    loc = url_for("web.analysis_results_page", run_dir=run_dir)
                    yield _sse_bytes({"type": "complete", "percent": 100, "redirect": loc})
                    return

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    try:
        results = _analysis_service().run_analysis_pipeline(
            repo_path, results_folder_slug=results_folder_slug
        )
        cleanup_temp_directory(repo_path, cleanup_temp)
        session.pop("analysis_data", None)
        if _wants_progressive_ui():
            run_dir = results.get("results_run_dir", "")
            return jsonify(
                {"ok": True, "redirect": url_for("web.analysis_results_page", run_dir=run_dir)}
            )
        return render_template("results_final.html", **_results_final_template_kwargs(results))
    except Exception as exc:
        logger.exception("analyze_repository failed")
        cleanup_temp_directory(repo_path, cleanup_temp)
        if _wants_progressive_ui():
            return jsonify({"ok": False, "error": f"Error during analysis: {exc!s}"}), 500
        flash(f"Error during analysis: {exc!s}")
        return redirect(url_for("web.index"))


@web_bp.route("/analysis-results/<run_dir>")
def analysis_results_page(run_dir: str):
    """Load a completed web run from ``results/<run_dir>/`` and render the results view."""
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        flash("Analysis results folder was not found or is not valid.")
        return redirect(url_for("web.index"))
    try:
        results = load_results_from_run_directory(base)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.exception("Failed to load results for run_dir=%s", run_dir)
        flash(f"Could not read analysis results for this run: {exc!s}")
        return redirect(url_for("web.index"))
    return render_template("results_final.html", **_results_final_template_kwargs(results))


@web_bp.route("/analysis-results/<run_dir>/bootstrap-bundle.json")
def analysis_results_bootstrap_bundle(run_dir: str):
    """Return the same JSON the results page uses for download helpers (not embedded in HTML).

    Keeping this payload out of ``<script type="application/json">`` avoids broken pages when
    analysis text or graph literals contain ``</script>`` or when the bundle is very large.
    """
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Analysis results folder was not found or is not valid."}), 404
    try:
        results = load_results_from_run_directory(base)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.exception("bootstrap_bundle read failed run_dir=%s", run_dir)
        return jsonify({"ok": False, "error": str(exc)}), 500
    payload = {
        "ok": True,
        "graph": results.get("graph_data"),
        "analysis": results.get("analysis_text") or "",
        "analysis_view": results.get("analysis_view") or {},
        "visual_summary_view": results.get("visual_summary_view") or {},
        "visual": results.get("visual_summary_text") or "",
        "pipeline": results.get("pipeline_output") or "",
        "llm_insights": results.get("llm_insights"),
    }
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@web_bp.route("/analysis-results/<run_dir>/chat", methods=["POST"])
def analysis_results_chat(run_dir: str):
    """Answer a natural-language question using subgraph retrieval and an LLM.

    Expects JSON ``{"message": "..."}``. Requires ``GRAPHRAG_OPENAI_BASE_URL`` and
    ``GRAPHRAG_CHAT_MODEL`` (see README). Returns JSON with ``ok``, ``reply`` on
    success, and diagnostic fields such as ``seed_nodes`` and ``subgraph_node_count``.
    """
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Analysis results folder was not found or is not valid."}), 404
    svc = current_app.extensions.get("graphrag_chat_service")
    if svc is None:
        return jsonify({"ok": False, "error": "GraphRAG chat service is not registered."}), 503
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    logger.info("graphrag_chat run_dir=%s message_chars=%d", run_dir, len(message))
    result = svc.answer(base, message)
    if not result.get("ok"):
        err = str(result.get("error", ""))
        status = 503 if "not configured" in err.lower() else 400
        return jsonify(result), status
    return jsonify(result)


@web_bp.route("/analysis-results/<run_dir>/llm-insights", methods=["POST"])
def analysis_results_llm_insights(run_dir: str):
    """Generate or return cached LLM interpretation of metrics, charts list, and text reports.

    Expects optional JSON ``{"regenerate": true}`` to force a new API call. Persists
    ``graphrag_llm_insights.json`` under the run directory. Requires the same OpenAI-compatible
    env vars as GraphRAG chat (``GRAPHRAG_OPENAI_BASE_URL``, ``GRAPHRAG_CHAT_MODEL``).
    """
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Analysis results folder was not found or is not valid."}), 404
    body = request.get_json(silent=True) or {}
    regenerate = bool(body.get("regenerate"))
    logger.info("llm_insights run_dir=%s regenerate=%s", run_dir, regenerate)
    result = generate_and_save_llm_insights(base, regenerate=regenerate)
    if not result.get("ok"):
        err = str(result.get("error", ""))
        status = 503 if "requires" in err.lower() or "not configured" in err.lower() else 400
        return jsonify(result), status
    return jsonify(result)


@web_bp.route("/analysis-results/<run_dir>/neo4j-property-graph.json")
def analysis_results_neo4j_property_graph(run_dir: str):
    """Return a bounded Neo4j property-graph snapshot for the GraphRAG run (JSON for vis).

    Loads ``graph.json`` for this run and ensures Neo4j is synced (same write path as GraphRAG
    chat expansion) before reading ``GraphRAGNode`` / ``GRAPHRAG_EDGE`` rows, so the preview is
    populated even if the user has not opened the assistant yet.

    Query params: ``max_edges`` (50–2000, default 500), ``max_nodes`` (20–800, default 400).
    Requires a configured Bolt driver on the app (same as chat Neo4j expansion).
    """
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Analysis results folder was not found or is not valid."}), 404
    graph_path = base / "graph.json"
    if not graph_path.is_file():
        return jsonify({"ok": False, "error": "graph.json not found for this run."}), 404
    try:
        doc = load_graph_document(graph_path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("neo4j_property_graph: could not read graph.json run_dir=%s: %s", run_dir, exc)
        return jsonify({"ok": False, "error": "Could not read graph.json for this run."}), 500
    nodes = list(doc.get("nodes") or [])
    edges = list(doc.get("edges") or [])

    driver = current_app.extensions.get("neo4j_driver")
    if driver is None:
        return jsonify({"ok": False, "error": "Neo4j is not configured on this server."}), 503

    expander = Neo4jSubgraphExpander(driver)
    synced = expander.ensure_synced(run_dir, nodes, edges, graph_path=graph_path)
    if not synced:
        logger.warning("neo4j_property_graph: ensure_synced returned false run_dir=%s", run_dir)

    max_edges = request.args.get("max_edges", default=500, type=int) or 500
    max_nodes = request.args.get("max_nodes", default=400, type=int) or 400
    max_edges = max(50, min(max_edges, 2000))
    max_nodes = max(20, min(max_nodes, 800))
    try:
        payload = export_graphrag_run_for_visualization(
            driver,
            run_dir,
            max_edges=max_edges,
            max_nodes=max_nodes,
        )
    except Exception as exc:
        logger.exception("neo4j_property_graph export failed run_dir=%s", run_dir)
        return jsonify({"ok": False, "error": str(exc)}), 500

    if not payload.get("nodes") and not payload.get("edges"):
        if len(edges) == 0:
            payload["viewer_hint"] = "This run has no edges in graph.json, so there is nothing to draw."
        elif not synced:
            payload["viewer_hint"] = (
                "Could not sync this run into Neo4j; check GRAPHRAG_NEO4J_* settings and logs/graphrag.log."
            )

    return jsonify({"ok": True, **payload})


@web_bp.route("/analysis-results/latest")
def analysis_results_latest():
    """Load the most recent ``results/web_analysis_*`` run and render results."""
    results_root = Path("results").resolve()
    if not results_root.is_dir():
        flash("No analysis results were found yet.")
        return redirect(url_for("web.index"))

    candidates = [
        p
        for p in results_root.iterdir()
        if p.is_dir() and p.name.startswith("web_analysis_") and (p / "graph.json").is_file()
    ]
    if not candidates:
        flash("No completed analysis run was found.")
        return redirect(url_for("web.index"))

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    results = load_results_from_run_directory(latest)
    return render_template("results_final.html", **_results_final_template_kwargs(results))


@web_bp.route("/analysis-results/<run_dir>/visuals/<filename>")
def analysis_visual_asset(run_dir: str, filename: str):
    """Serve one PNG from ``results/<run_dir>/visuals/``."""
    if not is_safe_visual_png_filename(filename):
        logger.warning("visual_asset_rejected_filename run_dir=%s filename=%r", run_dir, filename)
        return ("Not found", 404)
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return ("Not found", 404)
    visuals_dir = base / "visuals"
    if not visuals_dir.is_dir():
        return ("Not found", 404)
    target = resolve_visual_png_file(visuals_dir, filename)
    if target is None:
        logger.warning(
            "visual_asset_missing run_dir=%s filename=%r visuals_dir=%s",
            run_dir,
            filename,
            visuals_dir,
        )
        return ("Not found", 404)
    return send_from_directory(
        str(visuals_dir.resolve()),
        target.name,
        mimetype="image/png",
    )


@web_bp.route("/analysis-results/<run_dir>/report.docx")
def export_analysis_docx(run_dir: str):
    """Download a single Word document bundling text reports, pipeline log, and chart PNGs."""
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return ("Not found", 404)
    try:
        data, fname = build_analysis_docx_bytes(base)
    except Exception:
        logger.exception("DOCX export failed for run_dir=%s", run_dir)
        return ("Report could not be built", 500)
    return send_file(
        BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=fname,
    )
