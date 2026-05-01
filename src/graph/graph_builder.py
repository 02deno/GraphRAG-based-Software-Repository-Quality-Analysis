from __future__ import annotations

import json
import logging
from collections.abc import Callable
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

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Orchestrate scanning a Python repo and assembling typed nodes and edges."""

    def __init__(self, repo_path: Path) -> None:
        """Prepare empty stores keyed by the resolved repository root.

        Args:
            repo_path: Absolute path to the repository root directory.
        """
        self.repo_path = repo_path
        self.nodes: Dict[str, object] = {}
        self.edges: List[object] = []
        self.nodes_by_type: Dict[str, Dict[str, str]] = {
            "Function": {},
            "Class": {},
            "Test": {},
        }
        self.file_module_aliases: Dict[str, Set[str]] = {}

    def build(
        self,
        *,
        file_progress: Callable[[str, int, int, str], None] | None = None,
    ) -> None:
        """Populate ``nodes`` and ``edges`` by walking Python files under ``repo_path``.

        Args:
            file_progress: Optional ``(stage, index, total, relative_path)`` hook where
                ``stage`` is ``"scan"`` (file list), ``"extract"`` (imports + AST symbols),
                or ``"tests"`` (test discovery). ``index`` is 0-based within that stage.
        """
        python_files = collect_python_files(self.repo_path, exclude_dirs={"venv", "node_modules", "__pycache__"})
        n_py = len(python_files)
        logger.info("graph_build_start python_files=%d", n_py)
        file_nodes: List[FileNode] = []

        for i, file_path in enumerate(python_files):
            module_name = module_name_from_path(file_path, self.repo_path)
            file_id = str(file_path.relative_to(self.repo_path))
            file_node = FileNode(id=file_id, path=file_id, module=module_name, language="python")
            file_nodes.append(file_node)
            self.nodes[file_id] = file_node
            self.file_module_aliases[file_id] = module_aliases_from_path(file_path, self.repo_path)
            if file_progress is not None:
                file_progress("scan", i, n_py, file_id)
            if n_py and (i % max(1, min(25, n_py // 8 or 1)) == 0 or i == n_py - 1):
                logger.info("graph_build_scan %d/%d %s", i + 1, n_py, file_id)

        n_files = len(file_nodes)
        for i, file_node in enumerate(file_nodes):
            source_path = self.repo_path / file_node.path
            if file_progress is not None:
                file_progress("extract", i, n_files, file_node.path)
            if n_files and (i % max(1, min(20, n_files // 10 or 1)) == 0 or i == n_files - 1):
                logger.info("graph_build_extract %d/%d %s", i + 1, n_files, file_node.path)
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
        for i, file_node in enumerate(file_nodes):
            source_path = self.repo_path / file_node.path
            if file_progress is not None:
                file_progress("tests", i, n_files, file_node.path)
            if n_files and (i % max(1, min(20, n_files // 10 or 1)) == 0 or i == n_files - 1):
                logger.info("graph_build_tests %d/%d %s", i + 1, n_files, file_node.path)
            extracted_tests, extracted_edges = extract_tests(source_path, self.repo_path, file_node.module)
            for test_node in extracted_tests:
                self.nodes[test_node.id] = test_node
                self.nodes_by_type["Test"][test_node.name] = test_node.id
            test_nodes.extend(extracted_tests)
            test_edges.extend(extracted_edges)

        self.edges.extend(test_edges)
        self.edges.extend(build_tests_edges(test_nodes, self.nodes_by_type))

    def _build_import_edges(self, file_id: str, imports: Set[str]) -> List[ImportsEdge]:
        """Resolve ``imports`` against collected module aliases and emit IMPORTS edges."""
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
        """Return serializable ``nodes`` and ``edges`` lists (dict rows per element)."""
        return {
            "nodes": [self._node_to_dict(node) for node in self.nodes.values()],
            "edges": [self._edge_to_dict(edge) for edge in self.edges],
        }

    @staticmethod
    def _node_to_dict(node: object) -> dict:
        """Serialize a node instance using ``to_dict`` when available."""
        if hasattr(node, "to_dict"):
            return node.to_dict()
        return node.__dict__

    @staticmethod
    def _edge_to_dict(edge: object) -> dict:
        """Serialize an edge instance using ``to_dict`` when available."""
        if hasattr(edge, "to_dict"):
            return edge.to_dict()
        return edge.__dict__


def build_graph(repo_path: Path) -> dict:
    """Build and return a schema-wrapped graph document dict for *repo_path*.

    Returns:
        Mapping including ``nodes``, ``edges``, and schema metadata from :func:`graph_to_dict`.
    """
    builder = GraphBuilder(repo_path)
    builder.build()
    raw = builder.to_dict()
    return graph_to_dict(raw["nodes"], raw["edges"])


def save_graph(graph: dict, output_path: Path) -> None:
    """Write *graph* as indented JSON to *output_path* (parents created as needed).

    Args:
        graph: Full document from :func:`graph_to_dict` or equivalent.
        output_path: Destination ``.json`` file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
