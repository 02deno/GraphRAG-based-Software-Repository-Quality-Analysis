from __future__ import annotations

import argparse
from pathlib import Path

from src.pipeline.run_pipeline import resolve_default_cli_paths, run_repository_pipeline


def main() -> None:
    """CLI entry: parse arguments and run the full repository pipeline."""
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
        help="Optional analysis report output path (default under results/reports/)",
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
    graph_output, visual_summary_output = resolve_default_cli_paths(
        repo_path,
        args.graph_output,
        args.visual_summary_output,
    )
    analysis_explicit = Path(args.analysis_output).resolve() if args.analysis_output else None

    result = run_repository_pipeline(
        repo_path,
        graph_output=graph_output,
        analysis_output=analysis_explicit,
        visual_summary_output=visual_summary_output,
        skip_visualization=args.skip_visualization,
        top_k=args.top_k,
    )
    for line in result.log_lines:
        print(line)


if __name__ == "__main__":
    main()
