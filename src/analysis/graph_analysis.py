from __future__ import annotations

import argparse
import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Dict, List, Tuple

from src.graph.json_document import (
    compute_in_out_degrees_by_edge_type,
    human_readable_graph_edge_label,
    load_graph_document,
    map_node_id_to_path,
    graph_stem_display_name,
)

logger = logging.getLogger(__name__)


def top_k(counter: Counter, k: int) -> List[Tuple[str, int]]:
    """Return the top-*k* items from a counter by count descending.

    Args:
        counter: Counter mapping ids to scores.
        k: Maximum number of entries to return.

    Returns:
        List of ``(id, count)`` pairs from ``most_common(k)``.
    """
    return counter.most_common(k)


def format_top_nodes_section(
    title: str,
    items: List[Tuple[str, int]],
    path_by_id: Dict[str, str],
) -> List[str]:
    """Format one titled section listing top nodes with paths.

    Args:
        title: Section heading line.
        items: Ranked node ids and scores.
        path_by_id: Mapping from node id to display path.

    Returns:
        Lines of plain text for the report section.
    """
    lines: List[str] = []
    lines.append(title)
    if items:
        for node_id, score in items:
            lines.append(f"- {path_by_id.get(node_id, node_id)}: {score}")
    else:
        lines.append("- None")
    return lines


def format_analysis_report(
    graph_path: Path,
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    edge_type_counts: Dict[str, int],
    imports_in: List[Tuple[str, int]],
    imports_out: List[Tuple[str, int]],
    in_file_in: List[Tuple[str, int]],
    in_file_out: List[Tuple[str, int]],
    tests_in: List[Tuple[str, int]],
    tests_out: List[Tuple[str, int]],
    path_by_id: Dict[str, str],
    top_k_value: int,
) -> str:
    """Build a plain-text analysis report for one graph document.

    Args:
        graph_path: Source graph file path (for header).
        nodes: Graph nodes list.
        edges: Graph edges list.
        edge_type_counts: Precomputed counts per edge type.
        imports_in: Top nodes by incoming IMPORTS edges.
        imports_out: Top nodes by outgoing IMPORTS edges.
        in_file_in: Top nodes by incoming IN_FILE edges.
        in_file_out: Top nodes by outgoing IN_FILE edges.
        tests_in: Top nodes by incoming TESTS edges.
        tests_out: Top nodes by outgoing TESTS edges.
        path_by_id: Node id to path map for display.
        top_k_value: How many top entries to show per section.

    Returns:
        Full report as a single string with embedded newlines.
    """
    graph_label = human_readable_graph_edge_label(edges)
    lines: List[str] = []
    lines.append(f"Graph file: {graph_path}")
    lines.append(f"Graph type: {graph_label}")
    lines.append(f"Total nodes: {len(nodes)}")
    lines.append(f"Total edges: {len(edges)}")
    lines.append("")
    lines.append("Edge counts by type:")
    for edge_type, count in sorted(edge_type_counts.items()):
        lines.append(f"- {edge_type}: {count}")
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} nodes by incoming IMPORTS edges:",
            imports_in,
            path_by_id,
        )
    )
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} nodes by outgoing IMPORTS edges:",
            imports_out,
            path_by_id,
        )
    )
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} nodes by incoming IN_FILE edges:",
            in_file_in,
            path_by_id,
        )
    )
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} nodes by outgoing IN_FILE edges:",
            in_file_out,
            path_by_id,
        )
    )
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} nodes by incoming TESTS edges:",
            tests_in,
            path_by_id,
        )
    )
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} nodes by outgoing TESTS edges:",
            tests_out,
            path_by_id,
        )
    )
    return "\n".join(lines)


def generate_analysis_text_report(
    graph_path: Path,
    top_k_value: int = 10,
    *,
    progress_callback: Callable[[int, str], None] | None = None,
) -> tuple[str, Path]:
    """Load a graph JSON file and produce a degree-based text report.

    Args:
        graph_path: Path to the serialized graph document.
        top_k_value: Number of top-ranked nodes to include per category.
        progress_callback: Optional ``(percent, message)`` updates for web/SSE clients.

    Returns:
        Tuple of ``(report_text, default_report_path)`` where the default path is
        under ``results/reports/`` derived from the graph filename.
    """

    def _notify(pct: int, message: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(max(0, min(100, int(pct))), message)
        except Exception:
            pass

    graph_path = graph_path.resolve()
    _notify(53, f"Analysis: reading {graph_path.name} …")
    graph = load_graph_document(graph_path)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    path_by_id = map_node_id_to_path(nodes)
    logger.info(
        "analysis_report_loaded graph=%s nodes=%d edges=%d",
        graph_path.name,
        len(nodes),
        len(edges),
    )
    _notify(57, f"Analysis: computing per-type degree rankings (top_k={top_k_value})…")

    degrees_by_type = compute_in_out_degrees_by_edge_type(edges)
    edge_type_counts = Counter(edge.get("type", "UNKNOWN") for edge in edges)
    imports_in, imports_out = degrees_by_type.get("IMPORTS", (Counter(), Counter()))
    in_file_in, in_file_out = degrees_by_type.get("IN_FILE", (Counter(), Counter()))
    tests_in, tests_out = degrees_by_type.get("TESTS", (Counter(), Counter()))

    _notify(64, "Analysis: assembling plain-text sections (imports, IN_FILE, TESTS)…")
    report = format_analysis_report(
        graph_path=graph_path,
        nodes=nodes,
        edges=edges,
        edge_type_counts=edge_type_counts,
        imports_in=top_k(imports_in, top_k_value),
        imports_out=top_k(imports_out, top_k_value),
        in_file_in=top_k(in_file_in, top_k_value),
        in_file_out=top_k(in_file_out, top_k_value),
        tests_in=top_k(tests_in, top_k_value),
        tests_out=top_k(tests_out, top_k_value),
        path_by_id=path_by_id,
        top_k_value=top_k_value,
    )
    _notify(71, "Analysis: text report body ready.")

    report_path = Path(f"results/reports/{graph_stem_display_name(graph_path)}_graph_analysis.txt").resolve()
    return report, report_path


def save_analysis_report(report: str, report_path: Path) -> None:
    """Persist a text report to disk, creating parent directories as needed.

    Args:
        report: Full report body.
        report_path: Destination file path.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report + "\n", encoding="utf-8")


def main() -> None:
    """CLI entry: load a graph file, print analysis, optionally save report."""
    parser = argparse.ArgumentParser(description="Analyze a repository graph document.")
    parser.add_argument(
        "--graph",
        default="results/graph_file_imports.json",
        help="Path to graph JSON",
    )
    parser.add_argument("--top-k", type=int, default=10, help="How many top files to print")
    parser.add_argument(
        "--save-report",
        default="",
        help="Optional output path for saving analysis text report",
    )
    args = parser.parse_args()

    report, report_path = generate_analysis_text_report(Path(args.graph), top_k_value=args.top_k)
    actual_report_path = Path(args.save_report).resolve() if args.save_report else report_path
    save_analysis_report(report, actual_report_path)

    print(report)
    print("")
    print(f"Report saved to: {actual_report_path}")


if __name__ == "__main__":
    main()
