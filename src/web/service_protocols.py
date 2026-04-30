"""Structural typing contracts for web-layer services (dependency inversion)."""

from __future__ import annotations

from typing import Any, Dict, Protocol


class CompatibilityService(Protocol):
    """Port for pre-analysis repository scoring."""

    def run_compatibility_check(self, repo_path: str) -> Dict[str, Any]:
        """Return score, details, warnings, and metadata for *repo_path*."""
        ...


class AnalysisPipelineService(Protocol):
    """Port for full graph build and analysis used after compatibility passes."""

    def run_analysis_pipeline(self, repo_path: str) -> Dict[str, Any]:
        """Return graph payload, report text, logs, and output directory paths."""
        ...
