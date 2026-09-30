"""FastAPI DI wiring — everything resolves via the composition Container."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from legal_rag.application.agents import (LegalAgent)
from legal_rag.application.workflows import (IngestionService, JudgeService, MCPLookupService, QaService)
from legal_rag.application.agents.legal_agent import FixedWorkflow, compare_strategies
from legal_rag.composition import Container

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_qa_service(container: Container = Depends(get_container)) -> QaService:
    return container.qa_service


def get_ingestion_service(
    container: Container = Depends(get_container),
) -> IngestionService:
    return container.ingestion_service


def get_mcp_lookup_service(
    container: Container = Depends(get_container),
) -> MCPLookupService:
    return container.mcp_lookup_service


def get_agent_factory(container: Container = Depends(get_container)):
    return container.new_legal_agent


def get_fixed_factory(container: Container = Depends(get_container)):
    return container.new_fixed_workflow


def get_judge_service(container: Container = Depends(get_container)) -> JudgeService:
    return container.judge_service


async def verify_api_key(
    api_key: str | None = Security(_API_KEY_HEADER),
    container: Container = Depends(get_container),
) -> str:
    configured = container.settings.api_key_value
    if not configured:
        return "dev"
    if not api_key or api_key != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
