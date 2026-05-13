"""Compact precomputed analysis metrics for LLM grounding."""

from __future__ import annotations

from typing import Any, Mapping


def format_analysis_view_summary(view: Mapping[str, Any], *, max_chars: int = 6_000) -> str:
    """Serialize key parts of ``analysis_view.json`` for LLM context.

    Args:
        view: Parsed ``analysis_view`` dict (``schema_version`` 1 expected).
        max_chars: Upper bound on returned string length.

    Returns:
        Plain-text summary (may be empty if *view* has no usable sections).
    """
    if not view:
        return ""
    lines: list[str] = ["## Precomputed graph metrics (from pipeline)", ""]
    totals = view.get("totals") or {}
    if isinstance(totals, dict):
        lines.append(
            f"- Total nodes: {totals.get('nodes', '?')}, edges: {totals.get('edges', '?')}"
        )
    ec = view.get("edge_counts") or []
    if isinstance(ec, list) and ec:
        parts = [f"{x.get('type')}:{x.get('count')}" for x in ec if isinstance(x, dict)]
        lines.append("- Edge counts by type: " + ", ".join(parts))
    lines.append("")

    risk = view.get("risk") or {}
    if isinstance(risk, dict) and not risk.get("empty"):
        lines.append("### Risk candidates (composite z-score on File nodes)")
        for row in (risk.get("candidates") or [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- rank {row.get('rank')}: {row.get('file_path')} "
                f"total={row.get('total')} "
                f"(centrality_z={row.get('centrality_z')}, churn_z={row.get('churn_z')}, "
                f"test_gap_z={row.get('test_gap_z')}, cross_comm_z={row.get('cross_community_z')})"
            )
        lines.append("")

    for block in view.get("centrality_sections") or []:
        if not isinstance(block, dict):
            continue
        et = block.get("edge_type", "")
        lines.append(f"### Centrality ({et})")
        for row in (block.get("betweenness_rows") or [])[:5]:
            if isinstance(row, dict):
                lines.append(
                    f"- betweenness rank {row.get('rank')}: {row.get('label')} "
                    f"score={row.get('score')}"
                )
        for row in (block.get("pagerank_rows") or [])[:5]:
            if isinstance(row, dict):
                lines.append(
                    f"- pagerank rank {row.get('rank')}: {row.get('label')} score={row.get('score')}"
                )
        lines.append("")

    for csec in view.get("community_sections") or []:
        if not isinstance(csec, dict) or csec.get("empty"):
            continue
        et = csec.get("edge_type", "")
        summ = csec.get("summary") or {}
        lines.append(f"### Communities ({et})")
        if isinstance(summ, dict):
            lines.append(
                f"- algorithm={summ.get('algorithm')}, communities={summ.get('community_count')}, "
                f"modularity={summ.get('modularity')}"
            )
        for row in (csec.get("communities") or [])[:6]:
            if not isinstance(row, dict):
                continue
            prev = row.get("preview") or []
            prev_s = ", ".join(str(p) for p in list(prev)[:5])
            lines.append(
                f"- community rank {row.get('rank')}: size={row.get('size')} sample: {prev_s}"
            )
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…[truncated metrics]"
    return text
