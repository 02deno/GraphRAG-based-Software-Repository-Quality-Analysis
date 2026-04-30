from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..graph.edges.tests_edge import TestsEdge
from ..graph.nodes.test_node import TestNode


def is_test_file(file_path: Path) -> bool:
    return file_path.name.startswith("test_") or file_path.parent.name.startswith("test_")


class TestCollector(ast.NodeVisitor):
    """Extract test function definitions from a Python module."""

    def __init__(self, file_id: str, module_name: str) -> None:
        self.file_id = file_id
        self.module_name = module_name
        self.tests: List[TestNode] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("test_"):
            test_id = f"test::{self.file_id}::{self.module_name}.{node.name}"
            self.tests.append(
                TestNode(
                    id=test_id,
                    name=node.name,
                    file_path=self.file_id,
                    target_hint=node.name,
                )
            )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)


def extract_tests(file_path: Path, repo_path: Path, module_name: str) -> Tuple[List[TestNode], List[TestsEdge]]:
    """Extract test nodes and placeholder TESTS edges from test files."""
    file_id = str(file_path.relative_to(repo_path))
    if not is_test_file(file_path):
        return [], []

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return [], []

    collector = TestCollector(file_id=file_id, module_name=module_name)
    collector.visit(tree)
    tests_edges: List[TestsEdge] = [TestsEdge(source=test.id, target=file_id) for test in collector.tests]
    return collector.tests, tests_edges


def find_test_targets(test_node: TestNode, nodes_by_type: Dict[str, Dict[str, object]]) -> Optional[str]:
    """Resolve a test target node id by simple naming heuristics."""
    target_name = test_node.target_hint.replace("test_", "")
    if target_name in nodes_by_type.get("Function", {}):
        return nodes_by_type["Function"][target_name]
    if target_name in nodes_by_type.get("Class", {}):
        return nodes_by_type["Class"][target_name]
    return None


def build_tests_edges(test_nodes: List[TestNode], nodes_by_type: Dict[str, Dict[str, str]]) -> List[TestsEdge]:
    """Create TESTS edges from tests to target functions or classes."""
    edges: List[TestsEdge] = []
    for test_node in test_nodes:
        target_id = find_test_targets(test_node, nodes_by_type)
        if target_id:
            edges.append(TestsEdge(source=test_node.id, target=target_id))
    return edges
