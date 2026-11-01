"""Groq chat adapter using the OpenAI-compatible SDK transport."""
from __future__ import annotations

from typing import Any

from legal_rag.infrastructure.errors import (
    PermanentLLMError,
    TransientLLMError,
)
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class GroqClient:
    """Groq implementation of the LLMClient port."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise PermanentLLMError("openai package not installed") from exc
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        try:
            kwargs = {"model": self._model, "messages": messages, "temperature": temperature}
            if tools:
                kwargs["tools"] = tools
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            # Best-effort transient/permanent classification.
            text = str(exc).lower()
            if any(k in text for k in ("timeout", "rate limit", "429", "503", "502", "500")):
                raise TransientLLMError(str(exc)) from exc
            raise PermanentLLMError(str(exc)) from exc

        message = response.choices[0].message
        usage = getattr(response, "usage", None)
        payload = {
            "content": message.content,
            "tool_calls": [
                {"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"}
                for c in (message.tool_calls or [])
            ],
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
            },
        }
        log.debug("llm chat", extra={"model": self._model, "usage": payload["usage"]})
        return payload
