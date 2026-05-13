from __future__ import annotations

import argparse
import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Dict, List, Tuple

from src.analysis.centrality_measures import (
    build_typed_subgraph,
    compute_betweenness_centrality,
    compute_pagerank,
    top_k_scores,
)
from src.analysis.community_detection import (
    CommunityDetectionResult,
    detect_communities,
)
from src.graph.json_document import (
    compute_in_out_degrees_by_edge_type,
    human_readable_graph_edge_label,
    load_graph_document,
    map_node_id_to_path,
    graph_stem_display_name,
)

logger = logging.getLogger(__name__)

_CENTRALITY_EDGE_TYPES: Tuple[str, ...] = ("IMPORTS", "CALLS")
_COMMUNITY_EDGE_TYPES: Tuple[str, ...] = ("IMPORTS", "CALLS")
_COMMUNITY_MAX_MEMBERS_LISTED = 8


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


def format_top_scores_section(
    title: str,
    items: List[Tuple[str, float]],
    path_by_id: Dict[str, str],
    *,
    precision: int = 4,
) -> List[str]:
    """Format a top-K section for **float** scores (betweenness, PageRank, …).

    Args:
        title: Section heading line.
        items: Ranked ``(node_id, score)`` pairs where ``score`` is a float.
        path_by_id: Mapping from node id to display label.
        precision: Decimal places to show.

    Returns:
        Lines of plain text for the report section.
    """
    lines: List[str] = []
    lines.append(title)
    if items:
        for node_id, score in items:
            lines.append(
                f"- {path_by_id.get(node_id, node_id)}: {score:.{precision}f}"
            )
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
    calls_in: List[Tuple[str, int]],
    calls_out: List[Tuple[str, int]],
    tests_in: List[Tuple[str, int]],
    tests_out: List[Tuple[str, int]],
    modified_by_in: List[Tuple[str, int]],
    modified_by_out: List[Tuple[str, int]],
    centrality_sections: Dict[str, Dict[str, object]],
    community_sections: Dict[str, CommunityDetectionResult],
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
        calls_in: Top nodes by incoming CALLS edges.
        calls_out: Top nodes by outgoing CALLS edges.
        tests_in: Top nodes by incoming TESTS edges.
        tests_out: Top nodes by outgoing TESTS edges.
        modified_by_in: Top nodes by incoming MODIFIED_BY edges (commits with most files).
        modified_by_out: Top nodes by outgoing MODIFIED_BY edges (files with most commits).
        centrality_sections: Per-edge-type centrality results. Keyed by edge token
            (``"IMPORTS"`` / ``"CALLS"``) with values
            ``{"betweenness": [(id, score), …], "betweenness_approximated": bool,
            "pagerank": [(id, score), …]}``. Missing entries render as empty sections.
        community_sections: Per-edge-type Louvain community results keyed by edge
            token. Empty results render as a "None" line.
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
            f"Top {top_k_value} nodes by incoming CALLS edges:",
            calls_in,
            path_by_id,
        )
    )
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} nodes by outgoing CALLS edges:",
            calls_out,
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
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} commits by incoming MODIFIED_BY edges (files changed per commit):",
            modified_by_in,
            path_by_id,
        )
    )
    lines.append("")
    lines.extend(
        format_top_nodes_section(
            f"Top {top_k_value} files by outgoing MODIFIED_BY edges (commit churn):",
            modified_by_out,
            path_by_id,
        )
    )

    for edge_type in _CENTRALITY_EDGE_TYPES:
        section = centrality_sections.get(edge_type) or {}
        betweenness = section.get("betweenness") or []
        approximated = bool(section.get("betweenness_approximated"))
        pagerank = section.get("pagerank") or []
        lines.append("")
        approx_suffix = " (sampled estimator)" if approximated else ""
        lines.extend(
            format_top_scores_section(
                f"Top {top_k_value} nodes by betweenness centrality on {edge_type} graph{approx_suffix}:",
                list(betweenness),
                path_by_id,
            )
        )
        lines.append("")
        lines.extend(
            format_top_scores_section(
                f"Top {top_k_value} nodes by PageRank on {edge_type} graph:",
                list(pagerank),
                path_by_id,
            )
        )

    for edge_type in _COMMUNITY_EDGE_TYPES:
        community_result = community_sections.get(edge_type)
        lines.append("")
        if community_result is None:
            lines.append(f"Top {top_k_value} Louvain communities on {edge_type} graph:")
            lines.append("- None")
            continue
        lines.extend(
            format_community_section(
                f"Top {top_k_value} Louvain communities on {edge_type} graph:",
                community_result,
                path_by_id,
                top_k_value=top_k_value,
            )
        )
    return "\n".join(lines)


def format_community_section(
    title: str,
    result: CommunityDetectionResult,
    path_by_id: Dict[str, str],
    *,
    top_k_value: int,
    max_members: int = _COMMUNITY_MAX_MEMBERS_LISTED,
) -> List[str]:
    """Format one community-detection section into report lines.

    Args:
        title: Heading line.
        result: Output of :func:`detect_communities`.
        path_by_id: Display label lookup for each node id.
        top_k_value: Maximum number of communities to list.
        max_members: How many members to show inline per community.

    Returns:
        Lines of plain text ready to be joined into the report body.
    """
    lines: List[str] = [title]
    if result.modularity_score is None or not result.communities:
        lines.append("- None")
        return lines

    lines.append(
        f"- algorithm={result.algorithm}, nodes={result.node_count}, "
        f"edges={result.edge_count}, communities={len(result.communities)}, "
        f"modularity={result.modularity_score:.4f}"
    )
    for index, members in enumerate(result.communities[:top_k_value], start=1):
        size = len(members)
        preview_count = min(max_members, size)
        member_labels = ", ".join(
            path_by_id.get(node_id, node_id) for node_id in members[:preview_count]
        )
        ellipsis = "" if size <= preview_count else f", … (+{size - preview_count} more)"
        lines.append(f"- #{index} (size={size}): {member_labels}{ellipsis}")
    return lines


