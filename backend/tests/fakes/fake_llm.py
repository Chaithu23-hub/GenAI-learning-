"""Fake LLM client used by service tests."""
from __future__ import annotations

import json
from typing import Any


class FakeLLMClient:
    """Scripted responses; records every call for assertion."""

    def __init__(
        self,
        *,
        responses: list[dict[str, Any]] | None = None,
        model: str = "fake-model",
    ):
        self._responses = list(responses or [])
        self._model = model
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


class ContextLLMClient(FakeLLMClient):
    """Test-only model double that cites the supplied context without network I/O."""

    def __init__(self, out_of_scope_answer: str):
        super().__init__()
        self._out_of_scope_answer = out_of_scope_answer

    def chat(self, *, messages, tools=None, temperature=0.0):
        self.calls.append({"messages": list(messages), "tools": tools, "temperature": temperature})
        content = messages[1]["content"]
        marker = "Retrieved document chunks (cite ONLY these chunk_ids in sources):\n"
        if marker not in content:
            return {"content": '{"route":"documents","answer":""}', "tool_calls": []}
        chunks, _ = json.JSONDecoder().raw_decode(content.split(marker, 1)[1])
        payload = {
            "answer": "The retrieved passages provide the contract terms." if chunks else self._out_of_scope_answer,
            "reasoning": "Test model response from supplied context.",
            "sources": [{key: c[key] for key in ("document", "chunk_id", "excerpt")} for c in chunks],
            "confidence": "medium" if chunks else "low",
            "out_of_scope": not chunks,
        }
        return {"content": json.dumps(payload), "tool_calls": []}
