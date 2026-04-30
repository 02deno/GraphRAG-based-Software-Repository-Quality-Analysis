from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..graph.edges.tests_edge import TestsEdge
from ..graph.nodes.test_node import TestNode


def is_test_file(file_path: Path) -> bool:
    """Return True if the path looks like a pytest-style test module.

    Args:
        file_path: Candidate Python file.

    Returns:
        True when the filename starts with ``test_`` or parent directory suggests tests.
    """
    return file_path.name.startswith("test_") or file_path.parent.name.startswith("test_")


class TestCollector(ast.NodeVisitor):
    """AST visitor that collects ``test_*`` function definitions."""

    def __init__(self, file_id: str, module_name: str) -> None:
        """Store ids used to build stable :class:`TestNode` keys.

        Args:
            file_id: Repository-relative path for this file.
            module_name: Dotted module name for qualified test names.
        """
        self.file_id = file_id
        self.module_name = module_name
        self.tests: List[TestNode] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Record pytest-style test functions and recurse into the body."""
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
        """Treat async tests like synchronous test functions."""
        self.visit_FunctionDef(node)


def extract_tests(file_path: Path, repo_path: Path, module_name: str) -> Tuple[List[TestNode], List[TestsEdge]]:
    """If *file_path* is a test module, extract test nodes and file-level TESTS edges.

    Args:
        file_path: Python file to inspect.
        repo_path: Repository root for relative ids.
        module_name: Dotted module name.

    Returns:
        ``(test_nodes, tests_edges)``; empty when the file is not considered a test file
        or parsing fails.
    """
    file_id = str(file_path.relative_to(repo_path))
    if not is_test_file(file_path):
        return [], []

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return [], []

    collector = TestCollector(file_id=file_id, module_name=module_name)
    collector.visit(tree)
    tests_edges: List[TestsEdge] = [TestsEdge(source=test.id, target=file_id) for test in collector.tests]
    return collector.tests, tests_edges


def find_test_targets(test_node: TestNode, nodes_by_type: Dict[str, Dict[str, object]]) -> Optional[str]:
    """Map a test's ``target_hint`` to a function or class node id using simple name lookup.

    Args:
        test_node: Extracted test with ``target_hint`` (typically ``test_foo`` → ``foo``).
        nodes_by_type: Maps ``Function`` / ``Class`` to ``{simple_name: node_id}``.

    Returns:
        Target node id when a heuristic match exists, else ``None``.
    """
    target_name = test_node.target_hint.replace("test_", "")
    if target_name in nodes_by_type.get("Function", {}):
        return str(nodes_by_type["Function"][target_name])
    if target_name in nodes_by_type.get("Class", {}):
        return str(nodes_by_type["Class"][target_name])
    return None


def build_tests_edges(test_nodes: List[TestNode], nodes_by_type: Dict[str, Dict[str, str]]) -> List[TestsEdge]:
    """Create TESTS edges from each test node to a resolved function or class target.

    Args:
        test_nodes: All discovered tests (typically across the repo).
        nodes_by_type: Name lookup tables produced during graph construction.

    Returns:
        List of :class:`TestsEdge` instances for resolved targets only.
    """
    edges: List[TestsEdge] = []
    for test_node in test_nodes:
        target_id = find_test_targets(test_node, nodes_by_type)
        if target_id:
            edges.append(TestsEdge(source=test_node.id, target=target_id))
    return edges
