"""Optional Neo4j Bolt driver from environment (GraphRAG expansion backend)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def create_neo4j_driver_from_env() -> object | None:
    """Return a Neo4j ``Driver`` when URI and password are set, else ``None``.

    Uses ``GRAPHRAG_NEO4J_URI``, ``GRAPHRAG_NEO4J_USER`` (default ``neo4j``),
    ``GRAPHRAG_NEO4J_PASSWORD``, and optional ``GRAPHRAG_NEO4J_DATABASE``.

    Returns:
        Connected driver, or ``None`` if disabled / misconfigured / unreachable.

    Note:
        Caller owns the driver lifecycle (typically one instance per Flask app).
    """
    uri = os.environ.get("GRAPHRAG_NEO4J_URI", "").strip()
    password = os.environ.get("GRAPHRAG_NEO4J_PASSWORD", "").strip()
    if not uri or not password:
        return None
    user = os.environ.get("GRAPHRAG_NEO4J_USER", "neo4j").strip() or "neo4j"
    try:
        from neo4j import GraphDatabase
    except ImportError:
        logger.warning("neo4j package not installed; GraphRAG Neo4j backend disabled.")
        return None

    try:
        drv = GraphDatabase.driver(uri, auth=(user, password))
        drv.verify_connectivity()
        logger.info("Neo4j driver connected for GraphRAG expansion.")
        return drv
    except Exception as exc:
        logger.warning("Neo4j driver not available (GraphRAG Neo4j disabled): %s", exc)
        return None
