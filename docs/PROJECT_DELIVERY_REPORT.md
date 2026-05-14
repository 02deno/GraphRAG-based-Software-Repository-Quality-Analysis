# Project Delivery Report — GraphRAG-Based Repository Quality Analysis

**Course / context:** Graph Theory (graduate project) — *adjust title if required by your department*  
**Project:** GraphRAG_Project — software repository modeling, analysis, and conversational retrieval over a code graph  
**Author(s):** *[YOUR NAME(S)]*  
**Institution:** Istanbul Technical University (İTÜ) — *[YOUR PROGRAM]*  
**Submission date:** *[YYYY-MM-DD]*  
**Repository / artifact root:** `GraphRAG_Project/`

---

## Executive summary

This deliverable is a **web-first Python application** that ingests Python repositories, builds a **property graph** of files, symbols, tests, and commits, runs **graph-theoretic analyses** (e.g. degree-based metrics, relationship typing), and exposes results through a browser UI with optional **Neo4j**-backed subgraph views and a **GraphRAG** assistant. The assistant combines **bounded graph retrieval**, a short structured **analysis summary**, and **lexically ranked source chunks** (with optional **embedding-augmented seeds**) before calling an **OpenAI-compatible** chat API (hosted or local, e.g. Ollama). Outputs include JSON/text reports, charts, session-persisted chat, and optional **Word (.docx)** export.

---

## 1. Objectives and motivation

| Objective | How the project addresses it |
|-----------|-------------------------------|
| Represent a codebase as a graph | Nodes and typed edges (`IMPORTS`, `IN_FILE`, `CALLS`, `TESTS`, `MODIFIED_BY`, …) per `docs/GRAPH_SCHEMA.md` |
| Apply graph-based quality insight | Centrality and structural metrics in `src/analysis/`; visualizations under each run’s `results/` |
| Make analysis accessible | Flask web app: compatibility gate, pipeline, results dashboard, GraphRAG workspace |
| Connect graphs to LLM use cases | GraphRAG pipeline: seeds → subgraph expansion → formatted context → chat completions |

---

## 2. Scope of delivery

**In scope**

- End-to-end **web workflow**: repository input → compatibility scoring → full pipeline → results page.
- **CLI** entry points for graph build, analysis, and full pipeline (`README.md`).
- **GraphRAG chat**: multi-turn sessions, SSE streaming, Markdown rendering, persisted **source snippet diagnostics** per assistant turn.
- **Optional integrations** (configuration-driven): Neo4j Bolt expansion, embedding model for seed ranking, automatic session fork when context size thresholds are met.

**Out of scope / future work**

- Vector database backends and multimodal chart URLs are captured as design notes in `docs/GRAPHRAG_CHAT_ROADMAP.md` (not required for this delivery).

---

## 3. Technical approach

### 3.1 Graph model

The repository is abstracted as a **directed graph** (see `src/graph/`). Nodes include **File**, **Function**, **Class**, **Test**, and **Commit** (when `.git` history is available). Edges encode containment, imports, calls, tests, and file modification by commit. This supports standard analyses (e.g. degree by edge type, commit churn via `MODIFIED_BY`).

### 3.2 Pipeline

Orchestration uses `src/pipeline/run_pipeline.py` (`run_repository_pipeline`), invoked consistently from the web layer (no subprocess shell-out to the pipeline script from in-process code).

### 3.3 GraphRAG retrieval (high level)

