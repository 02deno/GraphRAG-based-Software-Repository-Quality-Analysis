"""Unit tests for GraphRAG retrieval helpers (no LLM)."""

from __future__ import annotations

from src.graphrag.community_seeds import community_member_seeds_from_view
from src.graphrag.context_formatter import format_subgraph_for_llm
from src.graphrag.query_index import rank_seed_node_ids
from src.graphrag.subgraph_retriever import (
    build_multidigraph,
    default_edge_types_for_query,
    expand_seeds_undirected_bfs,
    induced_subgraph_edges,
)


def _tiny_graph() -> tuple[list[dict], list[dict]]:
    nodes = [
        {"id": "f1", "type": "File", "path": "pkg/a.py", "module": "pkg.a", "language": "python"},
        {"id": "fn1", "type": "Function", "name": "foo", "qualified_name": "pkg.a.foo", "file_path": "pkg/a.py"},
        {"id": "f2", "type": "File", "path": "pkg/b.py", "module": "pkg.b", "language": "python"},
    ]
    edges = [
        {"source": "fn1", "target": "f1", "type": "IN_FILE"},
        {"source": "f1", "target": "f2", "type": "IMPORTS"},
    ]
    return nodes, edges


def test_rank_seed_prefers_path_match() -> None:
    nodes, _edges = _tiny_graph()
    ranked = rank_seed_node_ids(nodes, "pkg/b", top_k=5)
    assert ranked
    assert ranked[0][0] == "f2"


def test_expand_seeds_follows_imports() -> None:
    nodes, edges = _tiny_graph()
    g = build_multidigraph(nodes, edges)
    allowed = default_edge_types_for_query("imports between files")
    out = expand_seeds_undirected_bfs(
        g,
        ["fn1"],
        allowed_edge_types=allowed,
        max_depth=3,
        max_nodes=10,
    )
    assert "f1" in out and "f2" in out


def test_format_subgraph_under_budget() -> None:
    nodes, edges = _tiny_graph()
    text = format_subgraph_for_llm(nodes, edges, max_chars=10_000)
    assert "pkg.a.foo" in text or "fn1" in text
    assert "IMPORTS" in text


def test_induced_edges_respects_types() -> None:
    nodes, edges = _tiny_graph()
    g = build_multidigraph(nodes, edges)
    sub = {"fn1", "f1", "f2"}
    rows = induced_subgraph_edges(g, sub, {"IMPORTS", "IN_FILE"})
    assert len(rows) == 2


def test_rank_node_ids_by_cosine_orders_by_similarity() -> None:
    import numpy as np

    from src.graphrag.embedding_seeds import rank_node_ids_by_cosine

    emb = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype=np.float32)
    q = np.array([1.0, 0.0], dtype=np.float32)
    ids = ["a", "b", "c"]
    out = rank_node_ids_by_cosine(emb, q, ids, top_k=2)
    assert out[0] == "a"
    assert len(out) == 2


def test_community_seeds_use_member_ids() -> None:
    view = {
        "community_sections": [
            {
                "edge_type": "IMPORTS",
                "empty": False,
                "communities": [
                    {
                        "rank": 1,
                        "size": 3,
                        "preview": ["pkg/a.py", "pkg/b.py"],
                        "member_ids": ["f_a", "f_b", "fn_x"],
                    }
                ],
            }
        ]
    }
    ids = community_member_seeds_from_view("a.py imports", view, max_communities=2, max_ids_total=10)
    assert "f_a" in ids
