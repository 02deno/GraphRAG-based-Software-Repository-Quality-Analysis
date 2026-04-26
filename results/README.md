# Results Folder Organization

This folder is organized into subfolders for clarity:

- `graphs/`
  - Graph JSON files.
  - Examples:
    - `langgraph_graph.json` (all edges)
    - `langgraph_imports_graph.json` (`IMPORTS` only)
    - `langgraph_in_file_graph.json` (`IN_FILE` only)
- `visuals/`
  - PNG outputs for graph structure and degree plots.
- `reports/`
  - Text summaries and analysis reports.
- `legacy/`
  - Older files kept for traceability (including `step2`-named outputs).

If you only care about current clean outputs, use `graphs/`, `visuals/`, and `reports/`.
