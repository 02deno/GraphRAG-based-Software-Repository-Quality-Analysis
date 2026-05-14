"""ChatGPT-style GraphRAG workspace: projects (runs), persisted sessions, multi-turn chat."""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Iterator
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)

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

_CHAT_STREAM_HEADER = "X-GraphRAG-Chat-Stream"


def _sse_chat_event(obj: dict[str, object]) -> bytes:
    """Serialize one SSE ``data:`` frame (progress, token, complete, or error JSON)."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")

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


@graphrag_ws_bp.route("/api/<run_dir>/sessions/<session_id>/message", methods=["GET", "POST"])
def api_session_message(run_dir: str, session_id: str):
    """Append a user message, run GraphRAG + LLM, store the assistant reply.

    ``GET`` on this URL is not supported for chat; browsers or tools that probe it
    are redirected to the HTML workspace so logs are not spammed with 405 noise.

    With header ``X-GraphRAG-Chat-Stream: 1`` on ``POST``, returns ``text/event-stream``
    where each ``data:`` line is JSON: ``progress`` (retrieval), ``token`` (assistant
    text fragments from a streamed chat completion), then ``complete`` or ``error``.
    """
    if request.method == "GET":
        logger.debug(
            "graphrag_message_get_redirect run_dir=%s session_id=%s",
            run_dir,
            session_id,
        )
        if safe_resolve_results_run_dir(run_dir) is None:
            return redirect(url_for("graphrag_ws.workspace_page"), code=302)
        return redirect(url_for("graphrag_ws.workspace_page", run_dir=run_dir), code=302)
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

    wants_stream = request.headers.get(_CHAT_STREAM_HEADER, "").strip().lower() in ("1", "true", "yes")

    if wants_stream:

        @stream_with_context
        def event_stream() -> Iterator[bytes]:
            events: "queue.Queue[tuple[str, object]]" = queue.Queue()

            def emit_progress(stage: str, detail: str | None) -> None:
                events.put(("progress", (stage, detail)))

            def emit_token(fragment: str) -> None:
                if fragment:
                    events.put(("token", fragment))

            def worker() -> None:
                try:
                    result = svc.answer(
                        base,
                        message,
                        conversation_history=prior,
                        carryover_summary=carry if carry else None,
                        progress_hook=emit_progress,
                        token_hook=emit_token,
                    )
                    if not result.get("ok"):
                        events.put(("error", result))
                        return
                    reply = str(result.get("reply", "") or "")
                    updated = append_message_pair(
                        base,
                        session_id,
                        user_text=message,
                        assistant_text=reply,
                        title_if_empty=message[:80],
                        clear_carryover=had_carryover,
                        source_context_diagnostics=result.get("source_context_diagnostics"),
                    )
                    if updated is None:
                        events.put(("error", {"ok": False, "error": "Session could not be updated."}))
                        return
                    out = {k: v for k, v in result.items() if k != "reply"}
                    out["ok"] = True
                    out["reply"] = reply
                    out["session"] = updated
                    events.put(("complete", out))
                except Exception as exc:  # noqa: BLE001 — surfaced to client as SSE
                    logger.exception("graphrag_workspace_message stream worker failed")
                    events.put(("error", {"ok": False, "error": str(exc)}))

            threading.Thread(target=worker, daemon=True).start()
            while True:
                kind, payload = events.get()
                if kind == "progress":
                    stage, detail = payload  # type: ignore[misc]
                    if detail:
                        msg = f"{stage}: {detail}"
                    else:
                        msg = stage
                    yield _sse_chat_event({"type": "progress", "stage": stage, "message": msg})
                elif kind == "token":
                    text_chunk = str(payload)
                    yield _sse_chat_event({"type": "token", "text": text_chunk})
                elif kind == "error":
                    err_body = payload if isinstance(payload, dict) else {"ok": False, "error": str(payload)}
                    yield _sse_chat_event({"type": "error", **err_body})
                    return
                elif kind == "complete":
                    body = payload if isinstance(payload, dict) else {}
                    yield _sse_chat_event({"type": "complete", **body})
                    return

        logger.info(
            "graphrag_workspace_message_sse run_dir=%s session_id=%s prior_turns=%d carryover=%s",
            run_dir,
            session_id,
            len(prior),
            bool(carry),
        )
        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

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
        source_context_diagnostics=result.get("source_context_diagnostics"),
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
