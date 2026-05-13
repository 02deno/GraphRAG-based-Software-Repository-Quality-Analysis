"""Use Louvain community previews from ``analysis_view`` to widen seed sets."""

from __future__ import annotations

from typing import Any, List, Mapping, Set

from src.graphrag.query_index import query_token_set


def _global_repo_query(query: str) -> bool:
    """Return True when the user likely wants a broad architectural overview."""
    q = query.lower()
    keys = (
        "whole repo",
        "entire codebase",
        "overall architecture",
        "high level",
        "big picture",
        "repository-wide",
        "across the project",
        "global view",
        "all communities",
        "community structure",
    )
    return any(k in q for k in keys)


def community_member_seeds_from_view(
    query: str,
    view: Mapping[str, Any],
    *,
    max_communities: int = 4,
    max_ids_total: int = 56,
) -> List[str]:
    """Pick extra seed node ids from detected communities when *query* matches.

    Uses ``member_ids`` on each community row when present (written by the
    pipeline's ``analysis_view`` builder). Falls back to no extra seeds when
    community payloads omit ``member_ids``.

    Args:
        query: Natural language user question.
        view: ``analysis_view`` dict (``community_sections`` list).
        max_communities: How many top-scoring communities to draw members from.
        max_ids_total: Cap on distinct returned node ids.

    Returns:
        Ordered list of distinct node ids (may be empty).
    """
    q_words = query_token_set(query)
    sections = view.get("community_sections") or []
    if not isinstance(sections, list):
        return []

    scored: List[tuple[float, Mapping[str, Any]]] = []
    for block in sections:
        if not isinstance(block, dict) or block.get("empty"):
            continue
        for row in block.get("communities") or []:
            if not isinstance(row, dict):
                continue
            preview = row.get("preview") or []
            blob = " ".join(str(p) for p in preview if p).lower()
            score = 0.0
            qlow = query.strip().lower()
            for w in qlow.replace("/", " ").split():
                if len(w) >= 2 and w in blob:
                    score += 22.0
            if q_words:
                pw = query_token_set(blob)
                inter = q_words & pw
                union = q_words | pw
                if union:
                    score += 30.0 * len(inter) / len(union)
                score += 4.0 * len(inter)
            if _global_repo_query(query):
                score += 12.0
            if score > 0 or _global_repo_query(query):
                scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[str] = []
    seen: Set[str] = set()
    picked = 0
    for _s, row in scored:
        if picked >= max_communities:
            break
        mids = row.get("member_ids")
        if not isinstance(mids, list):
            picked += 1
            continue
        for mid in mids:
            sid = str(mid)
            if not sid or sid in seen:
                continue
            seen.add(sid)
            out.append(sid)
            if len(out) >= max_ids_total:
                return out
        picked += 1
    if not out and _global_repo_query(query):
        for block in sections:
            if not isinstance(block, dict) or block.get("empty"):
                continue
            rows = block.get("communities") or []
            if not rows or not isinstance(rows[0], dict):
                continue
            mids = rows[0].get("member_ids") or []
            if not isinstance(mids, list):
                break
            for mid in mids:
                sid = str(mid)
                if sid and sid not in seen:
                    seen.add(sid)
                    out.append(sid)
                    if len(out) >= max_ids_total:
                        return out
            break
    return out
