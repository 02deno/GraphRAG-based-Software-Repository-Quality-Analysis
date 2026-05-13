"""Turn a retrieved subgraph into bounded plain-text context for an LLM."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

_CTX_HEADER = (
    "The following is an induced subgraph from a static software repository graph "
    "(nodes: files, classes, functions, tests, commits; edges: imports, containment, "
    "calls, tests, commits touching files). Use only this structure to justify claims; "
    "mark speculation clearly when information is missing.\n\n"
)


def _node_one_liner(node: Mapping[str, Any]) -> str:
    """Format a single node as one compact line."""
    ntype = str(node.get("type", "?"))
    nid = str(node.get("id", ""))
    qn = str(node.get("qualified_name", "")).strip()
    path = str(node.get("path", "") or node.get("file_path", "")).strip()
    name = str(node.get("name", "")).strip()
    label = qn or path or name or nid
    return f"- [{ntype}] {label}  (id={nid})"


def format_subgraph_for_llm(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    max_chars: int = 28_000,
) -> str:
    """Render nodes and typed edges as readable text under a character budget.

    Args:
        nodes: Full node list; only ids referenced in *edges* need not all appear,
            but typically callers pass the induced node subset.
        edges: Induced edge records with ``source``, ``target``, ``type``.
        max_chars: Truncate output (keeps header and as many nodes as fit, then edges).

    Returns:
        A single string safe to inject as a user/assistant context block.
    """
    node_by_id: Dict[str, Mapping[str, Any]] = {}
    for n in nodes:
        nid = str(n.get("id", ""))
        if nid:
            node_by_id[nid] = n

    node_lines: List[str] = ["## Nodes", ""]
    for nid in sorted(node_by_id.keys()):
        node_lines.append(_node_one_liner(node_by_id[nid]))
    node_lines.append("")
    node_lines.append("## Edges (source --[TYPE]--> target)")
    node_lines.append("")
    edge_lines: List[str] = []
    for e in sorted(
        edges,
        key=lambda x: (str(x.get("source", "")), str(x.get("type", "")), str(x.get("target", ""))),
    ):
        src = str(e.get("source", ""))
        tgt = str(e.get("target", ""))
        et = str(e.get("type", ""))
        edge_lines.append(f"- {src} --[{et}]--> {tgt}")

    parts: List[str] = [_CTX_HEADER, "\n".join(node_lines)]
    body_edges = "\n".join(edge_lines)
    if body_edges:
        parts.append(body_edges)

    text = "\n".join(parts)
    if len(text) <= max_chars:
        return text

    # Truncate from the end of the edges block while keeping the header and node list
    # if possible.
    budget = max_chars - 80
    if budget <= 0:
        return text[:max_chars] + "\n…[truncated]"
    head = "\n".join(parts[:-1])  # header + nodes
    if len(head) >= budget:
        return head[:budget] + "\n…[truncated]"
    rest = budget - len(head) - 1
    return head + "\n" + body_edges[:rest] + "\n…[truncated edges]"
