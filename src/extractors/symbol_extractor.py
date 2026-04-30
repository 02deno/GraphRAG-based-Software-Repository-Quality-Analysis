from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Tuple

from ..graph.edges.in_file_edge import InFileEdge
from ..graph.nodes.class_node import ClassNode
from ..graph.nodes.function_node import FunctionNode


class SymbolCollector(ast.NodeVisitor):
    """Collect Python function and class declarations from a module AST."""

    def __init__(self, module_name: str, file_id: str) -> None:
        self.module_name = module_name
        self.file_id = file_id
        self.scope_stack: List[str] = []
        self.function_nodes: List[FunctionNode] = []
        self.class_nodes: List[ClassNode] = []

    def _qualified_name(self, symbol_name: str) -> str:
        scoped = ".".join(self.scope_stack + [symbol_name])
        return f"{self.module_name}.{scoped}" if self.module_name else scoped

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self._qualified_name(node.name)
        node_id = f"class::{self.file_id}::{qualified_name}"
        self.class_nodes.append(ClassNode(id=node_id, name=node.name, qualified_name=qualified_name, file_path=self.file_id))
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        qualified_name = self._qualified_name(node.name)
        node_id = f"function::{self.file_id}::{qualified_name}"
        self.function_nodes.append(FunctionNode(id=node_id, name=node.name, qualified_name=qualified_name, file_path=self.file_id))
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)


def extract_functions_and_classes(
    file_path: Path,
    repo_path: Path,
    module_name: str,
) -> Tuple[List[FunctionNode], List[ClassNode], List[InFileEdge]]:
    """Extract function and class nodes from a Python file."""
    file_id = str(file_path.relative_to(repo_path))
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return [], [], []

    collector = SymbolCollector(module_name=module_name, file_id=file_id)
    collector.visit(tree)
    in_file_edges: List[InFileEdge] = []
    for function_node in collector.function_nodes:
        in_file_edges.append(InFileEdge(source=function_node.id, target=file_id))
    for class_node in collector.class_nodes:
        in_file_edges.append(InFileEdge(source=class_node.id, target=file_id))

    return collector.function_nodes, collector.class_nodes, in_file_edges
