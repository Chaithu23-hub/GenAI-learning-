"""MCP discovery + tool call service (thin wrapper over the host adapter)."""

from __future__ import annotations

from typing import Any

from legal_rag.application.ports import ContractLookup


class MCPLookupService:
    def __init__(self, *, lookup: ContractLookup):
        self._lookup = lookup

    def lookup_contract(self, contract_id: str) -> dict[str, Any]:
        return self._lookup.lookup_contract(contract_id)
