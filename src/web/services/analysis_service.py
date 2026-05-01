from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.compatibility.repo_checker import RepoCompatibilityChecker
from src.pipeline import run_repository_pipeline
from src.pipeline.output_paths import new_web_session_results_dir


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
        self, repo_path: str, *, results_folder_slug: str | None = None
    ) -> Dict[str, Any]:
        """Execute the full build/analyze (and optional visualize) pipeline.

        Args:
            repo_path: Filesystem path to the repository root.
            results_folder_slug: Short label for ``results/web_analysis_*`` folder names
                (from upload/clone; optional for backward compatibility).

        Returns:
            Keys: ``graph_data``, ``analysis_text``, ``pipeline_output``, ``results_dir``,
            ``visual_summary_text`` (when visualization runs), and ``visual_summary_path``.

        Raises:
            OSError: If reading or writing pipeline artifacts fails.
            ValueError: If graph validation fails.
        """
        results_dir = new_web_session_results_dir(results_folder_slug)
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
        )

        visual_summary_text = ""
        if result.visual_summary_path is not None:
            visual_summary_text = Path(result.visual_summary_path).read_text(encoding="utf-8")

        return {
            "graph_data": dict(result.graph_document),
            "analysis_text": result.analysis_text,
            "pipeline_output": "\n".join(result.log_lines),
            "results_dir": str(results_dir),
            "visual_summary_text": visual_summary_text,
            "visual_summary_path": str(result.visual_summary_path)
            if result.visual_summary_path
            else None,
        }
