from __future__ import annotations

import argparse
from pathlib import Path

from src.analysis.graph_analysis import generate_analysis_text_report, save_analysis_report
from src.graph import GraphBuilder, graph_to_dict, save_graph, validate_graph_contract
from src.visualization.graph_visualization import generate_visual_summary, save_visual_summary


def default_graph_path(repo_path: Path) -> Path:
    output_dir = Path("results/graphs")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{repo_path.name}_graph.json"


def default_analysis_path(repo_path: Path) -> Path:
    output_dir = Path("results/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{repo_path.name}_pipeline_analysis.txt"


def default_visual_summary_path(repo_path: Path) -> Path:
    output_dir = Path("results/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{repo_path.name}_pipeline_visual_summary.txt"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full repository pipeline: build graph, analyze graph, and generate visual summaries."
    )
    parser.add_argument("--repo", required=True, help="Path to the target repository")
    parser.add_argument(
        "--graph-output",
        default="",
        help="Optional graph JSON output path",
    )
    parser.add_argument(
        "--analysis-output",
        default="",
        help="Optional analysis report output path",
    )
    parser.add_argument(
        "--visual-summary-output",
        default="",
        help="Optional visual summary output path",
    )
    parser.add_argument(
        "--skip-visualization",
        action="store_true",
        help="Skip visualization step and only build/analyze the graph",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top-K ranking for analysis and visualization summaries",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    graph_output = (
        Path(args.graph_output).resolve()
        if args.graph_output
        else default_graph_path(repo_path)
    )
    analysis_output = (
        Path(args.analysis_output).resolve()
        if args.analysis_output
        else default_analysis_path(repo_path)
    )
    visual_summary_output = (
        Path(args.visual_summary_output).resolve()
        if args.visual_summary_output
        else default_visual_summary_path(repo_path)
    )

    print(f"Building graph for repository: {repo_path}")
    builder = GraphBuilder(repo_path)
    builder.build()

    graph_document = graph_to_dict(builder.to_dict()["nodes"], builder.to_dict()["edges"])
    validate_graph_contract(graph_document["nodes"], graph_document["edges"])
    save_graph(graph_document, graph_output)
    print(f"Graph saved to: {graph_output}")
    print(f"Total nodes: {len(graph_document['nodes'])}")
    print(f"Total edges: {len(graph_document['edges'])}")

    print("\nRunning analysis...")
    report, default_report_path = generate_analysis_text_report(Path(graph_output), top_k_value=args.top_k)
    final_analysis_path = analysis_output if args.analysis_output else default_report_path
    save_analysis_report(report, final_analysis_path)
    print(f"Analysis saved to: {final_analysis_path}")

    if args.skip_visualization:
        print("Skipping visualization step.")
        return

    print("\nGenerating visualization outputs...")
    report_lines, summary_data = generate_visual_summary(
        Path(graph_output),
        top_k=args.top_k,
        summary_output=visual_summary_output,
    )
    save_visual_summary(summary_data["summary_text"], summary_data["summary_output"])
    for line in report_lines:
        print(line)
    print(f"Visual summary saved to: {summary_data['summary_output']}")


if __name__ == "__main__":
    main()
