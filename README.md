# GraphRAG-based Software Repository Quality Analysis

This project aims to model a software repository as a graph and analyze software quality risks.

## What is included for now?

- Basic folder structure
- Short project roadmap
- Repository compatibility checklist for the current prototype
- Step 2 partial graph construction (`Function/Class` + `IN_FILE`)

## Repository compatibility (before running on a new repo)

Please check:

- `docs/REPO_COMPATIBILITY_CHECKLIST.md`

## First step goal

First, we will define the graph data model and extract data from one repository.

## Run the first extractor

```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO"
```

Default output:

- `results/graph_file_imports.json`

Current extractor output includes:

- `File` nodes
- `Function` and `Class` nodes (AST-based)
- `IMPORTS` edges (`File -> File`)
- `IN_FILE` edges (`Function/Class -> File`)

## Run basic graph analysis

```bash
python src/analyze_graph.py --graph "results/graph_file_imports.json" --top-k 10
```

Save analysis to a text file:

```bash
python src/analyze_graph.py --graph "results/graph_file_imports.json" --top-k 10 --save-report "results/basic_analysis.txt"
```

## Create visual outputs

```bash
python src/visualize_graph.py --graph "results/graph_file_imports.json"
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