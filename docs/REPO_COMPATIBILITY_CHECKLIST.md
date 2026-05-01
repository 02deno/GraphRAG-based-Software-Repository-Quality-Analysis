# Repository Compatibility Checklist (Current Prototype)

Use this checklist before running the current graph pipeline on a new repository.

## Quick Result Legend

- **Green**: Works well with the current scripts.
- **Yellow**: Works partially; expect missing or noisy edges.
- **Red**: Out of scope for the current implementation.

## A) Repository Type Fit

- [ ] **Primary language is Python** (`.py` files are central to the codebase).  
  - Green: Mostly Python repo.  
  - Yellow: Mixed-language repo with a Python submodule.  
  - Red: Non-Python repo.

- [ ] **Repository is local and readable** (no permission/path issues).

## B) Import Graph Reliability

- [ ] **Imports are mostly static** (`import x`, `from x import y`) and parseable by AST.
- [ ] **Limited dynamic imports** (`importlib`, `__import__`, runtime string imports are not dominant).
- [ ] **Reasonable package structure** (`__init__.py`, package folders, stable module layout).
- [ ] **Relative imports are not heavily complex** (very deep or unusual relative patterns may reduce mapping quality).

## C) Scale and Performance

- [ ] **Repo size is manageable** for local AST traversal and graph writing.
- [ ] **You can tolerate initial best-effort extraction** (prototype prioritizes practicality over perfect static resolution).

## D) What You Get Today

- [ ] `File` nodes are generated.
- [ ] `IMPORTS` edges (`File -> File`, when resolvable) are generated.
- [ ] `IN_FILE` edges (`Function/Class -> File`) are generated.
- [ ] `CALLS` edges (`Function -> Function/Class`, static heuristic) are generated.
- [ ] `TESTS` edges (`Test -> Function/Class`) are generated.
- [ ] Degree-based analysis is available (`in-degree`, `out-degree`, top-k).
- [ ] Visualization and summary reports can be produced.
- [ ] Basic Python repo stats can be produced.

## E) What Is Not Implemented Yet

- [x] Function/class-level graph extraction (`Function`, `Class` nodes) is in the active pipeline.
- [x] Call graph edges (`CALLS`) are extracted with static name-based matching.
- [x] Test linkage (`TESTS`) is partially extracted for pytest/unittest-style tests.
- [ ] Commit-history edges (`MODIFIED_BY`) are not extracted.
- [ ] Issue-tracker integration is not extracted.
- [ ] GraphRAG retrieval + LLM reasoning pipeline is not implemented yet.

## F) Interpreting Readiness

- **Ready to run now**: A + B mostly Green, C acceptable.
- **Run with caution**: Some Yellow in B; use outputs as exploratory signals.
- **Postpone or narrow scope**: Any Red in A, or heavy dynamic/import complexity.

## Suggested Scope Strategy for Course Delivery

1. Start with one Python-first repo and generate a stable baseline graph.
2. Report known extraction boundaries explicitly (dynamic imports, unresolved modules).
3. Add one next-phase feature incrementally (for example `MODIFIED_BY`) and compare results.
