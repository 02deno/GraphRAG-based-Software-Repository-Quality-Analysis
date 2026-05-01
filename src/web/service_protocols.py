"""Structural typing contracts for web-layer services (dependency inversion)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, Protocol


class CompatibilityService(Protocol):
    """Port for pre-analysis repository scoring."""

    def run_compatibility_check(self, repo_path: str) -> Dict[str, Any]:
        """Return score, details, warnings, and metadata for *repo_path*."""
        ...


class AnalysisPipelineService(Protocol):
    """Port for full graph build and analysis used after compatibility passes."""

    def run_analysis_pipeline(
        self,
        repo_path: str,
        *,
        results_folder_slug: str | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> Dict[str, Any]:
        """Return graph payload, reports, logs, and artifact paths.

        Optional ``results_folder_slug`` names ``results/web_analysis_<slug>_…`` folders.
        Optional ``progress_callback`` receives ``(percent, message)`` during long runs.

        Expected keys include ``graph_data`` (dict with ``nodes``, ``edges``,
        ``implemented_node_types``, ``implemented_edge_types``, …),
        ``analysis_text``, ``pipeline_output``, ``results_dir``,
        ``visual_summary_text``, and ``visual_summary_path`` (path or ``None``).
        """
        ...
