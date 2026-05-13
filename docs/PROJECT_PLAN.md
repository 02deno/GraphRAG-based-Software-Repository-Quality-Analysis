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
- Done: `CALLS` edge generation (function-to-function / function-to-class call-site resolution by name)
- Done: `Commit` node extraction (`src/extractors/commit_extractor.py`, reads `git log`, capped to `GraphBuilder.DEFAULT_MAX_COMMITS = 200`)
- Done: `MODIFIED_BY` edge generation (File → Commit; skipped when no `.git` directory or `git` is unavailable)

## Step 3 - Initial Analysis

- Done: Degree centrality (in/out per edge type, including `MODIFIED_BY` as commit churn proxy)
- Done: Betweenness centrality (on `IMPORTS` and `CALLS` subgraphs; sampled estimator k=500 above 1000 nodes for tractability)
- Done: PageRank (on `IMPORTS` and `CALLS` subgraphs; complements in-degree with multi-hop influence)
- Done: Community detection (Louvain modularity on undirected projections of `IMPORTS` and `CALLS`; label propagation fallback)
- Done: Bar-chart visualizations for betweenness and PageRank on both subgraphs (PNG outputs per run)
- Done: Risk candidate list (`src/analysis/risk_score.py`) — per-`File` composite z-score combining centrality (IMPORTS + CALLS), commit churn (`MODIFIED_BY` out-degree), test gap (fraction of in-file symbols missing `TESTS`), and cross-community edge ratio. Reported as the final section of the analysis text.

Note: Step 3 complete.

## Step 4 - GraphRAG (retrieval + LLM)

- Done: Lexical seeding over node text (`src/graphrag/query_index.py`) with token-overlap scoring (lightweight hybrid without embeddings).
- Done: Typed ``MultiDiGraph`` + bounded undirected BFS expansion (`src/graphrag/subgraph_retriever.py`).
- Done: Subgraph + ``analysis_view`` text formatting for LLM context (`context_formatter.py`, `analysis_context.py`).
- Done: OpenAI-compatible HTTP client (``httpx``) + env-based wiring for hosted APIs and Ollama (`openai_compatible_client.py`).
- Done: Orchestrator `GraphRagChatService` (`chat_service.py`).
- Done: Web ``POST /analysis-results/<run_dir>/chat`` + results page assistant panel (`templates/results_final.html`).
- Done: Community-aware extra seeds via ``member_ids`` on Louvain preview rows (`community_seeds.py`, `analysis_web_payload.py`).

