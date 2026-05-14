# GraphRAG-based Software Repository Quality Analysis

This project provides a **full-stack web application** for analyzing Python repositories using graph-based techniques. It models software repositories as graphs and provides quality insights through automated analysis with compatibility checking and confidence scoring.

## 🚀 Quick Start

### Web Application (Recommended)
```bash
# Install dependencies
pip install -r requirements.txt

# Optional: environment file at project root (see .env.example). The web app and
# src/main_pipeline.py load ".env" with python-dotenv before reading GRAPHRAG_* /
# FLASK_* variables; existing shell env values are not overwritten on the first
# pass. If your shell or IDE pins an old ``GRAPHRAG_OPENAI_BASE_URL`` (e.g. local
# Ollama) but ``.env`` lists Ollama Cloud, set ``GRAPHRAG_DOTENV_OVERRIDE=1`` in
# ``.env`` (or export it) so the file wins; startup logs will note the override pass.

# Optional: verify Ollama (OpenAI-compatible) + Neo4j match your .env (no secrets printed)
python scripts/check_graphrag_connections.py --override-dotenv

# Optional: verbose UTC logs — stderr + rotating file logs/graphrag.log (5 MB × 5)
# set GRAPHRAG_LOG_LEVEL=DEBUG
# set GRAPHRAG_LOG_FILE=C:\path\to\my.log   # optional override
# set GRAPHRAG_LOG_TO_FILE=0               # stderr only, no file

# Start web application
python run_web_app.py

# Open your browser and go to: http://localhost:5000
```

### CLI Usage (Traditional)
```bash
# Build graph from repository
python src/build_graph.py --repo "PATH_TO_TARGET_REPO"

# Run analysis
python src/analyze_graph.py --graph "results/graphs/<repo_name>_graph.json" --top-k 10
```

## 🌟 Features

