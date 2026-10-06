"""GET /api/health"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from legal_rag import __version__
from legal_rag.composition import Container
from legal_rag.infrastructure.prompts import snapshot as prompt_snapshot
from legal_rag.interfaces.http.dependencies import get_container, verify_api_key
from legal_rag.interfaces.http.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health(
    _: Annotated[str, Depends(verify_api_key)],
    container: Annotated[Container, Depends(get_container)],
) -> HealthResponse:
    s = container.settings
    return HealthResponse(
        status="ok",
        version=__version__,
        embedding_model=s.embedding_model,
        rerank_model=s.rerank_model,
        llm_provider=s.llm_provider,
        llm_model=s.llm_model,
        vector_store_path=str(s.chroma_dir),
        api_key_configured=bool(s.api_key_value),
        prompt_versions=prompt_snapshot(),
    )
