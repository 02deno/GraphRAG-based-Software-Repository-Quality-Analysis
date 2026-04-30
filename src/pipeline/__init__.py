"""Repository analysis pipeline (build graph, analyze, optional visualization)."""

from .result import PipelineRunResult
from .run_pipeline import run_repository_pipeline

__all__ = ["PipelineRunResult", "run_repository_pipeline"]
