# Graph Schema (Step 1 - Fixed Dictionary)

This document defines the target schema dictionary for the project.
Current implementation is still partial, but names and required fields are now fixed.

## Schema Version

- `schema_version`: `0.1.0`

## Node Types and Required Fields

- `File`
  - Required fields: `id`, `type`, `path`, `module`, `language`
- `Function`
  - Required fields: `id`, `type`, `name`, `qualified_name`, `file_path`
- `Class`
  - Required fields: `id`, `type`, `name`, `qualified_name`, `file_path`
- `Test`
  - Required fields: `id`, `type`, `name`, `file_path`, `target_hint`
- `Commit`
  - Required fields: `id`, `type`, `hash`, `author`, `date`, `message`

## Edge Types and Required Fields

- `IMPORTS`
  - Required fields: `source`, `target`, `type`
  - Direction: `File -> File`
- `IN_FILE`
  - Required fields: `source`, `target`, `type`
  - Direction: `Function -> File` or `Class -> File`
- `CALLS`
  - Required fields: `source`, `target`, `type`
  - Direction: `Function -> Function`
- `TESTS`
  - Required fields: `source`, `target`, `type`
  - Direction: `Test -> Function` or `Test -> Class`
- `MODIFIED_BY`
  - Required fields: `source`, `target`, `type`
  - Direction: `File -> Commit`

## Current Implementation Status

- Implemented node types: `File`
- Implemented edge types: `IMPORTS`
- Implemented validation:
  - Node and edge type names are checked against fixed dictionaries.
  - Required fields are validated for generated nodes/edges.

## Where Schema Is Defined in Code

- `src/schema_contract.py`
- `src/build_graph.py`

## Initial Quality Signals (Target Analysis Layer)

- High centrality nodes (possible architectural bottlenecks)
- Files with high change frequency (`MODIFIED_BY` density)
- Critical nodes with weak test linkage (`TESTS` edges)
- Dense clusters with high coupling (`IMPORTS` and `CALLS`)
