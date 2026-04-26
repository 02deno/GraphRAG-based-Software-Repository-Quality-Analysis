from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Dict, List, Set

from schema_contract import (
    EDGE_REQUIRED_FIELDS,
    EDGE_TYPES,
    NODE_REQUIRED_FIELDS,
    NODE_TYPES,
    SCHEMA_VERSION,
)


def collect_python_files(repo_path: Path) -> List[Path]:
    """Collect all Python files under the repository path."""
    return [p for p in repo_path.rglob("*.py") if p.is_file()]


def module_name_from_path(file_path: Path, repo_path: Path) -> str:
    """Convert file path to a dotted module-like name."""
    rel = file_path.relative_to(repo_path)
    parts = list(rel.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def module_aliases_from_path(file_path: Path, repo_path: Path) -> Set[str]:
    """
    Generate module aliases from a file path.

    Why aliases?
    Monorepos can store packages under nested folders (e.g. libs/langgraph/langgraph).
    Imports usually reference the package path (langgraph.*), not the full repository path.
    """
    rel = file_path.relative_to(repo_path)
    parts = list(rel.parts)
    if not parts:
        return set()

    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return set()

    aliases: Set[str] = set()
    for i in range(len(parts)):
        alias = ".".join(parts[i:])
        if alias:
            aliases.add(alias)
    return aliases


def extract_imports(file_path: Path) -> Set[str]:
    """Extract imported module names from a Python file."""
    imports: Set[str] = set()
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


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


def build_file_import_graph(repo_path: Path) -> Dict[str, object]:
    """
    Build a minimal graph with:
    - File nodes
    - IMPORTS edges (File -> File when resolvable inside repository)
    """
    py_files = collect_python_files(repo_path)
    file_to_module: Dict[Path, str] = {p: module_name_from_path(p, repo_path) for p in py_files}
    module_to_file: Dict[str, Path] = {}
    for file_path in py_files:
        for alias in module_aliases_from_path(file_path, repo_path):
            module_to_file.setdefault(alias, file_path)

    nodes: List[Dict[str, str]] = []
    edges: List[Dict[str, str]] = []
    edge_keys: Set[tuple[str, str, str]] = set()

    for file_path, module_name in file_to_module.items():
        nodes.append(
            {
                "id": str(file_path.relative_to(repo_path)),
                "type": "File",
                "path": str(file_path.relative_to(repo_path)),
                "module": module_name,
                "language": "python",
            }
        )

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
        "implemented_node_types": ["File"],
        "implemented_edge_types": ["IMPORTS"],
        "nodes": nodes,
        "edges": edges,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build minimal File+IMPORTS graph.")
    parser.add_argument("--repo", required=True, help="Path to target repository")
    parser.add_argument(
        "--output",
        default="results/graph_file_imports.json",
        help="Output graph JSON path",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    output_path = Path(args.output).resolve()

    graph = build_file_import_graph(repo_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    print(f"Graph written to: {output_path}")
    print(f"Nodes: {len(graph['nodes'])}")
    print(f"Edges: {len(graph['edges'])}")


if __name__ == "__main__":
    main()
