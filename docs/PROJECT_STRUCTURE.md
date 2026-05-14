# Project Structure

This document describes the current full-stack architecture with optimal backend/frontend separation for the GraphRAG Repository Analysis project.

## High-Level Architecture

```
GraphRAG_Project/
├── src/                              # Backend Core
│   ├── web/                          # Web Application Layer
│   ├── logging_config.py              # UTC stderr + rotating file (GRAPHRAG_LOG_LEVEL, GRAPHRAG_LOG_FILE)
│   ├── utils/                         # Cross-layer filesystem helpers (e.g. repo slugs)
│   ├── compatibility/                 # Compatibility Checking Layer
│   ├── pipeline/                      # End-to-end pipeline orchestration (CLI + web)
│   ├── graphrag/                      # GraphRAG: subgraph retrieval + LLM chat wiring
│   ├── graph/                         # Graph Model & Construction Layer
│   ├── extractors/                    # Data Extraction Layer
│   ├── analysis/                      # Graph Analysis Layer
│   ├── visualization/                 # Visualization Layer
│   ├── stats/                         # Statistics Layer
│   └── CLI Scripts                   # Command Line Interface
├── templates/                         # Frontend Templates
├── docs/                             # Documentation
├── results/                          # Output Directory
├── data/                             # Sample Repositories
├── scripts/                          # Local diagnostics (e.g. check_graphrag_connections.py)
├── requirements.txt                    # Dependencies
├── .env.example                        # FLASK_* / GRAPHRAG_* template (copy to .env)
├── run_web_app.py                    # Web Application Launcher
└── README.md                         # Main Documentation
```

## Project documentation

- **`scripts/check_graphrag_connections.py`** — optional CLI: probes ``GRAPHRAG_OPENAI_*`` (Ollama-compatible ``/models``, ``/chat/completions``, ``/embeddings``) and ``GRAPHRAG_NEO4J_*`` after loading ``.env``; use ``--override-dotenv`` when shell vars should not win.
- **`docs/MIDTERM_PROJECT_REPORT.md`** — detailed midterm-style narrative (architecture, examples, implemented vs missing). Add screenshots under **`docs/assets/`** (see `docs/assets/README.md`).

## Backend Structure (`src/`)

