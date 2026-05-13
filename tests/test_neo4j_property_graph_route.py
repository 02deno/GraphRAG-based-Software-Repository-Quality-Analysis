"""Tests for Neo4j property graph JSON route."""

from __future__ import annotations

import json

import pytest

from src.web.factory import create_app


def test_neo4j_property_graph_invalid_run_dir_404() -> None:
    app = create_app()
    client = app.test_client()
    resp = client.get("/analysis-results/not_valid_/neo4j-property-graph.json")
    assert resp.status_code == 404


def test_neo4j_property_graph_503_without_neo4j_driver(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Valid run folder but no Bolt driver should yield 503."""
    monkeypatch.chdir(tmp_path)
    run_name = "web_analysis_unit_neo4j_pg"
    rd = tmp_path / "results" / run_name
    rd.mkdir(parents=True)
    (rd / "graph.json").write_text(
        json.dumps({"schema_version": 1, "nodes": [], "edges": []}),
        encoding="utf-8",
    )
    app = create_app()
    client = app.test_client()
    resp = client.get(f"/analysis-results/{run_name}/neo4j-property-graph.json")
    if app.extensions.get("neo4j_driver") is None:
        assert resp.status_code == 503
        data = resp.get_json()
        assert data is not None
        assert data.get("ok") is False
