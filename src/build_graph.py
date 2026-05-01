from __future__ import annotations

import argparse
from pathlib import Path

from src.graph.graph_builder import GraphBuilder, save_graph
from src.graph.schema import graph_to_dict, validate_graph_contract


def default_output_path(repo_path: Path) -> Path:
    """Build the default output path for the graph JSON output.

    Args:
        repo_path: Repository root used for naming.

    Returns:
        Path under ``results/graphs/`` for the JSON document.
    """
    output_dir = Path("results/graphs")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{repo_path.name}_graph.json"


def main() -> None:
    """CLI entry: build and validate a graph JSON for a repository."""
    parser = argparse.ArgumentParser(description="Build a repository graph document.")
    parser.add_argument("--repo", required=True, help="Path to target repository")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output path for the graph JSON file",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    output_path = Path(args.output).resolve() if args.output else default_output_path(repo_path)

    builder = GraphBuilder(repo_path)
    builder.build()

    raw = builder.to_dict()
    graph_payload = graph_to_dict(raw["nodes"], raw["edges"])
    validate_graph_contract(graph_payload["nodes"], graph_payload["edges"])
    save_graph(graph_payload, output_path)

    print(f"Graph built successfully: {output_path}")
    print(f"Total nodes: {len(graph_payload['nodes'])}")
    print(f"Total edges: {len(graph_payload['edges'])}")


if __name__ == "__main__":
    main()
