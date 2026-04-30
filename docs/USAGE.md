# GraphRAG Project Usage

This document explains how to run the repository graph extractor and analyze the output.

## Build a graph from a repository

```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO"
```

This generates a JSON graph file under `results/graphs/` by default.

### Optional output location

```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO" --output "results/graphs/myrepo_graph.json"
```

## Analyze a graph document

```bash
python src/analyze_graph.py --graph "results/graphs/myrepo_graph.json" --top-k 10
```

### Save the analysis report

```bash
python src/analyze_graph.py --graph "results/graphs/myrepo_graph.json" --top-k 10 --save-report "results/reports/myrepo_analysis.txt"
```

## Visualize a graph document

```bash
python src/visualize_graph.py --graph "results/graphs/myrepo_graph.json"
```

Default visualization output files are written to `results/`.

## Run repository statistics

```bash
python src/repo_stats.py --repo "data/langgraph"
```

This will compute repository-level statistics and save them into `results/repo_stats.txt` and `results/repo_stats.json` by default.

## Full pipeline: build, analyze, visualize

```bash
python src/main_pipeline.py --repo "PATH_TO_TARGET_REPO"
```

Optional outputs:

```bash
python src/main_pipeline.py --repo "PATH_TO_TARGET_REPO" --graph-output "results/graphs/myrepo_graph.json" \
  --analysis-output "results/reports/myrepo_analysis.txt" \
  --visual-summary-output "results/reports/myrepo_visual_summary.txt"
```

## Developer API example

The core builder is available as a Python class from `src.graph`:

```python
from pathlib import Path
from src.graph import GraphBuilder, graph_to_dict

repo_path = Path("PATH_TO_TARGET_REPO")
builder = GraphBuilder(repo_path)
builder.build()
graph_document = graph_to_dict(builder.to_dict()["nodes"], builder.to_dict()["edges"])
```

## Graph model and schema

The current graph schema includes:

- Node types: `File`, `Function`, `Class`, `Test`, `Commit`
- Edge types: `IMPORTS`, `IN_FILE`, `CALLS`, `TESTS`, `MODIFIED_BY`

Current implementation produces:

- Node types: `File`, `Function`, `Class`, `Test`
- Edge types: `IMPORTS`, `IN_FILE`, `TESTS`

Pending implementation:

- `Commit` nodes
- `CALLS` edges
- `MODIFIED_BY` edges

Schema validation is implemented in `src/graph/schema.py`.
