from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict

from src.compatibility.repo_checker import RepoCompatibilityChecker
from src.graphrag.source_context import build_source_chunk_index, write_run_meta
from src.pipeline import run_repository_pipeline
from src.pipeline.output_paths import new_web_session_results_dir
from src.pipeline.result import PipelineRunResult

logger = logging.getLogger(__name__)


def _png_display_title(filename: str) -> str:
    """Map a generated PNG filename to a short UI label."""
    key = filename.lower()
    ordered = (
        ("structure_imports", "Structure (IMPORTS only)"),
        ("structure_in_file", "Structure (IN_FILE only)"),
        ("structure_calls", "Structure (CALLS only)"),
        ("structure_tests", "Structure (TESTS only)"),
        ("structure_modified_by", "Structure (MODIFIED_BY only)"),
        ("betweenness_imports", "Betweenness centrality (IMPORTS)"),
        ("betweenness_calls", "Betweenness centrality (CALLS)"),
        ("pagerank_imports", "PageRank (IMPORTS)"),
        ("pagerank_calls", "PageRank (CALLS)"),
        ("degree_analysis_imports", "Degree chart (IMPORTS)"),
        ("degree_analysis_in_file", "Degree chart (IN_FILE)"),
        ("degree_analysis_calls", "Degree chart (CALLS)"),
        ("degree_analysis_tests", "Degree chart (TESTS)"),
        ("degree_analysis_modified_by", "Degree chart (MODIFIED_BY)"),
        ("degree_analysis", "Degree chart (combined)"),
        ("_structure", "Structure (all edges)"),
    )
    for needle, title in ordered:
        if needle in key:
            return title
    return filename


def collect_visual_gallery_entries(results_dir: Path) -> list[dict[str, str]]:
    """List PNG artifacts under ``results_dir/visuals`` for the results UI."""
    from src.web.results_paths import is_safe_visual_png_filename

    visuals = results_dir / "visuals"
    if not visuals.is_dir():
        return []
    entries: list[dict[str, str]] = []
    for p in sorted(visuals.glob("*.png")):
        if is_safe_visual_png_filename(p.name):
            entries.append({"name": p.name, "title": _png_display_title(p.name)})
        else:
            logger.warning("Skipping unsafe or non-PNG gallery name: %s", p.name)
    return entries


def _is_pipeline_section_start(line: str) -> bool:
    """Return True when *line* begins a new logical block in the pipeline log."""
    s = line.strip()
    if not s:
        return False
    prefixes = (
        "Building graph for repository:",
        "Graph saved to:",
        "Total nodes:",
        "Running analysis",
        "Analysis saved to:",
        "Analysis view JSON saved",
        "Generating visualization",
        "Skipping visualization",
        "Skipping structure",
        "Overall structure visualization",
        "IMPORTS structure visualization",
        "IN_FILE structure visualization",
        "CALLS structure visualization",
        "TESTS structure visualization",
        "MODIFIED_BY structure visualization",
        "Visualization:",
        "Overall degree analysis saved",
        "IMPORTS degree analysis saved",
        "IN_FILE degree analysis saved",
        "CALLS degree analysis saved",
        "TESTS degree analysis saved",
        "MODIFIED_BY degree analysis saved",
        "Visual summary saved",
        "Visual summary view JSON",
        "Pipeline finished",
    )
    if any(s.startswith(p) for p in prefixes):
        return True
    if "betweenness analysis saved to:" in s or "PageRank analysis saved to:" in s:
        return True
    return False


def build_pipeline_log_sections(text: str) -> list[dict[str, Any]]:
    """Split flat pipeline log text into titled blocks for the results UI."""
    lines = text.splitlines()
    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                groups.append(current)
                current = []
            continue
        if _is_pipeline_section_start(line) and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)
    sections: list[dict[str, Any]] = []
    for block in groups:
        title = block[0].strip()
        if len(title) > 88:
            title = title[:85] + "…"
        sections.append({"title": title, "lines": block})
    return sections


