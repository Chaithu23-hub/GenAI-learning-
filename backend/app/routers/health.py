from fastapi import APIRouter, Depends

from legal_assistant import config
from ..dependencies import verify_api_key
from ..models.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health(_: str = Depends(verify_api_key)) -> HealthResponse:
    """Return backend configuration status and readiness information."""
    return HealthResponse(
        status="ok",
        embedding_model=config.EMBEDDING_MODEL,
        rerank_model=config.RERANK_MODEL,
        llm_provider=config.LLM_PROVIDER,
        llm_model=config.LLM_MODEL,
        vector_store_path=str(config.CHROMA_DIR),
        api_key_configured=bool(config.API_KEY),
    )
