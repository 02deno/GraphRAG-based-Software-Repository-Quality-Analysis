# Web Application Guide

This document provides comprehensive guidance for the GraphRAG Repository Analysis web application, including features, configuration, and troubleshooting.

## 🌐 Web Application Overview

The GraphRAG web application provides a user-friendly interface for repository analysis with intelligent compatibility checking and automated quality insights.

### Key Features
- **📁 Repository input**: GitHub HTTPS URL (``git clone``) and local path; ZIP upload UI hidden until a later release
- **🔍 Compatibility Analysis**: Automated repository assessment with confidence scoring
- **⚠️ Risk Management**: User confirmation for low-compatibility repositories
- **📊 Real-time Analysis**: Immediate graph construction and quality metrics
- **📥 Downloadable Results**: JSON graphs and text reports
- **📱 Responsive Design**: Mobile-friendly interface
- **🛡️ Error Handling**: Graceful failure management

## 🚀 Getting Started

### Prerequisites
```bash
# Python 3.8+ required
python --version

# Install dependencies
pip install -r requirements.txt
```

### Launching the Application
```bash
# Development mode (default)
python run_web_app.py

# The application will be available at:
# http://localhost:5000
```

### Environment Configuration
```bash
# Development settings
export FLASK_ENV=development
export FLASK_DEBUG=True

# Production settings
export FLASK_ENV=production
export FLASK_DEBUG=False
```

## 📋 User Workflow

### 1. Repository Submission

#### GitHub URL
- **Format**: ``https://github.com/<owner>/<repo>`` (HTTPS only in the current checker)
- **Behavior**: Server runs ``git clone`` into a temporary directory (requires ``git`` on the server PATH)
- **Timeout**: Clone attempts time out after 60 seconds (see ``RepositoryHandler.clone_github_repository``)

#### Local Path Input
- **Supported Paths**: Local repository directories on the machine running the web app
- **Validation**: Path existence checks
- **Recommendation**: Use absolute paths for reliability

#### ZIP File Upload (UI deferred)
- The upload handler still accepts ZIP multipart posts; the home template keeps a ``hidden`` ZIP block so it can be re-enabled without rewriting the form.

### 2. Compatibility Analysis

#### Automated Checking Process
1. **Repository Scanning**: Quick structural analysis
2. **Category Evaluation**: Core and additional checks
3. **Score Calculation**: Weighted compatibility scoring
4. **Result Generation**: Detailed analysis report

#### Scoring System
**Core Checks (70% weight):**
- **Python Primary Language** (25%): Python file ratio analysis
- **Package root** (15%): ``src/``, ``backend/app``, ``backend/src``, top-level ``app/`` with Python, or fallbacks
- **Tests** (10%): ``tests/`` at root or under e.g. ``backend/tests``, ``app/tests``
- **Static Imports** (20%): AST-parsable import analysis

**Additional Checks (30% weight):**
- **Package Structure** (10%): `__init__.py` organization
- **Repository Size** (10%): Manageable size assessment
- **Requirements File** (5%): Dependency management
- **README File** (5%): Documentation presence

#### Score Interpretation
- 🟢 **70-100%**: Excellent compatibility
  - Automatic analysis execution
  - High confidence in results
  - Recommended for production use

- 🟡 **50-69%**: Good compatibility
  - Automatic analysis execution
  - Moderate confidence in results
  - Suitable for most repositories

- 🔴 **0-49%**: Low compatibility
  - User confirmation required
  - Lower confidence in results
  - May produce incomplete analysis

### 3. Analysis Execution

#### Automatic Processing (Score ≥ 50%)
1. **Graph Construction**: Build repository graph
2. **Schema Validation**: Verify node/edge compliance
3. **Quality Analysis**: Compute centrality metrics
4. **Results Generation**: Create analysis reports

#### User Confirmation (Score < 50%)
1. **Warning Display**: Clear risk communication
2. **User Choice**: "Analyze Anyway" or "Choose Different Repository"
3. **Proceed with Caution**: Analysis continues with warnings
4. **Enhanced Reporting**: Include confidence indicators in results

### 4. Results Display

#### Graph Statistics
- **Node Count**: Total graph nodes by type
- **Edge Count**: Total graph edges by type
- **Schema Information**: Version and type definitions
- **Implementation Status**: Current vs. planned features

