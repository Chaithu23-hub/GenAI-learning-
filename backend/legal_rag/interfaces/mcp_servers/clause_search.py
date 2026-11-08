"""MCP server: search local legal clauses."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from legal_rag.application.workflows.corpus_lookup import CorpusLookupService

mcp = FastMCP("clause-search")
_lookup: CorpusLookupService | None = None


def configure(lookup: CorpusLookupService) -> None:
    """Install the service supplied by the MCP interface's startup Container."""
    global _lookup
    _lookup = lookup


@mcp.tool()
def search_clauses(query: str) -> list[dict[str, Any]]:
    """Search the local legal document corpus for matching clause text."""
    return _lookup.search_clauses(query) if _lookup else []


@mcp.tool()
def get_contract_clause(contract_id: str, clause_number: str) -> dict[str, Any]:
    """Return an exact corpus clause, or a not-found/ambiguity result."""
    if _lookup is None:
        return {"error": "corpus_lookup_unavailable"}
    return _lookup.get_contract_clause(contract_id, clause_number)


if __name__ == "__main__":
    from legal_rag.composition import Container

    configure(Container().corpus_lookup_service)
    mcp.run()
