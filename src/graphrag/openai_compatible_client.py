"""HTTP client for OpenAI-compatible ``/chat/completions`` endpoints (incl. Ollama)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def _assistant_message_visible_text(msg: Mapping[str, object] | dict[str, object]) -> str | None:
    """Return user-visible assistant text from a ``choices[0].message`` object.

    Some providers (e.g. Ollama Cloud on certain models) put the visible reply in
    ``reasoning`` while leaving ``content`` empty until a finalization step; treat
    non-empty ``reasoning`` as a fallback so GraphRAG does not fail on HTTP 200.
    """
    if not isinstance(msg, dict):
        return None
    for key in ("content", "reasoning", "thinking"):
        val = msg.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s:
            return s
    return None


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
        parsed = urlparse(normalized if "://" in normalized else f"http://{normalized}")
        self._log_host = parsed.netloc or normalized or "unknown"

    def complete_chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
        response_format_json_object: bool = False,
    ) -> str:
        """Return assistant text from a chat completion response.

        Args:
            messages: OpenAI-style chat messages (role + content strings).
            max_tokens: Optional cap on generated tokens.
            temperature: Sampling temperature.
            response_format_json_object: When True, sends OpenAI ``response_format`` JSON object mode
                (supported on ``api.openai.com``; other servers may ignore or reject the field).
        """
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
        if response_format_json_object:
            payload["response_format"] = {"type": "json_object"}
        logger.info(
            "chat_completions POST /chat/completions host=%s model=%s messages=%d "
            "max_tokens=%s temperature=%s json_object=%s api_key_set=%s",
            self._log_host,
            self._model,
            len(messages),
            max_tokens,
            temperature,
            response_format_json_object,
            bool(self._api_key),
        )
        try:
            response = self._client.post("/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            preview = ""
            if exc.response is not None:
                try:
                    preview = (exc.response.text or "")[:800]
                except OSError:
                    preview = ""
            logger.warning(
                "chat_completions HTTP error host=%s model=%s status=%s body_preview=%r",
                self._log_host,
                self._model,
                exc.response.status_code if exc.response else None,
                preview,
            )
            raise
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            logger.error("chat_completions no choices host=%s model=%s", self._log_host, self._model)
            raise RuntimeError("chat completion returned no choices")
        ch0 = choices[0] if isinstance(choices[0], dict) else {}
        msg = ch0.get("message") or {}
        text = _assistant_message_visible_text(msg if isinstance(msg, dict) else {})
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        c_raw = msg.get("content") if isinstance(msg, dict) else None
        r_raw = msg.get("reasoning") if isinstance(msg, dict) else None
        t_raw = msg.get("thinking") if isinstance(msg, dict) else None
        if not text:
            logger.error(
                "chat_completions empty assistant host=%s model=%s finish_reason=%s "
                "message_keys=%s content_len=%s reasoning_len=%s thinking_len=%s usage=%s",
                self._log_host,
                self._model,
                ch0.get("finish_reason"),
                sorted(msg.keys()) if isinstance(msg, dict) else None,
                len(str(c_raw or "")),
                len(str(r_raw or "")),
                len(str(t_raw or "")),
                usage,
            )
            raise RuntimeError("chat completion returned empty assistant content")
        logger.info(
            "chat_completions response host=%s model=%s reply_chars=%d finish_reason=%s "
            "content_nonempty=%s reasoning_nonempty=%s thinking_nonempty=%s usage=%s",
            self._log_host,
            self._model,
            len(text),
            ch0.get("finish_reason"),
            bool(c_raw and str(c_raw).strip()),
            bool(r_raw and str(r_raw).strip()),
            bool(t_raw and str(t_raw).strip()),
            usage,
        )
        return text

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
        logger.info(
            "chat_completions stream POST /chat/completions host=%s model=%s messages=%d "
            "max_tokens=%s temperature=%s api_key_set=%s",
            self._log_host,
            self._model,
            len(messages),
            max_tokens,
            temperature,
            bool(self._api_key),
        )
        yielded_any = False
        streamed_chars = 0
        with self._client.stream(
            "POST",
            "/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                preview = ""
                if exc.response is not None:
                    try:
                        preview = (exc.response.text or "")[:800]
                    except OSError:
                        preview = ""
                logger.warning(
                    "chat_completions stream HTTP error host=%s model=%s status=%s body_preview=%r",
                    self._log_host,
                    self._model,
                    exc.response.status_code if exc.response else None,
                    preview,
                )
                raise
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
                if piece is None or (isinstance(piece, str) and not piece.strip()):
                    piece = delta.get("reasoning")
                if piece is None or (isinstance(piece, str) and not str(piece).strip()):
                    piece = delta.get("thinking")
                if piece is None:
                    msg_obj = ch0.get("message")
                    if isinstance(msg_obj, dict):
                        piece = msg_obj.get("content")
                        if piece is None or (isinstance(piece, str) and not str(piece).strip()):
                            piece = msg_obj.get("reasoning")
                        if piece is None or (isinstance(piece, str) and not str(piece).strip()):
                            piece = msg_obj.get("thinking")
                if piece:
                    yielded_any = True
                    frag = str(piece)
                    streamed_chars += len(frag)
                    yield frag
        if not yielded_any:
            logger.error(
                "chat_completions stream ended with no assistant text host=%s model=%s",
                self._log_host,
                self._model,
            )
            raise RuntimeError("stream ended without assistant content")
        logger.info(
            "chat_completions stream done host=%s model=%s yielded_chars=%d",
            self._log_host,
            self._model,
            streamed_chars,
        )

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
    client = OpenAICompatibleChatClient(base_url=base, api_key=key, model=model, timeout_s=timeout_s)
    logger.info(
        "OpenAI-compatible chat client ready host=%s model=%s timeout_s=%s api_key_set=%s",
        client._log_host,
        model,
        timeout_s,
        bool(key),
    )
    return client
