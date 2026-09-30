"""MCP discovery + tool call service (thin wrapper over the host adapter)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from legal_rag.infrastructure.mcp import run_lookup


class MCPLookupService:
    def __init__(self, *, mcp_config_path: Path):
        self._config_path = mcp_config_path

    def lookup_contract(self, contract_id: str) -> dict[str, Any]:
        return run_lookup(self._config_path, contract_id)
