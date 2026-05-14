"""HTTP client for OpenAI-compatible ``/chat/completions`` endpoints (incl. Ollama)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping, Sequence

import httpx


class OpenAICompatibleChatClient:
    """Call ``POST /chat/completions`` on an OpenAI-compatible base URL."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 300.0,
    ) -> None:
        """Store connection parameters for chat completions.

        Args:
            base_url: API root including ``/v1`` when required (e.g. OpenAI or Ollama).
            api_key: Bearer token; may be empty for local servers that omit auth.
            model: Model id accepted by the upstream server.
            timeout_s: HTTP read/write timeout in seconds (raise with ``GRAPHRAG_CHAT_TIMEOUT_S`` for slow local models).
        """
        normalized = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._client = httpx.Client(base_url=normalized, timeout=timeout_s)

    def complete_chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Return assistant text from a chat completion response."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [dict(m) for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = self._client.post("/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("chat completion returned no choices")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is None or str(content).strip() == "":
            raise RuntimeError("chat completion returned empty assistant content")
        return str(content).strip()

    def stream_chat_completion(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Yield assistant text fragments from a streaming ``POST /chat/completions``.

        OpenAI-compatible servers (including Ollama ``/v1``) return ``text/event-stream``
        lines of the form ``data: { ... "choices":[{"delta":{"content":"..."}}] ... }``.

        Yields:
            Non-empty text fragments as they arrive.

        Raises:
            RuntimeError: If the stream ends without any assistant text or an API error object appears.
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [dict(m) for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        yielded_any = False
        with self._client.stream(
            "POST",
            "/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                line_st = line.strip() if isinstance(line, str) else line.decode("utf-8", errors="replace").strip()
                if not line_st:
                    continue
                if not line_st.startswith("data:"):
                    continue
                data_s = line_st[5:].strip()
                if data_s == "[DONE]":
                    break
                try:
                    data = json.loads(data_s)
                except json.JSONDecodeError:
                    continue
                err = data.get("error")
                if err:
                    if isinstance(err, dict):
                        msg = str(err.get("message") or err)
                    else:
                        msg = str(err)
                    raise RuntimeError(msg)
                choices = data.get("choices") or []
                if not choices:
                    continue
                ch0 = choices[0] if isinstance(choices[0], dict) else {}
                delta = ch0.get("delta") if isinstance(ch0.get("delta"), dict) else {}
                piece = delta.get("content")
                if piece is None:
                    msg_obj = ch0.get("message")
                    if isinstance(msg_obj, dict):
                        piece = msg_obj.get("content")
                if piece:
                    yielded_any = True
                    yield str(piece)
        if not yielded_any:
            raise RuntimeError("stream ended without assistant content")

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()


def load_chat_client_from_env() -> OpenAICompatibleChatClient:
    """Build a client from ``GRAPHRAG_*`` environment variables.

    Returns:
        Configured :class:`OpenAICompatibleChatClient`.

    Raises:
        ValueError: When required variables are missing or blank.
    """
    base = os.environ.get("GRAPHRAG_OPENAI_BASE_URL", "").strip()
    model = os.environ.get("GRAPHRAG_CHAT_MODEL", "").strip()
    key = os.environ.get("GRAPHRAG_OPENAI_API_KEY", "").strip()
    if not base or not model:
        raise ValueError(
            "GraphRAG LLM requires GRAPHRAG_OPENAI_BASE_URL and GRAPHRAG_CHAT_MODEL "
            "(set GRAPHRAG_OPENAI_API_KEY for hosted APIs; optional for local Ollama)."
        )
    raw_timeout = os.environ.get("GRAPHRAG_CHAT_TIMEOUT_S", "").strip()
    timeout_s = 300.0
    if raw_timeout:
        try:
            parsed = float(raw_timeout)
            if parsed > 0:
                timeout_s = parsed
        except ValueError:
            pass
    return OpenAICompatibleChatClient(base_url=base, api_key=key, model=model, timeout_s=timeout_s)
