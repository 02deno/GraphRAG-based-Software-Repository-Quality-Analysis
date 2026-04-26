from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


def load_graph(graph_path: Path) -> Dict[str, List[Dict[str, str]]]:
    """Load graph JSON produced by build_graph.py."""
    return json.loads(graph_path.read_text(encoding="utf-8"))


def compute_degrees(edges: List[Dict[str, str]]) -> Tuple[Counter, Counter]:
    """Compute in-degree and out-degree counters from directed edges."""
    in_degree: Counter = Counter()
    out_degree: Counter = Counter()
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        out_degree[source] += 1
        in_degree[target] += 1
    return in_degree, out_degree


def compute_degrees_by_type(edges: List[Dict[str, str]]) -> Dict[str, Tuple[Counter, Counter]]:
    """Compute in/out-degree counters grouped by edge type."""
    degrees_by_type: Dict[str, Tuple[Counter, Counter]] = {}
    for edge in edges:
        edge_type = edge.get("type", "UNKNOWN")
        if edge_type not in degrees_by_type:
            degrees_by_type[edge_type] = (Counter(), Counter())
        in_deg, out_deg = degrees_by_type[edge_type]
        out_deg[edge["source"]] += 1
        in_deg[edge["target"]] += 1
    return degrees_by_type


def node_path_map(nodes: List[Dict[str, str]]) -> Dict[str, str]:
    """Map node id to display path."""
    return {node["id"]: node.get("path", node["id"]) for node in nodes}


def graph_name_from_path(graph_path: Path) -> str:
    """Extract a compact repository/graph name from the path."""
    stem = graph_path.stem
    if stem.endswith("_imports_graph"):
        return stem[: -len("_imports_graph")]
    if stem.endswith("_graph"):
        return stem[: -len("_graph")]
    return stem


def top_k(counter: Counter, k: int) -> List[Tuple[str, int]]:
    """Return top-k items from a counter."""
    return counter.most_common(k)


def graph_edge_type_label(edges: List[Dict[str, str]]) -> str:
    """Build a human-readable label for the graph edge type(s)."""
    edge_types = sorted({edge.get("type", "UNKNOWN") for edge in edges})
    if len(edge_types) == 1:
        return f"{edge_types[0]} graph"
    return f"{'+'.join(edge_types)} graph"


def format_top_nodes_section(
    title: str,
    items: List[Tuple[str, int]],
    path_by_id: Dict[str, str],
) -> List[str]:
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
    path_by_id: Dict[str, str],
    top_k_value: int,
) -> str:
    """Build a plain-text analysis report."""
    graph_label = graph_edge_type_label(edges)
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
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze File+IMPORTS graph.")
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

    graph_path = Path(args.graph).resolve()
    report_path = (
        Path(args.save_report).resolve()
        if args.save_report
        else Path(f"results/reports/{graph_name_from_path(graph_path)}_graph_analysis.txt").resolve()
    )
    graph = load_graph(graph_path)

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    path_by_id = node_path_map(nodes)

    in_degree, out_degree = compute_degrees(edges)
    degrees_by_type = compute_degrees_by_type(edges)
    edge_type_counts = Counter(edge.get("type", "UNKNOWN") for edge in edges)

    imports_in, imports_out = degrees_by_type.get("IMPORTS", (Counter(), Counter()))
    in_file_in, in_file_out = degrees_by_type.get("IN_FILE", (Counter(), Counter()))

    report = format_analysis_report(
        graph_path=graph_path,
        nodes=nodes,
        edges=edges,
        edge_type_counts=edge_type_counts,
        imports_in=top_k(imports_in, args.top_k),
        imports_out=top_k(imports_out, args.top_k),
        in_file_in=top_k(in_file_in, args.top_k),
        in_file_out=top_k(in_file_out, args.top_k),
        path_by_id=path_by_id,
        top_k_value=args.top_k,
    )
    print(report)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report + "\n", encoding="utf-8")
    print("")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
