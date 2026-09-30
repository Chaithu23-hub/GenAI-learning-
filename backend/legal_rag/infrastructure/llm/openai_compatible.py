"""OpenAI-compatible chat client (works with Google Gemini's OpenAI shim).

Wraps ``openai.OpenAI`` behind the ``LLMClient`` port so services never touch
the vendor SDK directly.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from legal_rag.infrastructure.errors import (
    LLMBackendError,
    PermanentLLMError,
    TransientLLMError,
)
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class OpenAICompatibleClient:
    """Concrete ``LLMClient`` using the OpenAI Python SDK."""

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
        self._base_url = base_url
        self._api_key = api_key

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

    def list_models(self) -> list[str]:
        # Use the SDK so auth headers, retries and provider quirks are handled
        # for us; fall back to a raw urllib probe only when the SDK path errors.
        try:
            models = self._client.models.list()
            return [m.id for m in getattr(models, "data", models) if getattr(m, "id", None)]
        except Exception:  # noqa: BLE001
            pass
        if not self._base_url:
            return []
        req = urllib.request.Request(
            self._base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if not (200 <= resp.status < 300):
                    return []
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return []
        return [item.get("id") for item in data.get("data", []) if item.get("id")]


def detect_llm_model(client: OpenAICompatibleClient) -> str | None:
    """Probe the endpoint and return either the configured model or an available fallback."""
    names = client.list_models()
    if client.model in names:
        return client.model
    if names:
        log.warning(
            "configured model not available; using fallback",
            extra={"configured": client.model, "fallback": names[0]},
        )
        return names[0]
    return None
