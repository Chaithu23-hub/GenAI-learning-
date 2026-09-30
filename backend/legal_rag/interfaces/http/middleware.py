"""HTTP middleware — request id + structured access log."""
from __future__ import annotations

import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from legal_rag.infrastructure.observability.logging import get_logger, set_request_id

log = get_logger("legal_rag.http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id, put it in the log context, and echo it in the response header."""

    HEADER = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(self.HEADER) or uuid4().hex
        set_request_id(rid)
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            # Stamp the header on the happy path before the finally clause
            # clears the request-id context.
            response.headers[self.HEADER] = rid
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            log.info(
                "http request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "client": request.client.host if request.client else None,
                    "status": getattr(response, "status_code", None),
                },
            )
            set_request_id(None)
