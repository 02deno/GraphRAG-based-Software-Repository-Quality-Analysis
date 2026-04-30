# GraphRAG-based Software Repository Quality Analysis

This project provides a **full-stack web application** for analyzing Python repositories using graph-based techniques. It models software repositories as graphs and provides quality insights through automated analysis with compatibility checking and confidence scoring.

## 🚀 Quick Start

### Web Application (Recommended)
```bash
# Install dependencies
pip install -r requirements.txt

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
- **📁 Repository Upload**: Upload ZIP files or provide local paths
- **🔍 Smart Compatibility Checking**: Automated repository analysis with confidence scoring
- **⚠️ Risk Assessment**: Repositories with <50% compatibility require user confirmation
- **📊 Real-time Analysis**: Automatic graph analysis for compatible repositories
- **📥 Downloadable Results**: Export JSON graphs and text reports
- **📱 Responsive Design**: Mobile-friendly interface

### Core Analysis Features
- **Graph Construction**: File, Function, Class, and Test nodes
- **Relationship Mapping**: IMPORTS, IN_FILE, and TESTS edges
- **Quality Metrics**: Degree centrality and structural analysis
- **Visualization Support**: Graph structure and analysis reports

## 🏗️ Architecture

```
GraphRAG_Project/
├── 📁 src/                          # Backend Core
│   ├── 📁 web/                      # Web Application
│   │   ├── app.py                    # Flask application
│   │   └── __init__.py
│   ├── 📁 compatibility/             # Compatibility Checking
│   │   ├── repo_checker.py           # Repository analysis & scoring
│   │   └── __init__.py
│   ├── 📁 graph/                    # Graph Model & Builder
│   │   ├── graph_builder.py          # Main graph construction
│   │   ├── schema.py                # Node/edge schema definitions
│   │   └── nodes/ & edges/         # Graph components
│   ├── 📁 extractors/               # Data Extraction
│   │   ├── symbol_extractor.py       # Functions & classes
│   │   ├── import_extractor.py       # Import relationships
│   │   ├── test_extractor.py        # Test discovery
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
│   └── results_final.html          # Analysis results
├── 📁 docs/                          # Documentation
├── 📁 results/                       # Analysis outputs
├── 📁 data/                          # Sample repositories
├── 📄 requirements.txt               # Python dependencies
├── 📄 run_web_app.py               # Web app launcher
└── 📄 README.md                    # This file
```

## 📋 Compatibility Checking System

### Scoring Categories

**Core Checks (70% weight):**
- **Python Primary Language** (25%): Repository is primarily Python-based
- **src/ Folder** (15%): Standard source directory structure
- **tests/ Folder** (10%): Test directory presence
- **Static Imports** (20%): Parseable import statements

**Additional Checks (30% weight):**
- **Package Structure** (10%): `__init__.py` files and organization
- **Repository Size** (10%): Manageable size for analysis
- **Requirements File** (5%): Dependency management
- **README File** (5%): Documentation presence

### Score Interpretation
- **🟢 70-100%**: Excellent compatibility - Automatic analysis
- **🟡 50-69%**: Good compatibility - Automatic analysis
- **🔴 0-49%**: Low compatibility - User confirmation required

## 🚦 Usage Guide

### Web Application Workflow

1. **Upload Repository**
   - Choose ZIP file upload or local path
   - Maximum file size: 100MB

2. **Compatibility Check**
   - Automated analysis runs immediately
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
- **Graph Construction**: File, Function, Class, Test nodes
- **Relationship Mapping**: IMPORTS, IN_FILE, TESTS edges
- **Analysis**: Degree centrality and basic metrics
- **Visualization**: Graph structure and analysis reports

### 🚧 In Development
- **GraphRAG Pipeline**: AI-powered retrieval and analysis
- **Advanced Metrics**: Betweenness centrality, community detection
- **Call Graph**: Function-to-function relationships
- **Commit History**: Version control integration

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