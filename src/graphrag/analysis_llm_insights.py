"""One-shot LLM narrative over deterministic graph analysis artifacts (cached per run)."""

from __future__ import annotations

import httpx
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.graphrag.analysis_context import format_analysis_view_summary
from src.graphrag.openai_compatible_client import load_chat_client_from_env
from src.web.results_paths import is_safe_visual_png_filename

logger = logging.getLogger(__name__)

LLM_INSIGHTS_FILENAME = "graphrag_llm_insights.json"
INSIGHTS_PROMPT_VERSION = "insights-v1"
INSIGHTS_SCHEMA_VERSION = 1


def _png_display_title(filename: str) -> str:
    """Map a generated PNG filename to a short UI label (mirrors web gallery labels)."""
    key = filename.lower()
    ordered = (
        ("structure_imports", "Structure (IMPORTS only)"),
        ("structure_in_file", "Structure (IN_FILE only)"),
        ("structure_calls", "Structure (CALLS only)"),
        ("structure_tests", "Structure (TESTS only)"),
        ("structure_modified_by", "Structure (MODIFIED_BY only)"),
        ("betweenness_imports", "Betweenness centrality (IMPORTS)"),
        ("betweenness_calls", "Betweenness centrality (CALLS)"),
        ("pagerank_imports", "PageRank (IMPORTS)"),
        ("pagerank_calls", "PageRank (CALLS)"),
        ("degree_analysis_imports", "Degree chart (IMPORTS)"),
        ("degree_analysis_in_file", "Degree chart (IN_FILE)"),
        ("degree_analysis_calls", "Degree chart (CALLS)"),
        ("degree_analysis_tests", "Degree chart (TESTS)"),
        ("degree_analysis_modified_by", "Degree chart (MODIFIED_BY)"),
        ("degree_analysis", "Degree chart (combined)"),
        ("_structure", "Structure (all edges)"),
    )
    for needle, title in ordered:
        if needle in key:
            return title
    return filename


def _collect_visual_gallery_titles(run_dir: Path) -> list[dict[str, str]]:
    """List safe PNGs under ``run_dir/visuals`` for LLM context."""
    visuals = run_dir / "visuals"
    if not visuals.is_dir():
        return []
    entries: list[dict[str, str]] = []
    for p in sorted(visuals.glob("*.png")):
        if is_safe_visual_png_filename(p.name):
            entries.append({"name": p.name, "title": _png_display_title(p.name)})
    return entries


_SYSTEM = (
    "You are a senior staff engineer reviewing **static** graph metrics for one Python repository run. "
    "The user message contains precomputed tables (degrees, centrality, communities, risk candidates) "
    "and excerpts of text reports. You must **not** invent file paths or metrics that are not implied "
    "by the supplied material; when uncertain, say so in caveats.\n\n"
    "Respond with **only** a single JSON object (no markdown fences, no commentary). Use this shape "
    "(all string arrays may be empty; use English for values):\n"
    "{\n"
    '  "executive_summary": "2–5 sentences",\n'
    '  "key_findings": ["bullet", "..."],\n'
    '  "suggested_actions": ["concrete next step", "..."],\n'
    '  "bug_risk_hotspots": [{"location": "file or module from metrics", '
    '"rationale": "why it may hide defects", "confidence": "low|medium|high"}],\n'
    '  "high_risk_areas": [{"title": "short label", "detail": "why it matters", '
    '"severity": "low|medium|high|critical"}],\n'
    '  "testing_observations": ["note about TESTS edges / gaps", "..."],\n'
    '  "caveats": "Remind reader this is LLM interpretation of static analysis, not runtime truth."\n'
    "}\n\n"
    "Severity and confidence are **relative** to this graph only. Prefer locations that appear "
    "in the metrics or report text."
)


