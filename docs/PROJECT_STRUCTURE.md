# Project Structure

This document describes the current full-stack architecture with optimal backend/frontend separation for the GraphRAG Repository Analysis project.

## High-Level Architecture

```
GraphRAG_Project/
├── src/                              # Backend Core
│   ├── web/                          # Web Application Layer
│   ├── compatibility/                 # Compatibility Checking Layer
│   ├── pipeline/                      # End-to-end pipeline orchestration (CLI + web)
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
├── requirements.txt                    # Dependencies
├── run_web_app.py                    # Web Application Launcher
└── README.md                         # Main Documentation
```

## Backend Structure (`src/`)

### Web Application Layer (`src/web/`)
**Purpose**: Flask-based web interface for repository analysis
- **`app.py`**: Exposes ``app = create_app()`` for ``run_web_app`` / WSGI servers
- **`factory.py`**: ``create_app()`` wires config, extensions, and blueprints
- **`blueprints/web.py`**: HTTP routes (blueprint name ``web`` → use ``url_for('web.index')`` etc.)
- **`service_protocols.py`**: ``typing.Protocol`` ports for services (dependency inversion)
- **`config.py`**: Project root resolution and Flask configuration (e.g. ``FLASK_SECRET_KEY``)
- **`handlers/`**: Upload and repository filesystem operations
- **`services/`**: Compatibility and pipeline orchestration for the UI
- **`utils/`**: Shared helpers (upload form parsing, GitHub URL rules, temp cleanup)

**Key Features**:
- Repository upload (ZIP files and local paths)
- Compatibility checking integration
- Analysis execution and results display
- Session management for analysis state
- Error handling and cleanup

### Compatibility Checking Layer (`src/compatibility/`)
**Purpose**: Repository analysis and confidence scoring system
- **`check_item.py`**: Value object for one scored check
- **`repo_checker.py`**: Weighted compatibility checker using ``CheckItem`` results

**Scoring Categories**:
- **Core Checks (70%)**: Python language, src/tests folders, static imports
- **Additional Checks (30%)**: Package structure, repo size, requirements, README

### Pipeline Layer (`src/pipeline/`)
**Purpose**: Single place to run build → validate → save graph → analyze → (optional) visualize, shared by **`main_pipeline.py`** and the web **`AnalysisService`** (no subprocess indirection).
- **`run_pipeline.py`**: ``run_repository_pipeline`` orchestration
- **`output_paths.py`**: Default output directories for CLI and web sessions
- **`result.py`**: ``PipelineRunResult`` structured return type

### Graph Model & Construction Layer (`src/graph/`)
**Purpose**: Core graph data model and construction logic
- **`graph_builder.py`**: Main graph construction orchestrator
- **`json_document.py`**: Shared graph JSON I/O and degree/label helpers (used by analysis and visualization)
- **`schema.py`**: Node/edge schema definitions and validation
- **`nodes/`**: Individual node type implementations
  - `file_node.py`: File node model
  - `function_node.py`: Function node model
  - `class_node.py`: Class node model
  - `test_node.py`: Test node model
- **`edges/`**: Individual edge type implementations
  - `imports_edge.py`: Import relationship model
  - `in_file_edge.py`: File containment model
  - `tests_edge.py`: Test coverage model

### Data Extraction Layer (`src/extractors/`)
**Purpose**: AST-based code extraction modules
- **`symbol_extractor.py`**: Functions and classes extraction
- **`import_extractor.py`**: Import relationship extraction
- **`test_extractor.py`**: Test discovery and mapping
- **`python_file_collector.py`**: Python file discovery
- **`__init__.py`**: Extraction utilities and exports

### Graph Analysis Layer (`src/analysis/`)
**Purpose**: Graph analysis and metrics calculation
- **`graph_analysis.py`**: Degree centrality and basic metrics
- **`__init__.py`**: Analysis utilities and exports

### Visualization Layer (`src/visualization/`)
**Purpose**: Graph visualization and reporting
- **`graph_visualization.py`**: Graph structure visualization
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
- **`main_pipeline.py`**: CLI entry that delegates to ``src.pipeline.run_repository_pipeline``
- **`repo_stats.py`**: CLI wrapper for repository statistics
- **`schema_contract.py`**: Legacy schema contract reference

## 🎨 Frontend Structure (`templates/`)

**Purpose**: HTML templates for web interface
- **`index.html`**: Repository upload interface
  - File upload and URL input forms
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
