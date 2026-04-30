from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from src.graph import GraphBuilder
from src.graph.schema import graph_to_dict, validate_graph_contract


def default_output_path(repo_path: Path) -> Path:
    """Build the default output path for the graph JSON output."""
    output_dir = Path("results/graphs")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{repo_path.name}_graph.json"


def save_json(document: dict, output_path: Path) -> None:
    """Save a JSON document to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def main() -> None:
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

    graph_payload = graph_to_dict(builder.to_dict()["nodes"], builder.to_dict()["edges"])
    validate_graph_contract(graph_payload["nodes"], graph_payload["edges"])
    save_json(graph_payload, output_path)

    print(f"Graph built successfully: {output_path}")
    print(f"Total nodes: {len(graph_payload['nodes'])}")
    print(f"Total edges: {len(graph_payload['edges'])}")


if __name__ == "__main__":
    main()

    for node in function_nodes + class_nodes:
        if matches(node):
            candidates.append(node["id"])

    return sorted(set(candidates))


def build_tests_edges(
    test_nodes: List[Dict[str, str]],
    function_nodes: List[Dict[str, str]],
    class_nodes: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Build TESTS edges from test nodes to function/class targets."""
    edges: List[Dict[str, str]] = []
    edge_keys: Set[tuple[str, str, str]] = set()
    for test_node in test_nodes:
        targets = find_test_targets(test_node["target_hint"], function_nodes, class_nodes)
        for target_id in targets:
            edge_key = (test_node["id"], target_id, "TESTS")
            if edge_key not in edge_keys:
                edge_keys.add(edge_key)
                edges.append(
                    {
                        "source": test_node["id"],
                        "target": target_id,
                        "type": "TESTS",
                    }
                )
    return edges


def validate_graph_contract(nodes: List[Dict[str, str]], edges: List[Dict[str, str]]) -> None:
    """Validate the currently generated graph against the schema contract."""
    for node in nodes:
        node_type = node.get("type", "")
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unknown node type: {node_type}")
        required = NODE_REQUIRED_FIELDS.get(node_type, set())
        missing = required - set(node.keys())
        if missing:
            raise ValueError(f"Node {node.get('id', '<no-id>')} missing fields: {sorted(missing)}")

    for edge in edges:
        edge_type = edge.get("type", "")
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge type: {edge_type}")
        required = EDGE_REQUIRED_FIELDS.get(edge_type, set())
        missing = required - set(edge.keys())
        if missing:
            raise ValueError(f"Edge {edge} missing fields: {sorted(missing)}")


def build_file_import_graph(repo_path: Path, exclude_dirs: Set[str] | None = None) -> Dict[str, object]:
    """
    Build a graph with:
    - File nodes
    - Function and Class nodes
    - Test nodes for pytest/unittest patterns
    - IMPORTS edges
    - IN_FILE edges
    - TESTS edges
    """
    py_files = collect_python_files(repo_path, exclude_dirs=exclude_dirs)
    file_to_module: Dict[Path, str] = {p: module_name_from_path(p, repo_path) for p in py_files}
    module_to_file: Dict[str, Path] = {}
    for file_path in py_files:
        for alias in module_aliases_from_path(file_path, repo_path):
            module_to_file.setdefault(alias, file_path)

    nodes: List[Dict[str, str]] = []
    edges: List[Dict[str, str]] = []
    edge_keys: Set[tuple[str, str, str]] = set()
    all_function_nodes: List[Dict[str, str]] = []
    all_class_nodes: List[Dict[str, str]] = []
    all_test_nodes: List[Dict[str, str]] = []

    for file_path, module_name in file_to_module.items():
        file_id = str(file_path.relative_to(repo_path))
        nodes.append(
            {
                "id": file_id,
                "type": "File",
                "path": file_id,
                "module": module_name,
                "language": "python",
            }
        )
        function_nodes, class_nodes, in_file_edges = extract_functions_and_classes(
            file_path=file_path,
            repo_path=repo_path,
            module_name=module_name,
        )
        test_nodes, _ = extract_tests(file_path=file_path, repo_path=repo_path)

        all_function_nodes.extend(function_nodes)
        all_class_nodes.extend(class_nodes)
        all_test_nodes.extend(test_nodes)

        nodes.extend(function_nodes)
        nodes.extend(class_nodes)
        nodes.extend(test_nodes)
        for edge in in_file_edges:
            edge_key = (edge["source"], edge["target"], edge["type"])
            if edge_key not in edge_keys:
                edge_keys.add(edge_key)
                edges.append(edge)

    tests_edges = build_tests_edges(all_test_nodes, all_function_nodes, all_class_nodes)
    for edge in tests_edges:
        edge_key = (edge["source"], edge["target"], edge["type"])
        if edge_key not in edge_keys:
            edge_keys.add(edge_key)
            edges.append(edge)

    for file_path in py_files:
        source_id = str(file_path.relative_to(repo_path))
        imports = extract_imports(file_path)
        for imported_module in imports:
            # Direct match
            target_path = module_to_file.get(imported_module)
            if target_path is None:
                # Try best-effort prefix fallback (e.g. package.sub.mod -> package)
                parts = imported_module.split(".")
                while len(parts) > 1 and target_path is None:
                    parts.pop()
                    target_path = module_to_file.get(".".join(parts))

            if target_path is not None:
                target_id = str(target_path.relative_to(repo_path))
                if source_id != target_id:
                    edge_key = (source_id, target_id, "IMPORTS")
                    if edge_key not in edge_keys:
                        edge_keys.add(edge_key)
                        edges.append(
                            {
                                "source": source_id,
                                "target": target_id,
                                "type": "IMPORTS",
                            }
                        )

    validate_graph_contract(nodes=nodes, edges=edges)
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_node_types": sorted(NODE_TYPES),
        "schema_edge_types": sorted(EDGE_TYPES),
        "implemented_node_types": ["File", "Function", "Class", "Test"],
        "implemented_edge_types": ["IMPORTS", "IN_FILE", "TESTS"],
        "nodes": nodes,
        "edges": edges,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build graph with File, Function, Class, Test nodes and IMPORTS/IN_FILE/TESTS edges.")
    parser.add_argument("--repo", required=True, help="Path to target repository")
    parser.add_argument(
        "--output",
        default=None,
        help="Output graph JSON path (default: results/graphs/<repo_name>_graph.json)",
    )
    parser.add_argument(
        "--exclude-dirs",
        default="examples,docs,data",
        help="Comma-separated directory names to exclude from repository traversal",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if args.output is None:
        output_path = Path("results") / "graphs" / f"{repo_path.name}_graph.json"
    else:
        output_path = Path(args.output).resolve()

    exclude_dirs = {
        directory.strip().lower()
        for directory in args.exclude_dirs.split(",")
        if directory.strip()
    }
    graph = build_file_import_graph(repo_path, exclude_dirs=exclude_dirs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    print(f"Graph written to: {output_path}")
    print(f"Nodes: {len(graph['nodes'])}")
    print(f"Edges: {len(graph['edges'])}")


if __name__ == "__main__":
    main()
