"""HTTP middleware — request id + structured access log."""

from __future__ import annotations

import asyncio
import time
from threading import BoundedSemaphore
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from legal_rag.infrastructure.observability.logging import get_logger, set_request_id

log = get_logger("legal_rag.http")


class _BodyTransferTimeoutError(Exception):
    """Raised when the complete request body misses its transfer deadline."""


class RequestBodyLimitMiddleware:
    """Bound transfer bytes and in-flight bodies before multipart/JSON parsing."""

    def __init__(self, app: ASGIApp, *, max_bytes: int, max_requests: int, timeout_seconds: float):
        self.app = app
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        self.slots = BoundedSemaphore(max_requests)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        async def reject(status: int, detail: str):
            response = JSONResponse(
                status_code=status,
                media_type="application/problem+json",
                content={
                    "type": "about:blank",
                    "title": "Request rejected",
                    "status": status,
                    "detail": detail,
                },
            )
            await response(scope, receive, send)

        lengths = [value for name, value in scope["headers"] if name.lower() == b"content-length"]
        if lengths and (len(lengths) != 1 or not lengths[0].isdigit()):
            await reject(400, "Invalid Content-Length.")
            return
        if lengths and int(lengths[0]) > self.max_bytes:
            await reject(413, "Request body limit exceeded.")
            return
        if not self.slots.acquire(blocking=False):
            await reject(503, "Too many in-flight requests.")
            return
        try:
            # Read the bounded body before parsing so a timeout remains an HTTP
            # 408 at this boundary instead of becoming a parser/disconnect error.
            deadline = asyncio.get_running_loop().time() + self.timeout_seconds
            chunks = bytearray()
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise _BodyTransferTimeoutError
                try:
                    message = await asyncio.wait_for(receive(), timeout=remaining)
                except TimeoutError as exc:
                    raise _BodyTransferTimeoutError from exc
                if message["type"] != "http.request":
                    if message["type"] == "http.disconnect":
                        return
                    continue
                chunks.extend(message.get("body", b""))
                if len(chunks) > self.max_bytes:
                    await reject(413, "Request body limit exceeded.")
                    return
                if not message.get("more_body", False):
                    break

            body = bytes(chunks)
            delivered = False

            async def replay_body():
                nonlocal delivered
                if delivered:
                    return {"type": "http.disconnect"}
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            await self.app(scope, replay_body, send)
        except _BodyTransferTimeoutError:
            await reject(408, "Request body transfer timed out.")
        finally:
            self.slots.release()


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