def package_web_results(
    results_dir: Path,
    result: PipelineRunResult,
    *,
    source_repo_path: str | None = None,
) -> Dict[str, Any]:
    """Shape the dict passed to ``results_final.html`` after a pipeline run.

    Adds ``analysis_view`` (card UI payload, ``schema_version`` 1) alongside legacy
    ``analysis_text`` for downloads and the collapsible raw report, plus
    ``visual_summary_view`` and ``pipeline_sections`` for structured cards.

    When ``source_repo_path`` is set, writes ``graphrag_run_meta.json`` and builds
    ``graphrag_source_chunks.jsonl`` for GraphRAG source excerpts (best-effort).

    Returns:
        Payload dict including ``graphrag_run_meta`` (``schema_version``, ``source_repo_root``).
    """
    pipeline_text = "\n".join(result.log_lines)
    pipeline_path = results_dir / "pipeline.txt"
    try:
        pipeline_path.write_text(pipeline_text + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist pipeline.txt under %s: %s", results_dir, exc)

    visual_summary_text = ""
    if result.visual_summary_path is not None:
        visual_summary_text = Path(result.visual_summary_path).read_text(encoding="utf-8")

    resolved_repo: str | None = None
    if source_repo_path:
        try:
            resolved_repo = str(Path(source_repo_path).resolve())
        except OSError:
            resolved_repo = source_repo_path.strip() or None
    write_run_meta(results_dir, resolved_repo)
    if resolved_repo:
        try:
            n_chunks = build_source_chunk_index(
                results_dir,
                Path(resolved_repo),
                list(result.graph_document.get("nodes") or []),
            )
            logger.info("GraphRAG source chunk index chunks=%d", n_chunks)
        except Exception:
            logger.exception("GraphRAG source chunk index failed (non-fatal)")

    return {
        "graph_data": dict(result.graph_document),
        "analysis_text": result.analysis_text,
        "analysis_view": dict(result.analysis_view),
        "pipeline_output": pipeline_text,
        "pipeline_sections": build_pipeline_log_sections(pipeline_text),
        "results_dir": str(results_dir.resolve()),
        "results_run_dir": results_dir.name,
        "visual_summary_text": visual_summary_text,
        "visual_summary_view": dict(result.visual_summary_view),
        "visual_summary_path": str(result.visual_summary_path)
        if result.visual_summary_path
        else None,
        "visual_gallery": collect_visual_gallery_entries(results_dir),
        "graphrag_run_meta": {"schema_version": 1, "source_repo_root": resolved_repo},
    }


def load_results_from_run_directory(run_path: Path) -> Dict[str, Any]:
    """Rebuild the results payload from a prior ``results/web_analysis_*`` folder."""
    graph_path = run_path / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    analysis_path = run_path / "analysis.txt"
    analysis_text = analysis_path.read_text(encoding="utf-8") if analysis_path.exists() else ""
    vis_path = run_path / "visual_summary.txt"
    visual_summary_text = vis_path.read_text(encoding="utf-8") if vis_path.exists() else ""
    pl_path = run_path / "pipeline.txt"
    pipeline_output = pl_path.read_text(encoding="utf-8") if pl_path.exists() else ""
    view_path = run_path / "analysis_view.json"
    analysis_view: Dict[str, Any] = {}
    if view_path.exists():
        try:
            loaded = json.loads(view_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                analysis_view = loaded
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read analysis_view.json under %s: %s", run_path, exc)
            analysis_view = {}
    vsum_view_path = run_path / "visual_summary_view.json"
    graphrag_meta: Dict[str, Any] = {}
    meta_path = run_path / "graphrag_run_meta.json"
    if meta_path.exists():
        try:
            gm = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(gm, dict):
                graphrag_meta = gm
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read graphrag_run_meta.json under %s: %s", run_path, exc)
    visual_summary_view: Dict[str, Any] = {}
    if vsum_view_path.exists():
        try:
            loaded_vs = json.loads(vsum_view_path.read_text(encoding="utf-8"))
            if isinstance(loaded_vs, dict):
                visual_summary_view = loaded_vs
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read visual_summary_view.json under %s: %s", run_path, exc)
            visual_summary_view = {}
    pipeline_sections = build_pipeline_log_sections(pipeline_output)
    return {
        "graph_data": graph,
        "analysis_text": analysis_text,
        "analysis_view": analysis_view,
        "pipeline_output": pipeline_output,
        "pipeline_sections": pipeline_sections,
        "results_dir": str(run_path.resolve()),
        "results_run_dir": run_path.name,
        "visual_summary_text": visual_summary_text,
        "visual_summary_view": visual_summary_view,
        "visual_summary_path": str(vis_path) if vis_path.exists() else None,
        "visual_gallery": collect_visual_gallery_entries(run_path),
        "graphrag_run_meta": graphrag_meta,
    }


class AnalysisService:
    """Coordinates compatibility checks and the graph analysis pipeline for the web UI.

    Satisfies the structural contracts ``CompatibilityService`` and
    ``AnalysisPipelineService`` in ``src.web.service_protocols`` (duck typing).
    """

    def __init__(self) -> None:
        """Create a service with a dedicated compatibility checker instance."""
        self.compatibility_checker = RepoCompatibilityChecker()

    def run_compatibility_check(self, repo_path: str) -> Dict[str, Any]:
        """Run compatibility scoring on a repository path.

        Args:
            repo_path: Filesystem path to the repository root.

        Returns:
            Dict with score, details, warnings, and related metadata.
        """
        return self.compatibility_checker.analyze_repository(repo_path)

    def run_analysis_pipeline(
        self,
        repo_path: str,
        *,
        results_folder_slug: str | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> Dict[str, Any]:
        """Execute the full build/analyze (and optional visualize) pipeline.

        Args:
            repo_path: Filesystem path to the repository root.
            results_folder_slug: Short label for ``results/web_analysis_*`` folder names
                (from upload/clone; optional for backward compatibility).
            progress_callback: Optional ``(percent, message)`` hook for streaming UIs.

        Returns:
            Keys include ``graph_data``, ``analysis_text``, ``analysis_view`` (structured
            metrics for the card UI), ``visual_summary_view`` (degree leaders by edge type),
            ``pipeline_sections`` (phase cards), ``pipeline_output``, ``results_dir``,
            ``results_run_dir``, ``visual_summary_text``, ``visual_summary_path``,
            ``visual_gallery`` (PNG list for the UI), ``graphrag_run_meta`` (``schema_version``,
            ``source_repo_root`` for source chunk indexing), and on-disk
            ``graphrag_source_chunks.jsonl`` when indexing succeeds.

        Raises:
            OSError: If reading or writing pipeline artifacts fails.
            ValueError: If graph validation fails.
        """
        results_dir = new_web_session_results_dir(results_folder_slug)
        logger.info(
            "Starting analysis pipeline repo_path=%s results_dir=%s",
            repo_path,
            results_dir.name,
        )
        graph_output = results_dir / "graph.json"
        analysis_output = results_dir / "analysis.txt"
        visual_summary_output = results_dir / "visual_summary.txt"

        result = run_repository_pipeline(
            Path(repo_path).resolve(),
            graph_output=graph_output,
            analysis_output=analysis_output,
            visual_summary_output=visual_summary_output,
            visual_artifacts_dir=results_dir / "visuals",
            skip_visualization=False,
            top_k=10,
            progress_callback=progress_callback,
        )

        payload = package_web_results(results_dir, result, source_repo_path=repo_path)
        logger.info(
            "Finished analysis pipeline results_dir=%s nodes=%s edges=%s",
            results_dir.name,
            len(payload.get("graph_data", {}).get("nodes", [])),
            len(payload.get("graph_data", {}).get("edges", [])),
        )
        return payload
