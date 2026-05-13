"""Lightweight lexical scoring to pick seed nodes for graph traversal."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple


def build_node_search_blob(node: Dict[str, Any]) -> str:
    """Concatenate searchable fields from a graph node dict.

    Args:
        node: Serialized node from ``graph.json`` (any node ``type``).

    Returns:
        Lowercased single string used for substring and token overlap scoring.
    """
    parts: List[str] = []
    ntype = str(node.get("type", ""))
    parts.append(ntype)
    parts.append(str(node.get("id", "")))
    parts.append(str(node.get("name", "")))
    parts.append(str(node.get("qualified_name", "")))
    parts.append(str(node.get("path", "")))
    parts.append(str(node.get("file_path", "")))
    parts.append(str(node.get("module", "")))
    parts.append(str(node.get("message", "")))
    parts.append(str(node.get("target_hint", "")))
    parts.append(str(node.get("author", "")))
    parts.append(str(node.get("hash", "")))
    return " ".join(p for p in parts if p).lower()


_TOKEN_RE = re.compile(r"[a-z0-9_./]+", re.IGNORECASE)


def _word_set(text: str) -> set[str]:
    """Extract a set of lowercase tokens (paths, identifiers, alphanumerics)."""
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text) if len(m.group(0)) > 1}


def score_query_against_blob(query: str, blob: str) -> float:
    """Score how well *query* matches a node's search *blob*.

    Combines a full-string substring bonus with token overlap (Jaccard-like)
    for robustness when the user does not type exact path substrings.

    Args:
        query: Raw user question or keyword phrase.
        blob: Output of :func:`build_node_search_blob` for one node.

    Returns:
        Non-negative score; higher is a better seed candidate.
    """
    q = query.strip().lower()
    if not q or not blob:
        return 0.0
    score = 0.0
    if q in blob:
        score += 80.0
    q_words = _word_set(q)
    b_words = _word_set(blob)
    if not q_words:
        return score
    inter = q_words & b_words
    union = q_words | b_words
    if union:
        score += 45.0 * (len(inter) / len(union))
    score += 3.0 * len(inter)
    return score


def rank_seed_node_ids(
    nodes: Sequence[Dict[str, Any]],
    query: str,
    *,
    top_k: int = 15,
) -> List[Tuple[str, float]]:
    """Rank node ids by lexical relevance to *query*.

    Args:
        nodes: All nodes from a graph document.
        query: User question or search phrase.
        top_k: Maximum number of ``(node_id, score)`` pairs to return.

    Returns:
        Sorted list of ``(node_id, score)`` descending by score.
    """
    if top_k <= 0:
        return []
    ranked: List[Tuple[str, float]] = []
    for node in nodes:
        nid = str(node.get("id", ""))
        if not nid:
            continue
        blob = build_node_search_blob(node)
        s = score_query_against_blob(query, blob)
        if s > 0:
            ranked.append((nid, s))
    ranked.sort(key=lambda x: x[1], reverse=True)
    out = ranked[:top_k]
    if out:
        return out
    # Fallback: generic questions may not match any token — anchor on a few files.
    files = [n for n in nodes if str(n.get("type", "")) == "File"][: max(5, top_k // 3)]
    return [(str(n["id"]), 0.0) for n in files if n.get("id")]


def query_token_set(query: str) -> set[str]:
    """Return token set for *query* using the same tokenization as node blobs."""
    return _word_set(query.strip().lower())