#### Quality Analysis
- **Degree Centrality**: Node importance metrics
- **Top-K Rankings**: Most connected nodes
- **Edge Distribution**: Relationship type analysis
- **Quality Insights**: Automated recommendations

#### Download Options
- **JSON Export**: Complete graph data structure
- **Text Report**: Human-readable analysis summary
- **Timestamped Results**: Organized by analysis date

## 🔧 Technical Architecture

### Backend Components

#### Flask Application (`src/web/app.py`)
- **Routes**: `/` (upload form), `POST /upload` (clone/ZIP + compatibility, then redirect), `GET /compatibility` (session-backed results + per-check explanations), `POST /analyze` (pipeline; progressive UI uses ``text/event-stream`` with ``X-GraphRAG-Analyze-Stream`` for phase **percent** updates, then redirects to ``GET /analysis-results/<run_dir>``), ``GET /analysis-results/<run_dir>/visuals/<filename>`` (PNG charts)
- **Session Management**: Analysis state preservation
- **Error Handling**: Comprehensive exception management
- **File Management**: Temporary upload handling

#### Compatibility System (`src/compatibility/repo_checker.py`)
- **Modular Checks**: Extensible check framework
- **Weighted Scoring**: Configurable importance weights
- **Detailed Reporting**: Pass/fail indicators with explanations
- **Custom Extensions**: Support for project-specific checks

#### Integration Layer
- **Pipeline Integration**: Seamless `main_pipeline.py` execution
- **Result Processing**: Format conversion and validation
- **Cleanup Management**: Automatic temporary file removal
- **Error Recovery**: Graceful failure handling

### Frontend Components

#### Upload Interface (`templates/index.html`)
- **Modern Design**: Clean, professional appearance
- **Responsive Layout**: Mobile and desktop optimization
- **Client Validation**: Input validation before submission
- **Progress Indicators**: Real-time feedback

#### Compatibility Results (`templates/compatibility.html`)
- **Visual Scoring**: Color-coded score display
- **Detailed Metrics**: Individual check results
- **Interactive Elements**: Confirmation dialogs and actions
- **Graph analysis progress**: ``POST /analyze`` with ``X-GraphRAG-Progressive-UI`` and ``X-GraphRAG-Analyze-Stream`` receives **Server-Sent Events** carrying ``percent`` (0–100) and a short **message** per pipeline phase
- **Accessibility**: Semantic HTML and keyboard navigation

#### Analysis Results (`templates/results_final.html`)
- **Graph stats**: Shows **implemented** node/edge types (what appears in the built graph), not the full schema contract reserved for future edge kinds
- **Pipeline timeline**: Includes the visualization step (PNG artifacts under the run’s ``results/…/visuals/`` folder on disk)
- **Chart gallery**: Embeds each PNG via ``web.analysis_visual_asset`` when ``visual_gallery`` is present
- **Interactive Downloads**: Client-side downloads read from an embedded JSON payload (avoids fragile string interpolation that could yield empty or ``undefined`` files for large graphs)
- **Error Handling**: Failed analysis presentation
- **Export Options**: Graph JSON, analysis report text, and visual summary text when available

## 🛠️ Configuration

### Application Settings
```python
# Flask configuration
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['UPLOAD_FOLDER'] = 'temp_uploads'
app.config['SECRET_KEY'] = 'graphrag-secret-key'
```

### Compatibility Thresholds
```python
# Default scoring thresholds
COMPATIBILITY_THRESHOLD = 50  # Minimum score for automatic analysis
HIGH_COMPATIBILITY = 70    # Score for "excellent" classification
```

### Analysis Limits
```python
# Processing constraints
MAX_REPO_SIZE = 1000      # Maximum Python files
ANALYSIS_TIMEOUT = 300      # Maximum analysis time (seconds)
EXCLUDE_DIRS = [            # Directories to ignore
    'venv', 'node_modules', '__pycache__', 
    '.git', '.pytest_cache', 'coverage'
]
```

## 🐛 Troubleshooting

### Common Issues

#### Upload Failures
**Problem**: ZIP file upload fails
**Solutions**:
- Check file size (max 100MB)
- Verify ZIP contains valid Python repository
- Ensure Python package and test folders exist (root or monorepo paths such as ``backend/``)
- Check for corrupted ZIP file

