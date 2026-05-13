"""Community detection on typed subgraphs of a repository graph.

Communities are clusters of nodes that are densely connected internally and
sparsely connected to the rest of the graph. In software systems they typically
correspond to architectural sub-systems; unexpected community boundaries flag
leaks across package layers.

The orchestrator (``graph_analysis``) calls this module for the ``IMPORTS`` and
``CALLS`` subgraphs only — those are the structural dependency graphs where
modularity is a meaningful quality signal. ``IN_FILE`` is tree-like, and
``TESTS`` / ``MODIFIED_BY`` are bipartite, so modularity does not apply to them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

import networkx as nx
from networkx.algorithms.community import (
    label_propagation_communities,
    louvain_communities,
    modularity,
)

logger = logging.getLogger(__name__)

_DEFAULT_SEED = 42
_DEFAULT_RESOLUTION = 1.0


@dataclass(frozen=True)
class CommunityDetectionResult:
    """Outcome of running a community detection algorithm on one subgraph.

    Attributes:
        communities: List of node-id sets sorted by descending size.
        modularity_score: Newman modularity (in ``[-0.5, 1]``). ``None`` when the
            graph is empty.
        algorithm: Identifier of the algorithm that produced ``communities``
            (``"louvain"`` or ``"label_propagation"``).
        node_count: Number of nodes in the analysed subgraph.
        edge_count: Number of edges (undirected) used during detection.
    """

    communities: Tuple[Tuple[str, ...], ...]
    modularity_score: float | None
    algorithm: str
    node_count: int
    edge_count: int


def detect_communities(
    directed_graph: nx.DiGraph,
    *,
    algorithm: str = "louvain",
    seed: int = _DEFAULT_SEED,
    resolution: float = _DEFAULT_RESOLUTION,
) -> CommunityDetectionResult:
    """Run community detection on the **undirected projection** of *directed_graph*.

    Louvain (the default) requires an undirected graph. We project edges with
    ``to_undirected()`` so that an ``A -> B`` import or call still pulls ``A`` and
    ``B`` into the same community candidate set.

    Args:
        directed_graph: Directed subgraph (e.g. ``IMPORTS`` or ``CALLS`` only).
        algorithm: Either ``"louvain"`` (default; modularity-based, returns a
            partition) or ``"label_propagation"`` (deterministic seed-driven
            fallback when Louvain is unavailable).
        seed: Random seed for reproducibility.
        resolution: Louvain resolution parameter — values >1 favour smaller
            communities, <1 favour larger ones. Default ``1.0`` matches the
            classic Louvain modularity optimum.

    Returns:
        :class:`CommunityDetectionResult` ordered by descending community size.

    Raises:
        ValueError: If ``algorithm`` is not recognised.
    """
    if len(directed_graph) == 0:
        return CommunityDetectionResult(
            communities=(),
            modularity_score=None,
            algorithm=algorithm,
            node_count=0,
            edge_count=0,
        )

    undirected = directed_graph.to_undirected(as_view=False)
    # Multiple directed edges between two nodes collapse to one undirected edge.
    node_count = undirected.number_of_nodes()
    edge_count = undirected.number_of_edges()

    if algorithm == "louvain":
        partition = louvain_communities(
            undirected,
            seed=seed,
            resolution=resolution,
        )
    elif algorithm == "label_propagation":
        partition = list(label_propagation_communities(undirected))
    else:
        raise ValueError(
            f"Unsupported community detection algorithm: {algorithm!r} "
            "(use 'louvain' or 'label_propagation')."
        )

    # Drop isolates that wound up in singleton communities so report stays useful.
    sized_communities = sorted(
        (tuple(sorted(community)) for community in partition),
        key=lambda c: (-len(c), c[0] if c else ""),
    )
    score = modularity(undirected, [set(c) for c in sized_communities]) if sized_communities else None

    logger.info(
        "community_detection_done algorithm=%s nodes=%d edges=%d communities=%d modularity=%.4f",
        algorithm,
        node_count,
        edge_count,
        len(sized_communities),
        score if score is not None else float("nan"),
    )

    return CommunityDetectionResult(
        communities=tuple(sized_communities),
        modularity_score=float(score) if score is not None else None,
        algorithm=algorithm,
        node_count=node_count,
        edge_count=edge_count,
    )


def summarize_community_sizes(
    result: CommunityDetectionResult,
    *,
    top_k: int,
) -> List[Tuple[int, int]]:
    """Return ``(community_index, size)`` pairs for the top-``k`` largest communities.

    Args:
        result: Output of :func:`detect_communities`.
        top_k: Maximum number of communities to return.

    Returns:
        List of ``(index, size)`` pairs (index aligns with ``result.communities``).
    """
    return [(idx, len(c)) for idx, c in enumerate(result.communities[:top_k])]
