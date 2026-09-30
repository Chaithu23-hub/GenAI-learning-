"""GET /metrics — Prometheus text format. Unauthenticated by design (scraper)."""
from __future__ import annotations

from fastapi import APIRouter, Response

from legal_rag.infrastructure.observability import get_metrics

router = APIRouter(tags=["observability"])


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    responses={200: {"content": {"text/plain": {"schema": {"type": "string"}}}}},
)
def metrics() -> Response:
    return Response(
        content=get_metrics().render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
