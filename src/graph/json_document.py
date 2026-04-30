"""Shared helpers for graph JSON documents (loading, degrees, labels).

This module centralizes logic that was duplicated across analysis and visualization.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_graph_document(graph_path: Path) -> Dict[str, Any]:
    """Load a graph JSON file produced by the graph builder.

    Args:
        graph_path: Path to the JSON document on disk.

    Returns:
        Parsed document with at least ``nodes`` and ``edges`` keys when valid.
    """
    return json.loads(graph_path.read_text(encoding="utf-8"))


def compute_in_out_degrees(edges: List[Dict[str, str]]) -> Tuple[Counter, Counter]:
    """Compute in-degree and out-degree counters from directed edges.

    Args:
        edges: List of edge dicts with ``source`` and ``target`` keys.

    Returns:
        A pair ``(in_degree, out_degree)`` counting edges into and out of each node id.
    """
    in_degree: Counter = Counter()
    out_degree: Counter = Counter()
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        out_degree[source] += 1
        in_degree[target] += 1
    return in_degree, out_degree


def compute_in_out_degrees_by_edge_type(
    edges: List[Dict[str, str]],
) -> Dict[str, Tuple[Counter, Counter]]:
    """Compute in/out-degree counters grouped by edge ``type``.

    Args:
        edges: List of edge dicts with ``source``, ``target``, and optional ``type``.

    Returns:
        Mapping from edge type string to ``(in_degree, out_degree)`` counters.
    """
    degrees_by_type: Dict[str, Tuple[Counter, Counter]] = {}
    for edge in edges:
        edge_type = edge.get("type", "UNKNOWN")
        if edge_type not in degrees_by_type:
            degrees_by_type[edge_type] = (Counter(), Counter())
        in_deg, out_deg = degrees_by_type[edge_type]
        out_deg[edge["source"]] += 1
        in_deg[edge["target"]] += 1
    return degrees_by_type


def map_node_id_to_path(nodes: List[Dict[str, str]]) -> Dict[str, str]:
    """Map each node id to a display path (falls back to id).

    Args:
        nodes: Node dicts from a graph document.

    Returns:
        Dict mapping node id to ``path`` field when present.
    """
    return {node["id"]: node.get("path", node["id"]) for node in nodes}


def graph_stem_display_name(graph_path: Path) -> str:
    """Derive a short repository or graph name from a graph JSON filename.

    Args:
        graph_path: Path whose stem is used for naming.

    Returns:
        Human-readable name with common suffixes stripped.
    """
    stem = graph_path.stem
    if stem.endswith("_imports_graph"):
        return stem[: -len("_imports_graph")]
    if stem.endswith("_graph"):
        return stem[: -len("_graph")]
    return stem


def human_readable_graph_edge_label(edges: List[Dict[str, str]]) -> str:
    """Build a short label describing which edge type(s) appear in the graph.

    Args:
        edges: Edge dicts from a graph document.

    Returns:
        A phrase such as ``IMPORTS graph`` or ``IMPORTS+IN_FILE graph``.
    """
    edge_types = sorted({edge.get("type", "UNKNOWN") for edge in edges})
    if len(edge_types) == 1:
        return f"{edge_types[0]} graph"
    return f"{'+'.join(edge_types)} graph"
