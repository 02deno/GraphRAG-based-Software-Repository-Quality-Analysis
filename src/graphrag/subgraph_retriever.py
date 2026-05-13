"""Build typed NetworkX graphs and expand seed nodes by bounded traversal."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Sequence, Set

import networkx as nx


def build_multidigraph(nodes: Sequence[Dict[str, Any]], edges: Sequence[Dict[str, Any]]) -> nx.MultiDiGraph:
    """Create a directed multigraph with ``type`` on each edge.

    Args:
        nodes: Graph nodes (``id`` required).
        edges: Graph edges (``source``, ``target``, optional ``type``).

    Returns:
        A :class:`networkx.MultiDiGraph` so parallel edge types between the same
        pair of nodes are preserved.
    """
    g: nx.MultiDiGraph = nx.MultiDiGraph()
    for node in nodes:
        nid = str(node.get("id", ""))
        if nid:
            g.add_node(nid)
    for i, edge in enumerate(edges):
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        if not src or not tgt:
            continue
        et = str(edge.get("type", "UNKNOWN"))
        g.add_edge(src, tgt, key=i, type=et)
    return g


def _neighbors_through_allowed(
    graph: nx.MultiDiGraph,
    node: str,
    allowed_edge_types: Set[str],
) -> Set[str]:
    """Return neighbor node ids reachable via one allowed directed or reverse edge."""
    out: Set[str] = set()
    for _u, v, _k, data in graph.out_edges(node, keys=True, data=True):
        if data.get("type") in allowed_edge_types and v in graph:
            out.add(v)
    for u, _v, _k, data in graph.in_edges(node, keys=True, data=True):
        if data.get("type") in allowed_edge_types and u in graph:
            out.add(u)
    return out


def expand_seeds_undirected_bfs(
    graph: nx.MultiDiGraph,
    seeds: Iterable[str],
    *,
    allowed_edge_types: Set[str],
    max_depth: int,
    max_nodes: int,
) -> Set[str]:
    """Grow *seeds* by undirected BFS along edges whose ``type`` is allowed.

    Each hop may follow an edge forward or backward; this matches typical
    "structural neighborhood" queries over a directed software graph.

    Args:
        graph: Repository multigraph.
        seeds: Starting node ids (must exist in *graph*).
        allowed_edge_types: Edge ``type`` values that may be traversed.
        max_depth: Maximum BFS depth from any seed (0 = seeds only).
        max_nodes: Hard cap on distinct nodes in the result.

    Returns:
        Node ids forming the retrieved subgraph vertex set.
    """
    visited: Set[str] = set()
    queue: deque[tuple[str, int]] = deque()
    for s in seeds:
        if s in graph and s not in visited:
            visited.add(s)
            queue.append((s, 0))
    while queue and len(visited) < max_nodes:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for nbr in _neighbors_through_allowed(graph, node, allowed_edge_types):
            if nbr in visited or len(visited) >= max_nodes:
                continue
            visited.add(nbr)
            queue.append((nbr, depth + 1))
    return visited


def induced_subgraph_edges(
    graph: nx.MultiDiGraph,
    node_ids: Set[str],
    allowed_edge_types: Set[str],
) -> List[Dict[str, Any]]:
    """List edge dicts (``source``, ``target``, ``type``) inside *node_ids*.

    Args:
        graph: Full repository multigraph.
        node_ids: Vertex set to restrict to.
        allowed_edge_types: Only edges whose type is in this set are included.

    Returns:
        Plain dicts suitable for :mod:`src.graphrag.context_formatter`.
    """
    rows: List[Dict[str, Any]] = []
    allowed = frozenset(allowed_edge_types)
    for u, v, k, data in graph.edges(keys=True, data=True):
        if u not in node_ids or v not in node_ids:
            continue
        et = str(data.get("type", "UNKNOWN"))
        if et not in allowed:
            continue
        rows.append({"source": u, "target": v, "type": et, "_key": k})
    rows.sort(key=lambda r: (r["source"], r["type"], r["target"], r["_key"]))
    for r in rows:
        r.pop("_key", None)
    return rows


def default_edge_types_for_query(query: str) -> Set[str]:
    """Heuristic edge-type set from a natural-language question.

    Args:
        query: User message (lowercasing applied internally).

    Returns:
        A non-empty set of edge types to traverse.
    """
    q = query.lower()
    base = {"IMPORTS", "IN_FILE", "CALLS"}
    out = set(base)
    if any(k in q for k in ("test", "tests", "pytest", "unittest", "coverage")):
        out.add("TESTS")
    if any(k in q for k in ("commit", "commits", "churn", "author", "git", "history", "modified")):
        out.add("MODIFIED_BY")
    return out
