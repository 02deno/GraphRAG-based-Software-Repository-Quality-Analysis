from __future__ import annotations

from typing import Dict, Set, Any

SCHEMA_VERSION = "0.1.0"

NODE_TYPES: Set[str] = {"File", "Function", "Class", "Test", "Commit"}
EDGE_TYPES: Set[str] = {"IMPORTS", "IN_FILE", "CALLS", "TESTS", "MODIFIED_BY"}

NODE_REQUIRED_FIELDS: Dict[str, Set[str]] = {
    "File": {"id", "type", "path", "module", "language"},
    "Function": {"id", "type", "name", "qualified_name", "file_path"},
    "Class": {"id", "type", "name", "qualified_name", "file_path"},
    "Test": {"id", "type", "name", "file_path", "target_hint"},
    "Commit": {"id", "type", "hash", "author", "date", "message"},
}

EDGE_REQUIRED_FIELDS: Dict[str, Set[str]] = {
    "IMPORTS": {"source", "target", "type"},
    "IN_FILE": {"source", "target", "type"},
    "CALLS": {"source", "target", "type"},
    "TESTS": {"source", "target", "type"},
    "MODIFIED_BY": {"source", "target", "type"},
}


def validate_graph_contract(nodes: list[Dict[str, Any]], edges: list[Dict[str, Any]]) -> None:
    """Ensure every node and edge satisfies known types and required field sets.

    Args:
        nodes: Serialized node dicts with a ``type`` field.
        edges: Serialized edge dicts with ``source``, ``target``, and ``type``.

    Raises:
        ValueError: On unknown type or missing required keys.
    """
    for node in nodes:
        node_type = node.get("type", "")
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unknown node type: {node_type}")
        required = NODE_REQUIRED_FIELDS[node_type]
        missing = required - set(node.keys())
        if missing:
            raise ValueError(f"Node {node.get('id', '<no-id>')} missing fields: {sorted(missing)}")

    for edge in edges:
        edge_type = edge.get("type", "")
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge type: {edge_type}")
        required = EDGE_REQUIRED_FIELDS[edge_type]
        missing = required - set(edge.keys())
        if missing:
            raise ValueError(f"Edge {edge} missing fields: {sorted(missing)}")


def graph_to_dict(nodes: list[Dict[str, Any]], edges: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrap node and edge lists with schema version and allowed type metadata.

    Args:
        nodes: List of node dicts ready for JSON.
        edges: List of edge dicts ready for JSON.

    Returns:
        Document suitable for persistence and web templates.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_node_types": sorted(NODE_TYPES),
        "schema_edge_types": sorted(EDGE_TYPES),
        "nodes": nodes,
        "edges": edges,
    }
