"""Tests for GraphRAG source chunk index and retrieval."""

from __future__ import annotations

import json
from pathlib import Path

from src.graphrag.source_context import (
    build_source_chunk_index,
    refresh_llm_insights_source_chunks,
    retrieve_source_context_for_llm,
    write_run_meta,
)


def test_build_and_retrieve_source_chunks(tmp_path: Path) -> None:
    """Chunk a small repo, then retrieve excerpts for a matching query."""
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "sample.py").write_text(
        "def unique_fn_marker_xyz():\n    return 42\n",
        encoding="utf-8",
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    nodes = [
        {
            "id": "file:pkg/sample.py",
            "type": "File",
            "path": "pkg/sample.py",
            "module": "pkg.sample",
            "language": "python",
        }
    ]

    write_run_meta(run_dir, str(repo.resolve()))
    n = build_source_chunk_index(run_dir, repo, nodes)
    assert n >= 1

    block, diag = retrieve_source_context_for_llm(
        run_dir,
        "unique_fn_marker_xyz",
        max_chars=8000,
        top_rank=10,
    )
    assert diag.get("enabled") is True
    assert int(diag.get("chunks_used") or 0) >= 1
    assert "unique_fn_marker_xyz" in block
    assert "pkg/sample.py" in block


def test_readme_and_docs_indexed_for_lexical_retrieval(tmp_path: Path) -> None:
    """README and docs/*.md are chunked and can outrank code for prose-heavy queries."""
    repo = tmp_path / "repo2"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text(
        "# Service\n\nRisk and deployment: zeta_doc_marker_unique.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "guide.md").write_text(
        "## Ops\n\nMonitoring zeta_doc_marker_unique.\n",
        encoding="utf-8",
    )
    pkg = repo / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "sample.py").write_text("def other():\n    return 1\n", encoding="utf-8")

    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    nodes = [
        {
            "id": "file:pkg/sample.py",
            "type": "File",
            "path": "pkg/sample.py",
            "module": "pkg.sample",
            "language": "python",
        }
    ]
    write_run_meta(run_dir, str(repo.resolve()))
    n = build_source_chunk_index(run_dir, repo, nodes)
    assert n >= 2

    block, diag = retrieve_source_context_for_llm(
        run_dir,
        "zeta_doc_marker_unique risks summary",
        max_chars=12000,
        top_rank=15,
    )
    assert diag.get("enabled") is True
    assert "README.md" in block
    assert "```markdown" in block
    chunks = diag.get("included_chunks") or []
    assert any(c.get("path") == "README.md" for c in chunks)
    assert any(c.get("excerpt") for c in chunks), "included_chunks should carry excerpt previews"


def test_analysis_report_chunks_in_source_index(tmp_path: Path) -> None:
    """Pipeline analysis artifacts are indexed under _analysis/ virtual paths."""
    repo = tmp_path / "repo3"
    pkg = repo / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "x.py").write_text("def x():\n    return 0\n", encoding="utf-8")
    run_dir = tmp_path / "run3"
    run_dir.mkdir()
    view = {
        "schema_version": 1,
        "totals": {"nodes": 2, "edges": 1},
        "risk": {
            "empty": False,
            "candidates": [
                {
                    "rank": 1,
                    "file_path": "pkg/x.py",
                    "total": 9.9,
                    "centrality_z": 2,
                    "churn_z": 1,
                    "test_gap_z": 0,
                    "cross_community_z": 0,
                }
            ],
        },
    }
    (run_dir / "analysis_view.json").write_text(json.dumps(view), encoding="utf-8")
    (run_dir / "analysis.txt").write_text(
        "Unique analysis body token zeta_analysis_blob_77.\n",
        encoding="utf-8",
    )

    nodes = [{"id": "file:pkg/x.py", "type": "File", "path": "pkg/x.py"}]
    write_run_meta(run_dir, str(repo.resolve()))
    n = build_source_chunk_index(run_dir, repo, nodes)
    assert n >= 1

    block, diag = retrieve_source_context_for_llm(
        run_dir,
        "zeta_analysis_blob_77",
        max_chars=12000,
        top_rank=20,
    )
    assert "_analysis/" in block
    assert "zeta_analysis_blob_77" in block
    chunks = diag.get("included_chunks") or []
    paths = [c.get("path") for c in chunks]
    assert any(p and str(p).startswith("_analysis/") for p in paths)
    assert any(c.get("excerpt") for c in chunks)


def test_metrics_intent_prioritizes_analysis_over_docs(tmp_path: Path) -> None:
    """Graph-metrics style questions should rank ``_analysis/*`` chunks above generic docs."""
    repo = tmp_path / "r4"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "USAGE.md").write_text(
        "# Usage\n\ngraph repository documentation filler text.\n" * 40,
        encoding="utf-8",
    )
    pkg = repo / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "x.py").write_text("def x():\n    return 0\n", encoding="utf-8")
    run_dir = tmp_path / "run4"
    run_dir.mkdir()
    view = {
        "schema_version": 1,
        "totals": {"nodes": 3, "edges": 2},
        "risk": {"empty": True},
    }
    (run_dir / "analysis_view.json").write_text(json.dumps(view), encoding="utf-8")
    (run_dir / "analysis.txt").write_text("Centrality and communities summary line.\n", encoding="utf-8")

    nodes = [{"id": "file:pkg/x.py", "type": "File", "path": "pkg/x.py"}]
    write_run_meta(run_dir, str(repo.resolve()))
    n = build_source_chunk_index(run_dir, repo, nodes)
    assert n >= 1

    block, diag = retrieve_source_context_for_llm(
        run_dir,
        "what are graph analysis results for this repo",
        max_chars=12000,
        top_rank=12,
    )
    assert "_analysis/" in block
    chunks = diag.get("included_chunks") or []
    assert chunks, "expected ranked chunks"
    top_paths = [str(c.get("path") or "") for c in chunks[:5]]
    assert any(p.startswith("_analysis/") for p in top_paths), top_paths


def test_repo_scope_intent_phrases() -> None:
    from src.graphrag import source_context as sc

    assert sc._repo_scope_intent("describe this codebase")
    assert sc._repo_scope_intent("yüklenen repo nedir")
    assert not sc._repo_scope_intent("betweenness on the calls graph")


def test_analysis_chunk_repo_intent_penalty_respects_graph_queries() -> None:
    from src.graphrag import source_context as sc

    rec = {"path": "_analysis/analysis.txt", "kind": "analysis_report"}
    assert sc._analysis_chunk_repo_intent_penalty("describe this project", rec) == -88.0
    assert sc._analysis_chunk_repo_intent_penalty("centrality and betweenness", rec) == 0.0
    assert sc._analysis_chunk_repo_intent_penalty("graph analysis results for this repo", rec) == 0.0


def test_llm_insights_chunks_in_full_index(tmp_path: Path) -> None:
    """Cached ``graphrag_llm_insights.json`` is flattened into the source chunk JSONL."""
    from src.graphrag.analysis_llm_insights import LLM_INSIGHTS_SOURCE_VIRTUAL_PATH

    repo = tmp_path / "r_ins"
    pkg = repo / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    run_dir = tmp_path / "run_ins"
    run_dir.mkdir()
    insights = {
        "schema_version": 1,
        "executive_summary": "unique_exec_token_alpha_llm_ins_42.",
        "key_findings": ["unique_finding_alpha_llm_ins_42 detail."],
        "suggested_actions": [],
        "bug_risk_hotspots": [],
        "high_risk_areas": [],
        "testing_observations": [],
        "caveats": "",
        "model": "stub",
        "generated_at": "2026-01-01T00:00:00Z",
    }
    (run_dir / "graphrag_llm_insights.json").write_text(json.dumps(insights), encoding="utf-8")
    nodes = [{"id": "file:pkg/m.py", "type": "File", "path": "pkg/m.py"}]
    write_run_meta(run_dir, str(repo.resolve()))
    n = build_source_chunk_index(run_dir, repo, nodes)
    assert n >= 1
    blobs = (run_dir / "graphrag_source_chunks.jsonl").read_text(encoding="utf-8")
    assert LLM_INSIGHTS_SOURCE_VIRTUAL_PATH in blobs
    assert "unique_exec_token_alpha_llm_ins_42" in blobs

    block, diag = retrieve_source_context_for_llm(
        run_dir,
        "what does the ai summary say about unique_exec_token_alpha_llm_ins_42",
        max_chars=12000,
        top_rank=15,
    )
    assert diag.get("enabled") is True
    assert "unique_exec_token_alpha_llm_ins_42" in block
    paths = [c.get("path") for c in (diag.get("included_chunks") or [])]
    assert any(p == LLM_INSIGHTS_SOURCE_VIRTUAL_PATH for p in paths), paths


def test_llm_insights_refresh_merges_into_existing_jsonl(tmp_path: Path) -> None:
    """``refresh_llm_insights_source_chunks`` updates JSONL after insights are written post-index."""
    from src.graphrag.analysis_llm_insights import LLM_INSIGHTS_SOURCE_VIRTUAL_PATH

    repo = tmp_path / "r_ref"
    repo.mkdir()
    (repo / "x.py").write_text("def x():\n    return 0\n", encoding="utf-8")
    run_dir = tmp_path / "run_ref"
    run_dir.mkdir()
    (run_dir / "analysis.txt").write_text("body tok_refresh_xyz.\n", encoding="utf-8")
    nodes = [{"id": "file:x.py", "type": "File", "path": "x.py"}]
    write_run_meta(run_dir, str(repo.resolve()))
    build_source_chunk_index(run_dir, repo, nodes)

    insights = {
        "schema_version": 1,
        "executive_summary": "tok_refresh_xyz executive line.",
        "key_findings": [],
        "suggested_actions": [],
        "bug_risk_hotspots": [],
        "high_risk_areas": [],
        "testing_observations": [],
        "caveats": "",
    }
    (run_dir / "graphrag_llm_insights.json").write_text(json.dumps(insights), encoding="utf-8")
    added = refresh_llm_insights_source_chunks(run_dir)
    assert added >= 1
    txt = (run_dir / "graphrag_source_chunks.jsonl").read_text(encoding="utf-8")
    assert LLM_INSIGHTS_SOURCE_VIRTUAL_PATH in txt
    assert "body tok_refresh_xyz" in txt
    assert "tok_refresh_xyz executive" in txt

    added2 = refresh_llm_insights_source_chunks(run_dir)
    assert added2 >= 1
