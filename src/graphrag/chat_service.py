"""Orchestrate subgraph retrieval and LLM answering for one analysis run."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Mapping

from src.graph.json_document import load_graph_document
from src.graphrag.analysis_context import format_analysis_view_summary
from src.graphrag.community_seeds import community_member_seeds_from_view
from src.graphrag.context_formatter import format_subgraph_for_llm
from src.graphrag.embedding_seeds import try_embedding_seed_ids
from src.graphrag.neo4j_subgraph import Neo4jSubgraphExpander
from src.graphrag.query_index import rank_seed_node_ids
from src.graphrag.source_context import load_run_meta, retrieve_source_context_for_llm
from src.graphrag.subgraph_retriever import (
    build_multidigraph,
    default_edge_types_for_query,
    expand_seeds_undirected_bfs,
    induced_subgraph_edges,
)
from src.web.service_protocols import ChatCompletionClient

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = (
    "You compress a software-repository Q&A thread into a compact handoff note. "
    "Output 8–14 bullet points in the same language as the thread when possible. "
    "Keep facts, file/module names, and conclusions; drop pleasantries. "
    "Do not exceed 3500 characters."
)

_SYSTEM_PROMPT = (
    "You are an expert assistant for software quality, testing, and architecture for "
    "**this** analyzed repository run. You answer **directly**—start with what the user "
    "asked for (facts, lists, trade-offs), using the graph subgraph, precomputed metrics, "
    "and indexed source excerpts as evidence. "
    "If the evidence is insufficient, say so briefly and name what is missing.\n\n"
    "**Voice (critical):** Write like an engineer on the team, not like a school essay "
    "about a 'passage'. Do **not** open with or lean on meta-phrases such as "
    "\"The provided text\", \"The following excerpt\", \"Based on the context supplied\", "
    "\"It appears that the text is\", or \"The output is divided into sections\". "
    "Do not narrate that you were 'given' material—just use it. When citing, name the "
    "artifact (e.g. precomputed metrics, `path:lines`, graph node label) instead.\n\n"
    "When the user asks about **graph analysis results** (centrality, degree, betweenness, "
    "PageRank, communities, Louvain/modularity, risk candidates, composite scores), "
    "anchor on the **Precomputed metrics** block and any excerpts under `_analysis/` "
    "(pipeline analysis for this run). Do not substitute a generic description of some "
    "other codebase.\n\n"
    "**Artifact paths:** Strings like ``results/web_analysis_*``, ``graph.json``, or "
    "virtual ``_analysis/…`` are **this run's outputs**, not the product's name. A Windows "
    "path may contain a parent folder (e.g. a checkout used to host the web app); do not "
    "rename the user's analyzed project after that folder unless the user asks about the tool itself.\n\n"
    "When **Source excerpts** appear, use them for implementation detail; cite paths and "
    "line ranges when possible. Prefer human-readable graph labels from the evidence.\n\n"
    "Respond in the same language as the user's question when possible.\n\n"
    "Format answers in **Markdown**: `##` / `###` headings (with a space after the hashes and "
    "after section numbers, e.g. `## 1. Title`), bullets where helpful, short fenced code only "
    "when quoting from the evidence. Avoid huge dumps.\n\n"
    "For **tables** (GFM): put a blank line before the table; use a proper `| --- |` separator row; "
    "keep **each entire table row on one physical line** (no line breaks inside a row—especially "
    "not inside cells with bullets or long prose). Use tabs only for alignment in a plain-text "
    "editor, not as a substitute for pipe columns. Open fenced code blocks on their own line "
    "(e.g. ```text then newline before the body).\n\n"
    "Be **substantive** on non-trivial questions: several paragraphs or clear sections "
    "unless the user explicitly wants brevity."
)

_CARRYOVER_USER_PREFIX = (
    "The following is a short summary from a prior chat session for continuity only; "
    "answer the next user message using the graph context attached to that message.\n\n"
)


def _retrieval_query_blend(
    user_message: str,
    conversation_history: Sequence[Mapping[str, Any]] | None,
    *,
    short_len: int = 42,
    max_len: int = 2800,
) -> str:
    """Blend the latest prior user turn into short follow-ups for retrieval only.

    Improves lexical seeds, embedding seeds, edge-type selection, and source excerpt
    ranking when the current message is brief (e.g. \"What about degree centrality?\")
    while leaving the visible ``### User question`` text as the actual latest message.

    Args:
        user_message: Current user message (trimmed internally).
        conversation_history: Prior ``user`` / ``assistant`` turns (current message excluded).
        short_len: When the current message is shorter than this, try blending.
        max_len: Cap on the blended query string.

    Returns:
        A string used only for retrieval scoring, never shown as the user's question line.
    """
    msg = (user_message or "").strip()
    if len(msg) >= short_len:
        return msg
    prev_user = ""
    for m in conversation_history or []:
        if not isinstance(m, Mapping):
            continue
        if str(m.get("role", "")).strip().lower() != "user":
            continue
        c = str(m.get("content", "") or "").strip()
        if c:
            prev_user = c
    if not prev_user or prev_user == msg:
        return msg
    blended = f"{prev_user}\n\nFollow-up: {msg}".strip()
    if len(blended) > max_len:
        return blended[: max(0, max_len - 3)] + "..."
    return blended


def _format_analyzed_repo_subject(run_dir_path: Path) -> str:
    """Clarify which codebase is the chat subject (vs host paths and pipeline artifacts).

    ``visual_summary_view`` / ``_analysis/*`` chunks often embed absolute paths that include
    a parent checkout (e.g. ``GraphRAG_Project``); without this hint models may describe the
    tooling host instead of the analyzed repository.

    Returns:
        Markdown lines ending with a blank line so callers can concatenate safely.
    """
    meta = load_run_meta(run_dir_path)
    root_s = meta.get("source_repo_root")
    lines: list[str] = ["### Analyzed repository (subject of this chat)", ""]
    if isinstance(root_s, str) and root_s.strip():
        root = root_s.strip()
        label = Path(root).name or root
        lines.append(
            f"- The uploaded/cloned project analyzed by this run lives under **`{root}`** "
            f"(short label: **{label}**). Explain *that* codebase using ``File`` nodes and "
            "indexed ``*.py`` / README excerpts (paths relative to that root)."
        )
    else:
        lines.append(
            "- ``graphrag_run_meta.json`` did not record ``source_repo_root``; infer the product "
            "from graph ``File`` paths and indexed excerpts, not from ``results/web_analysis_*`` "
            "folder names."
        )
    lines.append(
        "- Paths under ``results/web_analysis_*`` and virtual ``_analysis/*`` are **saved "
        "pipeline outputs** (metrics, summaries). They are not alternate product names; a "
        "segment like ``GraphRAG_Project`` may only mark where the web app ran the analysis."
    )
    lines.append("")
    return "\n".join(lines)


def _approx_chars_for_messages(msgs: Sequence[Mapping[str, str]]) -> int:
    total = 0
    for m in msgs:
        total += len(str(m.get("content") or ""))
    return total


def _context_warn_level(approx_chars: int) -> str:
    """Return ``none``, ``approaching``, or ``critical`` from env thresholds."""
    try:
        warn_at = int(os.getenv("GRAPHRAG_CHAT_WARN_INPUT_CHARS", "24000").strip() or "24000")
    except ValueError:
        warn_at = 24000
    try:
        crit_at = int(os.getenv("GRAPHRAG_CHAT_CRITICAL_INPUT_CHARS", "36000").strip() or "36000")
    except ValueError:
        crit_at = 36000
    if approx_chars >= crit_at:
        return "critical"
    if approx_chars >= warn_at:
        return "approaching"
    return "none"


def _context_auto_fork_chars() -> int:
    """Char threshold for optional UI auto fork; ``0`` disables."""
    raw = (os.getenv("GRAPHRAG_CHAT_AUTO_SUMMARY_AT_CHARS", "0") or "").strip()
    if not raw or raw == "0":
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _chat_temperature() -> float:
    """Sampling temperature for the main repository Q&A call."""
    raw = (os.getenv("GRAPHRAG_CHAT_TEMPERATURE", "0.28") or "").strip()
    try:
        t = float(raw)
    except ValueError:
        t = 0.28
    return max(0.0, min(1.5, t))


class GraphRagChatService:
    """Run lexical + community + optional embedding seeds, then expand and call the LLM."""

    def __init__(
        self,
        llm: ChatCompletionClient | None,
        *,
        neo4j_driver: object | None = None,
    ) -> None:
        """Attach an optional LLM client and optional Neo4j driver for expansion.

        Args:
            llm: Chat completion client; ``None`` disables chat until configured.
            neo4j_driver: Neo4j ``Driver`` from :func:`create_neo4j_driver_from_env`, or
                ``None`` to expand in-process with NetworkX (default).
        """
        self._llm = llm
        self._neo4j = neo4j_driver

    def _retrieve_context(
        self,
        run_dir_path: Path,
        user_message: str,
        *,
        retrieval_query: str | None = None,
        max_depth: int = 2,
        max_nodes: int = 220,
        top_seeds: int = 14,
        max_subgraph_chars: int = 18_000,
        max_metrics_chars: int = 4_500,
        max_source_chars: int = 11_000,
        progress_hook: Callable[[str, str | None], None] | None = None,
    ) -> Dict[str, Any]:
        """Build the RAG user block and diagnostics for *user_message* (no LLM call).

        Optional *progress_hook* receives ``(stage_id, human_message)`` for long phases
        (embeddings, Neo4j sync, etc.) so HTTP layers can stream status to the client.

        Args:
            retrieval_query: When set, used for lexical/embedding/source ranking instead of
                *user_message* (e.g. blended with a prior user turn for short follow-ups).
        """
        msg = (user_message or "").strip()
        if not msg:
            return {"ok": False, "error": "Empty message."}

        q_rank = (retrieval_query or "").strip() or msg
        graph_path = run_dir_path / "graph.json"
        if not graph_path.is_file():
            return {"ok": False, "error": "graph.json not found for this run."}

        doc = load_graph_document(graph_path)
        nodes: List[Dict[str, Any]] = list(doc.get("nodes") or [])
        edges: List[Dict[str, Any]] = list(doc.get("edges") or [])

        if progress_hook:
            progress_hook(
                "loading_graph",
                f"Loaded graph ({len(nodes)} nodes, {len(edges)} edges).",
            )

        analysis_view: Dict[str, Any] = {}
        view_path = run_dir_path / "analysis_view.json"
        if view_path.is_file():
            try:
                loaded = json.loads(view_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    analysis_view = loaded
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("GraphRAG: could not read analysis_view.json: %s", exc)

        if progress_hook:
            progress_hook("lexical_seeds", "Ranking lexical seeds and scanning communities…")

        ranked = rank_seed_node_ids(nodes, q_rank, top_k=top_seeds)
        lexical_seeds = [nid for nid, _s in ranked]
        comm_seeds = community_member_seeds_from_view(q_rank, analysis_view)
        if progress_hook:
            progress_hook(
                "embedding_seeds",
                "Dense embedding seeds (batched API; first run may build a cache)…",
            )
        embed_cb = (lambda detail: progress_hook("embedding_seeds", detail)) if progress_hook else None
        embed_seeds, embed_diag = try_embedding_seed_ids(
            run_dir_path,
            nodes,
            q_rank,
            top_k=min(12, top_seeds),
            progress=embed_cb,
        )
        seed_order: List[str] = []
        seen_seed: set[str] = set()
        for nid in lexical_seeds + comm_seeds + embed_seeds:
            if nid and nid not in seen_seed:
                seen_seed.add(nid)
                seed_order.append(nid)

        if progress_hook:
            progress_hook("graph_index", "Building in-memory graph index for expansion…")

        g = build_multidigraph(nodes, edges)
        allowed = default_edge_types_for_query(q_rank)
        seeds_in_graph = [s for s in seed_order if s in g]
        if not seeds_in_graph:
            return {"ok": False, "error": "No seed nodes could be mapped onto the graph."}

        retrieval_backend = "networkx"
        subgraph_ids: set[str]
        if self._neo4j is not None:
            expander = Neo4jSubgraphExpander(self._neo4j)
            synced = expander.ensure_synced(
                run_dir_path.name,
                nodes,
                edges,
                graph_path=graph_path,
            )
            if synced:
                subgraph_ids = expander.expand(
                    run_dir_path.name,
                    seeds_in_graph,
                    allowed,
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                )
                retrieval_backend = "neo4j"
            else:
                logger.warning("Neo4j sync failed; falling back to NetworkX expansion.")
                subgraph_ids = expand_seeds_undirected_bfs(
                    g,
                    seeds_in_graph,
                    allowed_edge_types=allowed,
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                )
        else:
            subgraph_ids = expand_seeds_undirected_bfs(
                g,
                seeds_in_graph,
                allowed_edge_types=allowed,
                max_depth=max_depth,
                max_nodes=max_nodes,
            )

        sub_edges = induced_subgraph_edges(g, subgraph_ids, allowed)
        if progress_hook:
            progress_hook(
                "subgraph_expand",
                f"Subgraph: {len(subgraph_ids)} nodes, {len(sub_edges)} edges ({retrieval_backend}).",
            )
        if progress_hook:
            progress_hook("format_context", "Formatting metrics, subgraph text, and source excerpts…")

        node_subset = [n for n in nodes if str(n.get("id", "")) in subgraph_ids]
        subgraph_text = format_subgraph_for_llm(
            node_subset,
            sub_edges,
            max_chars=max_subgraph_chars,
        )
        metrics_text = format_analysis_view_summary(analysis_view, max_chars=max_metrics_chars)
        source_block, source_diag = retrieve_source_context_for_llm(
            run_dir_path,
            q_rank,
            max_chars=max_source_chars,
        )
        subject = _format_analyzed_repo_subject(run_dir_path)
        user_block = (
            subject
            + "Evidence below is for this run only (metrics + graph slice + optional file/analysis "
            "excerpts). Answer the question directly; do not describe 'provided text' as an object.\n\n"
            f"### User question\n{msg}\n\n"
            f"### Precomputed metrics (may be partial)\n{metrics_text}\n\n"
            f"### Retrieved subgraph\n{subgraph_text}"
        )
        if source_block.strip():
            user_block += (
                "\n\n### Source excerpts (indexed repository / docs / `_analysis/` reports)\n"
                + source_block
            )

        if progress_hook:
            progress_hook(
                "context_ready",
                f"Context assembled (~{len(user_block)} chars in the user message block).",
            )

        return {
            "ok": True,
            "user_block": user_block,
            "seed_nodes": seeds_in_graph[:top_seeds],
            "lexical_seeds": lexical_seeds,
            "community_seeds": comm_seeds,
            "embedding_seeds": embed_seeds,
            "embedding_diagnostics": embed_diag,
            "retrieval_backend": retrieval_backend,
            "allowed_edge_types": sorted(allowed),
            "subgraph_node_count": len(subgraph_ids),
            "subgraph_edge_count": len(sub_edges),
            "max_depth": max_depth,
            "max_nodes": max_nodes,
            "source_context_diagnostics": source_diag,
        }

    def summarize_thread_for_carryover(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Ask the LLM for a compact bullet summary to seed a new session.

        Args:
            messages: Prior ``user`` / ``assistant`` turns (plain text only).

        Returns:
            ``ok``, ``summary`` on success, or ``error`` on failure.
        """
        if self._llm is None:
            return {
                "ok": False,
                "error": (
                    "GraphRAG chat is not configured. Set GRAPHRAG_OPENAI_BASE_URL and "
                    "GRAPHRAG_CHAT_MODEL (and API key when required)."
                ),
            }
        chunks: List[str] = []
        for m in messages:
            if not isinstance(m, Mapping):
                continue
            role = str(m.get("role", "")).strip().lower()
            content = str(m.get("content", "")).strip()
            if role not in ("user", "assistant") or not content:
                continue
            chunks.append(f"{role.upper()}:\n{content[:12000]}")
        transcript = "\n\n---\n\n".join(chunks)
        if not transcript.strip():
            return {"ok": False, "error": "No messages to summarize."}
        transcript = transcript[-52000:]
        llm_messages: List[Mapping[str, str]] = [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": "Prior conversation:\n\n" + transcript + "\n\nProduce the summary now.",
            },
        ]
        try:
            summary = self._llm.complete_chat(llm_messages, temperature=0.15)
        except Exception as exc:
            logger.exception("GraphRAG carryover summary failed")
            return {"ok": False, "error": f"LLM request failed: {exc!s}"}
        summary = (summary or "").strip()
        if len(summary) > 4000:
            summary = summary[:3997] + "..."
        return {"ok": True, "summary": summary}

    def answer(
        self,
        run_dir_path: Path,
        user_message: str,
        *,
        max_depth: int = 2,
        max_nodes: int = 220,
        top_seeds: int = 14,
        max_subgraph_chars: int = 18_000,
        max_metrics_chars: int = 4_500,
        max_source_chars: int = 11_000,
        conversation_history: Sequence[Mapping[str, Any]] | None = None,
        carryover_summary: str | None = None,
        max_history_messages: int = 24,
        max_history_chars_per_message: int = 12_000,
        progress_hook: Callable[[str, str | None], None] | None = None,
        token_hook: Callable[[str], None] | None = None,
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
            max_source_chars: Character budget for indexed ``.py`` source excerpts.
            conversation_history: Prior ``user`` / ``assistant`` messages (plain text).
            carryover_summary: Optional short summary from a forked session.
            max_history_messages: Max prior turns to include (each message counts as one).
            max_history_chars_per_message: Truncate each stored message to this length.
            progress_hook: Optional ``(stage, message)`` updates for streaming UIs (e.g. SSE).
            token_hook: Optional callback receiving each **assistant text fragment** when the
                HTTP client supports streaming (``stream_chat_completion``); otherwise one call
                with the full reply after a buffered completion.

        Returns:
            Dict with ``ok`` (bool), optional ``reply``, diagnostics, ``approx_input_chars``,
            ``context_warn`` (``none`` | ``approaching`` | ``critical``), and when enabled via
            ``GRAPHRAG_CHAT_AUTO_SUMMARY_AT_CHARS`` (and enough prior turns exist), the boolean
            ``context_auto_fork`` so the workspace can trigger an automatic session fork (same as ``POST …/sessions/fork``).
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

        prior_hist: List[Mapping[str, Any]] = list(conversation_history or [])
        retrieval_blend = _retrieval_query_blend(user_message, prior_hist)

        ret = self._retrieve_context(
            run_dir_path,
            user_message,
            retrieval_query=retrieval_blend,
            max_depth=max_depth,
            max_nodes=max_nodes,
            top_seeds=top_seeds,
            max_subgraph_chars=max_subgraph_chars,
            max_metrics_chars=max_metrics_chars,
            max_source_chars=max_source_chars,
            progress_hook=progress_hook,
        )
        if not ret.get("ok"):
            return ret

        user_block = str(ret.pop("user_block", "") or "")

        messages_out: List[Mapping[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        carry = (carryover_summary or "").strip()
        if carry:
            messages_out.append(
                {
                    "role": "user",
                    "content": _CARRYOVER_USER_PREFIX + carry[:8000],
                }
            )

        hist = prior_hist
        if max_history_messages > 0 and hist:
            hist = hist[-max_history_messages:]
            for m in hist:
                if not isinstance(m, Mapping):
                    continue
                role = str(m.get("role", "")).strip().lower()
                if role not in ("user", "assistant"):
                    continue
                content = str(m.get("content", "")).strip()
                if not content:
                    continue
                cap = max_history_chars_per_message
                if len(content) > cap:
                    content = content[: max(0, cap - 1)] + "…"
                messages_out.append({"role": role, "content": content})

        messages_out.append({"role": "user", "content": user_block})

        approx = _approx_chars_for_messages(messages_out)
        context_warn = _context_warn_level(approx)
        if approx > 32_000:
            logger.warning(
                "GraphRAG assembled prompt is very large (approx_input_chars=%d); expect slow "
                "local LLM turns. Prefer a new chat, shorter history, or smaller "
                "GRAPHRAG_SOURCE_* / subgraph budgets.",
                approx,
            )

        if progress_hook:
            progress_hook(
                "llm",
                "Calling the chat model (large prompts can take several minutes on local hardware)…",
            )
        logger.info("GraphRAG LLM request starting approx_input_chars=%d", approx)

        chat_temp = _chat_temperature()
        stream_fn = getattr(self._llm, "stream_chat_completion", None)
        try:
            if token_hook is not None and callable(stream_fn):
                parts: List[str] = []
                for piece in stream_fn(messages_out, temperature=chat_temp):
                    parts.append(piece)
                    token_hook(piece)
                reply = "".join(parts).strip()
                if not reply:
                    raise RuntimeError("stream returned empty assistant text")
            else:
                reply = self._llm.complete_chat(messages_out, temperature=chat_temp)
                if token_hook is not None and reply:
                    token_hook(reply)
            logger.info("GraphRAG LLM reply success reply_chars=%d", len(reply))
        except Exception as exc:
            logger.exception("GraphRAG LLM call failed")
            return {"ok": False, "error": f"LLM request failed: {exc!s}"}

        fork_thr = _context_auto_fork_chars()
        auto_fork = bool(
            fork_thr > 0
            and approx >= fork_thr
            and len(prior_hist) >= 2
        )
        if auto_fork:
            logger.info(
                "GraphRAG context_auto_fork set approx=%d threshold=%d prior_messages=%d",
                approx,
                fork_thr,
                len(prior_hist),
            )

        ret["ok"] = True
        ret["reply"] = reply
        ret["approx_input_chars"] = approx
        ret["context_warn"] = context_warn
        ret["context_auto_fork"] = auto_fork
        return ret
