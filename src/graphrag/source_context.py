"""Persist repository root metadata and lexical source chunks for GraphRAG chat.

Chunks are written to ``graphrag_source_chunks.jsonl``: ``.py`` excerpts from
``File`` nodes in ``graph.json``, optional repo-wide ``*.md`` and other root
documentation, and optional **analysis run** excerpts (``analysis_view`` summary,
``analysis.txt``, ``visual_summary.txt``) under virtual ``_analysis/`` paths for
the same lexical scoring at retrieval time.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from src.graph.json_document import load_graph_document
from src.graphrag.analysis_context import format_analysis_view_summary
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


_ROOT_DOC_FILENAMES: Tuple[str, ...] = (
    "README.md",
    "readme.md",
    "README.rst",
    "README.txt",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "SECURITY.md",
)


def _doc_rel_excluded(rel: str) -> bool:
    low = rel.replace("\\", "/").lower()
    needles = (
        "/.venv/",
        "/venv/",
        "__pycache__",
        "/.git/",
        "/site-packages/",
        "/node_modules/",
        "/dist/",
        "/build/",
    )
    return any(n in low for n in needles)


def _documentation_paths(repo_root: Path) -> List[str]:
    """Return repo-relative paths: root README-style files and all ``*.md`` under the repo.

    Controlled by ``GRAPHRAG_SOURCE_MAX_DOC_FILES`` (``0`` disables; default ``120``).
    Skips paths under venv, ``.git``, ``node_modules``, etc.
    """
    max_doc = int(os.environ.get("GRAPHRAG_SOURCE_MAX_DOC_FILES", "120"))
    if max_doc <= 0:
        return []
    out: List[str] = []
    seen: set[str] = set()
    try:
        root = repo_root.resolve()
    except OSError:
        return []
    if not root.is_dir():
        return []

    for name in _ROOT_DOC_FILENAMES:
        if len(out) >= max_doc:
            break
        p = root / name
        if not p.is_file():
            continue
        rel = name.replace("\\", "/")
        if _doc_rel_excluded(rel):
            continue
        low = rel.lower()
        if not (low.endswith(".md") or low.endswith(".rst") or low.endswith(".txt")):
            continue
        if rel not in seen:
            seen.add(rel)
            out.append(rel)

    for p in sorted(root.rglob("*.md")):
        if len(out) >= max_doc:
            break
        if not p.is_file():
            continue
        try:
            rel = str(p.resolve().relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        if _doc_rel_excluded(rel) or rel in seen:
            continue
        seen.add(rel)
        out.append(rel)

    return out


def _write_jsonl_chunks_for_rel(
    fh,
    root: Path,
    rel: str,
    *,
    window: int,
    overlap: int,
    max_bytes: int,
) -> int:
    """Append chunk JSONL lines for one repo-relative file; returns lines written."""
    abs_path = (root / rel).resolve()
    try:
        abs_path.relative_to(root)
    except ValueError:
        return 0
    if not abs_path.is_file():
        return 0
    try:
        raw = abs_path.read_bytes()[:max_bytes]
    except OSError:
        return 0
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    count = 0
    is_py = rel.lower().endswith(".py")
    for start, end, chunk in _chunk_lines(lines, window=window, overlap=overlap):
        if not chunk.strip():
            continue
        rec: Dict[str, Any] = {
            "path": rel,
            "start_line": start,
            "end_line": end,
            "text": chunk[:12000],
        }
        if not is_py:
            rec["kind"] = "documentation"
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        count += 1
    return count


def _write_virtual_text_chunks(
    fh,
    *,
    virtual_path: str,
    text: str,
    window: int,
    overlap: int,
    max_blob_chars: int,
    max_chunks: int,
    kind: str,
) -> int:
    """Write JSONL chunk lines for synthetic *virtual_path* content (e.g. analysis bundle)."""
    if not text.strip() or max_chunks <= 0:
        return 0
    blob = text[:max_blob_chars]
    lines = blob.splitlines(keepends=True)
    count = 0
    for start, end, chunk in _chunk_lines(lines, window=window, overlap=overlap):
        if not chunk.strip():
            continue
        rec: Dict[str, Any] = {
            "path": virtual_path,
            "start_line": start,
            "end_line": end,
            "text": chunk[:12000],
            "kind": kind,
        }
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        count += 1
        if count >= max_chunks:
            break
    return count


def _write_analysis_run_chunks(fh, results_dir: Path) -> int:
    """Append chunks derived from this run's graph analysis artifacts (virtual ``_analysis/`` paths)."""
    flag = os.environ.get("GRAPHRAG_SOURCE_DISABLE_ANALYSIS_CHUNKS", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return 0
    win = max(10, int(os.environ.get("GRAPHRAG_SOURCE_ANALYSIS_CHUNK_LINES", "80")))
    ovl = max(0, int(os.environ.get("GRAPHRAG_SOURCE_ANALYSIS_CHUNK_OVERLAP_LINES", "12")))
    max_blob = max(4096, int(os.environ.get("GRAPHRAG_SOURCE_ANALYSIS_MAX_BYTES", "400000")))
    per_file_cap = max(1, int(os.environ.get("GRAPHRAG_SOURCE_MAX_CHUNKS_PER_ANALYSIS_FILE", "60")))
    total = 0
    view_path = results_dir / "analysis_view.json"
    if view_path.is_file():
        try:
            raw_v = view_path.read_text(encoding="utf-8")
            view = json.loads(raw_v)
            if isinstance(view, dict):
                formatted = format_analysis_view_summary(view, max_chars=min(120_000, max_blob))
                total += _write_virtual_text_chunks(
                    fh,
                    virtual_path="_analysis/analysis_view.txt",
                    text=formatted,
                    window=win,
                    overlap=ovl,
                    max_blob_chars=max_blob,
                    max_chunks=per_file_cap,
                    kind="analysis_report",
                )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.debug("Skipping analysis_view.json chunks: %s", exc)

    for fname, vpath in (
        ("analysis.txt", "_analysis/analysis.txt"),
        ("visual_summary.txt", "_analysis/visual_summary.txt"),
    ):
        p = results_dir / fname
        if not p.is_file():
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")[:max_blob]
        except OSError as exc:
            logger.debug("Skipping %s chunks: %s", fname, exc)
            continue
        total += _write_virtual_text_chunks(
            fh,
            virtual_path=vpath,
            text=txt,
            window=win,
            overlap=ovl,
            max_blob_chars=max_blob,
            max_chunks=per_file_cap,
            kind="analysis_report",
        )

    vsum = results_dir / "visual_summary_view.json"
    if vsum.is_file():
        try:
            raw_j = vsum.read_text(encoding="utf-8", errors="replace")[:max_blob]
            obj = json.loads(raw_j)
            if isinstance(obj, dict):
                pretty = json.dumps(obj, indent=2, ensure_ascii=False)[:max_blob]
                total += _write_virtual_text_chunks(
                    fh,
                    virtual_path="_analysis/visual_summary_view.txt",
                    text=pretty,
                    window=win,
                    overlap=ovl,
                    max_blob_chars=max_blob,
                    max_chunks=per_file_cap,
                    kind="analysis_report",
                )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            logger.debug("Skipping visual_summary_view.json chunks: %s", exc)

    return total


def _fence_lang_for_source_path(path: str) -> str:
    """Return a Markdown code-fence language tag for *path*."""
    low = path.lower()
    if low.startswith("_analysis/"):
        return "text"
    if low.endswith(".py"):
        return "python"
    if low.endswith(".md"):
        return "markdown"
    if low.endswith(".rst"):
        return "rst"
    return "text"


def build_source_chunk_index(
    results_dir: Path,
    repo_root: Path,
    nodes: Sequence[Dict[str, Any]],
) -> int:
    """Write ``graphrag_source_chunks.jsonl`` from ``File`` nodes and documentation.

    Python chunks use ``File`` ``*.py`` paths from *nodes* (unchanged). Documentation
    chunks include root README-style files and **all** ``*.md`` paths under the
    repository (subject to ``GRAPHRAG_SOURCE_MAX_DOC_FILES``). **Analysis** chunks
    append formatted ``analysis_view`` metrics plus ``analysis.txt`` /
    ``visual_summary*.txt|json`` under virtual ``_analysis/`` paths.

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
    doc_window = max(10, int(os.environ.get("GRAPHRAG_SOURCE_DOC_CHUNK_LINES", "120")))
    doc_overlap = max(0, int(os.environ.get("GRAPHRAG_SOURCE_DOC_CHUNK_OVERLAP_LINES", "24")))

    try:
        root = repo_root.resolve()
    except OSError:
        return 0
    if not root.is_dir():
        logger.warning("Source index skipped: repo root is not a directory: %s", repo_root)
        return 0

    py_paths = _py_paths_from_nodes(nodes)[:max_files]
    doc_paths = _documentation_paths(root)
    seen_py = set(py_paths)
    doc_only = [p for p in doc_paths if p not in seen_py]

    out_path = results_dir / _CHUNKS_JSONL
    count = 0
    analysis_chunk_count = 0
    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            for rel in py_paths:
                count += _write_jsonl_chunks_for_rel(
                    fh, root, rel, window=window, overlap=overlap, max_bytes=max_bytes
                )
            for rel in doc_only:
                count += _write_jsonl_chunks_for_rel(
                    fh, root, rel, window=doc_window, overlap=doc_overlap, max_bytes=max_bytes
                )
            analysis_chunk_count = _write_analysis_run_chunks(fh, results_dir)
            count += analysis_chunk_count
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
    logger.info(
        "GraphRAG source index wrote %d chunks (%d py files, %d doc paths, %d analysis) under %s",
        count,
        len(py_paths),
        len(doc_only),
        analysis_chunk_count,
        results_dir.name,
    )
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


def _wants_graph_pipeline_metrics(query: str) -> bool:
    """True when the user is likely asking for this run's graph analysis artifacts."""
    q = (query or "").lower()
    needles_en = (
        "graph analysis",
        "analysis result",
        "analysis results",
        "centrality",
        "betweenness",
        "pagerank",
        "community",
        "communities",
        "louvain",
        "modularity",
        "risk candidate",
        "composite z-score",
        "visual summary",
        "degree centrality",
        "pipeline metrics",
        "precomputed metrics",
        "graph metrics",
        "graph statistic",
        "graph statistics",
    )
    needles_tr = (
        "graf analiz",
        "grafik analiz",
        "merkeziyet",
        "topluluk",
        "risk analiz",
        "analiz sonuç",
        "analiz sonuçları",
    )
    return any(n in q for n in needles_en) or any(n in q for n in needles_tr)


def _repo_scope_intent(query: str) -> bool:
    """True when the user likely asks about the product/codebase, not pipeline JSON layout."""
    q = (query or "").lower()
    needles_en = (
        "this repo",
        "the repo",
        "this project",
        "the project",
        "this codebase",
        "the codebase",
        "what does it",
        "what is it",
        "tell me about",
        "describe the",
        "describe this",
        "overview",
        "main modules",
        "entry point",
        "entry points",
        "what is this repository",
        "uploaded repo",
        "cloned repo",
    )
    needles_tr = (
        "bu repo",
        "şu repo",
        "yüklenen repo",
        "proje nedir",
        "repo nedir",
        "bu proje",
        "proje hakkında",
        "repo hakkında",
        "genel bilgi",
        "nedir bu",
    )
    return any(n in q for n in needles_en) or any(n in q for n in needles_tr)


def _analysis_chunk_repo_intent_penalty(query: str, rec: Dict[str, Any]) -> float:
    """Demote ``_analysis/*`` chunks when the user asks about the codebase, not graph metrics.

    ``visual_summary_view`` / ``analysis.txt`` excerpts often contain absolute host paths
    (e.g. a parent ``GraphRAG_Project`` checkout) and schema metadata; without this penalty
    the model may wrongly describe the **tooling checkout** instead of the analyzed repository.
    """
    if _wants_graph_pipeline_metrics(query):
        return 0.0
    if not _repo_scope_intent(query):
        return 0.0
    path = str(rec.get("path", ""))
    if rec.get("kind") == "analysis_report" or path.startswith("_analysis/"):
        return -88.0
    return 0.0


def _analysis_chunk_score_boost(query: str, rec: Dict[str, Any]) -> float:
    """Raise lexical rank for persisted ``_analysis/*`` chunks when the query targets metrics."""
    if not _wants_graph_pipeline_metrics(query):
        return 0.0
    path = str(rec.get("path", ""))
    if rec.get("kind") != "analysis_report" and not path.startswith("_analysis/"):
        return 0.0
    # Typical doc overlap scores are ~5–25; keep bonus below substring hit (+80) but above docs.
    return 72.0


def _diagnostic_excerpt_char_limit() -> int:
    """Max characters of raw chunk text to embed in ``included_chunks`` for the UI (0 = off)."""
    raw = os.environ.get("GRAPHRAG_SOURCE_DIAGNOSTIC_EXCERPT_CHARS", "4000").strip()
    try:
        n = int(raw)
    except ValueError:
        return 4000
    return max(0, n)


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
        Chunks whose paths start with ``_analysis/`` (pipeline metrics text) receive a
        **score bonus** when the question clearly targets graph-analysis metrics, so they
        are not drowned out by generic Markdown documentation hits. When the question is
        about the **product repository** (not graph metrics), ``_analysis/*`` excerpts are
        **demoted** so absolute host paths and schema headers do not override real source files.
        When ``enabled`` is true, diagnostics may include ``included_chunks`` (ordered
        list of path/line/score metadata for excerpts actually packed into the block),
        optional per-chunk ``excerpt`` text for UI (length capped by
        ``GRAPHRAG_SOURCE_DIAGNOSTIC_EXCERPT_CHARS``), optional ``kind``, plus
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
        diag["reason"] = "no source chunks (index empty: no Python files and no documentation paths indexed)"
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
                s += _analysis_chunk_score_boost(query, rec)
                s += _analysis_chunk_repo_intent_penalty(query, rec)
                if s > 0:
                    scored.append((s, rec))
    except OSError as exc:
        diag["reason"] = str(exc)
        return "", diag

    if not scored:
        skip_analysis_fallback = _repo_scope_intent(query) and not _wants_graph_pipeline_metrics(
            query
        )
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
                        if skip_analysis_fallback:
                            pth = str(rec.get("path", ""))
                            if pth.startswith("_analysis/") or rec.get("kind") == "analysis_report":
                                continue
                        scored.append((0.0, rec))
                    if len(scored) >= min(18, top_rank):
                        break
        except OSError:
            pass

    if not scored:
        try:
            with chunks_path.open(encoding="utf-8") as fh3:
                for line in fh3:
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
        lang = _fence_lang_for_source_path(path)
        block = f"#### {path} (lines {a}-{b})\n```{lang}\n{body}\n```\n"
        truncated = False
        if len(block) > budget:
            truncated = True
            block = block[: max(0, budget - 40)] + "\n…[truncated]\n```\n"
        if budget <= 0:
            break
        parts.append(block)
        used += 1
        budget -= len(block)
        ex_cap = _diagnostic_excerpt_char_limit()
        entry: Dict[str, Any] = {
            "rank": rank,
            "path": path,
            "start_line": a,
            "end_line": b,
            "score": round(float(_s), 4),
            "approx_chars": len(block),
            "truncated": truncated,
        }
        if isinstance(rec.get("kind"), str):
            entry["kind"] = rec["kind"]
        if ex_cap > 0 and body:
            entry["excerpt"] = body[:ex_cap]
        included.append(entry)
        if budget <= 0:
            break

    diag["chunks_used"] = used
    diag["candidates_scored"] = len(scored)
    diag["top_rank_cap"] = top_rank
    diag["max_chars_budget"] = max_chars
    diag["included_chunks"] = included
    return "\n".join(parts).strip(), diag
