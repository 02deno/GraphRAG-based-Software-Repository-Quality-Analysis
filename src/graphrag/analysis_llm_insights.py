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
# Virtual path for lexical chunks in ``graphrag_source_chunks.jsonl`` (chat RAG).
LLM_INSIGHTS_SOURCE_VIRTUAL_PATH = "_analysis/graphrag_llm_insights.txt"
INSIGHTS_PROMPT_VERSION = "insights-v2"
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
    "Output format: respond with **exactly one** JSON object and nothing else — no markdown fences, "
    "no code blocks, no text before or after the braces. Use ASCII double quotes for all JSON strings. "
    "Use this shape (arrays may be empty; English values):\n"
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


def _coerce_parsed_root(obj: Any) -> dict[str, Any] | None:
    """Accept a root object or a single-element array wrapping that object."""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
        return obj[0]
    return None


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    """Parse the first top-level `{ ... }` in *text*, skipping prose outside JSON."""
    s = _strip_json_fence(text.strip())
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    quote = ""
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                in_str = False
                quote = ""
        else:
            if c in "\"'":
                in_str = True
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    chunk = s[start : i + 1]
                    try:
                        return _coerce_parsed_root(json.loads(chunk))
                    except json.JSONDecodeError:
                        return None
    return None


def _parse_insights_response(raw_text: str) -> dict[str, Any] | None:
    """Return a dict from model output, or None if nothing parseable."""
    s = _strip_json_fence((raw_text or "").strip())
    if not s:
        return None
    try:
        return _coerce_parsed_root(json.loads(s))
    except json.JSONDecodeError:
        pass
    return _extract_first_json_object(s)


