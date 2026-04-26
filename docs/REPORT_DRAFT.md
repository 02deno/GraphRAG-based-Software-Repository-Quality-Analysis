# GraphRAG-based Software Repository Quality Analysis

## Project Snapshot

- **Target repository:** `langchain-ai/langgraph`
- **Python files:** 320
- **Lines of code (non-empty):** 117575
- **Classes:** 1116
- **Functions:** 4949
- **Variables (assignments):** 15353

## Graph Construction Snapshot

- **Graph type:** Directed file dependency graph
- **Node type (current step):** `File`
- **Edge type (current step):** `IMPORTS`
- **Total nodes:** 320
- **Total edges:** 1214

## Initial Structural Findings

### Most imported files (high in-degree)

- `libs\langgraph\langgraph\typing.py` (183)
- `libs\checkpoint\langgraph\checkpoint\base\__init__.py` (57)
- `libs\langgraph\langgraph\types.py` (57)
- `libs\langgraph\langgraph\graph\__init__.py` (38)
- `libs\checkpoint\langgraph\store\base\__init__.py` (36)

### Most importing files (high out-degree)

- `libs\langgraph\langgraph\pregel\main.py` (36)
- `libs\langgraph\langgraph\graph\state.py` (26)
- `libs\langgraph\langgraph\pregel\_loop.py` (25)
- `libs\langgraph\tests\test_pregel.py` (24)
- `libs\langgraph\tests\test_pregel_async.py` (24)

## Visual Outputs

- Graph structure image: `results/graph_structure.png`
- Degree analysis image: `results/graph_degree_analysis.png`
- Visual summary text: `results/visual_summary.txt`

## Interpretation (Current Step)

- The repository has a moderately dense internal import structure.
- A small set of utility and typing-related modules act as central dependency hubs.
- Core execution files in the `pregel` and `graph` areas have high outward coupling.
- Test modules with high out-degree suggest broad integration-style test coverage areas.

## Next Step

Move from file-level graph to function/class-level graph and add quality-risk heuristics (e.g., high centrality + weak test linkage).
