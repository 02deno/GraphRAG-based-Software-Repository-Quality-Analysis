# GraphRAG Project Usage

This document explains how to use both the **web application** and **CLI tools** for repository graph analysis.

## Web Application (Recommended)

### Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Start the web application
python run_web_app.py

# Open your browser and go to: http://localhost:5000
```

### Web Application Workflow

#### 1. Repository input
- **GitHub URL**: Paste an ``https://github.com/…`` URL; the app clones it server-side (``git`` required)
- **Local Path**: Provide a path to a repository on the machine running Flask
- **ZIP**: Supported by the upload handler; the default UI hides the ZIP field until a later release (see ``templates/index.html``)

#### 2. Compatibility Check
The system analyzes compatibility in the same step as upload, then sends you to ``GET /compatibility``. There you get a short **step timeline**, a collapsible **how scoring works** note, and **per-check** ``<details>`` blocks with plain-language explanations.

**Scoring Categories:**
- **Core Checks (70%)**: Python language, src/tests folders, static imports
- **Additional Checks (30%)**: Package structure, repo size, requirements, README

**Score Interpretation:**
- : Excellent - Automatic analysis
- : Good - Automatic analysis  
- : Low - User confirmation required

#### 3. Analysis Execution
- **Score ≥ 50%**: Use **Start Graph Analysis**; a progress overlay runs until the pipeline finishes (same-origin ``fetch`` + full HTML swap for results).
- **Score < 50%**: Low-score path with **Analyze Anyway**; same progress behavior.

#### 4. Results Display
- Graph statistics (nodes, edges, types)
- Quality analysis with centrality metrics
- Downloadable JSON and text reports

### Web Application Features
- **Smart Upload**: Validation plus a client-side **progress overlay** while clone/check runs; errors from ``POST /upload`` can return JSON when the progressive-UI header is sent
- **Compatibility page**: Session-backed ``/compatibility`` with expandable scoring help and per-check explanations
- **Interactive Results**: Downloadable analysis reports
- **Responsive Design**: Mobile-friendly interface
- **Error Handling**: Graceful failure management

## CLI Usage (Traditional)

### Build a Graph from Repository
```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO"
```

**Optional output location:**
```bash
python src/build_graph.py --repo "PATH_TO_TARGET_REPO" --output "results/graphs/myrepo_graph.json"
```

**Generated Output:**
- File, Function, Class, and Test nodes
- IMPORTS, IN_FILE, and TESTS edges
- Schema validation and metadata

### Analyze a Graph Document
```bash
python src/analyze_graph.py --graph "results/graphs/myrepo_graph.json" --top-k 10
```

**Save analysis report:**
```bash
python src/analyze_graph.py --graph "results/graphs/myrepo_graph.json" --top-k 10 --save-report "results/reports/myrepo_analysis.txt"
```

**Analysis includes:**
- Degree centrality metrics
- Top-K nodes by incoming/outgoing edges
- Edge type distribution
- Quality insights and recommendations

### Visualize a Graph Document
```bash
python src/visualize_graph.py --graph "results/graphs/myrepo_graph.json"
```

**Visualization outputs:**
- `results/graph_structure.png`
- `results/graph_degree_analysis.png`
- `results/visual_summary.txt`

### Repository Statistics
```bash
python src/repo_stats.py --repo "data/langgraph"
```

**Statistics outputs:**
- `results/repo_stats.txt`
- `results/repo_stats.json`

### Full Pipeline (Recommended for CLI)
```bash
python src/main_pipeline.py --repo "PATH_TO_TARGET_REPO"
```

**Pipeline outputs:**
- `results/<repo_name>_<YYYYMMDD>/<repo_name>_graph.json`
- `results/<repo_name>_<YYYYMMDD>/<repo_name>_pipeline_analysis.txt`
- `results/<repo_name>_<YYYYMMDD>/<repo_name>_pipeline_visual_summary.txt`

**Custom pipeline outputs:**
```bash
python src/main_pipeline.py --repo "PATH_TO_TARGET_REPO" \
  --graph-output "results/myrepo_20260501/myrepo_graph.json" \
  --analysis-output "results/myrepo_20260501/myrepo_analysis.txt" \
  --visual-summary-output "results/myrepo_20260501/myrepo_visual_summary.txt"
```

## Developer API

### Graph Builder API
```python
from pathlib import Path
from src.graph import GraphBuilder, graph_to_dict

# Create builder
repo_path = Path("PATH_TO_TARGET_REPO")
builder = GraphBuilder(repo_path)

# Build graph
builder.build()

