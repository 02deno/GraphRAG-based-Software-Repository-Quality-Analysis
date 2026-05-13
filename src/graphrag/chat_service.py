"""Orchestrate subgraph retrieval and LLM answering for one analysis run."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping

from src.graph.json_document import load_graph_document
from src.graphrag.analysis_context import format_analysis_view_summary
from src.graphrag.community_seeds import community_member_seeds_from_view
from src.graphrag.context_formatter import format_subgraph_for_llm
from src.graphrag.query_index import rank_seed_node_ids
from src.graphrag.subgraph_retriever import (
    build_multidigraph,
    default_edge_types_for_query,
    expand_seeds_undirected_bfs,
    induced_subgraph_edges,
)
from src.web.service_protocols import ChatCompletionClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert assistant for software quality, testing, and architecture. "
    "You answer using ONLY the supplied graph subgraph and precomputed metrics. "
    "If the evidence is insufficient, say so briefly. "
    "When you mention entities, prefer human-readable labels from the context. "
    "Respond in the same language as the user's question when possible."
)


class GraphRagChatService:
    """Run lexical + community seeding, graph expansion, and one LLM completion."""

    def __init__(self, llm: ChatCompletionClient | None) -> None:
        """Attach an optional LLM client (``None`` disables chat until configured)."""
        self._llm = llm

    def answer(
        self,
        run_dir_path: Path,
        user_message: str,
        *,
        max_depth: int = 2,
        max_nodes: int = 220,
        top_seeds: int = 14,
        max_subgraph_chars: int = 22_000,
        max_metrics_chars: int = 5_000,
    ) -> Dict[str, Any]:
        """Retrieve a subgraph for *user_message* and return an LLM reply.

        Args:
            run_dir_path: Resolved ``results/web_analysis_*`` directory.
            user_message: Natural language question.
            max_depth: BFS depth from combined seeds.
            max_nodes: Maximum nodes in the induced subgraph.
            top_seeds: How many lexical seed nodes to take from :func:`rank_seed_node_ids`.
            max_subgraph_chars: Character budget for serialized subgraph text.
            max_metrics_chars: Character budget for ``analysis_view`` summary text.

        Returns:
            Dict with ``ok`` (bool), optional ``reply``, and diagnostics keys.
        """
        if self._llm is None:
            return {
                "ok": False,
                "error": (
                    "GraphRAG chat is not configured. Set GRAPHRAG_OPENAI_BASE_URL, "
                    "GRAPHRAG_CHAT_MODEL, and (for hosted APIs) GRAPHRAG_OPENAI_API_KEY. "
                    "For Ollama use e.g. http://127.0.0.1:11434/v1 as the base URL."
                ),
            }
        msg = (user_message or "").strip()
        if not msg:
            return {"ok": False, "error": "Empty message."}

        graph_path = run_dir_path / "graph.json"
        if not graph_path.is_file():
            return {"ok": False, "error": "graph.json not found for this run."}

        doc = load_graph_document(graph_path)
        nodes: List[Dict[str, Any]] = list(doc.get("nodes") or [])
        edges: List[Dict[str, Any]] = list(doc.get("edges") or [])

        analysis_view: Dict[str, Any] = {}
        view_path = run_dir_path / "analysis_view.json"
        if view_path.is_file():
            try:
                loaded = json.loads(view_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    analysis_view = loaded
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("GraphRAG: could not read analysis_view.json: %s", exc)

        ranked = rank_seed_node_ids(nodes, msg, top_k=top_seeds)
        lexical_seeds = [nid for nid, _s in ranked]
        comm_seeds = community_member_seeds_from_view(msg, analysis_view)
        seed_order: List[str] = []
        seen_seed: set[str] = set()
        for nid in lexical_seeds + comm_seeds:
            if nid and nid not in seen_seed:
                seen_seed.add(nid)
                seed_order.append(nid)

        g = build_multidigraph(nodes, edges)
        allowed = default_edge_types_for_query(msg)
        seeds_in_graph = [s for s in seed_order if s in g]
        if not seeds_in_graph:
            return {"ok": False, "error": "No seed nodes could be mapped onto the graph."}

        subgraph_ids = expand_seeds_undirected_bfs(
            g,
            seeds_in_graph,
            allowed_edge_types=allowed,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
        sub_edges = induced_subgraph_edges(g, subgraph_ids, allowed)
        node_subset = [n for n in nodes if str(n.get("id", "")) in subgraph_ids]
        subgraph_text = format_subgraph_for_llm(
            node_subset,
            sub_edges,
            max_chars=max_subgraph_chars,
        )
        metrics_text = format_analysis_view_summary(analysis_view, max_chars=max_metrics_chars)
        user_block = (
            f"### User question\n{msg}\n\n"
            f"### Precomputed metrics (may be partial)\n{metrics_text}\n\n"
            f"### Retrieved subgraph\n{subgraph_text}"
        )
        messages: List[Mapping[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_block},
        ]
        try:
            reply = self._llm.complete_chat(messages, temperature=0.2)
        except Exception as exc:
            logger.exception("GraphRAG LLM call failed")
            return {"ok": False, "error": f"LLM request failed: {exc!s}"}

        return {
            "ok": True,
            "reply": reply,
            "seed_nodes": seeds_in_graph[:top_seeds],
            "lexical_seeds": lexical_seeds,
            "community_seeds": comm_seeds,
            "allowed_edge_types": sorted(allowed),
            "subgraph_node_count": len(subgraph_ids),
            "subgraph_edge_count": len(sub_edges),
            "max_depth": max_depth,
            "max_nodes": max_nodes,
        }
