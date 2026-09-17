import asyncio
from pathlib import Path

from legal_assistant.agent.mcp_host import MCPHost, discover_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_before_and_after_tool_discovery():
    before = asyncio.run(discover_config(PROJECT_ROOT / "mcp_servers.before.json"))
    after = asyncio.run(discover_config(PROJECT_ROOT / "mcp_servers.json"))

    assert before["clause-search"] == ["search_clauses", "get_contract_clause"]
    assert after["contract-repository"] == [
        "lookup_contract",
        "get_effective_date",
        "get_amendment_chain",
    ]


def test_second_server_tool_call_is_discovered():
    async def call():
        async with MCPHost() as host:
            assert "lookup_contract" in host.discovered["contract-repository"]
            return await host.call(
                "contract-repository",
                "lookup_contract",
                {"contract_id": "MSA-2021-0142"},
            )

    result = asyncio.run(call())
    assert result["tool"] == "lookup_contract"
    assert "2021-01-14" in result["content"][0]["text"]
