"""Tests for results page bootstrap JSON bundle (avoids giant inline HTML)."""

from __future__ import annotations

import json

import pytest

from src.web.factory import create_app


def test_bootstrap_bundle_404_invalid_run() -> None:
    app = create_app()
    client = app.test_client()
    r = client.get("/analysis-results/not_a_valid_run_/bootstrap-bundle.json")
    assert r.status_code == 404


def test_bootstrap_bundle_ok(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    run = "web_analysis_unit_bootstrap_20260101_120000"
    rd = tmp_path / "results" / run
    rd.mkdir(parents=True)
    graph = {"schema_version": 1, "nodes": [{"id": "n1", "type": "File"}], "edges": []}
    (rd / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (rd / "analysis.txt").write_text("ok", encoding="utf-8")
    (rd / "analysis_view.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    app = create_app()
    client = app.test_client()
    r = client.get(f"/analysis-results/{run}/bootstrap-bundle.json")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("graph", {}).get("nodes")
