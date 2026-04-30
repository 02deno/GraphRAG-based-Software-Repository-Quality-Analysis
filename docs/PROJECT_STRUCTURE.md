# Project Structure

This document describes the current high-level structure of the project.

- `README.md`
  - Main project overview and quick run commands.
- `requirements.txt`
  - Python dependency list (currently minimal).
- `src/`
  - Root package entrypoint for the project source modules.
  - `__init__.py`: Root package exports for `graph`, `extractors`, `analysis`, `visualization`, and `stats`.
  - `build_graph.py`: Thin CLI wrapper that delegates graph construction to `src.graph.GraphBuilder`.
  - `analyze_graph.py`: Thin CLI wrapper calling `src.analysis.graph_analysis`.
  - `visualize_graph.py`: Thin CLI wrapper calling `src.visualization.graph_visualization`.
  - `main_pipeline.py`: Full pipeline script that builds the graph, runs analysis, and generates visualization summaries.
  - `repo_stats.py`: Thin CLI wrapper calling `src.stats.repository_stats`.
  - `graph/`: modular graph model and builder.
    - `graph_builder.py`: Builds graph nodes/edges from repository AST data.
    - `schema.py`: Validates node/edge schema and serializes graph documents.
    - `nodes/`: one node class per file.
    - `edges/`: one edge class per file.
  - `extractors/`: modular AST extractors for Python files, imports, symbols, and tests.
  - `analysis/`: graph analysis package for reporting degrees and node centrality.
  - `visualization/`: graph visualization package for plotting and visual summaries.
  - `stats/`: repository statistics package for LOC, functions, classes, and variable counts.
  - `schema_contract.py`: legacy schema contract reference used for compatibility and docs.
- `docs/`
  - Project documentation.
  - `PROJECT_PLAN.md`: Step-by-step roadmap.
  - `REPO_SELECTION.md`: Why `langchain-ai/langgraph` was selected.
  - `GRAPH_SCHEMA.md`: Initial graph node/edge schema.
  - `REPO_COMPATIBILITY_CHECKLIST.md`: Readiness checklist for running the current pipeline on other repositories.
  - `FUNCTIONS.md`: Function-level script documentation.
  - `PROJECT_STRUCTURE.md`: Current folder and file organization.
  - `REPORT_DRAFT.md`: Draft report with snapshot and findings.
- `data/`
  - Target repositories and input data.
- `results/`
  - Generated outputs (e.g. `results/graphs/<repo_name>_graph.json`, `graph_structure.png`, `repo_stats.txt`).
