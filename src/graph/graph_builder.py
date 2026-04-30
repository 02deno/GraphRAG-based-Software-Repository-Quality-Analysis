from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set

from src.extractors import (
    build_tests_edges,
    collect_python_files,
    extract_functions_and_classes,
    extract_imports,
    extract_tests,
    module_aliases_from_path,
    module_name_from_path,
)
from src.graph.edges.imports_edge import ImportsEdge
from src.graph.edges.in_file_edge import InFileEdge
from src.graph.edges.tests_edge import TestsEdge
from src.graph.nodes.file_node import FileNode
from src.graph.nodes.function_node import FunctionNode
from src.graph.nodes.test_node import TestNode
from .schema import graph_to_dict


class GraphBuilder:
    """Build a structured graph from a Python repository."""

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path
        self.nodes: Dict[str, object] = {}
        self.edges: List[object] = []
        self.nodes_by_type: Dict[str, Dict[str, str]] = {
            "Function": {},
            "Class": {},
            "Test": {},
        }
        self.file_module_aliases: Dict[str, Set[str]] = {}

    def build(self) -> None:
        python_files = collect_python_files(self.repo_path, exclude_dirs={"venv", "node_modules", "__pycache__"})
        file_nodes: List[FileNode] = []

        for file_path in python_files:
            module_name = module_name_from_path(file_path, self.repo_path)
            file_id = str(file_path.relative_to(self.repo_path))
            file_node = FileNode(id=file_id, path=file_id, module=module_name, language="python")
            file_nodes.append(file_node)
            self.nodes[file_id] = file_node
            self.file_module_aliases[file_id] = module_aliases_from_path(file_path, self.repo_path)

        for file_node in file_nodes:
            source_path = self.repo_path / file_node.path
            imports = extract_imports(source_path)
            self.edges.extend(self._build_import_edges(file_node.path, imports))

            functions, classes, in_file_edges = extract_functions_and_classes(
                source_path,
                self.repo_path,
                file_node.module,
            )
            self.edges.extend(in_file_edges)
            for function_node in functions:
                self.nodes[function_node.id] = function_node
                self.nodes_by_type["Function"][function_node.name] = function_node.id
            for class_node in classes:
                self.nodes[class_node.id] = class_node
                self.nodes_by_type["Class"][class_node.name] = class_node.id

        test_nodes: List[TestNode] = []
        test_edges: List[TestsEdge] = []
        for file_node in file_nodes:
            source_path = self.repo_path / file_node.path
            extracted_tests, extracted_edges = extract_tests(source_path, self.repo_path, file_node.module)
            for test_node in extracted_tests:
                self.nodes[test_node.id] = test_node
                self.nodes_by_type["Test"][test_node.name] = test_node.id
            test_nodes.extend(extracted_tests)
            test_edges.extend(extracted_edges)

        self.edges.extend(test_edges)
        self.edges.extend(build_tests_edges(test_nodes, self.nodes_by_type))

    def _build_import_edges(self, file_id: str, imports: Set[str]) -> List[ImportsEdge]:
        module_lookup = {
            alias: target_file_id
            for target_file_id, aliases in self.file_module_aliases.items()
            for alias in aliases
        }
        edges: List[ImportsEdge] = []
        for imported_module in imports:
            if imported_module in module_lookup:
                edges.append(ImportsEdge(source=file_id, target=module_lookup[imported_module]))
        return edges

    def to_dict(self) -> dict:
        return {
            "nodes": [self._node_to_dict(node) for node in self.nodes.values()],
            "edges": [self._edge_to_dict(edge) for edge in self.edges],
        }

    @staticmethod
    def _node_to_dict(node: object) -> dict:
        if hasattr(node, "to_dict"):
            return node.to_dict()
        return node.__dict__

    @staticmethod
    def _edge_to_dict(edge: object) -> dict:
        if hasattr(edge, "to_dict"):
            return edge.to_dict()
        return edge.__dict__


def build_graph(repo_path: Path) -> dict:
    """Build a graph document from a repository path."""
    builder = GraphBuilder(repo_path)
    builder.build()
    return graph_to_dict(builder.to_dict()["nodes"], builder.to_dict()["edges"])


def save_graph(graph: dict, output_path: Path) -> None:
    """Write the graph document to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
