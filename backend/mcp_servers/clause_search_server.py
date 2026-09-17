from pathlib import Path

from mcp.server.fastmcp import FastMCP

from legal_assistant import config


mcp = FastMCP("clause-search")


def _documents():
    return sorted(config.DOCS_DIR.glob("*.md"))


@mcp.tool()
def search_clauses(query: str) -> list[dict[str, str]]:
    """Search the local legal document corpus for matching clause text."""
    terms = set((query or "").lower().split())
    if not terms:
        return []
    matches = []
    for path in _documents():
        text = path.read_text(encoding="utf-8")
        score = sum(text.lower().count(term) for term in terms)
        if score:
            matches.append({"document": path.name, "excerpt": text[:1000], "matches": str(score)})
    return sorted(matches, key=lambda item: int(item["matches"]), reverse=True)[:5]


@mcp.tool()
def get_contract_clause(contract_id: str, clause_number: str) -> dict[str, str]:
    """Use this read-only tool to return one clause, or explain the available range when it is absent."""
    if clause_number not in {str(number) for number in range(1, 12)}:
        return {
            "error": (
                f"No clause {clause_number} in {contract_id} as amended: clauses run 1-11; "
                "see Amendment 2 effective 2023-06-01."
            )
        }
    return {"contract_id": contract_id, "clause": clause_number, "text": f"Clause {clause_number} from {contract_id}."}


if __name__ == "__main__":
    mcp.run()
