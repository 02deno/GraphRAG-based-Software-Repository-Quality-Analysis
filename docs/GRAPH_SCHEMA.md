# Graph Schema

This document defines the complete graph schema for the GraphRAG Repository Analysis project, including current implementation status and future GraphRAG integration plans.

## Schema Version

- `schema_version`: `0.1.0`

## 📊 Node Types and Required Fields

### Currently Implemented Node Types

#### `File`
- **Required fields**: `id`, `type`, `path`, `module`, `language`
- **Description**: Repository files with path and module information
- **Implementation**: ✅ Complete

#### `Function`
- **Required fields**: `id`, `type`, `name`, `qualified_name`, `file_path`
- **Description**: Python functions with qualified names and file references
- **Implementation**: ✅ Complete

#### `Class`
- **Required fields**: `id`, `type`, `name`, `qualified_name`, `file_path`
- **Description**: Python classes with qualified names and file references
- **Implementation**: ✅ Complete

#### `Test`
- **Required fields**: `id`, `type`, `name`, `file_path`, `target_hint`
- **Description**: Test functions with target hints for test coverage analysis
- **Implementation**: ✅ Complete

#### `Commit`
- **Required fields**: `id`, `type`, `hash`, `author`, `date`, `message`
- **Description**: Git commit metadata (id format `commit::<full-hash>`; subject only in `message`).
- **Implementation**: ✅ Complete (via `src/extractors/commit_extractor.py`, capped to `GraphBuilder.DEFAULT_MAX_COMMITS = 200` most recent commits; skipped for non-git working trees or when `git` is unavailable).
- **Purpose**: Anchor `MODIFIED_BY` edges for change-frequency / churn analysis.

## 🔗 Edge Types and Required Fields

### Currently Implemented Edge Types

#### `IMPORTS`
- **Required fields**: `source`, `target`, `type`
- **Direction**: `File -> File`
- **Description**: Import relationships between files
- **Implementation**: ✅ Complete

#### `IN_FILE`
- **Required fields**: `source`, `target`, `type`
- **Direction**: `Function -> File` or `Class -> File`
- **Description**: Containment relationships for symbols within files
- **Implementation**: ✅ Complete

#### `TESTS`
- **Required fields**: `source`, `target`, `type`
- **Direction**: `Test -> Function` or `Test -> Class`
- **Description**: Test coverage relationships
- **Implementation**: ✅ Complete

#### `CALLS`
- **Required fields**: `source`, `target`, `type`
- **Direction**: `Function -> Function` or `Function -> Class`
- **Description**: Static call-sites inside function bodies, resolved against `Function` / `Class` nodes by simple name lookup.
- **Implementation**: ✅ Complete

#### `MODIFIED_BY`
- **Required fields**: `source`, `target`, `type`
- **Direction**: `File -> Commit`
- **Description**: File touched by a commit, read from `git log --no-merges --name-only`. Out-degree of a `File` approximates commit churn; in-degree of a `Commit` is the number of files it changed.
- **Implementation**: ✅ Complete (only emitted when the repository has a `.git` directory and `git` is on `PATH`).

## 🎯 Current Implementation Status

### ✅ Completed Features
- **Node Extraction**: File, Function, Class, Test, Commit nodes with full metadata
- **Edge Construction**: IMPORTS, IN_FILE, CALLS, TESTS, MODIFIED_BY relationships
- **Schema Validation**: Complete validation against fixed dictionaries
- **Web Integration**: Full compatibility with web application
- **Analysis Pipeline**: Integration with centrality metrics and quality analysis

### 🚧 In Development
- **Enhanced centrality**: Betweenness, community detection, hot-spot scoring
- **Per-author / per-file churn windows**: Extending `MODIFIED_BY` with time-bucketed views

### 📋 GraphRAG Integration Plans
- **Vector Embeddings**: Code semantic representation for retrieval
- **Subgraph Retrieval**: Graph traversal for context extraction
- **LLM Integration**: Natural language quality analysis
- **Semantic Search**: Enhanced repository querying capabilities

## 🏗️ Schema Implementation Architecture

### Core Components
- **`src/graph/schema.py`**: Schema definitions and validation logic
- **`src/graph/graph_builder.py`**: Main graph construction orchestrator
- **`src/extractors/`**: Modular extraction components
- **`src/analysis/`**: Graph analysis and metrics calculation

### Validation System
- **Type Checking**: Node and edge types validated against schema dictionaries
- **Field Validation**: Required fields validation for all generated elements
- **Schema Versioning**: Version tracking for schema evolution
- **Error Handling**: Graceful failure management for invalid structures

## 🔄 Data Flow Integration

### Web Application Integration
1. **Repository Upload** → Compatibility checking
2. **Compatibility Pass** → Graph construction
3. **Graph Built** → Schema validation
4. **Validation Success** → Analysis execution
5. **Analysis Complete** → Results display

### CLI Integration
1. **Repository Path** → Direct graph construction
2. **Graph Construction** → Schema validation
3. **Validation Success** → Analysis pipeline
4. **Analysis Complete** → Output generation

## 📈 Quality Analysis Framework

### Current Metrics
- **Degree Centrality**: Node importance based on connections
- **Edge Distribution**: Analysis of relationship types
- **Graph Statistics**: Overall repository structure metrics
- **Compatibility Scoring**: Repository readiness assessment

### Future GraphRAG Metrics
- **Semantic Similarity**: Code relationship analysis beyond structure
- **Risk Assessment**: Automated quality risk identification
- **Architectural Insights**: AI-powered repository analysis
- **Change Impact Analysis**: Commit-based evolution tracking

## 🔧 Schema Evolution Roadmap

### Phase 1: Current Implementation ✅
- Basic node and edge types
- Schema validation system
- Web application integration
- Compatibility checking

### Phase 2: Enhanced Analysis 🚧
- Commit history integration
- Function call graphs
- Advanced centrality metrics
- Change frequency analysis

### Phase 3: GraphRAG Integration 📋
- Vector embeddings for code
- Subgraph retrieval algorithms
- LLM-powered quality insights
- Semantic search capabilities

### Phase 4: Advanced Features 📋
- Multi-language support
- Real-time collaboration analysis
- Enterprise-scale processing
- Custom quality metrics

## 📚 Schema Documentation

### Where Schema Is Defined
- **`src/graph/schema.py`**: Core schema definitions
- **`src/graph/graph_builder.py`**: Schema implementation
- **`src/compatibility/repo_checker.py`**: Schema-aware validation
- **`src/web/app.py`**: Web integration

### API Usage Examples
```python
# Schema validation
from src.graph.schema import validate_graph_contract
validate_graph_contract(nodes, edges)

# Graph construction with schema
from src.graph import GraphBuilder
builder = GraphBuilder(repo_path)
builder.build()  # Automatically validates schema
```

---

This schema provides the foundation for both current repository analysis and future GraphRAG capabilities, ensuring extensibility and maintainability as the project evolves toward AI-powered repository quality analysis.
