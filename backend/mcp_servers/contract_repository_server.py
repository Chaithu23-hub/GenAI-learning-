from mcp.server.fastmcp import FastMCP


mcp = FastMCP("contract-repository")

_CONTRACTS = {
    "MSA-2021-0142": {
        "contract_id": "MSA-2021-0142",
        "effective_date": "2021-01-14",
        "amendments": [
            {"id": "AM-2023-02", "effective_date": "2023-06-01", "status": "executed"}
        ],
        "clauses": {str(number): f"MSA-2021-0142 clause {number} is present in the executed agreement." for number in range(1, 12)},
    }
}


@mcp.tool()
def lookup_contract(contract_id: str) -> dict[str, str | list[dict[str, str]]]:
    """Look up one contract by its repository identifier and return its effective date and amendments."""
    contract = _CONTRACTS.get(contract_id)
    if not contract:
        return {"error": f"Contract {contract_id} was not found; check the repository identifier."}
    return {
        "contract_id": contract["contract_id"],
        "effective_date": contract["effective_date"],
        "amendments": contract["amendments"],
    }


@mcp.tool()
def get_effective_date(contract_id: str) -> dict[str, str]:
    """Return the executed effective date for one contract identifier."""
    contract = _CONTRACTS.get(contract_id)
    if not contract:
        return {"error": f"No effective date exists for {contract_id}; verify the contract identifier."}
    return {"contract_id": contract_id, "effective_date": contract["effective_date"]}


@mcp.tool()
def get_amendment_chain(contract_id: str) -> dict[str, str | list[dict[str, str]]]:
    """Return the executed amendment chain for one contract identifier."""
    contract = _CONTRACTS.get(contract_id)
    if not contract:
        return {"error": f"No amendment chain exists for {contract_id}; verify the contract identifier."}
    return {"contract_id": contract_id, "amendments": contract["amendments"]}


if __name__ == "__main__":
    mcp.run()
