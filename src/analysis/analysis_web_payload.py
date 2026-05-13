"""JSON-serializable view model for rendering analysis in the web UI.

Plain-text reports remain the source for ``analysis.txt`` and CLI output; this
module builds a structured dict consumed by ``results_final.html`` as cards and
tables instead of a single monospace block.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from src.analysis.community_detection import CommunityDetectionResult
from src.analysis.risk_score import FileRiskScore
from src.graph.json_document import human_readable_graph_edge_label

_CENTRALITY_EDGE_TYPES: Tuple[str, ...] = ("IMPORTS", "CALLS")
_COMMUNITY_EDGE_TYPES: Tuple[str, ...] = ("IMPORTS", "CALLS")
_COMMUNITY_MAX_MEMBERS_LISTED = 8


def _rows_from_counter_items(
    items: Sequence[Tuple[str, int]],
    path_by_id: Mapping[str, str],
) -> List[Dict[str, Any]]:
    """Turn ranked (id, score) pairs into table row dicts with 1-based rank."""
    rows: List[Dict[str, Any]] = []
    for rank, (node_id, score) in enumerate(items, start=1):
        rows.append(
            {
                "rank": rank,
                "node_id": node_id,
                "label": path_by_id.get(node_id, node_id),
                "score": int(score),
            }
        )
    return rows


def _rows_from_float_items(
    items: Sequence[Tuple[str, float]],
    path_by_id: Mapping[str, str],
    *,
    precision: int = 4,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rank, (node_id, score) in enumerate(items, start=1):
        rows.append(
            {
                "rank": rank,
                "node_id": node_id,
                "label": path_by_id.get(node_id, node_id),
                "score": round(float(score), precision),
            }
        )
    return rows


def build_analysis_web_view(
    graph_path: Path,
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
    edge_type_counts: Counter,
    imports_in: List[Tuple[str, int]],
    imports_out: List[Tuple[str, int]],
    in_file_in: List[Tuple[str, int]],
    in_file_out: List[Tuple[str, int]],
    calls_in: List[Tuple[str, int]],
    calls_out: List[Tuple[str, int]],
    tests_in: List[Tuple[str, int]],
    tests_out: List[Tuple[str, int]],
    modified_by_in: List[Tuple[str, int]],
    modified_by_out: List[Tuple[str, int]],
    centrality_sections: Mapping[str, Mapping[str, object]],
    community_sections: Mapping[str, CommunityDetectionResult],
    risk_scores: List[FileRiskScore],
    path_by_id: Mapping[str, str],
    top_k_value: int,
) -> Dict[str, Any]:
    """Build the dict stored as ``analysis_view.json`` and passed to Jinja.

    Args:
        graph_path: Source graph path (display only).
        nodes: Graph nodes.
        edges: Graph edges.
        edge_type_counts: Counts per edge type.
        imports_in … modified_by_out: Top-K degree tuples (already truncated).
        centrality_sections: Same structure as ``graph_analysis`` centrality payload.
        community_sections: Louvain results per edge type.
        risk_scores: Sorted file risk records.
        path_by_id: Display labels.
        top_k_value: K used for ranking sections.

    Returns:
        JSON-serializable nested dict for the results template.
    """
    graph_label = human_readable_graph_edge_label(edges)
    degree_specs: List[Tuple[str, str, List[Tuple[str, int]]]] = [
        ("imports_in", f"Incoming IMPORTS (top {top_k_value})", imports_in),
        ("imports_out", f"Outgoing IMPORTS (top {top_k_value})", imports_out),
        ("in_file_in", f"Incoming IN_FILE (top {top_k_value})", in_file_in),
        ("in_file_out", f"Outgoing IN_FILE (top {top_k_value})", in_file_out),
        ("calls_in", f"Incoming CALLS (top {top_k_value})", calls_in),
        ("calls_out", f"Outgoing CALLS (top {top_k_value})", calls_out),
        ("tests_in", f"Incoming TESTS (top {top_k_value})", tests_in),
        ("tests_out", f"Outgoing TESTS (top {top_k_value})", tests_out),
        (
            "modified_by_in",
            f"Commits by file touch count (MODIFIED_BY in, top {top_k_value})",
            modified_by_in,
        ),
        (
            "modified_by_out",
            f"Files by commit churn (MODIFIED_BY out, top {top_k_value})",
            modified_by_out,
        ),
    ]

    degree_sections: List[Dict[str, Any]] = []
    for section_id, title, items in degree_specs:
        degree_sections.append(
            {
                "id": section_id,
                "title": title,
                "rows": _rows_from_counter_items(items, path_by_id),
                "empty": len(items) == 0,
            }
        )

    centrality_blocks: List[Dict[str, Any]] = []
    for edge_type in _CENTRALITY_EDGE_TYPES:
        section = centrality_sections.get(edge_type) or {}
        betweenness_raw = section.get("betweenness_top_k") or []
        pagerank_raw = section.get("pagerank_top_k") or []
        approximated = bool(section.get("betweenness_approximated"))
        centrality_blocks.append(
            {
                "edge_type": edge_type,
                "betweenness_approximated": approximated,
                "betweenness_title": (
                    f"Betweenness on {edge_type}"
                    + (" (sampled)" if approximated else "")
                ),
                "betweenness_rows": _rows_from_float_items(
                    list(betweenness_raw), path_by_id
                ),
                "betweenness_empty": len(betweenness_raw) == 0,
                "pagerank_title": f"PageRank on {edge_type}",
                "pagerank_rows": _rows_from_float_items(list(pagerank_raw), path_by_id),
                "pagerank_empty": len(pagerank_raw) == 0,
            }
        )

    community_blocks: List[Dict[str, Any]] = []
    for edge_type in _COMMUNITY_EDGE_TYPES:
        result = community_sections.get(edge_type)
        if result is None:
            community_blocks.append(
                {
                    "edge_type": edge_type,
                    "empty": True,
                    "summary": None,
                    "communities": [],
                }
            )
            continue
        modularity = result.modularity_score
        empty = modularity is None or not result.communities
        comm_rows: List[Dict[str, Any]] = []
        if not empty:
            for idx, members in enumerate(result.communities[:top_k_value], start=1):
                mlist = list(members)
                size = len(mlist)
                preview_count = min(_COMMUNITY_MAX_MEMBERS_LISTED, size)
                preview = [
                    path_by_id.get(nid, nid) for nid in mlist[:preview_count]
                ]
                comm_rows.append(
                    {
                        "rank": idx,
                        "size": size,
                        "preview": preview,
                        "remaining": max(0, size - preview_count),
                        "member_ids": mlist[:preview_count],
                    }
                )
        community_blocks.append(
            {
                "edge_type": edge_type,
                "empty": empty,
                "summary": None
                if empty
                else {
                    "algorithm": result.algorithm,
                    "node_count": result.node_count,
                    "edge_count": result.edge_count,
                    "community_count": len(result.communities),
                    "modularity": round(float(modularity), 4)
                    if modularity is not None
                    else None,
                },
                "communities": comm_rows,
            }
        )

    risk_rows: List[Dict[str, Any]] = []
    for idx, record in enumerate(risk_scores[:top_k_value], start=1):
        risk_rows.append(
            {
                "rank": idx,
                "file_path": record.file_path,
                "total": round(record.total, 3),
                "centrality_z": round(record.centrality_z, 3),
                "churn_z": round(record.churn_z, 3),
                "test_gap_z": round(record.test_gap_z, 3),
                "cross_community_z": round(record.cross_community_z, 3),
                "raw_churn": int(record.raw_churn),
                "raw_test_gap": round(record.raw_test_gap, 2),
                "raw_cross_community": round(record.raw_cross_community, 2),
                "symbol_count": record.symbol_count,
                "tested_symbol_count": record.tested_symbol_count,
            }
        )

    edge_count_items = [
        {"type": str(t), "count": int(c)}
        for t, c in sorted(edge_type_counts.items())
    ]

    return {
        "schema_version": 1,
        "graph_path": str(graph_path),
        "graph_label": graph_label,
        "top_k": top_k_value,
        "totals": {"nodes": len(nodes), "edges": len(edges)},
        "edge_counts": edge_count_items,
        "degree_sections": degree_sections,
        "centrality_sections": centrality_blocks,
        "community_sections": community_blocks,
        "risk": {
            "empty": len(risk_rows) == 0,
            "weights_note": (
                "Equal weights (1.0) on centrality, churn, test_gap, cross_community; "
                "z-scores use sample std across File nodes."
            ),
            "candidates": risk_rows,
        },
    }
