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


def node_path_map(nodes: List[Dict[str, str]]) -> Dict[str, str]:
    """Map node id to display path."""
    return {node["id"]: node.get("path", node["id"]) for node in nodes}


def top_k(counter: Counter, k: int) -> List[Tuple[str, int]]:
    """Return top-k items from a counter."""
    return counter.most_common(k)


def graph_edge_type_label(edges: List[Dict[str, str]]) -> str:
    """Build a human-readable label for the graph edge type(s)."""
    edge_types = sorted({edge.get("type", "UNKNOWN") for edge in edges})
    if len(edge_types) == 1:
        return f"{edge_types[0]} graph"
    return f"{'+'.join(edge_types)} graph"


def format_analysis_report(
    graph_path: Path,
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    top_imported: List[Tuple[str, int]],
    top_importing: List[Tuple[str, int]],
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
    lines.append(f"Top {top_k_value} nodes by incoming edges (high in-degree):")
    for node_id, score in top_imported:
        lines.append(f"- {path_by_id.get(node_id, node_id)}: {score}")
    lines.append("")
    lines.append(f"Top {top_k_value} nodes by outgoing edges (high out-degree):")
    for node_id, score in top_importing:
        lines.append(f"- {path_by_id.get(node_id, node_id)}: {score}")
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
    graph = load_graph(graph_path)

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    path_by_id = node_path_map(nodes)

    in_degree, out_degree = compute_degrees(edges)
    top_imported = top_k(in_degree, args.top_k)
    top_importing = top_k(out_degree, args.top_k)

    report = format_analysis_report(
        graph_path=graph_path,
        nodes=nodes,
        edges=edges,
        top_imported=top_imported,
        top_importing=top_importing,
        path_by_id=path_by_id,
        top_k_value=args.top_k,
    )
    print(report)

    if args.save_report:
        report_path = Path(args.save_report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report + "\n", encoding="utf-8")
        print("")
        print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
