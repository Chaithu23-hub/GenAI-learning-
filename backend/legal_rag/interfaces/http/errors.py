"""Global exception handlers — every error becomes an RFC 7807 problem+json response."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from legal_rag.domain.exceptions import (
    AgentBudgetExceeded,
    DomainError,
    GuardrailBlocked,
    OutOfScope,
    SchemaValidationError,
)
from legal_rag.infrastructure.errors import (
    DocumentSourceError,
    InfrastructureError,
    PermanentError,
    TransientError,
)
from legal_rag.infrastructure.observability.logging import current_request_id, get_logger

log = get_logger("legal_rag.http.errors")


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "request_id": current_request_id(),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(GuardrailBlocked)
    async def _guardrail(_: Request, exc: GuardrailBlocked):
        return _problem(400, f"Guardrail blocked ({exc.reason})", exc.message)

    @app.exception_handler(OutOfScope)
    async def _oos(_: Request, exc: OutOfScope):
        return _problem(422, "Out of scope", str(exc))

    @app.exception_handler(SchemaValidationError)
    async def _schema(_: Request, exc: SchemaValidationError):
        return _problem(422, "Schema validation failed", "; ".join(exc.errors))

    @app.exception_handler(AgentBudgetExceeded)
    async def _budget(_: Request, exc: AgentBudgetExceeded):
        return _problem(504, f"Agent budget exceeded ({exc.budget})", str(exc))

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        return _problem(400, "Domain rule violation", str(exc))

    @app.exception_handler(DocumentSourceError)
    async def _docs(_: Request, exc: DocumentSourceError):
        return _problem(404, "Document source unavailable", str(exc))

    @app.exception_handler(TransientError)
    async def _transient(_: Request, exc: TransientError):
        log.warning("transient infrastructure error", extra={"error": str(exc)})
        return _problem(503, "Upstream temporarily unavailable", str(exc))

    @app.exception_handler(PermanentError)
    async def _permanent(_: Request, exc: PermanentError):
        log.error("permanent infrastructure error", extra={"error": str(exc)})
        return _problem(500, "Upstream misconfiguration", str(exc))

    @app.exception_handler(InfrastructureError)
    async def _infra(_: Request, exc: InfrastructureError):
        log.error("infrastructure error", extra={"error": str(exc)})
        return _problem(500, "Infrastructure error", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return _problem(422, "Request validation failed", str(exc.errors()))

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        return _problem(exc.status_code, exc.detail if isinstance(exc.detail, str)
                        else "HTTP error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _catch_all(_: Request, exc: Exception):  # noqa: BLE001
        log.exception("unhandled exception", extra={"error": type(exc).__name__})
        return _problem(500, "Internal server error",
                        "An unexpected error occurred. See server logs for details.")
