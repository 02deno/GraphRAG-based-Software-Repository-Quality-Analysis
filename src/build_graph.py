from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Set

from schema_contract import (
    EDGE_REQUIRED_FIELDS,
    EDGE_TYPES,
    NODE_REQUIRED_FIELDS,
    NODE_TYPES,
    SCHEMA_VERSION,
)


def collect_python_files(repo_path: Path, exclude_dirs: Set[str] | None = None) -> List[Path]:
    """Collect all Python files under the repository path, excluding named directories."""
    if exclude_dirs is None:
        exclude_dirs = set()
    exclude_dirs = {directory.lower() for directory in exclude_dirs}

    python_files: List[Path] = []
    for p in repo_path.rglob("*.py"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(repo_path).parts
        if any(part.lower() in exclude_dirs for part in rel_parts):
            continue
        python_files.append(p)
    return python_files


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


class SymbolCollector(ast.NodeVisitor):
    """Collect function and class symbols with qualified names."""

    def __init__(self, module_name: str, file_id: str) -> None:
        self.module_name = module_name
        self.file_id = file_id
        self.scope_stack: List[str] = []
        self.function_nodes: List[Dict[str, str]] = []
        self.class_nodes: List[Dict[str, str]] = []

    def _qualified_name(self, symbol_name: str) -> str:
        scoped = ".".join(self.scope_stack + [symbol_name])
        if self.module_name:
            return f"{self.module_name}.{scoped}"
        return scoped

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self._qualified_name(node.name)
        self.class_nodes.append(
            {
                "id": f"class::{self.file_id}::{qualified_name}",
                "type": "Class",
                "name": node.name,
                "qualified_name": qualified_name,
                "file_path": self.file_id,
            }
        )
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        qualified_name = self._qualified_name(node.name)
        self.function_nodes.append(
            {
                "id": f"function::{self.file_id}::{qualified_name}",
                "type": "Function",
                "name": node.name,
                "qualified_name": qualified_name,
                "file_path": self.file_id,
            }
        )
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)


def extract_functions_and_classes(
    file_path: Path,
    repo_path: Path,
    module_name: str,
) -> tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Extract Function/Class nodes and IN_FILE edges for a Python file.
    Returns (function_nodes, class_nodes, in_file_edges).
    """
    file_id = str(file_path.relative_to(repo_path))
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return [], [], []

    collector = SymbolCollector(module_name=module_name, file_id=file_id)
    collector.visit(tree)

    in_file_edges: List[Dict[str, str]] = []
    for fn in collector.function_nodes:
        in_file_edges.append({"source": fn["id"], "target": file_id, "type": "IN_FILE"})
    for cls in collector.class_nodes:
        in_file_edges.append({"source": cls["id"], "target": file_id, "type": "IN_FILE"})

    return collector.function_nodes, collector.class_nodes, in_file_edges


def is_test_file(file_path: Path) -> bool:
    """Determine if a Python file is a test file by naming or path conventions."""
    filename = file_path.name
    if filename.startswith("test_") or filename.endswith("_test.py"):
        return True
    return any(part.lower() == "tests" or part.lower() == "test" for part in file_path.parts)


class TestCollector(ast.NodeVisitor):
    """Collect test functions and test methods from AST."""

    def __init__(self, file_id: str) -> None:
        self.file_id = file_id
        self.scope_stack: List[str] = []
        self.test_nodes: List[Dict[str, str]] = []

    def _qualified_name(self, symbol_name: str) -> str:
        return ".".join(self.scope_stack + [symbol_name]) if self.scope_stack else symbol_name

    def _target_hint(self, symbol_name: str) -> str:
        if symbol_name.startswith("test_"):
            return symbol_name[len("test_"):]
        return symbol_name

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("test_"):
            qualified_name = self._qualified_name(node.name)
            self.test_nodes.append(
                {
                    "id": f"test::{self.file_id}::{qualified_name}",
                    "type": "Test",
                    "name": node.name,
                    "file_path": self.file_id,
                    "target_hint": self._target_hint(node.name),
                }
            )
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)


def extract_tests(file_path: Path, repo_path: Path) -> tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Extract Test nodes from Python test files, plus placeholder test metadata."""
    if not is_test_file(file_path):
        return [], []

    file_id = str(file_path.relative_to(repo_path))
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return [], []

    collector = TestCollector(file_id=file_id)
    collector.visit(tree)
    return collector.test_nodes, []


def find_test_targets(
    target_hint: str,
    function_nodes: List[Dict[str, str]],
    class_nodes: List[Dict[str, str]],
) -> List[str]:
    """Find candidate function/class node ids that match a test target hint."""
    hint = target_hint.lower().replace("test_", "")
    tokens = [token for token in re.split(r"[^a-z0-9]+", hint) if token]
    candidates: List[str] = []

    def matches(node: Dict[str, str]) -> bool:
        if is_test_file(Path(node["file_path"])):
            return False
        name = node["name"].lower()
        qualified = node.get("qualified_name", "").lower()
        if hint and hint in qualified:
            return True
        if hint and hint == name:
            return True
        if any(token in name or token in qualified for token in tokens):
            return True
        return False

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
