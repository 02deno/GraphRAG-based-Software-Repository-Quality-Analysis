from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import networkx as nx


def load_graph(graph_path: Path) -> Dict[str, List[Dict[str, str]]]:
    """Load graph JSON from build_graph.py output."""
    return json.loads(graph_path.read_text(encoding="utf-8"))


def compute_degrees(edges: List[Dict[str, str]]) -> Tuple[Counter, Counter]:
    """Compute in-degree and out-degree counters for directed edges."""
    in_degree: Counter = Counter()
    out_degree: Counter = Counter()
    for edge in edges:
        out_degree[edge["source"]] += 1
        in_degree[edge["target"]] += 1
    return in_degree, out_degree


def node_path_map(nodes: List[Dict[str, str]]) -> Dict[str, str]:
    """Map node id to human-readable file path."""
    return {node["id"]: node.get("path", node["id"]) for node in nodes}


def build_nx_graph(nodes: List[Dict[str, str]], edges: List[Dict[str, str]]) -> nx.DiGraph:
    """Create a NetworkX directed graph."""
    graph = nx.DiGraph()
    for node in nodes:
        graph.add_node(node["id"])
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"])
    return graph


def safe_spring_layout(graph: nx.Graph, seed: int = 42):
    """Compute a layout for plotting, with a fallback when SciPy is unavailable."""
    try:
        return nx.spring_layout(graph, seed=seed)
    except ModuleNotFoundError:
        return nx.random_layout(graph, seed=seed)


def top_nodes_by_total_degree(
    in_degree: Counter, out_degree: Counter, top_n: int
) -> List[str]:
    """Select top nodes by total degree for readable subgraph plotting."""
    totals: Counter = Counter()
    for node_id, score in in_degree.items():
        totals[node_id] += score
    for node_id, score in out_degree.items():
        totals[node_id] += score
    return [node_id for node_id, _ in totals.most_common(top_n)]


def select_structure_nodes(
    graph: nx.DiGraph,
    in_degree: Counter,
    out_degree: Counter,
    top_n: int,
) -> List[str]:
    """Select nodes for the structure subgraph, including direct neighbors."""
    selected = top_nodes_by_total_degree(in_degree, out_degree, top_n)
    selected_set = set(selected)
    ordered_nodes = list(selected)

    for node_id in selected:
        for neighbor in graph.predecessors(node_id):
            if neighbor not in selected_set:
                selected_set.add(neighbor)
                ordered_nodes.append(neighbor)
        for neighbor in graph.successors(node_id):
            if neighbor not in selected_set:
                selected_set.add(neighbor)
                ordered_nodes.append(neighbor)

    return ordered_nodes


def plot_structure_subgraph(
    graph: nx.DiGraph,
    selected_nodes: List[str],
    path_by_id: Dict[str, str],
    output_path: Path,
    graph_label: str,
) -> None:
    """Plot a subgraph of high-degree nodes."""
    subgraph = graph.subgraph(selected_nodes).copy()
    plt.figure(figsize=(14, 10))
    pos = safe_spring_layout(subgraph, seed=42)
    nx.draw_networkx_nodes(subgraph, pos, node_size=350, alpha=0.9)
    nx.draw_networkx_edges(subgraph, pos, arrows=True, alpha=0.35, width=1.0)
    labels = {node_id: Path(path_by_id.get(node_id, node_id)).name for node_id in subgraph.nodes}
    nx.draw_networkx_labels(subgraph, pos, labels=labels, font_size=7)
    plt.title(f"{graph_label} Structure (Top-Degree Subgraph)")
    plt.axis("off")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=220)
    plt.close()


