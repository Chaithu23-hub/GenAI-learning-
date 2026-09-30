"""Fake LLM client used by service tests."""
from __future__ import annotations

from typing import Any


class FakeLLMClient:
    """Scripted responses; records every call for assertion."""

    def __init__(
        self,
        *,
        responses: list[dict[str, Any]] | None = None,
        model: str = "fake-model",
        models: list[str] | None = None,
    ):
        self._responses = list(responses or [])
        self._model = model
        self._models = models if models is not None else [model]
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append({"messages": messages, "tools": tools, "temperature": temperature})
        if not self._responses:
            return {
                "content": "{}",
                "tool_calls": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        response = self._responses.pop(0)
        response.setdefault("tool_calls", [])
        response.setdefault(
            "usage",
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        return response

    def list_models(self) -> list[str]:
        return list(self._models)
