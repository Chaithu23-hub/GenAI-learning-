"""MCP server: contract repository lookup."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from legal_rag.application.workflows.corpus_lookup import CorpusLookupService

mcp = FastMCP("contract-repository")
_lookup: CorpusLookupService | None = None


def configure(lookup: CorpusLookupService) -> None:
    """Install the service supplied by the MCP interface's startup Container."""
    global _lookup
    _lookup = lookup


@mcp.tool()
def lookup_contract(contract_id: str) -> dict:
    """Look up a source-backed contract record and metadata."""
    return (
        _lookup.lookup_contract(contract_id) if _lookup else {"error": "corpus_lookup_unavailable"}
    )


@mcp.tool()
def get_effective_date(contract_id: str) -> dict:
    """Return only the effective date metadata present in the current corpus."""
    return (
        _lookup.get_effective_date(contract_id)
        if _lookup
        else {"error": "corpus_lookup_unavailable"}
    )


@mcp.tool()
def get_amendment_chain(contract_id: str) -> dict:
    """Return documents explicitly linked to this contract by source metadata."""
    return (
        _lookup.get_amendment_chain(contract_id)
        if _lookup
        else {"error": "corpus_lookup_unavailable"}
    )


if __name__ == "__main__":
    from legal_rag.composition import Container

    configure(Container().corpus_lookup_service)
    mcp.run()