def _insights_json_object_mode() -> bool:
    """Whether to send OpenAI ``response_format: json_object`` for insights calls.

    Default on when ``GRAPHRAG_OPENAI_BASE_URL`` looks like OpenAI's API host; set
    ``GRAPHRAG_INSIGHTS_JSON_OBJECT=0`` to disable, or ``1`` to force on for other hosts
    that support the same field.
    """
    flag = os.environ.get("GRAPHRAG_INSIGHTS_JSON_OBJECT", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return True
    base = os.environ.get("GRAPHRAG_OPENAI_BASE_URL", "").strip().lower()
    return "api.openai.com" in base


def _insights_max_output_tokens() -> int:
    """Cap completion tokens for insights (smaller = faster/cheaper; JSON fits well under 3k)."""
    raw = os.environ.get("GRAPHRAG_INSIGHTS_MAX_TOKENS", "").strip()
    if raw:
        try:
            return max(512, min(int(raw), 8192))
        except ValueError:
            pass
    return 3072


def _insights_input_limits() -> tuple[int, int, int]:
    """``(metrics_max_chars, analysis_max_chars, visual_max_chars)`` for the user prompt."""
    compact = os.environ.get("GRAPHRAG_INSIGHTS_COMPACT", "").strip().lower() in ("1", "true", "yes", "on")
    if compact:
        return (4_000, 7_000, 3_000)
    return (5_000, 11_000, 4_500)


def _complete_insights_chat(
    client: Any,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    use_json_object: bool,
) -> str:
    """Call chat completions; if the server rejects ``json_object``, retry without it."""
    try:
        return str(
            client.complete_chat(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format_json_object=use_json_object,
            )
        ).strip()
    except httpx.HTTPStatusError as exc:
        if use_json_object and exc.response is not None and exc.response.status_code >= 400:
            logger.warning(
                "insights: json_object mode rejected (status=%s); retrying without response_format",
                exc.response.status_code,
            )
            return str(
                client.complete_chat(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format_json_object=False,
                )
            ).strip()
        raise


def _repair_insights_with_llm(
    client: Any,
    broken_text: str,
    *,
    use_json_object: bool,
) -> dict[str, Any] | None:
    """Ask the model to emit valid JSON only, given a broken prior reply."""
    clip = (broken_text or "").strip()[:14_000]
    repair_messages = [
        {
            "role": "system",
            "content": (
                "You only output one valid JSON object. No markdown, no commentary. "
                "Keys required: executive_summary, key_findings, suggested_actions, "
                "bug_risk_hotspots, high_risk_areas, testing_observations, caveats. "
                "Use the same key meanings as in the failed assistant output below; "
                "infer missing keys as empty strings or empty arrays."
            ),
        },
        {
            "role": "user",
            "content": (
                "Rewrite the following assistant text into a single valid JSON object "
                "with exactly those keys. If the text is prose, map it into "
                "executive_summary + key_findings.\n\n" + clip
            ),
        },
    ]
    try:
        fixed = _complete_insights_chat(
            client,
            repair_messages,
            max_tokens=_insights_max_output_tokens(),
            temperature=0.0,
            use_json_object=use_json_object,
        )
    except (RuntimeError, OSError, ValueError, httpx.HTTPError) as exc:
        logger.warning("insights repair call failed: %s", exc)
        return None
    return _parse_insights_response(fixed)


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


def format_llm_insights_for_source_index(data: Mapping[str, Any]) -> str:
    """Flatten cached LLM insights JSON to plain text for lexical source chunk indexing.

    Used as the body of virtual ``_analysis/graphrag_llm_insights.txt`` chunks so the
    workspace chat retriever can surface the same narrative when questions match.

    Args:
        data: Parsed ``graphrag_llm_insights.json`` (``schema_version`` 1).

    Returns:
        Multi-line UTF-8 text (may be empty if there is no usable summary content).
    """
    lines: list[str] = []
    model = str(data.get("model", "")).strip()
    gen_at = str(data.get("generated_at", "")).strip()
    if model or gen_at:
        lines.append("## Metadata")
        if model:
            lines.append(f"- model: {model}")
        if gen_at:
            lines.append(f"- generated_at: {gen_at}")
        lines.append("")

    summary = str(data.get("executive_summary", "")).strip()
    if summary:
        lines.append("## Executive summary")
        lines.append(summary)
        lines.append("")

    def _append_bullets(title: str, key: str) -> None:
        raw = data.get(key)
        if not isinstance(raw, list) or not raw:
            return
        items = [str(x).strip() for x in raw if str(x).strip()]
        if not items:
            return
        lines.append(f"## {title}")
        for it in items[:32]:
            lines.append(f"- {it}")
        lines.append("")

    _append_bullets("Key findings", "key_findings")
    _append_bullets("Suggested actions", "suggested_actions")
    _append_bullets("Testing observations", "testing_observations")

    hotspots = data.get("bug_risk_hotspots")
    if isinstance(hotspots, list) and hotspots:
        lines.append("## Bug / risk hotspots")
        for item in hotspots[:24]:
            if not isinstance(item, dict):
                continue
            loc = str(item.get("location", "")).strip()
            rat = str(item.get("rationale", "")).strip()
            conf = str(item.get("confidence", "")).strip()
            if loc or rat:
                lines.append(f"- ({conf}) {loc}: {rat}")
        lines.append("")

    risks = data.get("high_risk_areas")
    if isinstance(risks, list) and risks:
        lines.append("## High-risk areas")
        for item in risks[:24]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            detail = str(item.get("detail", "")).strip()
            sev = str(item.get("severity", "")).strip()
            if title or detail:
                lines.append(f"- ({sev}) {title}: {detail}")
        lines.append("")

    caveats = str(data.get("caveats", "")).strip()
    if caveats:
        lines.append("## Caveats")
        lines.append(caveats)
        lines.append("")

    return "\n".join(lines).strip()


def build_insights_user_message(
    run_dir: Path,
    *,
    analysis_text: str,
    analysis_view: Mapping[str, Any],
    visual_summary_text: str,
    metrics_max_chars: int = 5_000,
    analysis_max_chars: int = 11_000,
    visual_max_chars: int = 4_500,
) -> str:
    """Assemble the user turn sent to the chat model for insight generation.

    Args:
        run_dir: Run directory (for gallery file names).
        analysis_text: Contents of ``analysis.txt``.
        analysis_view: Parsed ``analysis_view.json``.
        visual_summary_text: Contents of ``visual_summary.txt``.
        metrics_max_chars: Cap on formatted ``analysis_view`` summary text.
        analysis_max_chars: Cap on ``analysis.txt`` excerpt.
        visual_max_chars: Cap on ``visual_summary.txt`` excerpt.

    Returns:
        Plain-text prompt body.
    """
    metrics = format_analysis_view_summary(analysis_view, max_chars=metrics_max_chars)
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
        _truncate(analysis_text, analysis_max_chars),
        "",
        "## visual_summary.txt (truncated)",
        _truncate(visual_summary_text, visual_max_chars),
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
            try:
                from src.graphrag.source_context import refresh_llm_insights_source_chunks

                refresh_llm_insights_source_chunks(run_dir)
            except Exception as exc:
                logger.warning("LLM insights source chunk refresh skipped: %s", exc)
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

    mc, ac, vc = _insights_input_limits()
    user_msg = build_insights_user_message(
        run_dir,
        analysis_text=analysis_text,
        analysis_view=analysis_view,
        visual_summary_text=visual_summary_text,
        metrics_max_chars=mc,
        analysis_max_chars=ac,
        visual_max_chars=vc,
    )
    json_hint = (
        "\n\nYour entire reply must be one JSON object (valid JSON.parse in JavaScript). "
        "Do not wrap it in markdown."
    )
    use_json_object = _insights_json_object_mode()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_msg + json_hint},
    ]
    max_out = _insights_max_output_tokens()
    logger.info(
        "LLM insights request run_dir=%s approx_user_chars=%d max_output_tokens=%d json_object=%s",
        run_dir.name,
        len(user_msg) + len(json_hint),
        max_out,
        use_json_object,
    )
    try:
        raw_text = _complete_insights_chat(
            client,
            messages,
            max_tokens=max_out,
            temperature=0.2,
            use_json_object=use_json_object,
        )
    except (RuntimeError, OSError, ValueError, httpx.HTTPError) as exc:
        logger.exception("LLM insights request failed")
        return {"ok": False, "error": f"LLM request failed: {exc!s}"}

    parsed = _parse_insights_response(raw_text)
    if parsed is None:
        logger.warning(
            "LLM insights primary parse failed; preview=%r",
            (raw_text[:400] + "…") if len(raw_text) > 400 else raw_text,
        )
        parsed = _repair_insights_with_llm(client, raw_text, use_json_object=use_json_object)
    if parsed is None:
        return {
            "ok": False,
            "error": (
                "Model did not return valid JSON. Try Regenerate, use a JSON-friendly model "
                "(e.g. gpt-4o-mini), or set GRAPHRAG_INSIGHTS_JSON_OBJECT=1 when your server "
                "supports OpenAI-style response_format json_object."
            ),
        }

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
    try:
        from src.graphrag.source_context import refresh_llm_insights_source_chunks

        added = refresh_llm_insights_source_chunks(run_dir)
        logger.info("LLM insights source chunk refresh run_dir=%s records=%s", run_dir.name, added)
    except Exception as exc:
        logger.warning("LLM insights source chunk refresh failed: %s", exc)
    return {"ok": True, "insights": envelope, "cached": False}
