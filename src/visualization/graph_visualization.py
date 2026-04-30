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


def compute_degrees_by_type(edges: List[Dict[str, str]]) -> Dict[str, Tuple[Counter, Counter]]:
    """Compute in-degree and out-degree counters for each edge type."""
    degrees_by_type: Dict[str, Tuple[Counter, Counter]] = {}
    for edge in edges:
        edge_type = edge.get("type", "UNKNOWN")
        if edge_type not in degrees_by_type:
            degrees_by_type[edge_type] = (Counter(), Counter())
        in_cnt, out_cnt = degrees_by_type[edge_type]
        out_cnt[edge["source"]] += 1
        in_cnt[edge["target"]] += 1
    return degrees_by_type


def node_path_map(nodes: List[Dict[str, str]]) -> Dict[str, str]:
    """Map node id to human-readable file path."""
    return {node["id"]: node.get("path", node["id"]) for node in nodes}


def graph_name_from_path(graph_path: Path) -> str:
    """Extract a compact repository/graph name from the path."""
    stem = graph_path.stem
    if stem.endswith("_imports_graph"):
        return stem[: -len("_imports_graph")]
    if stem.endswith("_graph"):
        return stem[: -len("_graph")]
    return stem


def build_nx_graph(nodes: List[Dict[str, str]], edges: List[Dict[str, str]]) -> nx.DiGraph:
    """Create a NetworkX directed graph."""
    graph = nx.DiGraph()
    for node in nodes:
        graph.add_node(node["id"])
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"])
    return graph


def safe_spring_layout(graph: nx.Graph, seed: int = 42, k: float = 0.7):
    """Compute a layout for plotting, with a fallback when SciPy is unavailable."""
    try:
        return nx.spring_layout(graph, seed=seed, k=k)
    except (ModuleNotFoundError, TypeError):
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
    plt.figure(figsize=(16, 12))
    pos = safe_spring_layout(subgraph, seed=42, k=0.8)
    nx.draw_networkx_nodes(subgraph, pos, node_size=350, alpha=0.9)
    nx.draw_networkx_edges(subgraph, pos, arrows=True, alpha=0.35, width=1.0)
    labels = {
        node_id: Path(path_by_id.get(node_id, node_id)).name for node_id in subgraph.nodes
    }
    nx.draw_networkx_labels(
        subgraph,
        pos,
        labels=labels,
        font_size=5,
        font_weight="bold",
        bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=0.2),
    )
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

    fig, axes = plt.subplots(2, 1, figsize=(14, 10), constrained_layout=True)

    imported_labels = [Path(path_by_id.get(node_id, node_id)).name for node_id, _ in top_imported]
    imported_scores = [score for _, score in top_imported]
    axes[0].barh(imported_labels[::-1], imported_scores[::-1])
    axes[0].set_title(f"Top {top_k} Nodes by Incoming Edges (In-Degree) — {graph_label}")
    axes[0].set_xlabel("In-Degree")
    axes[0].tick_params(axis="y", labelsize=8)

    importing_labels = [Path(path_by_id.get(node_id, node_id)).name for node_id, _ in top_importing]
    importing_scores = [score for _, score in top_importing]
    axes[1].barh(importing_labels[::-1], importing_scores[::-1])
    axes[1].set_title(f"Top {top_k} Nodes by Outgoing Edges (Out-Degree) — {graph_label}")
    axes[1].set_xlabel("Out-Degree")
    axes[1].tick_params(axis="y", labelsize=8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def compute_graph_for_edge_type(
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    edge_type: str,
) -> nx.DiGraph:
    """Build a graph from a given edge type."""
    graph = nx.DiGraph()
    for node in nodes:
        graph.add_node(node["id"])
    for edge in edges:
        if edge.get("type") == edge_type:
            graph.add_edge(edge["source"], edge["target"])
    return graph


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
    degrees_by_type: Dict[str, Tuple[Counter, Counter]],
    path_by_id: Dict[str, str],
    top_k: int,
) -> str:
    """Build a short text summary for generated visuals."""
    repo_name = graph_name_from_path(graph_path)
    graph_label = f"{repo_name} — {graph_edge_type_label(edges)}"
    lines: List[str] = []
    lines.append(f"Repository: {repo_name}")
    lines.append(f"Graph label: {graph_label}")
    lines.append(f"Graph file: {graph_path}")
    lines.append(f"Graph type: {graph_edge_type_label(edges)}")
    lines.append(f"Total nodes: {len(nodes)}")
    lines.append(f"Total edges: {len(edges)}")
    lines.append("")

    for edge_type in sorted(degrees_by_type.keys()):
        in_degree, out_degree = degrees_by_type[edge_type]
        lines.append(f"Edges of type: {edge_type}")
        lines.append(f"- Total edges: {sum(out_degree.values())}")
        lines.append(f"Top {top_k} nodes by incoming {edge_type} edges:")
        for node_id, score in in_degree.most_common(top_k):
            lines.append(f"- {path_by_id.get(node_id, node_id)}: {score}")
        lines.append(f"Top {top_k} nodes by outgoing {edge_type} edges:")
        for node_id, score in out_degree.most_common(top_k):
            lines.append(f"- {path_by_id.get(node_id, node_id)}: {score}")
        lines.append("")

    return "\n".join(lines) + "\n"


