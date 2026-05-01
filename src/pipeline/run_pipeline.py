"""Orchestrates graph build, validation, persistence, analysis, and visualization."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from src.analysis.graph_analysis import generate_analysis_text_report, save_analysis_report
from src.graph.graph_builder import GraphBuilder, save_graph
from src.graph.schema import graph_to_dict, validate_graph_contract
from src.visualization.graph_visualization import generate_visual_summary, save_visual_summary

from .output_paths import default_cli_graph_path, default_cli_visual_summary_path
from .result import PipelineRunResult

logger = logging.getLogger(__name__)


def _notify_progress(
    callback: Callable[[int, str], None] | None, percent: int, message: str
) -> None:
    if callback is None:
        return
    try:
        callback(max(0, min(100, int(percent))), message)
    except Exception:
        pass


def run_repository_pipeline(
    repo_path: Path,
    *,
    graph_output: Path,
    analysis_output: Path | None = None,
    visual_summary_output: Path | None = None,
    visual_artifacts_dir: Path | None = None,
    skip_visualization: bool = False,
    top_k: int = 10,
    progress_callback: Callable[[int, str], None] | None = None,
) -> PipelineRunResult:
    """Build a repository graph, analyze it, and optionally generate visual summaries.

    Args:
        repo_path: Absolute path to the repository root.
        graph_output: Where to write the graph JSON document.
        analysis_output: Where to write the text analysis report; if omitted, uses
            the default path derived by :func:`generate_analysis_text_report`.
        visual_summary_output: Optional path for the visual summary text file.
        visual_artifacts_dir: When set, PNG charts and structure plots are written under
            this directory (used by the web app per session). When omitted, defaults
            inside :func:`generate_visual_summary` apply (CLI).
        skip_visualization: When True, skip matplotlib/networkx visualization steps.
        top_k: Rank depth for analysis and visualization summaries.
        progress_callback: Optional ``(percent, message)`` updates for long-running UIs.

    Returns:
        Structured result including the graph document and human-readable analysis text.

    Raises:
        ValueError: If the graph fails schema validation.
        OSError: If reading or writing artifacts fails.
    """
    log_lines: list[str] = []
    repo_path = repo_path.resolve()

    logger.info(
        "pipeline_start repo=%s graph_output=%s skip_visualization=%s",
        repo_path,
        graph_output,
        skip_visualization,
    )
    _notify_progress(progress_callback, 5, "Preparing repository graph build…")
    log_lines.append(f"Building graph for repository: {repo_path}")

    def _graph_file_progress(stage: str, idx: int, total: int, rel_path: str) -> None:
        """Map builder file stages into coarse percent band 7–27 for SSE / UIs.

        To keep the web popup readable, emit only phase start and phase end
        (instead of per-file updates).
        """
        if total <= 0:
            return
        current = idx + 1
        if current != 1 and current != total:
            return
        if stage == "scan":
            lo, hi = 7, 11
        elif stage == "extract":
            lo, hi = 11, 24
        else:
            lo, hi = 24, 27
        span = hi - lo
        pct = lo + int(span * current / max(1, total))
        if current == 1:
            message = f"Graph build [{stage}] started ({total} files)…"
        else:
            message = f"Graph build [{stage}] completed ({total}/{total})."
        _notify_progress(
            progress_callback,
            pct,
            message,
        )

    builder = GraphBuilder(repo_path)
    builder.build(file_progress=_graph_file_progress if progress_callback else None)
    _notify_progress(progress_callback, 28, "Extracted symbols and edges; validating schema…")

    raw = builder.to_dict()
    graph_document = graph_to_dict(raw["nodes"], raw["edges"])
    validate_graph_contract(graph_document["nodes"], graph_document["edges"])
    _notify_progress(progress_callback, 42, "Saving graph JSON…")
    save_graph(graph_document, graph_output)
    log_lines.append(f"Graph saved to: {graph_output}")
    log_lines.append(f"Total nodes: {len(graph_document['nodes'])}")
    log_lines.append(f"Total edges: {len(graph_document['edges'])}")
    logger.info(
        "graph_saved path=%s nodes=%d edges=%d",
        graph_output,
        len(graph_document["nodes"]),
        len(graph_document["edges"]),
    )
    _notify_progress(
        progress_callback,
        50,
        f"Graph JSON written ({len(graph_document['nodes'])} nodes, {len(graph_document['edges'])} edges).",
    )

    log_lines.append("")
    log_lines.append("Running analysis...")
    _notify_progress(progress_callback, 52, f"Loading graph JSON for analysis: {graph_output.name}")
    report, default_report_path = generate_analysis_text_report(
        graph_output,
        top_k_value=top_k,
        progress_callback=progress_callback,
    )
    final_analysis_path = analysis_output if analysis_output is not None else default_report_path
    save_analysis_report(report, final_analysis_path)
    log_lines.append(f"Analysis saved to: {final_analysis_path}")
    _notify_progress(progress_callback, 72, "Analysis report saved.")
    logger.info("analysis_text_report_saved path=%s", final_analysis_path)

    visual_path: Path | None = None
    if skip_visualization:
        log_lines.append("Skipping visualization step.")
        _notify_progress(progress_callback, 100, "Pipeline finished.")
        logger.info("pipeline_complete visualization=skipped")
        return PipelineRunResult(
            graph_document=dict(graph_document),
            analysis_text=report,
            graph_path=graph_output,
            analysis_path=final_analysis_path,
            visual_summary_path=None,
            log_lines=tuple(log_lines),
        )

    log_lines.append("")
    log_lines.append("Generating visualization outputs...")
    _notify_progress(progress_callback, 78, "Rendering chart images (this can take a while)…")
    if visual_artifacts_dir is not None:
        vdir = visual_artifacts_dir.resolve()
        vdir.mkdir(parents=True, exist_ok=True)
        prefix = graph_output.parent.name
        report_lines, summary_data = generate_visual_summary(
            graph_output,
            top_k=top_k,
            structure_output=vdir / f"{prefix}_structure.png",
            structure_output_imports=vdir / f"{prefix}_structure_imports.png",
            structure_output_in_file=vdir / f"{prefix}_structure_in_file.png",
            structure_output_calls=vdir / f"{prefix}_structure_calls.png",
            structure_output_tests=vdir / f"{prefix}_structure_tests.png",
            analysis_output=vdir / f"{prefix}_degree_analysis.png",
            analysis_output_imports=vdir / f"{prefix}_degree_analysis_imports.png",
            analysis_output_in_file=vdir / f"{prefix}_degree_analysis_in_file.png",
            analysis_output_calls=vdir / f"{prefix}_degree_analysis_calls.png",
            analysis_output_tests=vdir / f"{prefix}_degree_analysis_tests.png",
            summary_output=visual_summary_output,
            progress_callback=progress_callback,
        )
    else:
        report_lines, summary_data = generate_visual_summary(
            graph_output,
            top_k=top_k,
            summary_output=visual_summary_output,
            progress_callback=progress_callback,
        )
    save_visual_summary(summary_data["summary_text"], summary_data["summary_output"])
    visual_path = Path(str(summary_data["summary_output"]))
    log_lines.extend(report_lines)
    log_lines.append(f"Visual summary saved to: {summary_data['summary_output']}")
    _notify_progress(progress_callback, 94, "Saving visual summary text…")
    _notify_progress(progress_callback, 100, "Pipeline finished.")
    logger.info(
        "pipeline_complete visualization=yes summary=%s",
        summary_data.get("summary_output"),
    )

    return PipelineRunResult(
        graph_document=dict(graph_document),
        analysis_text=report,
        graph_path=graph_output,
        analysis_path=final_analysis_path,
        visual_summary_path=visual_path,
        log_lines=tuple(log_lines),
    )


def resolve_default_cli_paths(
    repo_path: Path,
    graph_output_arg: str,
    visual_summary_output_arg: str,
) -> tuple[Path, Path]:
    """Resolve default graph and visual-summary paths for CLI runs.

    Args:
        repo_path: Repository path from CLI.
        graph_output_arg: Optional ``--graph-output`` string (empty uses default).
        visual_summary_output_arg: Optional ``--visual-summary-output`` string.

    Returns:
        Tuple ``(graph_path, visual_summary_path)`` (all resolved).
    """
    rp = repo_path.resolve()
    graph_path = Path(graph_output_arg).resolve() if graph_output_arg else default_cli_graph_path(rp)
    visual_path = (
        Path(visual_summary_output_arg).resolve()
        if visual_summary_output_arg
        else default_cli_visual_summary_path(rp)
    )
    return graph_path, visual_path
