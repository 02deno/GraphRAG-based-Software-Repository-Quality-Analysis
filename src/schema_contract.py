from __future__ import annotations

from typing import Dict, Set

SCHEMA_VERSION = "0.1.0"

NODE_TYPES: Set[str] = {"File", "Function", "Class", "Test", "Commit"}
EDGE_TYPES: Set[str] = {"IMPORTS", "IN_FILE", "CALLS", "TESTS", "MODIFIED_BY"}

# Required fields for each node type in the target schema.
NODE_REQUIRED_FIELDS: Dict[str, Set[str]] = {
    "File": {"id", "type", "path", "module", "language"},
    "Function": {"id", "type", "name", "qualified_name", "file_path"},
    "Class": {"id", "type", "name", "qualified_name", "file_path"},
    "Test": {"id", "type", "name", "file_path", "target_hint"},
    "Commit": {"id", "type", "hash", "author", "date", "message"},
}

# Required fields for each edge type in the target schema.
EDGE_REQUIRED_FIELDS: Dict[str, Set[str]] = {
    "IMPORTS": {"source", "target", "type"},
    "IN_FILE": {"source", "target", "type"},
    "CALLS": {"source", "target", "type"},
    "TESTS": {"source", "target", "type"},
    "MODIFIED_BY": {"source", "target", "type"},
}