def generate_visual_summary(
    graph_path: Path,
    top_k: int = 10,
    structure_nodes: int = 15,
    skip_structure: bool = False,
    structure_output: Path | None = None,
    structure_output_imports: Path | None = None,
    structure_output_in_file: Path | None = None,
    analysis_output: Path | None = None,
    analysis_output_imports: Path | None = None,
    analysis_output_in_file: Path | None = None,
    summary_output: Path | None = None,
) -> tuple[List[str], Dict[str, object]]:
    graph_path = graph_path.resolve()
    graph_data = load_graph(graph_path)
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    path_by_id = node_path_map(nodes)

    in_degree, out_degree = compute_degrees(edges)
    degrees_by_type = compute_degrees_by_type(edges)
    nx_graph = build_nx_graph(nodes, edges)

    repo_name = graph_name_from_path(graph_path)
    graph_label = f"{repo_name} — {graph_edge_type_label(edges)}"
    imports_graph_label = f"{repo_name} — IMPORTS graph"
    in_file_graph_label = f"{repo_name} — IN_FILE graph"

    structure_output = (
        structure_output
        or Path(f"results/visuals/{repo_name}_graph_structure.png").resolve()
    )
    structure_output_imports = (
        structure_output_imports
        or Path(f"results/visuals/{repo_name}_graph_structure_imports.png").resolve()
    )
    structure_output_in_file = (
        structure_output_in_file
        or Path(f"results/visuals/{repo_name}_graph_structure_in_file.png").resolve()
    )
    analysis_output = (
        analysis_output
        or Path(f"results/visuals/{repo_name}_graph_degree_analysis.png").resolve()
    )
    analysis_output_imports = (
        analysis_output_imports
        or Path(f"results/visuals/{repo_name}_graph_degree_analysis_imports.png").resolve()
    )
    analysis_output_in_file = (
        analysis_output_in_file
        or Path(f"results/visuals/{repo_name}_graph_degree_analysis_in_file.png").resolve()
    )
    summary_output = (
        summary_output
        or Path(f"results/reports/{repo_name}_visual_summary.txt").resolve()
    )

    report_lines: List[str] = []
    if not skip_structure:
        selected_nodes = select_structure_nodes(
            graph=nx_graph,
            in_degree=in_degree,
            out_degree=out_degree,
            top_n=max(5, structure_nodes),
        )
        if selected_nodes:
            plot_structure_subgraph(nx_graph, selected_nodes, path_by_id, structure_output, graph_label)
            report_lines.append(f"Overall structure visualization saved to: {structure_output}")

        imports_edges = [edge for edge in edges if edge.get("type") == "IMPORTS"]
        in_file_edges = [edge for edge in edges if edge.get("type") == "IN_FILE"]
        imports_graph = compute_graph_for_edge_type(nodes, edges, "IMPORTS")
        in_file_graph = compute_graph_for_edge_type(nodes, edges, "IN_FILE")
        imports_in_degree, imports_out_degree = compute_degrees(imports_edges)
        in_file_in_degree, in_file_out_degree = compute_degrees(in_file_edges)

        imports_selected = select_structure_nodes(
            graph=imports_graph,
            in_degree=imports_in_degree,
            out_degree=imports_out_degree,
            top_n=max(5, structure_nodes),
        )
        in_file_selected = select_structure_nodes(
            graph=in_file_graph,
            in_degree=in_file_in_degree,
            out_degree=in_file_out_degree,
            top_n=max(5, structure_nodes),
        )

        if imports_selected:
            plot_structure_subgraph(
                imports_graph,
                imports_selected,
                path_by_id,
                structure_output_imports,
                imports_graph_label,
            )
            report_lines.append(f"IMPORTS structure visualization saved to: {structure_output_imports}")

        if in_file_selected:
            plot_structure_subgraph(
                in_file_graph,
                in_file_selected,
                path_by_id,
                structure_output_in_file,
                in_file_graph_label,
            )
            report_lines.append(f"IN_FILE structure visualization saved to: {structure_output_in_file}")

    else:
        report_lines.append("Skipping structure visualization because skip_structure=True.")

    plot_degree_bars(in_degree, out_degree, path_by_id, top_k, analysis_output, graph_label)
    report_lines.append(f"Overall degree analysis saved to: {analysis_output}")

    imports_edges = [edge for edge in edges if edge.get("type") == "IMPORTS"]
    in_file_edges = [edge for edge in edges if edge.get("type") == "IN_FILE"]
    imports_in_degree, imports_out_degree = compute_degrees(imports_edges)
    in_file_in_degree, in_file_out_degree = compute_degrees(in_file_edges)

    plot_degree_bars(
        imports_in_degree,
        imports_out_degree,
        path_by_id,
        top_k,
        analysis_output_imports,
        imports_graph_label,
    )
    report_lines.append(f"IMPORTS degree analysis saved to: {analysis_output_imports}")

    plot_degree_bars(
        in_file_in_degree,
        in_file_out_degree,
        path_by_id,
        top_k,
        analysis_output_in_file,
        in_file_graph_label,
    )
    report_lines.append(f"IN_FILE degree analysis saved to: {analysis_output_in_file}")

    summary_text = build_visual_summary(
        graph_path=graph_path,
        nodes=nodes,
        edges=edges,
        degrees_by_type=degrees_by_type,
        path_by_id=path_by_id,
        top_k=top_k,
    )
    return report_lines, {
        "summary_text": summary_text,
        "summary_output": summary_output,
    }


