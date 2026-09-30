"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from legal_rag import __version__
from legal_rag.composition import Container, get_container
from legal_rag.infrastructure.observability.logging import configure_logging, get_logger
from legal_rag.infrastructure.settings import Settings, get_settings
from legal_rag.interfaces.http.errors import register_exception_handlers
from legal_rag.interfaces.http.middleware import RequestIdMiddleware
from legal_rag.interfaces.http.routers import agent, health, ingest, mcp, metrics, qa

log = get_logger("legal_rag.http.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, format=settings.log_format)
    container = Container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("startup", extra={"version": __version__, "provider": settings.llm_provider})
        app.state.container = container
        yield
        log.info("shutdown")

    app = FastAPI(
        title="LegalRAG API",
        description=(
            "Production-grade RAG pipeline for legal contracts and amendments. "
            "Every answer is grounded in retrieved chunks with source citations."
        ),
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(qa.router)
    app.include_router(ingest.router)
    app.include_router(agent.router)
    app.include_router(mcp.router)
    app.include_router(metrics.router)

    return app


# ASGI entry point — ``uvicorn legal_rag.interfaces.http.app:app``
app = create_app()
