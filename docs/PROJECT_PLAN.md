# Project Plan (Step-by-step)

## Step 1 - Setup and Scope

- Select one open-source repository
- Define node and edge types
- Prepare a simple graph construction script

Step 1 deliverables (schema clarification):

- Fix dictionary names for nodes:
  - `File`, `Function`, `Class`, `Test`, `Commit`
- Fix dictionary names for edges:
  - `IMPORTS`, `IN_FILE`, `CALLS`, `TESTS`, `MODIFIED_BY`
- Define required fields for each node and edge type
- Add schema version metadata in graph output
- Validate generated nodes/edges against required field sets

## Step 2 - Graph Construction

- Create file, function/class, test, and commit nodes
- Add relationship edges (CALLS, IN_FILE, TESTS, MODIFIED_BY)
- Add thin CLI wrappers for package entrypoints

Step 2 current progress:

- Done: Modular `src/graph` package created
- Done: Modular `src/extractors` package created
- Done: `GraphBuilder` pipeline implemented
- Done: thin CLI wrappers created in `src/build_graph.py`, `src/analyze_graph.py`, `src/visualize_graph.py`, `src/repo_stats.py`
- Done: `Test` node extraction and `TESTS` edge generation
- Done: `IMPORTS` and `IN_FILE` edge generation
- Pending:
  - `Commit` nodes
  - `CALLS`, `MODIFIED_BY` edges

## Step 3 - Initial Analysis

- Degree centrality
- Betweenness centrality
- Simple risk candidate list

Note: We will move to the next step only after completing the current one.
