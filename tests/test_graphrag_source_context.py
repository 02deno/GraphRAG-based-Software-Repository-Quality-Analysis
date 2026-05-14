"""Tests for GraphRAG source chunk index and retrieval."""

from __future__ import annotations

from pathlib import Path

from src.graphrag.source_context import (
    build_source_chunk_index,
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
