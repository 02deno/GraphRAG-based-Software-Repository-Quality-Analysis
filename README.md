# GraphRAG-based Software Repository Quality Analysis

This project models a Python repository as a graph and analyzes code structure, test coverage signals, and dependency relationships.

## What is included

- Modular extraction pipeline in `src/extractors`
- Graph model implementation in `src/graph`
- CLI wrappers for graph construction and analysis
- Validated node/edge schema contract

## Repository compatibility (before running on a new repo)

Please check:

- `docs/REPO_COMPATIBILITY_CHECKLIST.md`

## Architecture overview

- `src/graph/`: data model, builder, schema validation
- `src/extractors/`: AST extraction for files, imports, symbols, and tests
- `src/build_graph.py`: CLI wrapper to build graph JSON
- `src/analyze_graph.py`: CLI wrapper to report edge-degree metrics
- `src/main_pipeline.py`: full pipeline entrypoint for build + analyze + visualize
- Full usage examples are available in `docs/USAGE.md`

## Run the first extractor

```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO"
```

Default output:

- `results/graphs/<repo_name>_graph.json`

Optional output path:

```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO" --output "results/graphs/myrepo_graph.json"
```

Current extractor output includes:

- `File` nodes
- `Function` nodes
- `Class` nodes
- `Test` nodes
- `IMPORTS` edges (`File -> File`)
- `IN_FILE` edges (`Function/Class -> File`)
- `TESTS` edges (`Test -> Function/Class`)

The project schema also defines additional targets for future implementation:

- `Commit` nodes
- `CALLS` edges (`Function -> Function`)
- `MODIFIED_BY` edges (`File -> Commit`)

## Developer API

You can use the builder directly in Python:

```python
from pathlib import Path
from src.graph import GraphBuilder, graph_to_dict

builder = GraphBuilder(Path("PATH_TO_TARGET_REPO"))
builder.build()
graph_document = graph_to_dict(builder.to_dict()["nodes"], builder.to_dict()["edges"])
```

## Run basic graph analysis

```bash
python src/analyze_graph.py --graph "results/graphs/<repo_name>_graph.json" --top-k 10
```

Save analysis to a text file:

```bash
python src/analyze_graph.py --graph "results/graphs/<repo_name>_graph.json" --top-k 10 --save-report "results/basic_analysis.txt"
```

## Create visual outputs

```bash
python src/visualize_graph.py --graph "results/graphs/<repo_name>_graph.json"
```

Default visualization outputs:

- `results/graph_structure.png`
- `results/graph_degree_analysis.png`
- `results/visual_summary.txt`

## Run general repository stats

```bash
python src/repo_stats.py --repo "data/langgraph"
```

Default stats outputs:

- `results/repo_stats.txt`
- `results/repo_stats.json`