def _compute_community_sections(
    *,
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    progress: Callable[[int, str], None],
) -> Dict[str, CommunityDetectionResult]:
    """Run Louvain (with label-propagation fallback) for each eligible edge type.

    Args:
        nodes: Graph nodes.
        edges: Graph edges.
        progress: ``(percent, message)`` callback (already bounded internally).

    Returns:
        Mapping from edge type to a :class:`CommunityDetectionResult`. Edge
        types with no edges in the graph map to an empty result so the report
        layout is stable.
    """
    sections: Dict[str, CommunityDetectionResult] = {}
    base_pct = 71
    span = 2
    for index, edge_type in enumerate(_COMMUNITY_EDGE_TYPES):
        edge_count = sum(1 for edge in edges if edge.get("type") == edge_type)
        if edge_count == 0:
            sections[edge_type] = CommunityDetectionResult(
                communities=(),
                modularity_score=None,
                algorithm="louvain",
                node_count=0,
                edge_count=0,
            )
            continue

        progress(
            base_pct + index * span,
            f"Analysis: community detection on {edge_type} graph (edges={edge_count})…",
        )
        subgraph = build_typed_subgraph(nodes, edges, edge_type)
        sections[edge_type] = detect_communities(subgraph)
    return sections


def _compute_centrality_sections(
    *,
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    top_k_value: int,
    progress: Callable[[int, str], None],
) -> Dict[str, Dict[str, object]]:
    """Compute betweenness + PageRank for each centrality-eligible edge type.

    Args:
        nodes: Graph nodes.
        edges: Graph edges.
        top_k_value: Number of top entries kept per metric.
        progress: ``(percent, message)`` callback (already bounded internally).

    Returns:
        Mapping ``edge_type -> {"betweenness": [(id, score), …],
        "betweenness_approximated": bool, "pagerank": [(id, score), …]}`` for
        every type in :data:`_CENTRALITY_EDGE_TYPES`. Edge types with no edges in
        the graph still appear with empty lists so the report layout is stable.
    """
    sections: Dict[str, Dict[str, object]] = {}
    base_pct = 66
    span = 2
    for index, edge_type in enumerate(_CENTRALITY_EDGE_TYPES):
        edge_count = sum(1 for edge in edges if edge.get("type") == edge_type)
        if edge_count == 0:
            sections[edge_type] = {
                "betweenness": [],
                "betweenness_approximated": False,
                "pagerank": [],
            }
            continue

        progress(
            base_pct + index * span,
            f"Analysis: centrality on {edge_type} graph (nodes={len(nodes)}, edges={edge_count})…",
        )
        subgraph = build_typed_subgraph(nodes, edges, edge_type)
        betweenness_scores, approximated = compute_betweenness_centrality(subgraph)
        pagerank_scores = compute_pagerank(subgraph)
        sections[edge_type] = {
            "betweenness": top_k_scores(betweenness_scores, top_k_value),
            "betweenness_approximated": approximated,
            "pagerank": top_k_scores(pagerank_scores, top_k_value),
        }
        logger.info(
            "centrality_done edge_type=%s nodes=%d edges=%d betweenness_approx=%s",
            edge_type,
            len(subgraph),
            edge_count,
            approximated,
        )
    return sections


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
    calls_in, calls_out = degrees_by_type.get("CALLS", (Counter(), Counter()))
    tests_in, tests_out = degrees_by_type.get("TESTS", (Counter(), Counter()))
    modified_by_in, modified_by_out = degrees_by_type.get(
        "MODIFIED_BY", (Counter(), Counter())
    )

    centrality_sections = _compute_centrality_sections(
        nodes=nodes,
        edges=edges,
        top_k_value=top_k_value,
        progress=_notify,
    )
    community_sections = _compute_community_sections(
        nodes=nodes,
        edges=edges,
        progress=_notify,
    )

    _notify(76, "Analysis: assembling plain-text sections (degree + centrality + communities)…")
    report = format_analysis_report(
        graph_path=graph_path,
        nodes=nodes,
        edges=edges,
        edge_type_counts=edge_type_counts,
        imports_in=top_k(imports_in, top_k_value),
        imports_out=top_k(imports_out, top_k_value),
        in_file_in=top_k(in_file_in, top_k_value),
        in_file_out=top_k(in_file_out, top_k_value),
        calls_in=top_k(calls_in, top_k_value),
        calls_out=top_k(calls_out, top_k_value),
        tests_in=top_k(tests_in, top_k_value),
        tests_out=top_k(tests_out, top_k_value),
        modified_by_in=top_k(modified_by_in, top_k_value),
        modified_by_out=top_k(modified_by_out, top_k_value),
        centrality_sections=centrality_sections,
        community_sections=community_sections,
        path_by_id=path_by_id,
        top_k_value=top_k_value,
    )
    _notify(77, "Analysis: text report body ready.")

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
