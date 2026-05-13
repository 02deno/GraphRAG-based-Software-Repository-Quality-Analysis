"""Sync a run's ``graph.json`` into Neo4j and expand seeds by typed hops."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

logger = logging.getLogger(__name__)

_META_FILE = "graphrag_neo4j_sync_meta.json"


def _node_props(node: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten node attributes to Neo4j property map (primitives only)."""
    out: Dict[str, Any] = {"id": str(node.get("id", ""))}
    for key in ("type", "name", "qualified_name", "path", "file_path", "module", "language"):
        val = node.get(key)
        if val is not None and val != "":
            s = str(val)
            if len(s) > 4000:
                s = s[:3997] + "…"
            out[key] = s
    return out


class Neo4jSubgraphExpander:
    """Write ``GraphRAGNode`` / ``GRAPHRAG_EDGE`` rows per analysis run and BFS-expand."""

    def __init__(self, driver: Any) -> None:
        """Store an open Neo4j driver.

        Args:
            driver: ``neo4j.Driver`` instance from :func:`create_neo4j_driver_from_env`.
        """
        self._driver = driver

    def ensure_synced(
        self,
        run_id: str,
        nodes: Sequence[Dict[str, Any]],
        edges: Sequence[Dict[str, Any]],
        *,
        graph_path: Path,
    ) -> bool:
        """Load *nodes* and *edges* into Neo4j for *run_id* if cache is stale.

        Args:
            run_id: Stable run key (e.g. ``web_analysis_*`` folder name).
            nodes: Graph nodes from ``graph.json``.
            edges: Graph edges from ``graph.json``.
            graph_path: Path to ``graph.json`` (mtime used for invalidation).

        Returns:
            True if sync ran (or was already fresh), False on failure.
        """
        try:
            mtime_ns = graph_path.stat().st_mtime_ns
        except OSError as exc:
            logger.warning("Neo4j sync skipped (stat graph.json failed): %s", exc)
            return False
        meta_path = graph_path.parent / _META_FILE
        meta: Dict[str, Any] = {}
        if meta_path.is_file():
            try:
                loaded = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    meta = loaded
            except (OSError, json.JSONDecodeError):
                meta = {}
        if (
            meta.get("run_id") == run_id
            and meta.get("mtime_ns") == mtime_ns
            and meta.get("node_count") == len(nodes)
            and meta.get("edge_count") == len(edges)
        ):
            return True

        try:
            self._write_graph(run_id, list(nodes), list(edges))
        except Exception:
            logger.exception("Neo4j sync failed run_id=%s", run_id)
            return False

        try:
            meta_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "mtime_ns": mtime_ns,
                        "node_count": len(nodes),
                        "edge_count": len(edges),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Could not write Neo4j sync meta: %s", exc)
        return True

    def _write_graph(self, run_id: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
        """Replace graph data for *run_id* in Neo4j."""
        dbname = os.environ.get("GRAPHRAG_NEO4J_DATABASE", "").strip() or None

        def delete_tx(tx: Any) -> None:
            tx.run(
                "MATCH (n:GraphRAGNode {run: $run}) DETACH DELETE n",
                run=run_id,
            )

        def write_nodes_tx(tx: Any, batch: List[Dict[str, Any]]) -> None:
            tx.run(
                """
                UNWIND $rows AS row
                MERGE (n:GraphRAGNode {run: $run, id: row.id})
                SET n += row.props
                """,
                run=run_id,
                rows=batch,
            )

        def write_edges_tx(tx: Any, batch: List[Dict[str, Any]]) -> None:
            tx.run(
                """
                UNWIND $rows AS row
                MATCH (a:GraphRAGNode {run: $run, id: row.source})
                MATCH (b:GraphRAGNode {run: $run, id: row.target})
                MERGE (a)-[e:GRAPHRAG_EDGE {run: $run, t: row.t}]->(b)
                """,
                run=run_id,
                rows=batch,
            )

        with self._driver.session(database=dbname) as session:
            session.execute_write(delete_tx)
            chunk = 400
            for i in range(0, len(nodes), chunk):
                batch = []
                for n in nodes[i : i + chunk]:
                    nid = str(n.get("id", ""))
                    if not nid:
                        continue
                    batch.append({"id": nid, "props": _node_props(n)})
                if batch:
                    session.execute_write(write_nodes_tx, batch)
            edge_rows: List[Dict[str, str]] = []
            for e in edges:
                src = str(e.get("source", ""))
                tgt = str(e.get("target", ""))
                et = str(e.get("type", "UNKNOWN"))
                if src and tgt:
                    edge_rows.append({"source": src, "target": tgt, "t": et})
            for i in range(0, len(edge_rows), chunk):
                batch = edge_rows[i : i + chunk]
                if batch:
                    session.execute_write(write_edges_tx, batch)
        logger.info(
            "Neo4j graph synced run_id=%s nodes=%d edges=%d",
            run_id,
            len(nodes),
            len(edge_rows),
        )

    def expand(
        self,
        run_id: str,
        seeds: Iterable[str],
        allowed_edge_types: Set[str],
        *,
        max_depth: int,
        max_nodes: int,
    ) -> Set[str]:
        """Undirected multi-hop expansion over ``GRAPHRAG_EDGE`` with ``t`` in *allowed*.

        Args:
            run_id: Same key passed to :meth:`ensure_synced`.
            seeds: Starting node ids.
            allowed_edge_types: Edge type strings to traverse.
            max_depth: Number of BFS layers.
            max_nodes: Cap on distinct node ids returned (including seeds).

        Returns:
            Node id set (may be smaller than *max_nodes* if frontier exhausts).
        """
        dbname = os.environ.get("GRAPHRAG_NEO4J_DATABASE", "").strip() or None
        allowed = sorted(allowed_edge_types)
        frontier = {s for s in seeds if s}
        collected: Set[str] = set(frontier)
        if not frontier:
            return collected

        cypher = """
        MATCH (s:GraphRAGNode {run: $run})
        WHERE s.id IN $ids
        MATCH (s)-[e:GRAPHRAG_EDGE]-(t:GraphRAGNode {run: $run})
        WHERE e.run = $run AND e.t IN $types
        RETURN DISTINCT t.id AS id
        """

        with self._driver.session(database=dbname) as session:
            for _ in range(max_depth):
                if len(collected) >= max_nodes:
                    break
                rec = session.run(
                    cypher,
                    run=run_id,
                    ids=list(frontier),
                    types=allowed,
                )
                nxt: Set[str] = set()
                for row in rec:
                    nid = row.get("id")
                    if nid and nid not in collected:
                        nxt.add(str(nid))
                if not nxt:
                    break
                for nid in nxt:
                    collected.add(nid)
                    if len(collected) >= max_nodes:
                        break
                frontier = nxt
        return collected