def plot_degree_bars(
    in_degree: Counter,
    out_degree: Counter,
    path_by_id: Dict[str, str],
    top_k: int,
    output_path: Path,
    graph_label: str,
) -> None:
    """Plot top in-degree and out-degree nodes as bar charts."""
    top_imported = in_degree.most_common(top_k)
    top_importing = out_degree.most_common(top_k)

    fig, axes = plt.subplots(2, 1, figsize=(12, 10))

    imported_labels = [Path(path_by_id.get(node_id, node_id)).name for node_id, _ in top_imported]
    imported_scores = [score for _, score in top_imported]
    axes[0].barh(imported_labels[::-1], imported_scores[::-1])
    axes[0].set_title(f"Top {top_k} Nodes by Incoming Edges (In-Degree) — {graph_label}")
    axes[0].set_xlabel("In-Degree")

    importing_labels = [Path(path_by_id.get(node_id, node_id)).name for node_id, _ in top_importing]
    importing_scores = [score for _, score in top_importing]
    axes[1].barh(importing_labels[::-1], importing_scores[::-1])
    axes[1].set_title(f"Top {top_k} Nodes by Outgoing Edges (Out-Degree) — {graph_label}")
    axes[1].set_xlabel("Out-Degree")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=220)
    plt.close()


def graph_edge_type_label(edges: List[Dict[str, str]]) -> str:
    """Build a human-readable label for the graph edge type(s)."""
    edge_types = sorted({edge.get("type", "UNKNOWN") for edge in edges})
    if len(edge_types) == 1:
        return f"{edge_types[0]} graph"
    return f"{'+'.join(edge_types)} graph"


def build_visual_summary(
    graph_path: Path,
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    in_degree: Counter,
    out_degree: Counter,
    path_by_id: Dict[str, str],
    top_k: int,
) -> str:
    """Build a short text summary for generated visuals."""
    graph_label = graph_edge_type_label(edges)
    lines: List[str] = []
    lines.append(f"Graph file: {graph_path}")
    lines.append(f"Graph type: {graph_label}")
    lines.append(f"Total nodes: {len(nodes)}")
    lines.append(f"Total edges: {len(edges)}")
    lines.append("")
    lines.append(f"Top {top_k} nodes by incoming edges (high in-degree):")
    for node_id, score in in_degree.most_common(top_k):
        lines.append(f"- {path_by_id.get(node_id, node_id)}: {score}")
    lines.append("")
    lines.append(f"Top {top_k} nodes by outgoing edges (high out-degree):")
    for node_id, score in out_degree.most_common(top_k):
        lines.append(f"- {path_by_id.get(node_id, node_id)}: {score}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize graph structure and degree analysis.")
    parser.add_argument(
        "--graph",
        default="results/graph_file_imports.json",
        help="Path to graph JSON",
    )
    parser.add_argument(
        "--structure-output",
        default="results/graph_structure.png",
        help="Output image for graph structure",
    )
    parser.add_argument(
        "--analysis-output",
        default="results/graph_degree_analysis.png",
        help="Output image for degree analysis",
    )
    parser.add_argument(
        "--summary-output",
        default="results/visual_summary.txt",
        help="Output text summary for visuals",
    )
    parser.add_argument(
        "--structure-nodes",
        type=int,
        default=40,
        help="Number of high-degree nodes to include in structure plot",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Top-k files for bar charts")
    args = parser.parse_args()

    graph_data = load_graph(Path(args.graph).resolve())
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    in_degree, out_degree = compute_degrees(edges)
    path_by_id = node_path_map(nodes)
    nx_graph = build_nx_graph(nodes, edges)

    selected_nodes = select_structure_nodes(
        graph=nx_graph,
        in_degree=in_degree,
        out_degree=out_degree,
        top_n=max(5, args.structure_nodes),
    )

    graph_label = graph_edge_type_label(edges)
    structure_output = Path(args.structure_output).resolve()
    analysis_output = Path(args.analysis_output).resolve()

    plot_structure_subgraph(nx_graph, selected_nodes, path_by_id, structure_output, graph_label)
    plot_degree_bars(in_degree, out_degree, path_by_id, args.top_k, analysis_output, graph_label)
    summary_output = Path(args.summary_output).resolve()
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_text = build_visual_summary(
        graph_path=Path(args.graph).resolve(),
        nodes=nodes,
        edges=edges,
        in_degree=in_degree,
        out_degree=out_degree,
        path_by_id=path_by_id,
        top_k=args.top_k,
    )
    summary_output.write_text(summary_text, encoding="utf-8")

    print(f"Structure visualization saved to: {structure_output}")
    print(f"Degree analysis visualization saved to: {analysis_output}")
    print(f"Visual summary saved to: {summary_output}")


if __name__ == "__main__":
    main()
