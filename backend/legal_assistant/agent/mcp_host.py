import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "mcp_servers.json"


class MCPHost:
    """Async context manager that connects to all MCP servers defined in mcp_servers.json."""

    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self._stack = contextlib.AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}
        self.discovered: dict[str, list[str]] = {}

    async def __aenter__(self):
        await self._stack.__aenter__()
        for server in self.config["servers"]:
            params = StdioServerParameters(
                command=sys.executable,
                args=server["args"],
                cwd=str(CONFIG_PATH.parent),
            )
            read_stream, write_stream = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            tools = await session.list_tools()
            self.sessions[server["name"]] = session
            self.discovered[server["name"]] = [tool.name for tool in tools.tools]
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return await self._stack.__aexit__(exc_type, exc_value, traceback)

    async def call(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self.discovered.get(server_name, []):
            raise ValueError(f"Tool {tool_name} was not discovered from {server_name}.")
        result = await self.sessions[server_name].call_tool(tool_name, arguments)
        return {
            "server": server_name,
            "tool": tool_name,
            "content": [item.model_dump() if hasattr(item, "model_dump") else item for item in result.content],
        }


async def discover_and_lookup(contract_id: str) -> dict[str, Any]:
    async with MCPHost() as host:
        tool_name = next(name for name in host.discovered["contract-repository"] if name == "lookup_contract")
        result = await host.call("contract-repository", tool_name, {"contract_id": contract_id})
        return {"discovered": host.discovered, "trace": result}


async def discover_config(config_path: Path = CONFIG_PATH) -> dict[str, list[str]]:
    async with MCPHost(config_path) as host:
        return host.discovered


def run_lookup(contract_id: str) -> dict[str, Any]:
    return asyncio.run(discover_and_lookup(contract_id))