### Web Application Features
- **📁 Repository input**: GitHub HTTPS URL (clone) or local path; ZIP upload in the web UI is reserved for a later release (handler still supports ZIP)
- **🔍 Smart Compatibility Checking**: Automated repository analysis with confidence scoring
- **⚠️ Risk Assessment**: Repositories with <50% compatibility require user confirmation
- **📊 Analysis progress**: Compatibility sends **SSE** (``X-GraphRAG-Analyze-Stream``) so the overlay can list **live** pipeline messages (per-file graph build, analysis phases, each chart PNG). On the ``complete`` event the client triggers a **GET form submit** to the results URL (then a short-delay ``location.replace`` retry if still on ``/compatibility``), which avoids fragile ``location`` writes from inside the fetch reader alone. If the tab is still on the compatibility page after ~5s, an **Open results** link appears. If the response is plain **HTML** (buffered dev server), the same page shows **timed milestones** (unique lines with elapsed seconds). See ``docs/MIDTERM_PROJECT_REPORT.md`` for a narrative report (add screenshots under ``docs/assets/``).
- **GraphRAG assistant** (after a successful run): natural-language Q&amp;A uses the **GraphRAG workspace** (``/graphrag/workspace`` or **Open full chat workspace** on the results page). The server retrieves a **bounded subgraph** from ``graph.json``, a short **analysis_view** summary, **lexically ranked `.py` source excerpts** from an on-disk chunk index (built at analyze time from the same repo root), and calls an OpenAI-compatible chat API. The results page keeps a **Neo4j property-graph preview** (optional Bolt) and links to the workspace for all chat, **multi-turn** sessions, context-size warnings, and **optional automatic session carryover** when ``GRAPHRAG_CHAT_AUTO_SUMMARY_AT_CHARS`` is set (same behavior as ``POST /graphrag/api/<run_dir>/sessions/fork`` with an LLM summary). While a reply is prepared, the workspace uses **SSE** (request header ``X-GraphRAG-Chat-Stream: 1``): the server streams ``progress`` events (retrieval and context assembly), then ``token`` events (assistant text fragments from a streamed ``/chat/completions`` call), then ``complete``. **User** text is written to the session JSON **before** SSE starts; the **assistant** message is appended when the turn finishes, so switching chats (aborting the reader) or refreshing mid-stream still keeps your question on disk. The UI keeps the usual chat bubbles: a **typing indicator** (three dots) in the assistant bubble until the first ``token``, then streamed text in that same bubble; assistant text is rendered as **Markdown** (via CDN ``marked`` + ``DOMPurify``). Retrieval lines accumulate under a collapsible **“> Steps”** ``<details>`` row below the bubble (open during retrieval, then **closes automatically** when the first answer ``token`` arrives). After ``complete``, **Source snippets** summarizes which indexed ``.py`` chunks were packed into the prompt (rank, path, line span, score — **not** the whole repository); that metadata is **saved on each assistant message** in ``results/.../graphrag_chat_sessions/*.json`` so the panel returns when you reopen a session (older saved chats from before this feature will not have it). Session delete uses an **in-page modal** (no native ``confirm``). If the stream stops before ``complete``, the workspace shows an inline notice (often a proxy timeout or the model still running past ``GRAPHRAG_CHAT_TIMEOUT_S``). Configure before ``python run_web_app.py`` (or place keys in ``.env`` — see ``.env.example``):
  - ``GRAPHRAG_DOTENV_OVERRIDE`` (optional) — when ``1`` / ``true`` / ``yes`` / ``on`` (in ``.env`` after the first load, or exported), reload ``.env`` with ``override=True`` so project file values replace shell ``GRAPHRAG_*`` (fixes logs still showing ``127.0.0.1:11434`` when ``.env`` points at cloud)
  - ``GRAPHRAG_OPENAI_BASE_URL`` — e.g. ``https://api.openai.com/v1``, ``https://ollama.com/v1`` (Ollama Cloud OpenAI-compatible), or ``http://127.0.0.1:11434/v1`` (local Ollama)
  - ``GRAPHRAG_CHAT_MODEL`` — model id accepted by that server
  - ``GRAPHRAG_OPENAI_API_KEY`` — bearer token for hosted APIs (Ollama Cloud: create a key at ollama.com; often empty for local Ollama). Some Ollama Cloud models return visible text in the JSON ``reasoning`` field while ``content`` is empty; the bundled client reads ``reasoning`` as a fallback so chat and insights still work.
  - ``GRAPHRAG_CHAT_TIMEOUT_S`` (optional) — HTTP timeout in seconds for ``/chat/completions`` (default **300**; raise for slow local models, lower for stricter hosted limits)
  - ``GRAPHRAG_EMBEDDING_MODEL`` (optional) — when set with the same base URL, **dense embedding** seeds are merged with lexical/community seeds; vectors are cached per run as ``graphrag_embedding_cache.npz``. The client targets ``…/v1/embeddings`` and strips a trailing ``/v1`` from the base URL first so Ollama-style ``http://127.0.0.1:11434/v1`` does not become ``…/v1/v1/embeddings``.
  - ``GRAPHRAG_NEO4J_URI``, ``GRAPHRAG_NEO4J_USER``, ``GRAPHRAG_NEO4J_PASSWORD`` (optional) — when set, subgraph **expansion** runs in Neo4j (Bolt) instead of in-process NetworkX; graphs are keyed by run folder name. Optional ``GRAPHRAG_NEO4J_DATABASE`` for multi-database setups. On the results page, **Neo4j property graph** (under **Graph preview**) loads a capped interactive view from ``GET /analysis-results/<run_dir>/neo4j-property-graph.json`` (that request **syncs** this run's ``graph.json`` into Neo4j if needed, then reads it with a **per edge-type row budget** so ``MODIFIED_BY`` is not dropped by a single global cap; vis-network over CDN after you click **Load graph preview**). After load, use the **node** and **edge** tag buttons to narrow the view (click the same tag again to clear); when **both** filters are active, matching edges include **all endpoints** (e.g. ``MODIFIED_BY`` + ``Commit`` still shows linked ``File`` nodes).
  - Source index (optional tuning): ``GRAPHRAG_SOURCE_MAX_FILES``, ``GRAPHRAG_SOURCE_CHUNK_LINES``, ``GRAPHRAG_SOURCE_CHUNK_OVERLAP_LINES``, ``GRAPHRAG_SOURCE_MAX_BYTES_PER_FILE`` — size of ``graphrag_source_chunks.jsonl`` under each ``results/web_analysis_*`` run; if the original repo directory is removed later, chat still uses chunks already written beside ``graph.json``. The same JSONL includes **documentation** chunks (root ``README*`` / ``CONTRIBUTING.md`` / ``CHANGELOG.md`` / ``SECURITY.md``, then **all** ``*.md`` under the repo up to ``GRAPHRAG_SOURCE_MAX_DOC_FILES``), **analysis** chunks from this run (formatted ``analysis_view`` summary, ``analysis.txt``, ``visual_summary`` artifacts under virtual ``_analysis/`` paths), and **Python** ``File`` excerpts — all ranked by the **same lexical scorer**. Tune doc/analysis windows with ``GRAPHRAG_SOURCE_DOC_CHUNK_*``, ``GRAPHRAG_SOURCE_ANALYSIS_*``, disable analysis chunks with ``GRAPHRAG_SOURCE_DISABLE_ANALYSIS_CHUNKS=1``, and cap UI-stored chunk previews via ``GRAPHRAG_SOURCE_DIAGNOSTIC_EXCERPT_CHARS``. Re-run analysis (or delete ``graphrag_source_chunks.jsonl`` for on-demand rebuild) so older runs pick up new indexing.
  - ``GRAPHRAG_CHAT_WARN_INPUT_CHARS`` / ``GRAPHRAG_CHAT_CRITICAL_INPUT_CHARS`` (optional) — character-count thresholds for **workspace** context warnings (defaults: 24000 / 36000); not a hard API cap, only UI guidance
  - ``GRAPHRAG_CHAT_AUTO_SUMMARY_AT_CHARS`` (optional) — when >0 and the session already has at least one prior user–assistant exchange, the workspace **automatically** calls the fork flow after a reply whose ``approx_input_chars`` reaches this value (``0`` = disabled). Prevents unbounded multi-turn growth; does **not** shrink the per-turn RAG block alone. Integrations can still call ``POST …/sessions/fork`` manually.
  - ``GRAPHRAG_CHAT_TEMPERATURE`` (optional) — sampling temperature for the main repository Q&A call (default **0.28**); increase slightly if answers feel too short (trade-off: more creative drift).
  - **AI-assisted interpretation (results page)**: after a run, the **Quality Analysis** area can call ``POST /analysis-results/<run_dir>/llm-insights`` (same ``GRAPHRAG_OPENAI_BASE_URL`` / ``GRAPHRAG_CHAT_MODEL`` as chat) to produce a structured narrative — executive summary, suggested actions, likely defect hotspots, graph-relative risk themes, and testing notes. The response is saved as ``graphrag_llm_insights.json`` in that run folder (re-run the button with JSON ``{"regenerate": true}`` to replace it). For ``api.openai.com``, the client requests **JSON object mode** by default (set ``GRAPHRAG_INSIGHTS_JSON_OBJECT=0`` to turn off, or ``=1`` to force on for other OpenAI-compatible hosts that support ``response_format``). Optional tuning: ``GRAPHRAG_INSIGHTS_COMPACT=1`` shrinks embedded report excerpts for faster cloud calls; ``GRAPHRAG_INSIGHTS_MAX_TOKENS`` caps completion size (default **3072**). The button uses a **single blocking** HTTP request until JSON is saved — remote models (including Ollama Cloud) can take **tens of seconds to a few minutes** on large ``analysis.txt`` payloads; raise ``GRAPHRAG_CHAT_TIMEOUT_S`` if the HTTP client times out early. Deterministic tables and charts remain the source of truth; this block is explicitly labeled as LLM interpretation.
  - **Chat speed**: logs include ``approx_input_chars`` before each LLM call and a **WARNING** when the assembled prompt is very large (≳32k), which makes local models slow; start a new chat, enable auto carryover, or tune ``GRAPHRAG_SOURCE_*`` chunk settings.
- **📥 Downloadable Results**: Export JSON, text reports, structured **analysis_view.json** (same metrics as the card UI), individual PNGs, pipeline log, or a **single Word (.docx)** bundling overview text, ``pipeline.txt``, ``analysis.txt``, ``visual_summary.txt``, and embedded chart images
- **📜 Structured logging**: UTC ISO timestamps and levels via ``GRAPHRAG_LOG_LEVEL``; duplicate stream to a **rotating** ``logs/graphrag.log`` (override with ``GRAPHRAG_LOG_FILE``, or set ``GRAPHRAG_LOG_TO_FILE=0`` for console-only); HTTP lines under ``src.web.request``; each LLM ``/chat/completions`` call logs at INFO from ``src.graphrag.openai_compatible_client`` (host, model, message count, optional ``max_tokens``, reply length or empty-body diagnostics) and ``src.graphrag.chat_service`` logs ``GraphRAG LLM request starting`` / ``reply success`` with ``approx_input_chars`` / ``reply_chars``
- **📱 Responsive Design**: Mobile-friendly interface

### Core Analysis Features
- **Graph Construction**: File, Function, Class, Test, and Commit nodes (all ``*.py`` under the repo root, including e.g. ``backend/`` — not limited to a top-level ``src/`` layout). Commit nodes come from ``git log`` and are skipped automatically when the working tree has no ``.git`` directory.
- **Relationship Mapping**: IMPORTS, IN_FILE, CALLS, TESTS, and MODIFIED_BY (File → Commit) edges
- **Quality Metrics**: Degree centrality and structural analysis (per edge type, including commit churn via MODIFIED_BY)
- **Visualization Support**: Graph structure and analysis reports

## 🏗️ Architecture

```
GraphRAG_Project/
├── 📁 src/                          # Backend Core
│   ├── 📄 logging_config.py         # UTC stderr logging (GRAPHRAG_LOG_LEVEL)
│   ├── 📁 utils/                    # Cross-layer helpers (repo → safe path slug)
│   ├── 📁 web/                      # Web Application
│   │   ├── app.py                    # Flask application
│   │   └── __init__.py
│   ├── 📁 compatibility/             # Compatibility Checking
│   │   ├── repo_checker.py           # Repository analysis & scoring
│   │   └── __init__.py
│   ├── 📁 graphrag/                 # GraphRAG: seeding, subgraph retrieval, LLM client, chat service
│   │   ├── graph_builder.py          # Main graph construction
│   │   ├── schema.py                # Node/edge schema definitions
│   │   └── nodes/ & edges/         # Graph components
│   ├── 📁 extractors/               # Data Extraction
│   │   ├── symbol_extractor.py       # Functions & classes
│   │   ├── import_extractor.py       # Import relationships
│   │   ├── tests_extractor.py        # Test discovery
│   │   └── python_file_collector.py # File discovery
│   ├── 📁 analysis/                 # Graph Analysis
│   │   └── graph_analysis.py       # Centrality & metrics
│   ├── 📁 visualization/             # Graph Visualization
│   ├── 📁 stats/                    # Repository Statistics
│   ├── build_graph.py               # CLI: Graph building
│   ├── analyze_graph.py             # CLI: Graph analysis
│   ├── main_pipeline.py            # CLI: Full pipeline
│   └── repo_stats.py              # CLI: Repository stats
├── 📁 templates/                     # Frontend Templates
│   ├── index.html                  # Upload interface
│   ├── compatibility.html           # Compatibility results
│   ├── results_final.html          # Analysis results
│   └── graphrag_workspace.html   # Full-page GraphRAG chat (projects + sessions)
├── 📁 docs/                          # Documentation (incl. ``MIDTERM_PROJECT_REPORT.md``)
├── 📁 scripts/                       # Local helper scripts
├── 📁 results/                       # Analysis outputs
├── 📁 data/                          # Sample repositories
├── 📄 requirements.txt               # Python dependencies
├── 📄 .env.example                   # Template for FLASK_* / GRAPHRAG_* (copy to .env)
├── 📄 run_web_app.py               # Web app launcher
└── 📄 README.md                    # This file
```

## 📋 Compatibility Checking System

### Scoring Categories

**Core Checks (70% weight):**
- **Python Primary Language** (25%): Repository is primarily Python-based
- **Python package root** (15%): ``src/``, ``backend/app`` or ``backend/src``, top-level ``app/`` or ``api/`` with Python files, or ``lib/``-style fallbacks (monorepo-friendly; ``api/`` covers common FastAPI layouts where the service lives beside ``tests/``)
- **Tests directory** (10%): ``tests/`` at repo root or under paths like ``backend/tests``, ``app/tests``, ``api/tests``
- **Static Imports** (20%): Parseable import statements

**Additional Checks (30% weight):**
- **Package Structure** (10%): `__init__.py` files and organization
- **Repository Size** (10%): Manageable size for analysis
- **Requirements File** (5%): `requirements.txt` / `setup.py` / `pyproject.toml` / `Pipfile` at repo root (Python packaging only)
- **README File** (5%): Documentation presence

**Not Python-primary:** The graph builder only analyzes `.py` files. If there are **no** `.py` files, **no** tracked source files (`.py`, `.java`, …), or Python’s share of those tracked files is **below 30%**, the **headline compatibility score is capped below 50%** (with an explanation in warnings) so a Java-only or Node-only repo cannot read as “good” for this Python pipeline.

### Score Interpretation
- **🟢 70-100%**: Excellent compatibility - Automatic analysis
- **🟡 50-69%**: Good compatibility - Automatic analysis
- **🔴 0-49%**: Low compatibility - User confirmation required

## 🚦 Usage Guide

### Web Application Workflow

1. **Submit a repository**
   - Paste a GitHub URL (for example `https://github.com/org/repo`) or a local filesystem path
   - ZIP upload is not shown in the UI yet; the server-side upload handler remains for future use

2. **Compatibility Check**
   - After submit, the UI shows a short progress state, then **redirects** to `/compatibility` with scores, expandable explanations per check, and a “how scoring works” section
   - Automated analysis runs in the same request as upload (before the redirect)
   - Detailed scoring with pass/fail indicators
   - Warnings and recommendations provided

3. **Analysis Execution**
   - **Score ≥ 50%**: Automatic analysis start
   - **Score < 50%**: Confirmation dialog with "Analyze Anyway" option

4. **Results Display**
   - Graph statistics (nodes, edges, types)
   - Quality analysis with centrality metrics
   - Downloadable JSON and text reports

### CLI Workflow

```bash
# Step 1: Build graph
python src/build_graph.py --repo "PATH_TO_REPO" --output "results/my_graph.json"

# Step 2: Analyze graph
python src/analyze_graph.py --graph "results/my_graph.json" --top-k 10 --save-report "results/analysis.txt"

# Step 3: Full pipeline (recommended)
python src/main_pipeline.py --repo "PATH_TO_REPO" --top-k 10
```

## 📊 Current Implementation Status

### ✅ Implemented Features
- **Web Application**: Full Flask-based interface
- **Compatibility Checking**: Smart scoring system
- **Graph Construction**: File, Function, Class, Test, Commit nodes
- **Relationship Mapping**: IMPORTS, IN_FILE, CALLS, TESTS, MODIFIED_BY edges (commit churn from `git log`)
- **Analysis**: Degree centrality (in/out per edge type, including commit churn), **betweenness centrality**, **PageRank**, **Louvain community detection** on the `IMPORTS` and `CALLS` subgraphs, plus a composite **risk candidate list** (z-normalised centrality + churn + test gap + cross-community ratio) per File node
- **Visualization**: Per-edge-type structure plots, degree bar charts (including MODIFIED_BY), and **centrality bar charts** (betweenness + PageRank for IMPORTS and CALLS)

### 🚧 In Development
- **GraphRAG Pipeline**: AI-powered retrieval and analysis
- **Advanced Metrics**: Betweenness centrality, community detection
- **Hot-spot scoring**: Combine `MODIFIED_BY` churn with structural centrality and missing tests

### 📋 Planned Features
- **LLM Integration**: Natural language quality insights
- **Vector Embeddings**: Semantic code analysis
- **Risk Scoring**: Automated quality risk assessment
- **Multi-language Support**: JavaScript, Java, C++ support

## � File Structure Details

### Backend (`src/`)
- **`web/`**: Flask web application and API endpoints
- **`compatibility/`**: Repository analysis and scoring system
- **`graph/`**: Core graph data model and construction logic
- **`extractors/`**: AST-based code extraction modules
- **`analysis/`**: Graph analysis and metrics calculation
- **`visualization/`**: Graph visualization and reporting

### Frontend (`templates/`)
- **`index.html`**: Repository upload interface
- **`compatibility.html`**: Compatibility check results
- **`results_final.html`**: Analysis results display

### Outputs (`results/`)
- **`graphs/`**: Generated graph JSON files
- **`reports/`**: Text-based analysis reports
- **`visualizations/`**: Graph structure images

## 🛠️ Dependencies

```txt
matplotlib          # Graph visualization
networkx            # Graph algorithms
scipy               # Scientific computing
flask               # Web framework
werkzeug            # WSGI utilities
```

## 📚 Documentation

- **`docs/USAGE.md`**: Detailed usage examples
- **`docs/PROJECT_STRUCTURE.md`**: Architecture details
- **`docs/PROJECT_DELIVERY_REPORT.md`**: English course / submission report template with figure placeholders under `docs/assets/`
- **`docs/GRAPHRAG_CHAT_ROADMAP.md`**: GraphRAG chat future work (vector DB, analysis embeddings, `image_url` + safe Markdown images)
- **`docs/GRAPH_SCHEMA.md`**: Graph schema definition
- **`docs/REPO_COMPATIBILITY_CHECKLIST.md`**: Compatibility requirements

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure compatibility checking passes
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🎯 Future Roadmap

1. **Q1 2026**: Complete GraphRAG pipeline implementation
2. **Q2 2026**: Advanced graph analysis algorithms
3. **Q3 2026**: Multi-language repository support
4. **Q4 2026**: Enterprise features and scaling

---

**Note**: This project focuses on providing actionable insights into software repository quality through graph-based analysis. The web interface makes it accessible to both technical and non-technical users.