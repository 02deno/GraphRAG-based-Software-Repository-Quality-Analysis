"""ChatGPT-style GraphRAG workspace: projects (runs), persisted sessions, multi-turn chat."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request

from src.graphrag.chat_service import GraphRagChatService
from src.graphrag.session_store import (
    append_message_pair,
    create_session,
    delete_session,
    list_sessions,
    load_session,
)
from src.web.results_paths import safe_resolve_results_run_dir

logger = logging.getLogger(__name__)

graphrag_ws_bp = Blueprint("graphrag_ws", __name__, url_prefix="/graphrag")


def _results_root() -> Path:
    return Path("results").resolve()


def _list_project_runs() -> list[dict[str, object]]:
    """Completed web analysis runs that contain ``graph.json`` (newest first)."""
    root = _results_root()
    if not root.is_dir():
        return []
    candidates = [
        p
        for p in root.iterdir()
        if p.is_dir() and p.name.startswith("web_analysis_") and (p / "graph.json").is_file()
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, object]] = []
    for p in candidates:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        out.append(
            {
                "run_dir": p.name,
                "label": p.name.removeprefix("web_analysis_") or p.name,
                "updated_at": int(mtime),
            }
        )
    return out


@graphrag_ws_bp.route("/workspace")
@graphrag_ws_bp.route("/workspace/<run_dir>")
def workspace_page(run_dir: str | None = None):
    """Render the full-page chat workspace (optional pre-selected *run_dir*)."""
    initial = (run_dir or "").strip()
    if initial and safe_resolve_results_run_dir(initial) is None:
        initial = ""
    return render_template("graphrag_workspace.html", initial_run_dir=initial)


@graphrag_ws_bp.route("/api/projects")
def api_projects():
    """JSON list of analysis runs usable as GraphRAG projects."""
    return jsonify({"ok": True, "projects": _list_project_runs()})


@graphrag_ws_bp.route("/api/<run_dir>/sessions", methods=["GET", "POST"])
def api_sessions(run_dir: str):
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Invalid or missing run directory."}), 404
    if request.method == "GET":
        return jsonify({"ok": True, "sessions": list_sessions(base)})
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip() or "New chat"
    carry = str(payload.get("carryover_summary", "")).strip()
    data = create_session(base, title=title[:120], carryover_summary=carry[:8000])
    logger.info("graphrag_session_created run_dir=%s session_id=%s", run_dir, data.get("id"))
    return jsonify({"ok": True, "session": data})


@graphrag_ws_bp.route("/api/<run_dir>/sessions/fork", methods=["POST"])
def api_fork_session(run_dir: str):
    """Create a new session, optionally filling ``carryover_summary`` via LLM."""
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Invalid or missing run directory."}), 404
    svc = current_app.extensions.get("graphrag_chat_service")
    if not isinstance(svc, GraphRagChatService):
        return jsonify({"ok": False, "error": "GraphRAG chat service is not registered."}), 503
    payload = request.get_json(silent=True) or {}
    from_sid = str(payload.get("from_session_id", "")).strip()
    manual = str(payload.get("carryover_summary", "")).strip()
    title = str(payload.get("title", "")).strip() or "New chat"
    old = load_session(base, from_sid) if from_sid else None
    if from_sid and old is None:
        return jsonify({"ok": False, "error": "Source session not found."}), 404
    summary = manual[:8000]
    if not summary and old is not None:
        sum_res = svc.summarize_thread_for_carryover(list(old.get("messages") or []))
        if not sum_res.get("ok"):
            err = str(sum_res.get("error", ""))
            status = 503 if "not configured" in err.lower() else 400
            return jsonify(sum_res), status
        summary = str(sum_res.get("summary", "")).strip()[:8000]
    data = create_session(base, title=title[:120], carryover_summary=summary)
    logger.info(
        "graphrag_session_forked run_dir=%s from=%s new=%s",
        run_dir,
        from_sid or "(manual)",
        data.get("id"),
    )
    return jsonify({"ok": True, "session": data})


@graphrag_ws_bp.route("/api/<run_dir>/sessions/<session_id>", methods=["GET", "DELETE"])
def api_session_detail(run_dir: str, session_id: str):
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Invalid or missing run directory."}), 404
    if request.method == "DELETE":
        if not delete_session(base, session_id):
            return jsonify({"ok": False, "error": "Session not found."}), 404
        logger.info("graphrag_session_deleted run_dir=%s session_id=%s", run_dir, session_id)
        return jsonify({"ok": True})
    data = load_session(base, session_id)
    if data is None:
        return jsonify({"ok": False, "error": "Session not found."}), 404
    return jsonify({"ok": True, "session": data})


@graphrag_ws_bp.route("/api/<run_dir>/sessions/<session_id>/message", methods=["POST"])
def api_session_message(run_dir: str, session_id: str):
    """Append a user message, run GraphRAG + LLM, store the assistant reply."""
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Invalid or missing run directory."}), 404
    svc = current_app.extensions.get("graphrag_chat_service")
    if not isinstance(svc, GraphRagChatService):
        return jsonify({"ok": False, "error": "GraphRAG chat service is not registered."}), 503
    data = load_session(base, session_id)
    if data is None:
        return jsonify({"ok": False, "error": "Session not found."}), 404
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "error": "Empty message."}), 400

    prior = list(data.get("messages") or [])
    carry = str(data.get("carryover_summary") or "").strip()
    had_carryover = bool(carry)

    logger.info(
        "graphrag_workspace_message run_dir=%s session_id=%s prior_turns=%d carryover=%s",
        run_dir,
        session_id,
        len(prior),
        bool(carry),
    )
    result = svc.answer(
        base,
        message,
        conversation_history=prior,
        carryover_summary=carry if carry else None,
    )
    if not result.get("ok"):
        err = str(result.get("error", ""))
        status = 503 if "not configured" in err.lower() else 400
        return jsonify(result), status

    reply = str(result.get("reply", "") or "")
    updated = append_message_pair(
        base,
        session_id,
        user_text=message,
        assistant_text=reply,
        title_if_empty=message[:80],
        clear_carryover=had_carryover,
    )
    if updated is None:
        return jsonify({"ok": False, "error": "Session could not be updated."}), 500

    out = {k: v for k, v in result.items() if k != "reply"}
    out["ok"] = True
    out["reply"] = reply
    out["session"] = updated
    return jsonify(out)


@graphrag_ws_bp.route("/api/<run_dir>/sessions/<session_id>/summarize-for-fork", methods=["POST"])
def api_summarize_for_fork(run_dir: str, session_id: str):
    """Return a bullet summary suitable for starting a new session (no session created)."""
    base = safe_resolve_results_run_dir(run_dir)
    if base is None:
        return jsonify({"ok": False, "error": "Invalid or missing run directory."}), 404
    svc = current_app.extensions.get("graphrag_chat_service")
    if not isinstance(svc, GraphRagChatService):
        return jsonify({"ok": False, "error": "GraphRAG chat service is not registered."}), 503
    data = load_session(base, session_id)
    if data is None:
        return jsonify({"ok": False, "error": "Session not found."}), 404
    sum_res = svc.summarize_thread_for_carryover(list(data.get("messages") or []))
    if not sum_res.get("ok"):
        err = str(sum_res.get("error", ""))
        status = 503 if "not configured" in err.lower() else 400
        return jsonify(sum_res), status
    return jsonify(sum_res)
