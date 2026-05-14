"""Tests for on-disk GraphRAG chat session storage."""

from __future__ import annotations

from pathlib import Path

from src.graphrag import session_store


def test_create_append_delete_roundtrip(tmp_path: Path) -> None:
    run = tmp_path / "web_analysis_dummy_20260101_000000"
    run.mkdir()
    (run / "graph.json").write_text("{}", encoding="utf-8")

    s = session_store.create_session(run, title="T", carryover_summary="carry")
    assert s["id"]
    assert s["carryover_summary"] == "carry"

    updated = session_store.append_message_pair(
        run,
        s["id"],
        user_text="Hello",
        assistant_text="Hi",
        title_if_empty="Hello",
        clear_carryover=True,
        source_context_diagnostics={"enabled": True, "chunks_used": 2, "included_chunks": []},
    )
    assert updated is not None
    assert len(updated["messages"]) == 2
    assert updated["messages"][1].get("source_context_diagnostics", {}).get("chunks_used") == 2
    assert updated["carryover_summary"] == ""

    reloaded = session_store.load_session(run, s["id"])
    assert reloaded is not None
    assert reloaded["messages"][1].get("source_context_diagnostics", {}).get("chunks_used") == 2

    listed = session_store.list_sessions(run)
    assert len(listed) == 1
    assert listed[0]["message_count"] == 2

    assert session_store.delete_session(run, s["id"]) is True
    assert session_store.load_session(run, s["id"]) is None


def test_append_user_then_assistant_roundtrip(tmp_path: Path) -> None:
    run = tmp_path / "web_analysis_dummy_20260101_000002"
    run.mkdir()
    (run / "graph.json").write_text("{}", encoding="utf-8")
    s = session_store.create_session(run, title="New chat", carryover_summary="")
    sid = s["id"]
    u = session_store.append_user_message(run, sid, user_text="Q?", title_if_empty="Q?")
    assert u is not None
    assert len(u["messages"]) == 1
    assert u["messages"][0]["role"] == "user"
    listed = session_store.list_sessions(run)
    assert listed[0]["message_count"] == 1
    a = session_store.append_assistant_reply(
        run,
        sid,
        assistant_text="A.",
        clear_carryover=False,
        source_context_diagnostics=None,
    )
    assert a is not None
    assert len(a["messages"]) == 2
    assert a["messages"][1]["role"] == "assistant"


def test_invalid_session_id_returns_none(tmp_path: Path) -> None:
    run = tmp_path / "web_analysis_dummy_20260101_000001"
    run.mkdir()
    assert session_store.load_session(run, "../etc") is None
