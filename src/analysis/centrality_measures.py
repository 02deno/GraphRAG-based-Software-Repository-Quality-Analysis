"""Betweenness and PageRank centrality for typed subgraphs of a repository graph.

These metrics complement degree counts produced by ``graph_analysis``:

- **Betweenness** highlights *bridge* nodes that sit on many shortest paths between
  other nodes. In software graphs they are usually modules whose removal would
  fragment the architecture.
- **PageRank** ranks nodes by how *broadly relied upon* they are, propagating
  influence across multiple hops (more than a one-step in-degree count).

The computations operate on a single edge type at a time. ``IN_FILE`` is
tree-like and ``TESTS`` / ``MODIFIED_BY`` are bipartite, so the orchestrator only
calls these for ``IMPORTS`` and ``CALLS``.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

import networkx as nx


_EXACT_NODE_LIMIT = 1000
_DEFAULT_SAMPLE_K = 500
_DEFAULT_SEED = 42


def build_typed_subgraph(
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    edge_type: str,
) -> nx.DiGraph:
    """Build a directed graph restricted to one edge ``type``.

    Args:
        nodes: Graph node dicts (only ``id`` is consumed).
        edges: Graph edge dicts; only those whose ``type`` matches are added.
        edge_type: Edge type token (e.g. ``"IMPORTS"`` or ``"CALLS"``).

    Returns:
        A :class:`networkx.DiGraph` with all nodes plus the filtered edges. Nodes
        without any edge of the requested type remain isolated, which keeps id →
        path lookups stable in downstream reports.
    """
    graph = nx.DiGraph()
    for node in nodes:
        graph.add_node(node["id"])
    for edge in edges:
        if edge.get("type") == edge_type:
            graph.add_edge(edge["source"], edge["target"])
    return graph


def compute_betweenness_centrality(
    graph: nx.DiGraph,
    *,
    exact_node_limit: int = _EXACT_NODE_LIMIT,
    sample_k: int = _DEFAULT_SAMPLE_K,
    seed: int = _DEFAULT_SEED,
) -> Tuple[Counter, bool]:
    """Compute betweenness centrality, switching to sampling for large graphs.

    Args:
        graph: Directed graph to analyse.
        exact_node_limit: When ``len(graph) <= exact_node_limit`` the algorithm
            runs on every source node; above that it samples ``sample_k`` random
            sources to keep runtime bounded.
        sample_k: Number of source nodes used for the sampled estimator.
        seed: Random seed for the sampler (reproducible across runs).

    Returns:
        Tuple ``(scores, approximated)`` where ``scores`` maps node id to a
        normalized betweenness value and ``approximated`` is ``True`` when the
        sampled estimator was used.
    """
    if len(graph) == 0:
        return Counter(), False

    if len(graph) <= exact_node_limit:
        raw = nx.betweenness_centrality(graph, normalized=True, endpoints=False)
        approximated = False
    else:
        effective_k = min(sample_k, len(graph))
        raw = nx.betweenness_centrality(
            graph,
            k=effective_k,
            normalized=True,
            endpoints=False,
            seed=seed,
        )
        approximated = True

    scores: Counter = Counter()
    for node_id, score in raw.items():
        if score > 0.0:
            scores[node_id] = float(score)
    return scores, approximated


def compute_pagerank(
    graph: nx.DiGraph,
    *,
    alpha: float = 0.85,
) -> Counter:
    """Compute PageRank scores for a directed graph.

    Args:
        graph: Directed graph to analyse.
        alpha: Damping factor (default 0.85, NetworkX standard).

    Returns:
        Counter mapping node id to PageRank score. Empty when ``graph`` has no
        nodes. Isolated nodes still receive the uniform-teleport baseline value.
    """
    if len(graph) == 0:
        return Counter()
    raw = nx.pagerank(graph, alpha=alpha)
    scores: Counter = Counter()
    for node_id, score in raw.items():
        scores[node_id] = float(score)
    return scores


def top_k_scores(scores: Counter, k: int) -> List[Tuple[str, float]]:
    """Return the top-``k`` ``(node_id, score)`` pairs by descending score.

    Args:
        scores: Counter of float-valued centrality scores.
        k: Maximum number of entries to return.

    Returns:
        List sorted by score descending. Empty when ``scores`` is empty.
    """
    return scores.most_common(k)
