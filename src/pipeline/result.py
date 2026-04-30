"""Structured outcome of a full repository pipeline run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class PipelineRunResult:
    """All artifacts and messages produced by :func:`run_repository_pipeline`."""

    graph_document: Mapping[str, Any]
    analysis_text: str
    graph_path: Path
    analysis_path: Path
    visual_summary_path: Path | None
    log_lines: tuple[str, ...]
