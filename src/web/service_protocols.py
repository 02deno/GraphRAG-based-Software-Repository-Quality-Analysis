"""Structural typing contracts for web-layer services (dependency inversion)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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
        ``analysis_text``, ``analysis_view`` (structured metrics for the results UI),
        ``visual_summary_view`` (degree tables JSON), ``pipeline_sections`` (log cards),
        ``pipeline_output``, ``results_dir``, ``visual_summary_text``, and
        ``visual_summary_path`` (path or ``None``). Reloaded runs may also expose
        ``llm_insights`` when ``graphrag_llm_insights.json`` exists (see ``POST …/llm-insights``).
        """
        ...


class ChatCompletionClient(Protocol):
    """Minimal port for OpenAI-compatible chat completion HTTP APIs.

    Implementations may also define ``stream_chat_completion(...) -> Iterator[str]``
    for the same ``POST /chat/completions`` endpoint with ``stream: true``; the
    workspace SSE path uses it for token-by-token assistant text.
    """

    def complete_chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Return assistant message text from a chat completion call."""
        ...