#### Compatibility Issues
**Problem**: Low compatibility score
**Solutions**:
- Add requirements.txt or setup.py file
- Include __init__.py files in packages
- Reduce dynamic imports (importlib, __import__)
- Add README.md documentation
- Ensure Python layout is coherent (``src/`` or ``backend/app`` + ``backend/tests``, etc.)

#### Analysis Errors
**Problem**: Graph construction fails
**Solutions**:
- Check Python syntax in all files
- Verify import statements are resolvable
- Ensure repository read permissions
- Check for circular imports

#### Performance Issues
**Problem**: Slow analysis processing
**Solutions**:
- Reduce repository size (<1000 Python files)
- Exclude unnecessary directories (.git, __pycache__)
- Use SSD storage for better I/O performance
- Increase analysis timeout if needed

### Debug Mode
```bash
# Enable Flask debug mode
export FLASK_DEBUG=1
python run_web_app.py

# Enable verbose analysis
python src/main_pipeline.py --repo "PATH_TO_REPO" --verbose
```

### Log Analysis
```bash
# Check Flask application logs
tail -f flask_app.log

# Check analysis pipeline logs
tail -f analysis.log
```

## 🔒 Security Considerations

### File Upload Security
- **File Type Validation**: Only ZIP files accepted
- **Size Limits**: 100MB maximum upload size
- **Content Scanning**: Basic file structure validation
- **Temporary Storage**: Secure temp directory handling

### Path Security
- **Path Traversal Prevention**: Directory escape protection
- **Permission Validation**: Read access verification
- **Sanitization**: Input path cleaning
- **Access Control**: Local file system restrictions

### Data Privacy
- **No Data Storage**: Analysis results not persisted
- **Temporary Files**: Automatic cleanup after processing
- **Session Data**: Minimal information retention
- **Local Processing**: All analysis happens locally

## 📈 Performance Optimization

### Backend Optimization
- **Parallel Processing**: Multi-threaded analysis support
- **Memory Management**: Efficient graph construction
- **Caching**: Result caching for repeated analyses
- **Resource Limits**: Configurable processing constraints

### Frontend Optimization
- **Lazy Loading**: Progressive content loading
- **Compression**: Gzip response compression
- **CDN Ready**: Static asset optimization
- **Browser Caching**: Client-side caching headers

## 🚀 Deployment

### Development Deployment
```bash
# Local development
python run_web_app.py

# With custom host/port
python run_web_app.py --host 0.0.0.0 --port 8080
```

### Production Deployment
```bash
# Using Gunicorn (recommended)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 src.web.app:app

# Using Docker
docker build -t graphrag-web .
docker run -p 5000:5000 graphrag-web

# Environment variables
export FLASK_ENV=production
export SECRET_KEY=your-production-secret-key
```

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 📚 API Reference

### REST Endpoints
```http
GET  /                    # Upload interface
POST /upload             # Repository upload + compatibility; redirects to GET /compatibility
GET /compatibility       # Renders last compatibility snapshot from session
POST /analyze            # Full pipeline; returns results HTML (or JSON error if X-GraphRAG-Progressive-UI)
```

### Response Formats
```json
// Compatibility check response
{
    "score": 75.5,
    "passed": true,
    "details": [...],
    "warnings": [...]
}

// Analysis results response
{
    "graph_data": {...},
    "analysis_text": "...",
    "pipeline_output": "..."
}
```

## 🎯 Best Practices

### For Users
1. **Repository Preparation**: Ensure proper structure before upload
2. **Compatibility Review**: Check score before proceeding
3. **Result Download**: Save analysis reports for reference
4. **Multiple Analyses**: Compare different repository versions

### For Administrators
1. **Regular Updates**: Keep dependencies current
2. **Monitoring**: Track application performance
3. **Backup Strategy**: Regular configuration backups
4. **Security Updates**: Apply security patches promptly

### For Developers
1. **Modular Extensions**: Use existing check framework
2. **Schema Compliance**: Follow defined node/edge structures
3. **Error Handling**: Implement graceful failure management
4. **Testing**: Comprehensive test coverage for new features

---

This guide provides complete coverage of the GraphRAG web application, ensuring successful deployment and usage for repository analysis workflows.