def save_visual_summary(summary_text: str, summary_output: Path) -> None:
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(summary_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize graph structure and degree analysis.")
    parser.add_argument(
        "--graph",
        default="results/graphs/graph_imports.json",
        help="Path to graph JSON",
    )
    parser.add_argument(
        "--structure-output",
        default="results/visuals/graph_structure.png",
        help="Output image for overall graph structure",
    )
    parser.add_argument(
        "--structure-output-imports",
        default="results/visuals/graph_structure_imports.png",
        help="Output image for IMPORTS structure graph",
    )
    parser.add_argument(
        "--structure-output-in-file",
        default="results/visuals/graph_structure_in_file.png",
        help="Output image for IN_FILE structure graph",
    )
    parser.add_argument(
        "--analysis-output",
        default="results/visuals/graph_degree_analysis.png",
        help="Output image for overall degree analysis",
    )
    parser.add_argument(
        "--analysis-output-imports",
        default="results/visuals/graph_degree_analysis_imports.png",
        help="Output image for IMPORTS degree analysis",
    )
    parser.add_argument(
        "--analysis-output-in-file",
        default="results/visuals/graph_degree_analysis_in_file.png",
        help="Output image for IN_FILE degree analysis",
    )
    parser.add_argument(
        "--summary-output",
        default="results/reports/visual_summary.txt",
        help="Output text summary for visuals",
    )
    parser.add_argument(
        "--structure-nodes",
        type=int,
        default=15,
        help="Number of high-degree nodes to include in structure plot",
    )
    parser.add_argument(
        "--skip-structure",
        action="store_true",
        help="Skip structure graph visualization when the graph is large or noisy",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Top-k files for bar charts")
    args = parser.parse_args()

    graph_path = Path(args.graph).resolve()
    report_lines, summary_data = generate_visual_summary(
        graph_path,
        top_k=args.top_k,
        structure_nodes=args.structure_nodes,
        skip_structure=args.skip_structure,
        structure_output=Path(args.structure_output).resolve(),
        structure_output_imports=Path(args.structure_output_imports).resolve(),
        structure_output_in_file=Path(args.structure_output_in_file).resolve(),
        analysis_output=Path(args.analysis_output).resolve(),
        analysis_output_imports=Path(args.analysis_output_imports).resolve(),
        analysis_output_in_file=Path(args.analysis_output_in_file).resolve(),
        summary_output=Path(args.summary_output).resolve(),
    )
    save_visual_summary(summary_data["summary_text"], summary_data["summary_output"])

    for line in report_lines:
        print(line)
