"""Persist repository root metadata and lexical source chunks for GraphRAG chat."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from src.graph.json_document import load_graph_document
from src.graphrag.query_index import score_query_against_blob

logger = logging.getLogger(__name__)

_RUN_META = "graphrag_run_meta.json"
_CHUNKS_JSONL = "graphrag_source_chunks.jsonl"
_INDEX_META = "graphrag_source_index_meta.json"


def write_run_meta(results_dir: Path, source_repo_root: str | None) -> None:
    """Persist optional absolute repository path for later source retrieval.

    Args:
        results_dir: ``results/web_analysis_*`` folder for one run.
        source_repo_root: Resolved repository root at analysis time, or ``None``.
    """
    payload = {"schema_version": 1, "source_repo_root": source_repo_root}
    path = results_dir / _RUN_META
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write %s: %s", path.name, exc)


def load_run_meta(run_dir: Path) -> Dict[str, Any]:
    """Load ``graphrag_run_meta.json`` if present."""
    path = run_dir / _RUN_META
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _py_paths_from_nodes(nodes: Sequence[Dict[str, Any]]) -> List[str]:
    """Collect unique ``.py`` file paths from ``File`` nodes."""
    out: List[str] = []
    seen: set[str] = set()
    for n in nodes:
        if str(n.get("type", "")) != "File":
            continue
        rel = str(n.get("path", "")).strip().replace("\\", "/")
        if not rel or ".." in rel or rel.startswith("/"):
            continue
        if not rel.endswith(".py"):
            continue
        low = rel.lower()
        if any(
            x in low
            for x in (
                "/.venv/",
                "/venv/",
                "__pycache__",
                ".git/",
                "/site-packages/",
                "/node_modules/",
            )
        ):
            continue
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _chunk_lines(lines: List[str], *, window: int, overlap: int) -> List[Tuple[int, int, str]]:
    """Return (start_line_1based, end_line_1based, text) windows."""
    if window <= 0 or overlap < 0 or overlap >= window:
        overlap = max(0, min(overlap, window - 1))
    step = max(1, window - overlap)
    chunks: List[Tuple[int, int, str]] = []
    n = len(lines)
    i = 0
    while i < n:
        end = min(n, i + window)
        block = lines[i:end]
        text = "".join(block)
        chunks.append((i + 1, end, text))
        if end >= n:
            break
        i += step
    return chunks


def build_source_chunk_index(
    results_dir: Path,
    repo_root: Path,
    nodes: Sequence[Dict[str, Any]],
) -> int:
    """Write ``graphrag_source_chunks.jsonl`` from ``File`` nodes under *repo_root*.

    Args:
        results_dir: Run output directory.
        repo_root: Repository root used when the graph was built.
        nodes: Graph nodes (typically from ``graph.json``).

    Returns:
        Number of chunk records written.
    """
    max_files = max(1, int(os.environ.get("GRAPHRAG_SOURCE_MAX_FILES", "500")))
    max_bytes = max(4096, int(os.environ.get("GRAPHRAG_SOURCE_MAX_BYTES_PER_FILE", "200000")))
    window = max(10, int(os.environ.get("GRAPHRAG_SOURCE_CHUNK_LINES", "90")))
    overlap = max(0, int(os.environ.get("GRAPHRAG_SOURCE_CHUNK_OVERLAP_LINES", "12")))

    try:
        root = repo_root.resolve()
    except OSError:
        return 0
    if not root.is_dir():
        logger.warning("Source index skipped: repo root is not a directory: %s", repo_root)
        return 0

    paths = _py_paths_from_nodes(nodes)[:max_files]
    out_path = results_dir / _CHUNKS_JSONL
    count = 0
    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            for rel in paths:
                abs_path = (root / rel).resolve()
                try:
                    abs_path.relative_to(root)
                except ValueError:
                    continue
                if not abs_path.is_file():
                    continue
                try:
                    raw = abs_path.read_bytes()[:max_bytes]
                except OSError:
                    continue
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("utf-8", errors="replace")
                lines = text.splitlines(keepends=True)
                for start, end, chunk in _chunk_lines(lines, window=window, overlap=overlap):
                    if not chunk.strip():
                        continue
                    rec = {
                        "path": rel,
                        "start_line": start,
                        "end_line": end,
                        "text": chunk[:12000],
                    }
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    count += 1
    except OSError as exc:
        logger.warning("Could not write source chunk index: %s", exc)
        return 0

    meta_path = results_dir / _INDEX_META
    try:
        meta_path.write_text(
            json.dumps(
                {"schema_version": 1, "chunk_count": count, "repo_root": str(root)},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not write %s: %s", meta_path.name, exc)
    logger.info("GraphRAG source index wrote %d chunks under %s", count, results_dir.name)
    return count


def _ensure_chunk_index(run_dir_path: Path) -> int:
    """Build chunk JSONL on demand if meta + repo exist but chunks are missing."""
    meta = load_run_meta(run_dir_path)
    root_s = meta.get("source_repo_root")
    if not isinstance(root_s, str) or not root_s.strip():
        return 0
    repo = Path(root_s)
    chunks_path = run_dir_path / _CHUNKS_JSONL
    if chunks_path.is_file() and chunks_path.stat().st_size > 0:
        return 0
    graph_path = run_dir_path / "graph.json"
    if not graph_path.is_file():
        return 0
    doc = load_graph_document(graph_path)
    nodes = list(doc.get("nodes") or [])
    return build_source_chunk_index(run_dir_path, repo, nodes)


def retrieve_source_context_for_llm(
    run_dir_path: Path,
    query: str,
    *,
    max_chars: int = 14_000,
    top_rank: int = 28,
) -> Tuple[str, Dict[str, Any]]:
    """Rank indexed source chunks by lexical relevance and format for the LLM.

    Args:
        run_dir_path: One ``results/web_analysis_*`` directory.
        query: User question.
        max_chars: Total character budget for returned excerpts.
        top_rank: How many highest-scoring chunks to consider before trimming by *max_chars*.

    Returns:
        ``(excerpt_block, diagnostics)``; block may be empty when no index or repo.
        When ``enabled`` is true, diagnostics may include ``included_chunks`` (ordered
        list of path/line/score metadata for excerpts actually packed into the block),
        ``candidates_scored``, ``top_rank_cap``, and ``max_chars_budget``.
    """
    diag: Dict[str, Any] = {"enabled": False, "chunks_used": 0}
    meta = load_run_meta(run_dir_path)
    root_s = meta.get("source_repo_root")
    if not isinstance(root_s, str) or not root_s.strip():
        diag["reason"] = "no source_repo_root in graphrag_run_meta.json"
        return "", diag

    repo = Path(root_s)
    if not repo.is_dir():
        diag["reason"] = "source_repo_root no longer exists on disk"
        return "", diag

    chunks_path = run_dir_path / _CHUNKS_JSONL
    if not chunks_path.is_file() or chunks_path.stat().st_size == 0:
        _ensure_chunk_index(run_dir_path)
    if not chunks_path.is_file() or chunks_path.stat().st_size == 0:
        diag["reason"] = "no source chunks (build failed or no Python files)"
        return "", diag

    diag["enabled"] = True
    scored: List[Tuple[float, Dict[str, Any]]] = []
    try:
        with chunks_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                blob = f"{rec.get('path', '')}\n{rec.get('text', '')}"
                s = score_query_against_blob(query, blob.lower())
                if s > 0:
                    scored.append((s, rec))
    except OSError as exc:
        diag["reason"] = str(exc)
        return "", diag

    if not scored:
        try:
            with chunks_path.open(encoding="utf-8") as fh2:
                for line in fh2:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(rec, dict):
                        scored.append((0.0, rec))
                    if len(scored) >= min(18, top_rank):
                        break
        except OSError:
            pass

    scored.sort(key=lambda x: x[0], reverse=True)
    parts: List[str] = []
    included: List[Dict[str, Any]] = []
    used = 0
    budget = max_chars
    for rank, (_s, rec) in enumerate(scored[:top_rank], start=1):
        path = str(rec.get("path", ""))
        a = int(rec.get("start_line", 0))
        b = int(rec.get("end_line", 0))
        body = str(rec.get("text", ""))
        block = f"#### {path} (lines {a}-{b})\n```python\n{body}\n```\n"
        truncated = False
        if len(block) > budget:
            truncated = True
            block = block[: max(0, budget - 40)] + "\n…[truncated]\n```\n"
        if budget <= 0:
            break
        parts.append(block)
        used += 1
        budget -= len(block)
        included.append(
            {
                "rank": rank,
                "path": path,
                "start_line": a,
                "end_line": b,
                "score": round(float(_s), 4),
                "approx_chars": len(block),
                "truncated": truncated,
            }
        )
        if budget <= 0:
            break

    diag["chunks_used"] = used
    diag["candidates_scored"] = len(scored)
    diag["top_rank_cap"] = top_rank
    diag["max_chars_budget"] = max_chars
    diag["included_chunks"] = included
    return "\n".join(parts).strip(), diag
