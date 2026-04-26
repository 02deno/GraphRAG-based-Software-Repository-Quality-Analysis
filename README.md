# GraphRAG-based Software Repository Quality Analysis

This project aims to model a software repository as a graph and analyze software quality risks.

## What is included for now?

- Basic folder structure
- Short project roadmap
- Repository compatibility checklist for the current prototype

## Repository compatibility (before running on a new repo)

Please check:

- `docs/REPO_COMPATIBILITY_CHECKLIST.md`

## First step goal

First, we will define the graph data model and extract data from one repository.

## Run the first extractor

```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO"