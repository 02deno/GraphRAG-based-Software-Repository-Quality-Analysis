from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict

from src.compatibility.repo_checker import RepoCompatibilityChecker
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
        ("structure_tests", "Structure (TESTS only)"),
        ("degree_analysis_imports", "Degree chart (IMPORTS)"),
        ("degree_analysis_in_file", "Degree chart (IN_FILE)"),
        ("degree_analysis_tests", "Degree chart (TESTS)"),
        ("degree_analysis", "Degree chart (combined)"),
        ("_structure", "Structure (all edges)"),
    )
    for needle, title in ordered:
        if needle in key:
            return title
    return filename


def collect_visual_gallery_entries(results_dir: Path) -> list[dict[str, str]]:
    """List PNG artifacts under ``results_dir/visuals`` for the results UI."""
    visuals = results_dir / "visuals"
    if not visuals.is_dir():
        return []
    return [{"name": p.name, "title": _png_display_title(p.name)} for p in sorted(visuals.glob("*.png"))]


def package_web_results(results_dir: Path, result: PipelineRunResult) -> Dict[str, Any]:
    """Shape the dict passed to ``results_final.html`` after a pipeline run."""
    pipeline_text = "\n".join(result.log_lines)
    pipeline_path = results_dir / "pipeline.txt"
    try:
        pipeline_path.write_text(pipeline_text + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist pipeline.txt under %s: %s", results_dir, exc)

    visual_summary_text = ""
    if result.visual_summary_path is not None:
        visual_summary_text = Path(result.visual_summary_path).read_text(encoding="utf-8")
    return {
        "graph_data": dict(result.graph_document),
        "analysis_text": result.analysis_text,
        "pipeline_output": pipeline_text,
        "results_dir": str(results_dir.resolve()),
        "results_run_dir": results_dir.name,
        "visual_summary_text": visual_summary_text,
        "visual_summary_path": str(result.visual_summary_path)
        if result.visual_summary_path
        else None,
        "visual_gallery": collect_visual_gallery_entries(results_dir),
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
    return {
        "graph_data": graph,
        "analysis_text": analysis_text,
        "pipeline_output": pipeline_output,
        "results_dir": str(run_path.resolve()),
        "results_run_dir": run_path.name,
        "visual_summary_text": visual_summary_text,
        "visual_summary_path": str(vis_path) if vis_path.exists() else None,
        "visual_gallery": collect_visual_gallery_entries(run_path),
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
            Keys include ``graph_data``, ``analysis_text``, ``pipeline_output``,
            ``results_dir``, ``results_run_dir``, ``visual_summary_text``,
            ``visual_summary_path``, and ``visual_gallery`` (PNG list for the UI).

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

        payload = package_web_results(results_dir, result)
        logger.info(
            "Finished analysis pipeline results_dir=%s nodes=%s edges=%s",
            results_dir.name,
            len(payload.get("graph_data", {}).get("nodes", [])),
            len(payload.get("graph_data", {}).get("edges", [])),
        )
        return payload
