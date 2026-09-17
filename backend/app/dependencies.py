from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from legal_assistant import config

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> str:
    """Dependency that enforces X-API-Key header authentication.

    If LEGAL_RAG_API_KEY is not set in the environment, auth is disabled (dev mode).
    In production, always set this variable.
    """
    configured_key = config.API_KEY
    if not configured_key:
        # No key configured — open access (dev / local mode)
        return "dev"
    if api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Supply it in the X-API-Key header.",
        )
    return api_key
