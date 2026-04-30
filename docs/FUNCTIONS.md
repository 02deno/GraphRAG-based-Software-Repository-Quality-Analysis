# Functions Documentation

This document explains the current package-level API and CLI entrypoints in the project.

## `src/build_graph.py`

- `main()`
  - CLI entrypoint for building a repository graph document.
  - Delegates graph construction to `src.graph.GraphBuilder`.
- `default_output_path(repo_path)`
  - Builds a default output path under `results/graphs`.
- `save_json(document, output_path)`
  - Serializes a graph document to JSON on disk.

## `src/analyze_graph.py`

- `main()`
  - CLI entrypoint for graph analysis.
  - Delegates analysis to `src.analysis.graph_analysis`.

## `src/visualize_graph.py`

- `main()`
  - CLI entrypoint for graph visualization.
  - Delegates visualization to `src.visualization.graph_visualization`.

## `src/repo_stats.py`

- `main()`
  - CLI entrypoint for repository statistics.
  - Delegates stats computation to `src.stats.repository_stats`.

## `src/main_pipeline.py`

- `main()`
  - CLI entrypoint for the full repository pipeline.
  - Runs graph build, analysis report generation, and visualization summary creation.

## `src/graph/graph_builder.py`

- `GraphBuilder`
  - Builds the repository graph by collecting Python files and extracting graph elements.
  - Creates `File`, `Function`, `Class`, and `Test` nodes.
  - Generates `IMPORTS`, `IN_FILE`, and `TESTS` edges.
- `build_graph(repo_path)`
  - Convenience wrapper that returns a serialized graph document.
- `save_graph(graph, output_path)`
  - Writes graph JSON to disk.

## `src/graph/schema.py`

- `validate_graph_contract(nodes, edges)`
  - Validates nodes and edges against the target schema.
- `graph_to_dict(nodes, edges)`
  - Serializes nodes and edges into a graph document with schema metadata.

## `src/extractors/python_file_collector.py`

- `collect_python_files(repo_path, exclude_dirs)`
  - Collects Python files under a repository while excluding folders such as `venv`, `node_modules`, and `__pycache__`.
- `module_name_from_path(file_path, repo_path)`
  - Converts a file path to a dotted Python module name.
- `module_aliases_from_path(file_path, repo_path)`
  - Builds import alias candidates for local modules.

## `src/extractors/import_extractor.py`

- `extract_imports(file_path)`
  - Parses a file AST and extracts imported module names.

## `src/extractors/symbol_extractor.py`

- `extract_functions_and_classes(file_path, repo_path, module_name)`
  - Extracts `Function` and `Class` nodes.
  - Builds `IN_FILE` edges linking symbols to their source file.

## `src/extractors/test_extractor.py`

- `extract_tests(file_path, repo_path, module_name)`
  - Extracts `Test` nodes from pytest-style test files.
  - Builds placeholder `TESTS` edges to the containing file.
- `build_tests_edges(test_nodes, nodes_by_type)`
  - Resolves test targets by heuristic name matching and creates `TESTS` edges.

## `src/graph/nodes/`

- `FileNode`, `FunctionNode`, `ClassNode`, `TestNode`, `CommitNode`
  - Data classes representing graph node types.

## `src/graph/edges/`

- `ImportsEdge`, `InFileEdge`, `TestsEdge`, `CallsEdge`, `ModifiedByEdge`
  - Data classes representing graph edge types.
