# Project Structure

This document describes the current high-level structure of the project.

- `README.md`
  - Main project overview and quick run commands.
- `requirements.txt`
  - Python dependency list (currently minimal).
- `src/`
  - Source scripts.
  - `schema_contract.py`: Fixed schema dictionary (types + required fields + version).
  - `build_graph.py`: Extracts `File` and `IMPORTS` graph.
  - `analyze_graph.py`: Runs basic degree-based graph analysis.
  - `visualize_graph.py`: Generates structure and degree-analysis visuals.
  - `repo_stats.py`: Computes general repository-level Python statistics.
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