# Get graph document
graph_document = graph_to_dict(
    builder.to_dict()["nodes"], 
    builder.to_dict()["edges"]
)
```

### Compatibility Checker API
```python
from src.compatibility.repo_checker import RepoCompatibilityChecker

# Create checker
checker = RepoCompatibilityChecker()

# Analyze repository
result = checker.analyze_repository("PATH_TO_REPO")

# Access results
print(f"Compatibility Score: {result['score']}%")
print(f"Passed: {result['passed']}")
print(f"Warnings: {result['warnings']}")

# Detailed check results
for check in result['details']:
    print(f"{check.name}: {check.passed} (score: {check.score})")
```

## Graph Schema

### Current Implementation
**Node Types:**
- `File`: Repository files with path and module information
- `Function`: Python functions with qualified names
- `Class`: Python classes with qualified names  
- `Test`: Test functions with target hints

**Edge Types:**
- `IMPORTS`: File-to-file import relationships
- `IN_FILE`: Function/Class-to-file containment
- `TESTS`: Test-to-function/class coverage

### Planned Implementation
**Additional Node Types:**
- `Commit`: Version control commits with metadata

**Additional Edge Types:**
- `CALLS`: Function-to-function call relationships
- `MODIFIED_BY`: File-to-commit modification history

## Advanced Usage

### Custom Compatibility Checks
```python
from src.compatibility.repo_checker import RepoCompatibilityChecker, CheckItem

# Extend with custom checks
class CustomChecker(RepoCompatibilityChecker):
    def _define_checks(self):
        checks = super()._define_checks()
        checks.append({
            "name": "custom_check",
            "description": "Custom validation",
            "weight": 0.10,
            "check_fn": self._custom_validation
        })
        return checks
    
    def _custom_validation(self, repo_path):
        # Implement custom logic
        return True, 0.8, ""
```

### Integration with Existing Pipelines
```python
# Use in existing CI/CD
from src.compatibility.repo_checker import RepoCompatibilityChecker
from src.web.app import run_analysis_pipeline

def analyze_pr(repo_path):
    checker = RepoCompatibilityChecker()
    result = checker.analyze_repository(repo_path)
    
    if result['score'] >= 50:
        return run_analysis_pipeline(repo_path)
    else:
        return {"error": "Low compatibility score", "score": result['score']}
```

## Configuration

### Environment Variables
```bash
# Flask configuration
export FLASK_ENV=development
export FLASK_DEBUG=True

# Analysis limits
export MAX_REPO_SIZE=1000
export MAX_FILE_SIZE=100MB
```

### Custom Configuration File
```python
# config.py
ANALYSIS_CONFIG = {
    "max_repo_size": 1000,
    "timeout_seconds": 300,
    "exclude_dirs": ["venv", "node_modules", "__pycache__"],
    "compatibility_threshold": 50
}
```

## Troubleshooting

### Common Issues

**Repository Upload Fails:**
- Check file size (max 100MB)
- Ensure ZIP contains valid Python repository
- Verify src/ and tests/ folders exist

**Low Compatibility Score:**
- Add requirements.txt or setup.py
- Include __init__.py files in packages
- Reduce dynamic imports
- Add README.md documentation

**Analysis Errors:**
- Check Python syntax in all files
- Ensure imports are resolvable
- Verify repository permissions

### Debug Mode
```bash
# Enable debug logging
export FLASK_DEBUG=1
python run_web_app.py

# CLI debug mode
python src/main_pipeline.py --repo "PATH_TO_REPO" --verbose
```

## Additional Resources

- **`docs/PROJECT_STRUCTURE.md`**: Detailed architecture
- **`docs/GRAPH_SCHEMA.md`**: Schema definitions
- **`docs/REPO_COMPATIBILITY_CHECKLIST.md`**: Compatibility requirements
- **`README.md`**: Project overview and quick start

## Best Practices

### For Web Users
1. **Prepare Repository**: Ensure src/ and tests/ folders exist
2. **Check Compatibility**: Review score before analysis
3. **Download Results**: Save analysis reports for reference
4. **Monitor Progress**: Watch for completion notifications

### For CLI Users  
1. **Use Full Pipeline**: Prefer `main_pipeline.py` over individual scripts
2. **Customize Output**: Use explicit output paths for organization
3. **Validate Results**: Check schema validation output
4. **Automate**: Integrate into CI/CD pipelines

### For Developers
1. **Extend Compatibility**: Add custom checks for specific needs
2. **Modular Design**: Use existing components for new features
3. **Schema Compliance**: Follow defined node/edge schemas
4. **Error Handling**: Implement graceful failure management

---
This usage guide covers both web application and CLI workflows, providing comprehensive instructions for all user levels.
