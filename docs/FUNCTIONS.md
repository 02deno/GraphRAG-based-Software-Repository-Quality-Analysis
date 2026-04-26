# Functions Documentation

This document explains the current functions in the project scripts.

## `src/build_graph.py`

- `collect_python_files(repo_path)`
  - Collects all `.py` files in the target repository.
- `module_name_from_path(file_path, repo_path)`
  - Converts a file path into a dotted module-like name.
- `module_aliases_from_path(file_path, repo_path)`
  - Generates possible module aliases to support monorepo import matching.
- `extract_imports(file_path)`
  - Parses Python AST and extracts imported module names.
- `SymbolCollector(ast.NodeVisitor)`
  - Walks AST scopes and collects `Function` / `Class` symbols with qualified names.
- `extract_functions_and_classes(file_path, repo_path, module_name)`
  - Extracts `Function` and `Class` nodes and generates `IN_FILE` edges.
- `validate_graph_contract(nodes, edges)`
  - Validates generated nodes/edges against the fixed schema contract.
- `build_file_import_graph(repo_path)`
  - Builds graph JSON with `File`, `Function`, `Class` nodes and `IMPORTS`, `IN_FILE` edges.
- `main()`
  - CLI entry point for building and saving the graph.

## `src/analyze_graph.py`

- `load_graph(graph_path)`
  - Loads graph JSON output from `build_graph.py`.
- `compute_degrees(edges)`
  - Computes in-degree and out-degree for directed edges.
- `node_path_map(nodes)`
  - Maps node ids to readable file paths.
- `top_k(counter, k)`
  - Returns top-k ranked entries from a counter.
- `main()`
  - CLI entry point that prints top imported and top importing files.

## `src/visualize_graph.py`

- `load_graph(graph_path)`
  - Loads graph JSON for visualization.
- `compute_degrees(edges)`
  - Computes in-degree and out-degree counters.
- `node_path_map(nodes)`
  - Maps node ids to readable file paths.
- `build_nx_graph(nodes, edges)`
  - Builds a `networkx.DiGraph` from nodes and edges.
- `top_nodes_by_total_degree(in_degree, out_degree, top_n)`
  - Selects high-degree nodes for readable structure plots.
- `plot_structure_subgraph(graph, selected_nodes, output_path)`
  - Saves a labeled network visualization image of selected nodes.
- `plot_degree_bars(in_degree, out_degree, path_by_id, top_k, output_path)`
  - Saves bar-chart visualization for top in/out degree files.
- `build_visual_summary(graph_path, nodes, edges, in_degree, out_degree, path_by_id, top_k)`
  - Builds a text summary for visual outputs.
- `main()`
  - CLI entry point that creates structure and analysis visual outputs.

## `src/repo_stats.py`

- `collect_python_files(repo_path)`
  - Collects all Python files in the target repository.
- `count_loc(file_path)`
  - Counts non-empty lines in a file.
- `analyze_python_file(file_path)`
  - Counts classes, functions, and variable assignments using Python AST.
- `build_repo_stats(repo_path)`
  - Aggregates file-level counts into repository-level totals.
- `format_stats_report(repo_path, stats)`
  - Converts statistics into a readable text report.
- `main()`
  - CLI entry point that prints and saves repository statistics.
