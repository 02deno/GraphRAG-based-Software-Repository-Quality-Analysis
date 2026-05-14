#!/usr/bin/env python3
"""Probe Ollama (OpenAI-compatible) and Neo4j using the same env vars as the web app.

Loads ``.env`` from the project root (two levels above this file), then checks:

- ``GET {GRAPHRAG_OPENAI_BASE_URL}/models`` and a short ``POST …/chat/completions``
- optional ``POST …/embeddings`` when ``GRAPHRAG_EMBEDDING_MODEL`` is set
- Neo4j ``verify_connectivity`` and ``RETURN 1`` on ``GRAPHRAG_NEO4J_DATABASE`` (or default DB)

Usage (from repository root)::

    python scripts/check_graphrag_connections.py

Override shell with ``.env`` values (useful when testing)::

    python scripts/check_graphrag_connections.py --override-dotenv

Use a different env file::

    python scripts/check_graphrag_connections.py --env-file .env.local
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    """Return ``GraphRAG_Project`` root (parent of ``scripts/``)."""
    return Path(__file__).resolve().parent.parent


def _load_dotenv(env_path: Path, *, override: bool) -> None:
    """Load *env_path* if ``python-dotenv`` is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning(
            "python-dotenv not installed; only process environment is used. "
            "Install with: pip install python-dotenv"
        )
        return
    if env_path.is_file():
        load_dotenv(env_path, override=override)
        print(f"Loaded env file: {env_path}")
    else:
        print(f"Env file not found (skipped): {env_path}")


def _check_ollama(base: str, model: str, embedding_model: str) -> tuple[list[str], list[str]]:
    """Return ``(oks, errs)`` for HTTP checks against Ollama-compatible API."""
    oks: list[str] = []
    errs: list[str] = []
    base = base.strip().rstrip("/")
    if not base or not model:
        errs.append("GRAPHRAG_OPENAI_BASE_URL or GRAPHRAG_CHAT_MODEL is empty.")
        return oks, errs

    try:
        import httpx
    except ImportError as exc:
        errs.append(f"httpx not installed: {exc}")
        return oks, errs

    try:
        r = httpx.get(f"{base}/models", timeout=10.0)
        if r.status_code != 200:
            errs.append(f"GET /models -> HTTP {r.status_code}")
        else:
            data = r.json()
            ids = [m.get("id", "") for m in data.get("data", [])]
            oks.append(f"GET /models OK ({len(ids)} models)")
            exact = model in ids
            prefixed = any(i == model or i.startswith(model + ":") for i in ids)
            if not exact and not prefixed:
                errs.append(
                    f"GRAPHRAG_CHAT_MODEL={model!r} not found in /models; first ids: {ids[:12]!r}"
                )
            else:
                oks.append(f"Chat model {model!r} appears in /models")

        r2 = httpx.post(
            f"{base}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with one word: OK"}],
                "max_tokens": 24,
                "temperature": 0,
            },
            timeout=120.0,
        )
        if r2.status_code != 200:
            body = (r2.text or "")[:400]
            errs.append(f"POST /chat/completions -> HTTP {r2.status_code}: {body}")
        else:
            oks.append("POST /chat/completions smoke test OK")
    except Exception as exc:
        errs.append(f"Ollama HTTP error: {exc!s}")

    if embedding_model.strip():
        try:
            key = os.environ.get("GRAPHRAG_OPENAI_API_KEY", "").strip()
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            r3 = httpx.post(
                f"{base}/embeddings",
                json={"model": embedding_model.strip(), "input": "ping"},
                headers=headers,
                timeout=60.0,
            )
            if r3.status_code != 200:
                errs.append(
                    f"POST /embeddings ({embedding_model!r}) -> HTTP {r3.status_code}: "
                    f"{(r3.text or '')[:300]}"
                )
            else:
                oks.append(f"POST /embeddings OK ({embedding_model!r})")
        except Exception as exc:
            errs.append(f"Embeddings error: {exc!s}")

    return oks, errs


def _check_neo4j() -> tuple[list[str], list[str]]:
    """Return ``(oks, errs)`` for Bolt connectivity (password never printed)."""
    oks: list[str] = []
    errs: list[str] = []
    uri = os.environ.get("GRAPHRAG_NEO4J_URI", "").strip()
    user = os.environ.get("GRAPHRAG_NEO4J_USER", "neo4j").strip() or "neo4j"
    password = os.environ.get("GRAPHRAG_NEO4J_PASSWORD", "").strip()
    dbname = os.environ.get("GRAPHRAG_NEO4J_DATABASE", "").strip() or None

    if not uri or not password:
        errs.append("Neo4j skipped or misconfigured: GRAPHRAG_NEO4J_URI / GRAPHRAG_NEO4J_PASSWORD empty.")
        return oks, errs

    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        errs.append(f"neo4j driver not installed: {exc}")
        return oks, errs

    try:
        drv = GraphDatabase.driver(uri, auth=(user, password))
        drv.verify_connectivity()
        oks.append("Neo4j verify_connectivity OK")
        with drv.session(database=dbname) as session:
            row = session.run("RETURN 1 AS x").single()
            if row and row.get("x") == 1:
                oks.append(f"Neo4j session RETURN 1 OK (database={dbname!r})")
            else:
                errs.append("Neo4j RETURN 1 unexpected result")
        drv.close()
    except Exception as exc:
        errs.append(f"Neo4j error: {exc!s}")

    return oks, errs


def main() -> int:
    """Parse CLI, run checks, print lines, return exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root = _project_root()
    parser = argparse.ArgumentParser(description="Check GraphRAG Ollama + Neo4j connectivity.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=root / ".env",
        help="Path to dotenv file (default: <project>/.env)",
    )
    parser.add_argument(
        "--override-dotenv",
        action="store_true",
        help="Pass override=True to load_dotenv (env file wins over existing shell vars).",
    )
    parser.add_argument("--skip-neo4j", action="store_true", help="Do not test Neo4j.")
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip POST /embeddings even if GRAPHRAG_EMBEDDING_MODEL is set.",
    )
    args = parser.parse_args()

    env_path = args.env_file if args.env_file.is_absolute() else (root / args.env_file).resolve()
    _load_dotenv(env_path, override=args.override_dotenv)

    base = os.environ.get("GRAPHRAG_OPENAI_BASE_URL", "").strip()
    model = os.environ.get("GRAPHRAG_CHAT_MODEL", "").strip()
    emb = "" if args.skip_embeddings else os.environ.get("GRAPHRAG_EMBEDDING_MODEL", "").strip()

    all_ok: list[str] = []
    all_err: list[str] = []

    o1, e1 = _check_ollama(base, model, emb)
    all_ok.extend(o1)
    all_err.extend(e1)

    if not args.skip_neo4j:
        o2, e2 = _check_neo4j()
        all_ok.extend(o2)
        all_err.extend(e2)

    for line in all_ok:
        print("OK ", line)
    for line in all_err:
        print("ERR", line)

    if all_err:
        print("\nSome checks failed (see ERR lines above).", file=sys.stderr)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