### Web Application Layer (`src/web/`)
**Purpose**: Flask-based web interface for repository analysis
- **`app.py`**: Exposes ``app = create_app()`` for ``run_web_app`` / WSGI servers
- **`factory.py`**: ``create_app()`` loads optional project-root ``.env`` via ``python-dotenv`` (``override=False``), then ``configure_standard_logging()`` and registers lightweight ``after_request`` access logging (``src.web.request``); wires ``graphrag_chat_service`` (LLM optional via ``GRAPHRAG_*`` env vars) and registers blueprints ``web`` and ``graphrag_ws``
- **`blueprints/web.py`**: HTTP routes (blueprint name ``web`` → ``url_for('web.index')``, ``web.upload_repository``, ``web.compatibility_results``, ``web.analyze_repository``, ``web.analysis_results_page``, ``web.analysis_results_chat`` (JSON ``POST`` one-shot chat; primary UI is ``/graphrag/workspace``), ``web.analysis_results_bootstrap_bundle`` (``GET …/bootstrap-bundle.json`` for download-helper JSON), ``web.analysis_visual_asset``, …). Successful upload uses **redirect** to ``GET /compatibility`` so results reload cleanly; the landing page uses ``fetch`` with header ``X-GraphRAG-Progressive-UI`` for JSON validation errors and a step-style progress overlay while waiting. Graph analysis from the compatibility page also sends ``X-GraphRAG-Analyze-Stream`` for **SSE** (``run_repository_pipeline`` reports per-file build steps and per-chart visualization steps); ``templates/compatibility.html`` navigates on the ``complete`` SSE event (then cancels the ``fetch`` stream reader) so results open even if the analyze response lingers half-open. **HTML** + ``document.write`` remains the fallback when streaming is buffered.
- **`blueprints/graphrag_workspace.py`**: Blueprint ``graphrag_ws`` — ``GET /graphrag/workspace`` / ``GET /graphrag/workspace/<run_dir>`` (``templates/graphrag_workspace.html``), ``GET /graphrag/api/projects``, JSON session API under ``/graphrag/api/<run_dir>/sessions`` (persisted under ``results/<run_dir>/graphrag_chat_sessions/``), ``POST …/sessions/fork`` (LLM summary → new session), ``POST …/sessions/<id>/message`` (multi-turn GraphRAG + persistence; mistaken ``GET`` on the same path redirects to the HTML workspace). When the client sends ``X-GraphRAG-Chat-Stream: 1`` (or ``true`` / ``yes``), that ``POST`` returns **SSE** (``text/event-stream``): ``progress`` lines during retrieval, ``token`` lines with assistant text fragments from a streamed ``/chat/completions`` response, then ``complete`` (same payload shape as the non-streaming JSON response) or ``error``. The workspace renders assistant text as **Markdown** (CDN ``marked`` + ``DOMPurify``): typing dots, then streamed tokens in the same bubble; pipeline ``progress`` lines go under collapsible **“> Steps”** ``<details>`` (**open** until the first streamed answer token, then **closed**). The ``complete`` payload includes ``source_context_diagnostics`` (with ``included_chunks``) and optional ``context_auto_fork`` for automatic session fork when ``GRAPHRAG_CHAT_AUTO_SUMMARY_AT_CHARS`` is set (same as ``POST …/sessions/fork``). Session delete uses an **in-page modal** (no native ``confirm``). Client-side errors use a **dismissible banner** under the top bar (not blocking ``alert`` dialogs).
- **`results_paths.py`**: Validates ``web_analysis_*`` run directory names and safe PNG filenames for chart URLs
- **`report_docx.py`**: Builds a combined ``.docx`` export (text artifacts + embedded PNGs) for ``GET …/report.docx``
- **`service_protocols.py`**: ``typing.Protocol`` ports for services (``CompatibilityService``, ``AnalysisPipelineService``, ``ChatCompletionClient`` for GraphRAG)
- **`config.py`**: Project root resolution and Flask configuration (e.g. ``FLASK_SECRET_KEY``)
- **`handlers/`**: Upload and repository filesystem operations
- **`services/`**: Compatibility and pipeline orchestration for the UI
- **`utils/`**: Shared helpers (upload form parsing, GitHub URL rules, temp cleanup)

**Key Features**:
- Repository input (GitHub URL clone, local path; ZIP block in ``index.html`` is hidden until a later UI iteration)
- Compatibility checking integration
- Analysis execution and results display
- Session management for analysis state
- Error handling and cleanup

### Compatibility Checking Layer (`src/compatibility/`)
**Purpose**: Repository analysis and confidence scoring system
- **`check_item.py`**: Value object for one scored check (includes ``result_note`` for per-repository outcome text in the UI)
- **`repo_checker.py`**: Weighted compatibility checker using ``CheckItem`` results

**Scoring Categories**:
- **Core Checks (70%)**: Python language, package-root/tests layout (root or ``backend/`` monorepo paths, top-level ``api/`` or ``app/`` with Python sources), static imports; headline score is **capped under 50%** when the repo is not Python-primary (see ``repo_checker``)
- **Additional Checks (30%)**: Package structure, repo size, requirements, README

### Shared helpers (`src/utils/`)
**Purpose**: Small modules without Flask/HTTP dependencies, safe for pipeline and web imports.
- **`repo_slug.py`**: Sanitize labels for temp upload prefixes and ``results/web_analysis_<slug>_…`` directory names

### Pipeline Layer (`src/pipeline/`)
**Purpose**: Single place to run build → validate → save graph → analyze → visualize (skippable via flag), shared by **`main_pipeline.py`** and the web **`AnalysisService`** (no subprocess indirection). The web app runs visualization by default and writes PNGs under each session’s ``results/…/visuals/`` via ``visual_artifacts_dir``.
- **`run_pipeline.py`**: ``run_repository_pipeline`` orchestration
- **`output_paths.py`**: Default output directories for CLI and web sessions (web uses ``new_web_session_results_dir(repo_slug)`` so folders include the repository label from upload/clone)
- **`result.py`**: ``PipelineRunResult`` structured return type

