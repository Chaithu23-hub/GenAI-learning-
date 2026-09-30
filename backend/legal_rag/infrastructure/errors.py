"""Infrastructure errors: TransientError (retryable) vs PermanentError."""
from __future__ import annotations


class InfrastructureError(Exception):
    """Base class for infrastructure adapter failures."""


class TransientError(InfrastructureError):
    """Failure the caller may retry."""


class PermanentError(InfrastructureError):
    """Failure that will not resolve on retry — misconfiguration or missing data."""


class VectorStoreError(InfrastructureError):
    """Persistence adapter failure."""


class EmbeddingError(InfrastructureError):
    """Embedding backend failure."""


class LLMBackendError(InfrastructureError):
    """LLM call failure. Prefer TransientLLMError / PermanentLLMError to allow retry logic."""


class TransientLLMError(LLMBackendError, TransientError):
    """Rate limit, timeout, upstream 5xx — safe to retry."""


class PermanentLLMError(LLMBackendError, PermanentError):
    """Bad API key, invalid request — do not retry."""


class MCPTransportError(TransientError):
    """MCP transport / process launch failure."""


class DocumentSourceError(PermanentError):
    """Missing or unreadable source documents."""
