"""Fake MCP host — no subprocesses, records calls."""
from __future__ import annotations

from typing import Any


class FakeMCPHost:
    def __init__(
        self,
        *,
        discovered: dict[str, list[str]] | None = None,
        tool_responses: dict[tuple[str, str], dict[str, Any]] | None = None,
    ):
        self._discovered = discovered or {
            "clause-search": ["search_clauses", "get_contract_clause"],
            "contract-repository": ["lookup_contract", "get_effective_date", "get_amendment_chain"],
        }
        self._tool_responses = tool_responses or {}
        self.calls: list[dict[str, Any]] = []

    async def discover(self) -> dict[str, list[str]]:
        return dict(self._discovered)

    async def call(
        self, server: str, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({"server": server, "tool": tool, "arguments": arguments})
        return {
            "server": server, "tool": tool,
            "content": [self._tool_responses.get((server, tool), {"ok": True})],
        }
