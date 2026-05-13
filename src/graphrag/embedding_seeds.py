"""Dense embedding seeds via OpenAI-compatible ``/embeddings`` + on-disk cache."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import httpx
import numpy as np

from src.graphrag.query_index import build_node_search_blob

logger = logging.getLogger(__name__)

_CACHE_FILE = "graphrag_embedding_cache.npz"
_META_FILE = "graphrag_embedding_cache_meta.json"
_EMBED_BATCH = 64


def build_node_embed_text(node: Dict[str, Any]) -> str:
    """Build a single string to embed for *node* (richer than search-only blob)."""
    blob = build_node_search_blob(node)
    ntype = str(node.get("type", ""))
    return f"{ntype}: {blob}"[:8000]


def _fingerprint(graph_path: Path, model: str) -> Dict[str, Any]:
    st = graph_path.stat()
    return {"mtime_ns": st.st_mtime_ns, "model": model}


def embed_texts_openai_compatible(
    texts: Sequence[str],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_s: float = 120.0,
) -> List[List[float]]:
    """POST batches to ``/v1/embeddings`` and return vectors in order."""
    root = base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    out: List[List[float]] = []
    with httpx.Client(base_url=root, timeout=timeout_s) as client:
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = list(texts[i : i + _EMBED_BATCH])
            resp = client.post(
                "/v1/embeddings",
                headers=headers,
                json={"model": model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            # API returns one object per input with index
            by_idx = {int(x.get("index", -1)): x.get("embedding") for x in items if isinstance(x, dict)}
            for j in range(len(batch)):
                vec = by_idx.get(j)
                if not isinstance(vec, list):
                    raise RuntimeError(f"embedding response missing index {j}")
                out.append([float(v) for v in vec])
    return out


def _l2_normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return mat / norms


def rank_node_ids_by_cosine(
    emb: np.ndarray,
    query_vec: np.ndarray,
    id_list: Sequence[str],
    *,
    top_k: int,
) -> List[str]:
    """Return *top_k* node ids with highest cosine similarity to *query_vec*."""
    if top_k <= 0 or emb.shape[0] == 0:
        return []
    if len(id_list) != emb.shape[0]:
        raise ValueError("id_list length must match embedding row count")
    emb_n = _l2_normalize_rows(np.asarray(emb, dtype=np.float32, copy=False))
    q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
    q_n = _l2_normalize_rows(q)
    sims = (emb_n @ q_n.T).ravel()
    k = min(top_k, sims.shape[0])
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    return [id_list[int(i)] for i in idx]


def try_embedding_seed_ids(
    run_dir_path: Path,
    nodes: Sequence[Dict[str, Any]],
    query: str,
    *,
    top_k: int = 12,
) -> Tuple[List[str], Dict[str, Any]]:
    """Return top node ids by cosine similarity of query embedding to node texts.

    Uses ``GRAPHRAG_OPENAI_BASE_URL``, ``GRAPHRAG_OPENAI_API_KEY``, and
    ``GRAPHRAG_EMBEDDING_MODEL`` when the model name is non-empty. Caches vectors
    under the run directory in ``graphrag_embedding_cache.npz``.

    Args:
        run_dir_path: Analysis run folder containing ``graph.json``.
        nodes: All graph nodes.
        query: User question.
        top_k: How many ids to return.

    Returns:
        ``(ids, diagnostics)`` where *diagnostics* explains cache hit / skip reason.
    """
    diag: Dict[str, Any] = {"enabled": False, "ids": []}
    model = os.environ.get("GRAPHRAG_EMBEDDING_MODEL", "").strip()
    base = os.environ.get("GRAPHRAG_OPENAI_BASE_URL", "").strip()
    if not model or not base:
        diag["reason"] = "GRAPHRAG_EMBEDDING_MODEL or GRAPHRAG_OPENAI_BASE_URL not set"
        return [], diag

    key = os.environ.get("GRAPHRAG_OPENAI_API_KEY", "").strip()
    graph_path = run_dir_path / "graph.json"
    if not graph_path.is_file():
        return [], diag

    diag["enabled"] = True
    fp = _fingerprint(graph_path, model)
    cache_path = run_dir_path / _CACHE_FILE
    meta_path = run_dir_path / _META_FILE

    texts: List[str] = []
    ids: List[str] = []
    for n in nodes:
        nid = str(n.get("id", ""))
        if not nid:
            continue
        ids.append(nid)
        texts.append(build_node_embed_text(dict(n)))

    if not ids:
        diag["reason"] = "no nodes"
        return [], diag

    meta_ok = False
    if cache_path.is_file() and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict) and meta.get("mtime_ns") == fp["mtime_ns"] and meta.get("model") == model:
                meta_ok = True
        except (OSError, json.JSONDecodeError):
            meta_ok = False

    try:
        if meta_ok:
            loaded = np.load(cache_path, allow_pickle=True)
            arr_ids = loaded["ids"]
            emb = np.asarray(loaded["emb"], dtype=np.float32)
            id_list = [str(x) for x in arr_ids.tolist()]
            if len(id_list) != emb.shape[0]:
                raise ValueError("cache shape mismatch")
        else:
            logger.info(
                "GraphRAG: building embedding cache nodes=%d model=%s",
                len(texts),
                model,
            )
            vectors = embed_texts_openai_compatible(texts, base_url=base, api_key=key, model=model)
            emb = np.asarray(vectors, dtype=np.float32)
            np.savez_compressed(cache_path, ids=np.asarray(ids, dtype=object), emb=emb)
            meta_path.write_text(json.dumps({**fp, "node_count": len(ids)}, indent=2) + "\n", encoding="utf-8")
            id_list = ids
    except Exception as exc:
        logger.warning("GraphRAG embedding cache failed: %s", exc)
        diag["reason"] = str(exc)
        return [], diag

    try:
        qvec_list = embed_texts_openai_compatible([query.strip()], base_url=base, api_key=key, model=model)
        q = np.asarray(qvec_list[0], dtype=np.float32)
    except Exception as exc:
        logger.warning("GraphRAG query embedding failed: %s", exc)
        diag["reason"] = str(exc)
        return [], diag

    picked = rank_node_ids_by_cosine(emb, q, id_list, top_k=top_k)
    emb_n = _l2_normalize_rows(np.asarray(emb, dtype=np.float32, copy=False))
    q_n = _l2_normalize_rows(np.asarray(q, dtype=np.float32).reshape(1, -1))
    sims = (emb_n @ q_n.T).ravel()
    score_by_id = {id_list[i]: float(sims[i]) for i in range(len(id_list))}
    diag["cache_hit"] = meta_ok
    diag["model"] = model
    diag["top_scores"] = [score_by_id[p] for p in picked[:5] if p in score_by_id]
    return picked, diag