def _truncate(s: str, max_chars: int) -> str:
    t = (s or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 24)] + "\n…[truncated]"


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _normalize_insights_blob(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce parsed LLM JSON into a stable UI payload."""

    def _str_list(key: str) -> list[str]:
        v = raw.get(key)
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for x in v:
            s = str(x).strip()
            if s:
                out.append(s)
        return out[:24]

    def _hotspots() -> list[dict[str, str]]:
        v = raw.get("bug_risk_hotspots")
        if not isinstance(v, list):
            return []
        rows: list[dict[str, str]] = []
        for item in v[:16]:
            if not isinstance(item, dict):
                continue
            loc = str(item.get("location", "")).strip()
            rat = str(item.get("rationale", "")).strip()
            conf = str(item.get("confidence", "medium")).strip().lower()
            if conf not in ("low", "medium", "high"):
                conf = "medium"
            if loc or rat:
                rows.append({"location": loc or "—", "rationale": rat, "confidence": conf})
        return rows

    def _risks() -> list[dict[str, str]]:
        v = raw.get("high_risk_areas")
        if not isinstance(v, list):
            return []
        rows: list[dict[str, str]] = []
        for item in v[:16]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            detail = str(item.get("detail", "")).strip()
            sev = str(item.get("severity", "medium")).strip().lower()
            if sev not in ("low", "medium", "high", "critical"):
                sev = "medium"
            if title or detail:
                rows.append({"title": title or "—", "detail": detail, "severity": sev})
        return rows

    summary = str(raw.get("executive_summary", "")).strip()
    caveats = str(raw.get("caveats", "")).strip()
    if not caveats:
        caveats = (
            "This section is generated by an LLM from static graph metrics only; "
            "it is not a substitute for tests, profiling, or security review."
        )

    return {
        "schema_version": INSIGHTS_SCHEMA_VERSION,
        "executive_summary": summary,
        "key_findings": _str_list("key_findings"),
        "suggested_actions": _str_list("suggested_actions"),
        "bug_risk_hotspots": _hotspots(),
        "high_risk_areas": _risks(),
        "testing_observations": _str_list("testing_observations"),
        "caveats": caveats,
    }


def load_llm_insights_file(run_dir: Path) -> dict[str, Any] | None:
    """Return parsed insights document if present and valid enough for the UI.

    Args:
        run_dir: Resolved ``results/web_analysis_*`` directory.

    Returns:
        Dict with ``schema_version`` 1 and insight fields, or ``None`` if missing/invalid.
    """
    path = run_dir / LLM_INSIGHTS_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != INSIGHTS_SCHEMA_VERSION:
        return None
    return data


def build_insights_user_message(
    run_dir: Path,
    *,
    analysis_text: str,
    analysis_view: Mapping[str, Any],
    visual_summary_text: str,
) -> str:
    """Assemble the user turn sent to the chat model for insight generation.

    Args:
        run_dir: Run directory (for gallery file names).
        analysis_text: Contents of ``analysis.txt``.
        analysis_view: Parsed ``analysis_view.json``.
        visual_summary_text: Contents of ``visual_summary.txt``.

    Returns:
        Plain-text prompt body.
    """
    metrics = format_analysis_view_summary(analysis_view, max_chars=6_000)
    gallery = _collect_visual_gallery_titles(run_dir)
    titles = [f"- {g['title']} ({g['name']})" for g in gallery[:40]]
    gallery_block = "\n".join(titles) if titles else "(no PNG list; charts may still exist)"
    parts = [
        "## Run context",
        f"- Results folder name: {run_dir.name}",
        "",
        "## Chart artifacts (filenames)",
        gallery_block,
        "",
        "## Precomputed metrics (truncated)",
        metrics or "(no analysis_view summary)",
        "",
        "## analysis.txt (truncated)",
        _truncate(analysis_text, 14_000),
        "",
        "## visual_summary.txt (truncated)",
        _truncate(visual_summary_text, 6_000),
    ]
    return "\n".join(parts)


def generate_and_save_llm_insights(
    run_dir: Path,
    *,
    regenerate: bool = False,
) -> dict[str, Any]:
    """Call the configured LLM once, parse JSON, and persist ``graphrag_llm_insights.json``.

    Args:
        run_dir: Resolved results directory for one web run.
        regenerate: When ``False``, return the existing file without calling the API.

    Returns:
        ``{"ok": True, "insights": {...}}`` or ``{"ok": False, "error": "..."}``.
    """
    out_path = run_dir / LLM_INSIGHTS_FILENAME
    if not regenerate and out_path.is_file():
        cached = load_llm_insights_file(run_dir)
        if cached:
            return {"ok": True, "insights": cached, "cached": True}
    try:
        client = load_chat_client_from_env()
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    analysis_path = run_dir / "analysis.txt"
    analysis_text = analysis_path.read_text(encoding="utf-8") if analysis_path.is_file() else ""
    view_path = run_dir / "analysis_view.json"
    analysis_view: dict[str, Any] = {}
    if view_path.is_file():
        try:
            loaded = json.loads(view_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                analysis_view = loaded
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("insights: could not read analysis_view.json: %s", exc)
    vis_path = run_dir / "visual_summary.txt"
    visual_summary_text = vis_path.read_text(encoding="utf-8") if vis_path.is_file() else ""

    user_msg = build_insights_user_message(
        run_dir,
        analysis_text=analysis_text,
        analysis_view=analysis_view,
        visual_summary_text=visual_summary_text,
    )
    try:
        raw_text = client.complete_chat(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=4_096,
            temperature=0.25,
        )
    except (RuntimeError, OSError, ValueError, httpx.HTTPError) as exc:
        logger.exception("LLM insights request failed")
        return {"ok": False, "error": f"LLM request failed: {exc!s}"}

    try:
        parsed = json.loads(_strip_json_fence(raw_text))
    except json.JSONDecodeError as exc:
        logger.warning("LLM insights JSON parse failed: %s", exc)
        return {"ok": False, "error": "Model did not return valid JSON. Try again or use a JSON-capable model."}

    if not isinstance(parsed, dict):
        return {"ok": False, "error": "Model JSON was not an object."}

    normalized = _normalize_insights_blob(parsed)
    envelope: dict[str, Any] = {
        **normalized,
        "prompt_version": INSIGHTS_PROMPT_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": os.environ.get("GRAPHRAG_CHAT_MODEL", "").strip(),
    }

    try:
        out_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write %s: %s", out_path, exc)
        return {"ok": False, "error": f"Could not save insights file: {exc!s}"}

    logger.info("Wrote LLM insights run_dir=%s path=%s", run_dir.name, out_path.name)
    return {"ok": True, "insights": envelope, "cached": False}
