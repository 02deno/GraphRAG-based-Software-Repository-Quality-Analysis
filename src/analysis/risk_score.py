"""Composite per-File risk scoring.

Combines four signals previously computed elsewhere in the analysis pipeline:

1. **Structural centrality** — sum of betweenness + PageRank on the ``IMPORTS``
   and ``CALLS`` subgraphs, aggregated to the *owning* ``File`` for any
   ``Function`` / ``Class`` symbols.
2. **Commit churn** — out-degree of ``MODIFIED_BY`` from the ``File`` (how many
   commits touched it).
3. **Test gap** — fraction of in-file symbols (``Function`` / ``Class``) that
   have **no** incoming ``TESTS`` edge.
4. **Cross-community ratio** — share of ``IMPORTS`` + ``CALLS`` edges leaving
   the ``File`` (or one of its symbols) whose endpoint falls in a different
   Louvain community than the source.

Each dimension is z-normalised (sample std, ``n − 1``) across the population of
``File`` nodes in the graph, then combined with configurable weights. The total
is dimensionless and *relative* — useful for ranking, not for absolute thresholds.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

from .community_detection import CommunityDetectionResult

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: Mapping[str, float] = {
    "centrality": 1.0,
    "churn": 1.0,
    "test_gap": 1.0,
    "cross_community": 1.0,
}

_CENTRALITY_EDGE_TYPES = ("IMPORTS", "CALLS")
_COMMUNITY_EDGE_TYPES = ("IMPORTS", "CALLS")


@dataclass(frozen=True)
class FileRiskScore:
    """Per-``File`` risk record with both totals and per-dimension z-scores.

    Attributes:
        file_id: Node id (graph-relative path).
        file_path: Display path for reports (same as id today).
        total: Weighted sum of the four z-scored dimensions.
        centrality_z: Z-score of summed betweenness + PageRank (IMPORTS + CALLS).
        churn_z: Z-score of ``MODIFIED_BY`` out-degree.
        test_gap_z: Z-score of the fraction of in-file symbols missing TESTS coverage.
        cross_community_z: Z-score of the fraction of outgoing IMPORTS/CALLS edges
            that cross Louvain community boundaries.
        raw_centrality: Pre-z aggregated centrality (betweenness + PageRank sum).
        raw_churn: Pre-z commit count.
        raw_test_gap: Pre-z fraction of symbols without a TESTS edge.
        raw_cross_community: Pre-z fraction of cross-community edges.
        symbol_count: Total Function/Class symbols hosted by the file (denominator
            for ``raw_test_gap``).
        tested_symbol_count: Symbols with at least one incoming TESTS edge.
    """

    file_id: str
    file_path: str
    total: float
    centrality_z: float
    churn_z: float
    test_gap_z: float
    cross_community_z: float
    raw_centrality: float
    raw_churn: float
    raw_test_gap: float
    raw_cross_community: float
    symbol_count: int
    tested_symbol_count: int


def _zscore_series(values: Mapping[str, float]) -> Dict[str, float]:
    """Return z-scores keyed by the same ids (zero when std is zero).

    Args:
        values: Mapping from id to raw score.

    Returns:
        Dict of ``id -> (value - mean) / std`` (sample std with Bessel correction).
        When the population has zero variance, every id maps to ``0.0``.
    """
    if not values:
        return {}
    arr = list(values.values())
    n = len(arr)
    mean = sum(arr) / n
    if n < 2:
        return {k: 0.0 for k in values}
    var = sum((x - mean) ** 2 for x in arr) / (n - 1)
    std = math.sqrt(var)
    if std == 0.0:
        return {k: 0.0 for k in values}
    return {k: (v - mean) / std for k, v in values.items()}


def _file_id_for_node(
    node_id: str,
    file_ids: set[str],
    symbol_to_file: Mapping[str, str],
) -> Optional[str]:
    """Map any node id to the owning ``File`` id, or ``None`` when not applicable.

    Args:
        node_id: Graph node id to resolve.
        file_ids: Set of all ``File`` ids in the graph.
        symbol_to_file: Lookup from ``Function``/``Class`` id to owning file id.

    Returns:
        File id when ``node_id`` is a File, the symbol's hosting file when it is
        a Function/Class, otherwise ``None`` (e.g. Commit or Test nodes).
    """
    if node_id in file_ids:
        return node_id
    return symbol_to_file.get(node_id)


def _aggregate_to_files(
    centrality_counter: Counter,
    file_ids: set[str],
    symbol_to_file: Mapping[str, str],
) -> Dict[str, float]:
    """Sum centrality scores onto the owning ``File`` node for each Function/Class."""
    result: Dict[str, float] = defaultdict(float)
    for node_id, score in centrality_counter.items():
        owner = _file_id_for_node(node_id, file_ids, symbol_to_file)
        if owner is not None:
            result[owner] += float(score)
    return dict(result)


def _build_node_to_community(
    community_sections: Mapping[str, CommunityDetectionResult],
) -> Dict[str, Dict[str, int]]:
    """Build ``edge_type -> {node_id: community_index}`` lookup tables."""
    lookups: Dict[str, Dict[str, int]] = {}
    for edge_type, result in community_sections.items():
        node_to_community: Dict[str, int] = {}
        for idx, members in enumerate(result.communities):
            for node_id in members:
                node_to_community[node_id] = idx
        lookups[edge_type] = node_to_community
    return lookups


def compute_risk_scores(
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    centrality_sections: Mapping[str, Mapping[str, object]],
    community_sections: Mapping[str, CommunityDetectionResult],
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> List[FileRiskScore]:
    """Compute a composite risk score for every ``File`` in the graph.

    Args:
        nodes: Graph node dicts (must include ``id`` and ``type``; ``File`` nodes
            also expect ``path``; ``Function``/``Class`` nodes expect ``file_path``).
        edges: Graph edge dicts (``source``, ``target``, ``type``).
        centrality_sections: Output of ``graph_analysis._compute_centrality_sections``
            (must include full ``Counter`` instances under ``"betweenness"`` and
            ``"pagerank"`` keys).
        community_sections: Output of ``graph_analysis._compute_community_sections``.
        weights: Optional override mapping merged on top of :data:`DEFAULT_WEIGHTS`.
            Keys: ``centrality``, ``churn``, ``test_gap``, ``cross_community``.

    Returns:
        List of :class:`FileRiskScore` sorted by ``total`` descending. Empty when
        the graph contains no ``File`` nodes.
    """
    file_nodes = [node for node in nodes if node.get("type") == "File"]
    if not file_nodes:
        return []
    file_ids: set[str] = {node["id"] for node in file_nodes}
    file_path_lookup: Dict[str, str] = {
        node["id"]: node.get("path", node["id"]) for node in file_nodes
    }
    symbol_to_file: Dict[str, str] = {}
    symbols_per_file: Dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        if node.get("type") in ("Function", "Class"):
            file_path = node.get("file_path") or ""
            if file_path:
                symbol_to_file[node["id"]] = file_path
                symbols_per_file[file_path].add(node["id"])

    centrality_per_file: Dict[str, float] = defaultdict(float)
    for edge_type in _CENTRALITY_EDGE_TYPES:
        section = centrality_sections.get(edge_type) or {}
        betweenness = section.get("betweenness") or Counter()
        pagerank = section.get("pagerank") or Counter()
        for owner, score in _aggregate_to_files(
            betweenness, file_ids, symbol_to_file
        ).items():
            centrality_per_file[owner] += score
        for owner, score in _aggregate_to_files(
            pagerank, file_ids, symbol_to_file
        ).items():
            centrality_per_file[owner] += score

    churn_per_file: Dict[str, float] = defaultdict(float)
    for edge in edges:
        if edge.get("type") == "MODIFIED_BY":
            source = edge.get("source", "")
            if source in file_ids:
                churn_per_file[source] += 1.0

    tested_symbols_per_file: Dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.get("type") != "TESTS":
            continue
        target = edge.get("target", "")
        owner = symbol_to_file.get(target)
        if owner is not None:
            tested_symbols_per_file[owner].add(target)

    test_gap_per_file: Dict[str, float] = {}
    for file_id in file_ids:
        total = len(symbols_per_file.get(file_id, set()))
        tested = len(tested_symbols_per_file.get(file_id, set()))
        test_gap_per_file[file_id] = ((total - tested) / total) if total else 0.0

    community_lookups = _build_node_to_community(community_sections)
    cross_edges_per_file: Dict[str, int] = defaultdict(int)
    total_edges_per_file: Dict[str, int] = defaultdict(int)
    for edge in edges:
        edge_type = edge.get("type", "")
        if edge_type not in _COMMUNITY_EDGE_TYPES:
            continue
        node_to_community = community_lookups.get(edge_type)
        if not node_to_community:
            continue
        source = edge.get("source", "")
        target = edge.get("target", "")
        source_file = _file_id_for_node(source, file_ids, symbol_to_file)
        if source_file is None:
            continue
        total_edges_per_file[source_file] += 1
        source_comm = node_to_community.get(source)
        target_comm = node_to_community.get(target)
        if source_comm is None or target_comm is None:
            continue
        if source_comm != target_comm:
            cross_edges_per_file[source_file] += 1

    cross_ratio_per_file: Dict[str, float] = {}
    for file_id in file_ids:
        total = total_edges_per_file.get(file_id, 0)
        cross = cross_edges_per_file.get(file_id, 0)
        cross_ratio_per_file[file_id] = (cross / total) if total else 0.0

    centrality_z = _zscore_series(
        {file_id: centrality_per_file.get(file_id, 0.0) for file_id in file_ids}
    )
    churn_z = _zscore_series(
        {file_id: churn_per_file.get(file_id, 0.0) for file_id in file_ids}
    )
    test_gap_z = _zscore_series(test_gap_per_file)
    cross_z = _zscore_series(cross_ratio_per_file)

    effective_weights = dict(DEFAULT_WEIGHTS)
    if weights:
        effective_weights.update(weights)

    risk_scores: List[FileRiskScore] = []
    for file_id in file_ids:
        cz = centrality_z.get(file_id, 0.0)
        chz = churn_z.get(file_id, 0.0)
        tz = test_gap_z.get(file_id, 0.0)
        ccz = cross_z.get(file_id, 0.0)
        total = (
            effective_weights["centrality"] * cz
            + effective_weights["churn"] * chz
            + effective_weights["test_gap"] * tz
            + effective_weights["cross_community"] * ccz
        )
        risk_scores.append(
            FileRiskScore(
                file_id=file_id,
                file_path=file_path_lookup.get(file_id, file_id),
                total=total,
                centrality_z=cz,
                churn_z=chz,
                test_gap_z=tz,
                cross_community_z=ccz,
                raw_centrality=centrality_per_file.get(file_id, 0.0),
                raw_churn=churn_per_file.get(file_id, 0.0),
                raw_test_gap=test_gap_per_file.get(file_id, 0.0),
                raw_cross_community=cross_ratio_per_file.get(file_id, 0.0),
                symbol_count=len(symbols_per_file.get(file_id, set())),
                tested_symbol_count=len(tested_symbols_per_file.get(file_id, set())),
            )
        )

    risk_scores.sort(key=lambda record: record.total, reverse=True)
    logger.info(
        "risk_scores_done files=%d weights=%s",
        len(risk_scores),
        dict(effective_weights),
    )
    return risk_scores