1. **Seeding** from query text (lexical / community / optional embeddings).  
2. **Subgraph expansion** (NetworkX or Neo4j when configured).  
3. **Source context** from on-disk `graphrag_source_chunks.jsonl` per analysis run (Python ``File`` excerpts plus README / ``docs/**`` prose), capped by character budget and top-`k` rank.  
4. **LLM** call with system instructions, analysis snippet, graph/context block, and conversation history.

Detailed module map: `docs/PROJECT_STRUCTURE.md`.

---

## 4. Figures *(placeholders — add your screenshots under `docs/assets/`)*

Create a folder `docs/assets/` if it does not exist. Replace each filename with your own image; keep paths as below so this report resolves correctly when viewed from the `docs/` directory.

<!-- PLACEHOLDER FIGURE 1: Home / repository input page (index) -->
![Figure 1 — Home page: repository URL or path input (PLACEHOLDER: add image)](assets/delivery_fig01_home.png)

**Caption (edit after inserting image):** Main entry point for submitting a repository for analysis.

---

<!-- PLACEHOLDER FIGURE 2: Compatibility results with score breakdown -->
![Figure 2 — Compatibility check results (PLACEHOLDER: add image)](assets/delivery_fig02_compatibility.png)

**Caption:** Compatibility scoring and gating before running the full pipeline.

---

<!-- PLACEHOLDER FIGURE 3: Analysis progress (SSE overlay or results milestone view) -->
![Figure 3 — Analysis progress (streaming or milestone UI) (PLACEHOLDER: add image)](assets/delivery_fig03_analysis_progress.png)

**Caption:** User-visible progress during graph build, analysis, and chart generation.

---

<!-- PLACEHOLDER FIGURE 4: Results dashboard (metrics + charts) -->
![Figure 4 — Analysis results dashboard (PLACEHOLDER: add image)](assets/delivery_fig04_results_dashboard.png)

**Caption:** Aggregated metrics, textual reports, and chart thumbnails for the analyzed run.

---

<!-- PLACEHOLDER FIGURE 5: Optional Neo4j / graph preview -->
![Figure 5 — Graph preview (optional Neo4j property graph) (PLACEHOLDER: add image)](assets/delivery_fig05_graph_preview.png)

**Caption:** Interactive or capped graph preview (skip this figure if you did not configure Neo4j).

---

<!-- PLACEHOLDER FIGURE 6: GraphRAG workspace (chat + Steps + Source snippets) -->
![Figure 6 — GraphRAG workspace: multi-turn chat (PLACEHOLDER: add image)](assets/delivery_fig06_graphrag_workspace.png)

**Caption:** Full-page chat workspace with streamed reply, collapsible **Steps**, and **Source snippets** panel.

---

<!-- PLACEHOLDER FIGURE 7: Export or documentation bundle (optional) -->
![Figure 7 — Export: JSON / docx / downloads (PLACEHOLDER: add image)](assets/delivery_fig07_exports.png)

**Caption:** Example of downloadable artifacts (omit if not used).

---

## 5. Reproducibility

1. **Environment:** Python 3.x; `pip install -r requirements.txt`.  
2. **Configuration:** Copy `.env.example` to `.env`; set at least `FLASK_SECRET_KEY` and any `GRAPHRAG_*` variables you use (LLM base URL, model, optional Neo4j, optional embeddings).  
3. **Run:** `python run_web_app.py` → open `http://localhost:5000` (or the host/port shown in the console).  
4. **Evidence:** Attach screenshots above and, if required by the grader, a sample `results/web_analysis_*` folder listing or a zipped **non-sensitive** run output.

---

## 6. Testing and quality checks

- Automated tests exist under `tests/` (e.g. session persistence for GraphRAG chat metadata).  
- *Optional for your submission:* record the command `pytest -q` and its outcome as a short note in an appendix.

---

## 7. Limitations and honesty statement

- Chat **source index** is built from Python files represented in `graph.json`; broad Markdown/docs-only RAG is not merged into the same index yet.  
- **LLM answers** depend on model quality, timeout settings, and prompt size; very large repositories may require chunk-tuning (`GRAPHRAG_SOURCE_*`) or session fork settings.  
- **Neo4j** and **embeddings** are optional; the core delivery remains valid without them.

---

## 8. Conclusion

The project delivers a **coherent graph-theoretic representation** of Python repositories, **automated metrics and visuals**, and a **GraphRAG-style assistant** grounded in retrieved graph and source context, packaged as a maintainable Flask application with documented architecture and extension points.

---

## Appendix A — Suggested asset filenames

| File | Suggested content |
|------|-------------------|
| `docs/assets/delivery_fig01_home.png` | Landing / upload |
| `docs/assets/delivery_fig02_compatibility.png` | Compatibility page |
| `docs/assets/delivery_fig03_analysis_progress.png` | Progress UI |
| `docs/assets/delivery_fig04_results_dashboard.png` | Results |
| `docs/assets/delivery_fig05_graph_preview.png` | Graph / Neo4j preview |
| `docs/assets/delivery_fig06_graphrag_workspace.png` | Chat workspace |
| `docs/assets/delivery_fig07_exports.png` | Downloads / docx |

## Appendix B — Key references inside the repo

- `README.md` — quick start and feature list  
- `docs/PROJECT_STRUCTURE.md` — layers and data flow  
- `docs/GRAPH_SCHEMA.md` — node and edge types  
- `docs/GRAPHRAG_CHAT_ROADMAP.md` — optional future retrieval backends  

---

*End of delivery report.*
