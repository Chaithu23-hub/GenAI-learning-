"""POST /api/mcp/lookup"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from legal_rag.application.workflows import MCPLookupService
from legal_rag.composition import Container
from legal_rag.interfaces.http.dependencies import (
    get_container,
    get_mcp_lookup_service,
    verify_api_key,
)
from legal_rag.interfaces.http.schemas import MCPLookupRequest

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.post("/lookup", summary="Discover MCP tools and look up a contract")
async def lookup_contract_via_mcp(
    request: MCPLookupRequest,
    _: Annotated[str, Depends(verify_api_key)],
    service: Annotated[MCPLookupService, Depends(get_mcp_lookup_service)],
    container: Annotated[Container, Depends(get_container)],
) -> dict:
    return await container.work_executor.run(lambda: service.lookup_contract(request.contract_id))
