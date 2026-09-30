"""Stdio-based MCP host adapter.

Spawns each configured server as a subprocess, initialises the session,
lists tools, and forwards tool calls. Async context manager.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from legal_rag.infrastructure.errors import MCPTransportError
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class StdioMCPHost:
    """Concrete ``MCPHost`` using the stdio transport."""

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path).resolve()
        try:
            self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MCPTransportError(f"mcp config not found: {self.config_path}") from exc
        self._stack = contextlib.AsyncExitStack()
        self.sessions: dict[str, Any] = {}
        self.discovered: dict[str, list[str]] = {}

    async def __aenter__(self) -> "StdioMCPHost":
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # pragma: no cover
            raise MCPTransportError("mcp package not installed") from exc

        await self._stack.__aenter__()
        for server in self.config["servers"]:
            params = StdioServerParameters(
                command=sys.executable,
                args=server["args"],
                cwd=str(self.config_path.parent),
            )
            read_stream, write_stream = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            tools = await session.list_tools()
            self.sessions[server["name"]] = session
            self.discovered[server["name"]] = [tool.name for tool in tools.tools]
            log.info(
                "mcp server discovered",
                extra={"server": server["name"], "tools": self.discovered[server["name"]]},
            )
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return await self._stack.__aexit__(exc_type, exc_value, traceback)

    async def discover(self) -> dict[str, list[str]]:
        return dict(self.discovered)

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool not in self.discovered.get(server, []):
            raise MCPTransportError(f"tool {tool} was not discovered from {server}")
        result = await self.sessions[server].call_tool(tool, arguments)
        content_items = result.content or []
        return {
            "server": server,
            "tool": tool,
            "content": [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in content_items
            ],
        }


# ─── Convenience blocking helpers used by CLI + FastAPI (sync path) ─────


async def discover_config(config_path: Path) -> dict[str, list[str]]:
    async with StdioMCPHost(config_path) as host:
        return await host.discover()


def run_lookup(config_path: Path, contract_id: str) -> dict[str, Any]:
    async def _lookup() -> dict[str, Any]:
        async with StdioMCPHost(config_path) as host:
            tools = host.discovered.get("contract-repository", [])
            tool_name = next(
                (name for name in tools if name == "lookup_contract"), None,
            )
            if tool_name is None:
                raise MCPTransportError(
                    "contract-repository server did not advertise lookup_contract; "
                    f"discovered tools: {tools}"
                )
            trace = await host.call("contract-repository", tool_name, {"contract_id": contract_id})
            return {"discovered": await host.discover(), "trace": trace}

    return asyncio.run(_lookup())
