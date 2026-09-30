"""POST /api/mcp/lookup"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from legal_rag.application.workflows import MCPLookupService
from legal_rag.interfaces.http.dependencies import get_mcp_lookup_service, verify_api_key
from legal_rag.interfaces.http.schemas import MCPLookupRequest

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.post("/lookup", summary="Discover MCP tools and look up a contract")
def lookup_contract_via_mcp(
    request: MCPLookupRequest,
    _: str = Depends(verify_api_key),
    service: MCPLookupService = Depends(get_mcp_lookup_service),
) -> dict:
    return service.lookup_contract(request.contract_id)
