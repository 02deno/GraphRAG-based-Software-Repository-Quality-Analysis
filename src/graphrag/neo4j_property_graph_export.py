"""Export a bounded Neo4j ``GraphRAGNode`` / ``GRAPHRAG_EDGE`` view for web visualization."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Mapping, MutableMapping

logger = logging.getLogger(__name__)


def _label_for_row(
    nid: str,
    ntype: Any,
    name: Any,
    path: Any,
    qualified: Any,
) -> str:
    """Build a short UI label from common GraphRAG node properties."""
    for candidate in (name, qualified, path):
        if candidate is not None:
            s = str(candidate).strip()
            if s:
                return s if len(s) <= 80 else s[:77] + "…"
    s = str(ntype or "node").strip() or "node"
    tail = nid[-36:] if len(nid) > 40 else nid
    return f"{s}:{tail}"


def _row_to_node(row: Mapping[str, Any], prefix: str) -> Tuple[str, Dict[str, Any]]:
    """Map one endpoint column group to ``(id, node_dict)``."""
    if prefix == "s":
        nid = str(row.get("sid") or "").strip()
        ntype = row.get("st")
        name = row.get("sname")
        path = row.get("spath")
        qual = row.get("sq")
    else:
        nid = str(row.get("tid") or "").strip()
        ntype = row.get("mt")
        name = row.get("mname")
        path = row.get("mpath")
        qual = row.get("mq")
    if not nid:
        return "", {}
    label = _label_for_row(nid, ntype, name, path, qual)
    return nid, {
        "id": nid,
        "label": label,
        "node_type": str(ntype or "Unknown"),
    }


def export_graphrag_run_for_visualization(
    driver: Any,
    run_id: str,
    *,
    max_edges: int = 500,
    max_nodes: int = 400,
) -> Dict[str, Any]:
    """Read directed ``GRAPHRAG_EDGE`` rows for one ``run`` and cap for browser layout.

    Args:
        driver: Open Neo4j ``Driver``.
        run_id: Same ``run`` property as sync (typically ``web_analysis_*`` folder name).
        max_edges: Upper bound on relationships returned from the server.
        max_nodes: After edge fetch, keep at most this many nodes by incident-edge degree.

    Returns:
        JSON-serializable dict with ``schema_version``, ``run_id``, ``nodes``, ``edges``,
        and ``truncation`` metadata (counts, caps).

    Raises:
        Exception: Propagates Bolt/driver errors to the HTTP layer.
    """
    lim = max(1, min(int(max_edges), 2000))
    cap_nodes = max(20, min(int(max_nodes), 800))
    dbname = os.environ.get("GRAPHRAG_NEO4J_DATABASE", "").strip() or None

    cypher = """
    MATCH (n:GraphRAGNode {run: $run})-[e:GRAPHRAG_EDGE {run: $run}]->(m:GraphRAGNode {run: $run})
    RETURN n.id AS sid, n.type AS st, n.name AS sname, n.path AS spath, n.qualified_name AS sq,
           m.id AS tid, m.type AS mt, m.name AS mname, m.path AS mpath, m.qualified_name AS mq,
           e.t AS etype
    LIMIT $lim
    """

    rows: List[Mapping[str, Any]] = []
    with driver.session(database=dbname) as session:
        result = session.run(cypher, run=run_id, lim=lim)
        rows = [dict(r) for r in result]

    raw_edges: List[Dict[str, Any]] = []
    node_accum: Dict[str, Dict[str, Any]] = {}
    deg: MutableMapping[str, int] = defaultdict(int)

    for row in rows:
        sid, sn = _row_to_node(row, "s")
        tid, tn = _row_to_node(row, "t")
        et = str(row.get("etype") or "UNKNOWN").strip()
        if not sid or not tid:
            continue
        if sn:
            node_accum[sid] = sn
        if tn:
            node_accum[tid] = tn
        deg[sid] += 1
        deg[tid] += 1
        raw_edges.append({"from": sid, "to": tid, "type": et})

    if len(node_accum) > cap_nodes:
        ranked = sorted(node_accum.keys(), key=lambda x: deg.get(x, 0), reverse=True)
        keep = set(ranked[:cap_nodes])
        raw_edges = [e for e in raw_edges if e["from"] in keep and e["to"] in keep]
        node_accum = {k: v for k, v in node_accum.items() if k in keep}

    vis_edges: List[Dict[str, str]] = []
    for i, e in enumerate(raw_edges):
        vis_edges.append(
            {
                "id": f"e{i}_{e['from']}_{e['type']}_{e['to']}",
                "from": e["from"],
                "to": e["to"],
                "label": e["type"],
                "edge_type": e["type"],
            }
        )

    vis_nodes = list(node_accum.values())
    return {
        "schema_version": 1,
        "run_id": run_id,
        "nodes": vis_nodes,
        "edges": vis_edges,
        "truncation": {
            "edge_limit_requested": lim,
            "edges_returned": len(vis_edges),
            "node_cap": cap_nodes,
            "nodes_shown": len(vis_nodes),
        },
    }
