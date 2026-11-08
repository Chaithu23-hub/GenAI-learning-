"""MCP failure/deadline tests with fake contexts, without subprocesses or files."""

import asyncio
import contextlib
from pathlib import Path
from types import SimpleNamespace

import mcp
import mcp.client.stdio
import pytest

from legal_rag.infrastructure.errors import MCPTransportError
from legal_rag.infrastructure.mcp import stdio_host


@pytest.mark.asyncio
async def test_failed_startup_closes_all_entered_contexts(monkeypatch):
    closed = []

    @contextlib.asynccontextmanager
    async def transport(params):
        try:
            yield object(), object()
        finally:
            closed.append("transport")

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.append("session")

        async def initialize(self):
            raise MCPTransportError("Initialization failed")

    monkeypatch.setattr(mcp, "ClientSession", Session)
    monkeypatch.setattr(mcp.client.stdio, "stdio_client", transport)
    host = object.__new__(stdio_host.StdioMCPHost)
    host.config_path = Path("unused.json")
    host.config = {"servers": [{"name": "test", "args": []}]}
    host._stack = contextlib.AsyncExitStack()
    host.sessions, host.discovered = {}, {}
    try:
        with pytest.raises(MCPTransportError):
            await host.__aenter__()
        assert closed == ["session", "transport"]
        assert host.sessions == host.discovered == {}
    finally:
        await host._stack.aclose()


@pytest.mark.parametrize("stage", ["startup", "call"])
def test_lookup_deadline_closes_host_and_returns_capacity(monkeypatch, stage):
    closed = []

    class Host:
        discovered = {"contract-repository": ["lookup_contract"]}

        def __init__(self, *args):
            pass

        async def __aenter__(self):
            if stage == "startup":
                await asyncio.Event().wait()
            return self

        async def __aexit__(self, *args):
            closed.append(True)

        async def call(self, *args):
            await asyncio.Event().wait()

    monkeypatch.setattr(stdio_host, "StdioMCPHost", Host)
    with pytest.raises(MCPTransportError, match="deadline"):
        stdio_host.run_lookup(Path("unused"), "synthetic", timeout_seconds=0.02)
    if stage == "call":
        assert closed == [True]


def test_lookup_service_depends_on_port_only():
    from legal_rag.application.workflows.mcp_lookup import MCPLookupService

    calls = []

    def lookup(contract_id):
        calls.append(contract_id)
        return {"contract_id": contract_id}

    service = MCPLookupService(lookup=SimpleNamespace(lookup_contract=lookup))
    assert service.lookup_contract("MSA-2026-014") == {"contract_id": "MSA-2026-014"}
    assert calls == ["MSA-2026-014"]
