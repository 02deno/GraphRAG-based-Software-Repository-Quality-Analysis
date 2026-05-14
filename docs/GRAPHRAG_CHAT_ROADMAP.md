# GraphRAG chat — future retrieval and media

This note captures planned directions after the current **lexical** source index (``graphrag_source_chunks.jsonl``: Python ``File`` nodes, repo-wide ``*.md``, and virtual ``_analysis/*`` metrics/text from the same run), optional **dense embedding seeds** (`graphrag_embedding_cache.npz` per run), and **automatic session fork** (`GRAPHRAG_CHAT_AUTO_SUMMARY_AT_CHARS` / `POST /graphrag/api/<run_dir>/sessions/fork`).

## Vector index and storage

When embedding-based retrieval becomes a first-class requirement:

- **Keep the same logical index** (chunk ids, paths, line spans, scores) but back the vector leg with a **dedicated store**: [Qdrant](https://qdrant.tech/), [Chroma](https://www.trychroma.com/), or **pgvector** in PostgreSQL, instead of—or in addition to—loading vectors only from `graphrag_embedding_cache.npz`.
- **Offline / analysis artifacts**: mirror today’s `graphrag_embedding_cache.npz` pattern with versioned sidecars (e.g. `graphrag_analysis_embeddings.jsonl` or `.npz`) for **analysis text** (metrics paragraphs, chart captions, structured `analysis_view` snippets) so chat retrieval can fuse **code chunks** + **analysis chunks** without re-embedding on every request.

Design constraints to preserve:

- Run-scoped data under `results/<run_dir>/` (or explicit DB namespaces keyed by `run_dir`).
- Diagnostics in API responses (`source_context_diagnostics`, `included_chunks`) should stay aligned with whatever the LLM actually receives.

## Images in answers

- Extend retrieval payloads with an optional **`image_url`** (or list) when a hit ties to a **chart PNG** or other allowed static asset URL (same-origin paths served by the app are easiest to reason about for CSP and hygiene).
- **System prompt**: instruct the model to surface those URLs to the user (e.g. Markdown `![…](url)`), not to invent URLs.
- **UI**: keep rendering behind **Markdown + sanitization** (e.g. `marked` + `DOMPurify`) with a strict allowlist for `img` `src` (https + same-origin relative paths as configured).

This path favors **text + URL** over embedding raw image pixels unless a product requirement explicitly asks for multimodal models.
