"""Persist GraphRAG chat sessions on disk under each ``results/web_analysis_*`` run."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_SESSIONS_SUBDIR = "graphrag_chat_sessions"
_SESSION_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_SCHEMA_VERSION = 1


def sessions_root(run_path: Path) -> Path:
    """Directory where JSON session files for *run_path* are stored."""
    return run_path / _SESSIONS_SUBDIR


def new_session_id() -> str:
    """Return a new 32-char hex session id (safe filename)."""
    return uuid.uuid4().hex


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_sessions(run_path: Path) -> List[Dict[str, Any]]:
    """Return lightweight metadata for each session under *run_path*, newest first."""
    root = sessions_root(run_path)
    if not root.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(root.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        sid = str(data.get("id") or p.stem)
        out.append(
            {
                "id": sid,
                "title": str(data.get("title") or "Chat"),
                "updated_at": str(data.get("updated_at") or ""),
                "message_count": len(data.get("messages") or []),
            }
        )
    return out


def load_session(run_path: Path, session_id: str) -> Dict[str, Any] | None:
    """Load a session dict or ``None`` if missing / invalid id."""
    if not _SESSION_ID_RE.fullmatch(session_id.strip()):
        return None
    path = sessions_root(run_path) / f"{session_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_session(run_path: Path, data: Dict[str, Any]) -> None:
    """Write *data* atomically to ``<sessions_root>/<id>.json``."""
    sid = str(data.get("id", "")).strip()
    if not _SESSION_ID_RE.fullmatch(sid):
        raise ValueError("invalid session id")
    root = sessions_root(run_path)
    root.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now_iso()
    path = root / f"{sid}.json"
    tmp = path.with_suffix(".tmp")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def create_session(
    run_path: Path,
    *,
    title: str = "",
    carryover_summary: str = "",
) -> Dict[str, Any]:
    """Create a new empty session record and persist it."""
    sid = new_session_id()
    now = _utc_now_iso()
    data: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "id": sid,
        "run_dir": run_path.name,
        "title": (title or "New chat").strip()[:120] or "New chat",
        "created_at": now,
        "updated_at": now,
        "carryover_summary": (carryover_summary or "").strip()[:8000],
        "messages": [],
    }
    save_session(run_path, data)
    return data


def append_user_message(
    run_path: Path,
    session_id: str,
    *,
    user_text: str,
    title_if_empty: str,
) -> Dict[str, Any] | None:
    """Append a user message only (used before streaming LLM work).

    Persists the question immediately so switching tabs or aborting the SSE
    reader does not leave the session file empty on disk.

    Args:
        run_path: Run directory containing ``graphrag_chat_sessions/``.
        session_id: Session file id.
        user_text: User message body.
        title_if_empty: Session title when still ``New chat`` / empty.
    """
    data = load_session(run_path, session_id)
    if data is None:
        return None
    msgs = list(data.get("messages") or [])
    msgs.append({"role": "user", "content": user_text.strip()[:32000]})
    data["messages"] = msgs
    if (data.get("title") or "").strip() in ("", "New chat"):
        data["title"] = (title_if_empty or "Chat").strip()[:120]
    save_session(run_path, data)
    return data


def append_assistant_reply(
    run_path: Path,
    session_id: str,
    *,
    assistant_text: str,
    clear_carryover: bool = False,
    source_context_diagnostics: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """Append an assistant message after the latest user message on disk."""
    data = load_session(run_path, session_id)
    if data is None:
        return None
    msgs = list(data.get("messages") or [])
    if not msgs or str(msgs[-1].get("role") or "") != "user":
        return None
    assistant_msg: Dict[str, Any] = {
        "role": "assistant",
        "content": assistant_text.strip()[:64000],
    }
    if isinstance(source_context_diagnostics, dict) and source_context_diagnostics:
        assistant_msg["source_context_diagnostics"] = source_context_diagnostics
    msgs.append(assistant_msg)
    data["messages"] = msgs
    if clear_carryover:
        data["carryover_summary"] = ""
    save_session(run_path, data)
    return data


def append_message_pair(
    run_path: Path,
    session_id: str,
    *,
    user_text: str,
    assistant_text: str,
    title_if_empty: str,
    clear_carryover: bool = False,
    source_context_diagnostics: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """Append user + assistant messages and refresh title when still default.

    Args:
        run_path: Run directory containing ``graphrag_chat_sessions/``.
        session_id: Session file id.
        user_text: Latest user message body.
        assistant_text: Latest assistant reply body.
        title_if_empty: Session title when still ``New chat`` / empty.
        clear_carryover: When True, clear ``carryover_summary`` after append.
        source_context_diagnostics: Optional per-turn source index metadata for the UI
            (JSON-serializable dict); stored only on the new assistant message.
    """
    if append_user_message(
        run_path,
        session_id,
        user_text=user_text,
        title_if_empty=title_if_empty,
    ) is None:
        return None
    return append_assistant_reply(
        run_path,
        session_id,
        assistant_text=assistant_text,
        clear_carryover=clear_carryover,
        source_context_diagnostics=source_context_diagnostics,
    )


def estimate_context_chars_for_turn(
    messages: List[Dict[str, Any]],
    user_block: str,
    carryover_summary: str,
) -> int:
    """Include carryover summary in estimate."""
    total = len(user_block) + len(carryover_summary or "")
    for m in messages:
        if isinstance(m, dict):
            total += len(str(m.get("content") or ""))
    return total + 1200  # system prompt + framing fudge


def delete_session(run_path: Path, session_id: str) -> bool:
    """Remove a session file. Returns False if id invalid or file missing."""
    if not _SESSION_ID_RE.fullmatch(session_id.strip()):
        return False
    path = sessions_root(run_path) / f"{session_id}.json"
    try:
        path.unlink()
    except OSError:
        return False
    return True
