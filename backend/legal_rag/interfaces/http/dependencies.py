"""FastAPI DI wiring — everything resolves via the composition Container."""

from __future__ import annotations

from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from legal_rag.application.workflows import (
    IngestionService,
    MCPLookupService,
    QaService,
)
from legal_rag.composition import Container

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_qa_service(container: Annotated[Container, Depends(get_container)]) -> QaService:
    return container.qa_service


def get_ingestion_service(
    container: Annotated[Container, Depends(get_container)],
) -> IngestionService:
    return container.ingestion_service


def get_mcp_lookup_service(
    container: Annotated[Container, Depends(get_container)],
) -> MCPLookupService:
    return container.mcp_lookup_service


def get_agent_factory(container: Annotated[Container, Depends(get_container)]):
    return container.new_legal_agent


def get_fixed_factory(container: Annotated[Container, Depends(get_container)]):
    return container.new_fixed_workflow


async def verify_api_key(
    container: Annotated[Container, Depends(get_container)],
    api_key: Annotated[str | None, Security(_API_KEY_HEADER)] = None,
) -> str:
    settings = container.settings
    if settings.development_mode and not settings.api_key_value:
        return "dev"
    supplied = (api_key or "").encode("utf-8")
    reader_matches = compare_digest(supplied, settings.api_key_value.encode("utf-8"))
    admin_matches = compare_digest(supplied, settings.admin_api_key_value.encode("utf-8"))
    if not api_key or not (reader_matches or admin_matches):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


async def verify_admin_api_key(
    container: Annotated[Container, Depends(get_container)],
    api_key: Annotated[str | None, Security(_API_KEY_HEADER)] = None,
) -> str:
    configured = container.settings.admin_api_key_value
    if (
        not configured
        or not api_key
        or not compare_digest(
            api_key.encode("utf-8"),
            configured.encode("utf-8"),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing administrator API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