### GraphRAG layer (`src/graphrag/`)
**Purpose**: Graph-first retrieval (bounded BFS on a typed ``networkx.MultiDiGraph``), optional lexical **source chunk** retrieval from each web run’s ``graphrag_source_chunks.jsonl`` (Python, repo-wide Markdown, and persisted **analysis report** text under ``_analysis/``), plus optional LLM answering for the web assistant.
- **`query_index.py`**: Lexical seed ranking over node fields (substring + token overlap); shared scoring for source blobs.
- **`subgraph_retriever.py`**: Multigraph build, undirected expansion, induced edge listing; query-aware default edge-type sets.
- **`context_formatter.py`**: Serialize an induced subgraph to a capped plain-text block for the model.
- **`analysis_context.py`**: Short text summary from persisted ``analysis_view.json`` (risk, centrality, communities).
- **`community_seeds.py`**: Extra seeds from Louvain community rows when previews overlap the question (uses ``member_ids`` from ``analysis_view``).
- **`source_context.py`**: Writes ``graphrag_run_meta.json``, builds ``graphrag_source_chunks.jsonl`` from ``File`` ``*.py`` paths, repo-wide ``*.md`` (and root ``.rst``/``.txt`` readmes), and virtual ``_analysis/*`` chunks from pipeline metrics/text; ranks all chunks lexically for chat. ``_analysis/*`` chunks get a **score bonus** when the question clearly targets graph metrics, and a **penalty** when the question is about the product/codebase (so host paths in reports do not drown real source files). ``included_chunks`` may include ``kind``, ``excerpt`` (for UI), path, line span, score.
- **`neo4j_driver.py`**: Optional Bolt driver from ``GRAPHRAG_NEO4J_*`` environment variables.
- **`neo4j_property_graph_export.py`**: Bounded Cypher export of ``GraphRAGNode`` / ``GRAPHRAG_EDGE`` for the results-page Neo4j preview (per edge-type row budget so ``MODIFIED_BY`` is not starved by a single global ``LIMIT``); ``web.analysis_results_neo4j_property_graph`` calls ``Neo4jSubgraphExpander.ensure_synced`` from ``graph.json`` before export so the browser view is populated even if chat was never used.
- **`neo4j_subgraph.py`**: ``Neo4jSubgraphExpander`` syncs ``graph.json`` into Neo4j and performs typed BFS expansion when a driver is configured.
- **`embedding_seeds.py`**: OpenAI-compatible ``POST …/v1/embeddings`` (base URL normalized so a trailing ``/v1`` is not doubled) + per-run ``.npz`` cache; cosine-ranked seed ids merged in the chat service.
- **`openai_compatible_client.py`**: OpenAI-compatible ``POST /chat/completions`` (buffered and streamed via ``stream_chat_completion``) from ``GRAPHRAG_OPENAI_*`` / ``GRAPHRAG_CHAT_MODEL``; optional ``GRAPHRAG_CHAT_TIMEOUT_S`` (seconds) for slow local hardware.
- **`chat_service.py`**: Orchestrates seeds, subgraph expansion, source excerpts, optional **conversation history** + **carryover summary** for multi-turn prompts, ``approx_input_chars`` / ``context_warn`` heuristics, optional ``context_auto_fork`` when ``GRAPHRAG_CHAT_AUTO_SUMMARY_AT_CHARS`` is met (requires prior turns), and LLM summarization for session fork.
- **`session_store.py`**: JSON files per chat session under ``results/<run_dir>/graphrag_chat_sessions/`` (list/load/save/delete helpers); streaming ``POST …/message`` persists the **user** turn before SSE starts, then appends the **assistant** when the model finishes (so switching chats or aborting the reader still leaves the question on disk). Assistant messages may include persisted ``source_context_diagnostics`` for workspace **Source snippets** after reload.

### Graph Model & Construction Layer (`src/graph/`)
**Purpose**: Core graph data model and construction logic
- **`graph_builder.py`**: Main graph construction orchestrator
- **`json_document.py`**: Shared graph JSON I/O and degree/label helpers (used by analysis and visualization)
- **`schema.py`**: Node/edge schema definitions and validation
- **`nodes/`**: Individual node type implementations
  - `file_node.py`: File node model
  - `function_node.py`: Function node model
  - `class_node.py`: Class node model
  - `tests_node.py`: Test node model
  - `commit_node.py`: Commit node model (hash, author, ISO date, subject)
- **`edges/`**: Individual edge type implementations
  - `imports_edge.py`: Import relationship model
  - `in_file_edge.py`: File containment model
  - `calls_edge.py`: Function-to-function/class call relationship model
  - `tests_edge.py`: Test coverage model
  - `modified_by_edge.py`: File → Commit relationship model

### Data Extraction Layer (`src/extractors/`)
**Purpose**: AST + VCS extraction modules
- **`symbol_extractor.py`**: Functions and classes extraction
- **`import_extractor.py`**: Import relationship extraction
- **`calls_extractor.py`**: Static call-site collection for `CALLS` edges
- **`tests_extractor.py`**: Test discovery and mapping (``test_*.py``, parents named ``tests`` / ``test`` / ``specs``, etc.)
- **`commit_extractor.py`**: `git log` reader producing `Commit` nodes + `MODIFIED_BY` pairs (capped via `GraphBuilder.DEFAULT_MAX_COMMITS`; no-op without `.git`)
- **`python_file_collector.py`**: Recursive ``*.py`` discovery from the repo root (includes ``backend/``, ``src/``, etc.; excludes name-based dirs like ``node_modules``)
- **`__init__.py`**: Extraction utilities and exports

### Graph Analysis Layer (`src/analysis/`)
**Purpose**: Graph analysis and metrics calculation
- **`graph_analysis.py`**: Orchestrates the text report (degree + centrality + community + risk sections) and the structured web payload (see `analysis_web_payload.py`)
- **`analysis_web_payload.py`**: Builds `analysis_view` (JSON-serializable dict) for `results_final.html` cards; persisted beside `analysis.txt` as `analysis_view.json` in each `results/web_analysis_*` run
- **`centrality_measures.py`**: Pure helpers for betweenness centrality (sampled k=500 above 1000 nodes) and PageRank on typed subgraphs
- **`community_detection.py`**: Louvain modularity (with label-propagation fallback) over the undirected projections of `IMPORTS` / `CALLS`; returns `CommunityDetectionResult` (size-sorted communities + modularity)
- **`risk_score.py`**: Composite per-`File` risk record (`FileRiskScore`) combining z-normalised centrality (IMPORTS + CALLS aggregated to owning files), commit churn (`MODIFIED_BY` out-degree), test gap (uncovered-symbol fraction), and cross-community edge ratio
- **`__init__.py`**: Analysis utilities and exports

### Visualization Layer (`src/visualization/`)
**Purpose**: Graph visualization and reporting
- **`graph_visualization.py`**: Structure subgraphs, degree bar charts per edge kind (IMPORTS, IN_FILE, CALLS, TESTS, MODIFIED_BY, plus combined), centrality bar charts (betweenness + PageRank for IMPORTS and CALLS), plain-text visual summary and a parallel **`visual_summary_view`** dict (schema v1) saved as ``visual_summary_view.json`` next to ``visual_summary.txt`` on web pipeline runs
- **`__init__.py`**: Visualization utilities and exports

### Statistics Layer (`src/stats/`)
**Purpose**: Repository statistics and metrics
- **`repository_stats.py`**: Basic repository statistics
- **`__init__.py`**: Statistics utilities and exports

### CLI Scripts
**Purpose**: Command-line interface for individual operations
- **`build_graph.py`**: CLI wrapper for graph construction
- **`analyze_graph.py`**: CLI wrapper for graph analysis
- **`visualize_graph.py`**: CLI wrapper for visualization
- **`main_pipeline.py`**: CLI entry; loads optional project-root ``.env`` then delegates to ``src.pipeline.run_repository_pipeline``
- **`repo_stats.py`**: CLI wrapper for repository statistics
- **`schema_contract.py`**: Legacy schema contract reference

## 🎨 Frontend Structure (`templates/`)

**Purpose**: HTML templates for web interface
- **`index.html`**: Repository upload interface
  - GitHub URL / local path form (ZIP upload markup kept but ``hidden`` for a future release)
  - Modern responsive design
  - Client-side validation
- **`compatibility.html`**: Compatibility check results
  - Score visualization with color coding
  - Detailed check results with pass/fail indicators
  - Warning messages and recommendations
  - User confirmation flow for low scores
- **`results_final.html`**: Analysis results display
  - Graph statistics overview
  - Quality analysis results
  - Download functionality for JSON/text reports
  - Error handling for failed analyses

## 📁 Output Structure (`results/`)

**Purpose**: Generated analysis outputs
- **`graphs/`**: Generated graph JSON files
- **`reports/`**: Text-based analysis reports
- **`visualizations/`**: Graph structure images
- **`web_analysis_*/`**: Timestamped web analysis results

## 📁 Documentation Structure (`docs/`)

**Purpose**: Project documentation and guides
- **`PROJECT_DELIVERY_REPORT.md`**: English project delivery / submission report (screenshot placeholders in `docs/assets/`)
- **`GRAPHRAG_CHAT_ROADMAP.md`**: Planned vector-store migration, analysis embeddings artifacts, and `image_url` retrieval + UI notes for GraphRAG chat
- **`USAGE.md`**: Detailed usage examples (CLI and web)
- **`PROJECT_STRUCTURE.md`**: Architecture details (this file)
- **`GRAPH_SCHEMA.md`**: Graph schema definition
- **`REPO_COMPATIBILITY_CHECKLIST.md`**: Compatibility requirements
- **`PROJECT_PLAN.md`**: Development roadmap
- **`REPO_SELECTION.md`**: Repository selection criteria
- **`FUNCTIONS.md`**: Function-level documentation
- **`REPORT_DRAFT.md`**: Draft analysis reports

## 🔄 Data Flow Architecture

### Web Application Flow
1. **Upload/Input** → `templates/index.html`
2. **Compatibility Check** → `src/compatibility/repo_checker.py`
3. **Analysis Decision** → Score-based routing in `src/web/app.py`
4. **Graph Construction** → `src/graph/graph_builder.py`
5. **Analysis Execution** → `src/analysis/graph_analysis.py`
6. **Results Display** → `templates/results_final.html`

### CLI Flow
1. **Graph Building** → `src/build_graph.py` → `src/graph/graph_builder.py`
2. **Analysis** → `src/analyze_graph.py` → `src/analysis/graph_analysis.py`
3. **Visualization** → `src/visualize_graph.py` → `src/visualization/graph_visualization.py`
4. **Full Pipeline** → `src/main_pipeline.py` (orchestrates all steps)

## 🔧 Configuration and Dependencies

### Backend Dependencies
- **Flask**: Web framework
- **NetworkX**: Graph algorithms
- **Matplotlib**: Visualization
- **SciPy**: Scientific computing
- **AST**: Python code parsing

### Frontend Technologies
- **HTML5**: Semantic markup
- **CSS3**: Modern styling with responsive design
- **JavaScript**: Client-side interactions and downloads
- **Bootstrap-inspired**: Clean, mobile-friendly UI components

## 🎯 Design Principles

### Backend Design
- **Modularity**: Separate layers for different concerns
- **Extensibility**: Easy to add new extractors and analyzers
- **Testability**: Each component can be tested independently
- **Performance**: Efficient graph construction and analysis

### Frontend Design
- **Responsiveness**: Mobile-friendly interface
- **Accessibility**: Semantic HTML and keyboard navigation
- **User Experience**: Clear feedback and error handling
- **Progressive Enhancement**: Works without JavaScript, enhanced with it

### Integration Design
- **API-First**: Clean separation between frontend and backend
- **Stateless**: Each analysis is independent
- **Error Resilient**: Graceful handling of failures
- **Scalable**: Can handle multiple concurrent analyses

## 🚀 Deployment Considerations

### Development Environment
- **Local Flask Server**: `python run_web_app.py`
- **Debug Mode**: Enabled for development
- **Hot Reload**: Automatic restart on code changes

### Production Considerations
- **WSGI Server**: Use Gunicorn or similar for production
- **Static Files**: Serve via CDN or dedicated server
- **Database**: Consider adding persistent storage for analyses
- **Security**: Add authentication and rate limiting

## 📋 Future Architecture Enhancements

### Planned Additions
1. **API Layer**: RESTful API for programmatic access
2. **Database Layer**: Persistent storage for analyses and results
3. **Caching Layer**: Redis or similar for performance
4. **Queue System**: Background job processing for large repositories
5. **Microservices**: Separate services for different analysis types

### Scalability Improvements
1. **Horizontal Scaling**: Multiple worker processes
2. **Load Balancing**: Distribute analysis requests
3. **Cloud Storage**: S3 or similar for file storage
4. **CDN**: Global content delivery for static assets

---
