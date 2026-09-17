from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, qa, ingest, agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    # Pre-warm: import config to trigger validation on startup
    from legal_assistant import config  # noqa: F401
    yield
    # Shutdown: nothing to tear down for stateless workers


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Legal Document Assistant API",
        description=(
            "Production-grade RAG pipeline for answering questions about legal contracts and amendments. "
            "Every answer is grounded in retrieved document chunks with source citations."
        ),
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS — allow local development servers and deployed frontend origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",        # Docker frontend on port 80
            "http://localhost:5173",   # Vite dev server
            "http://localhost:4200",   # Angular dev server
            "http://localhost:3000",   # Alternative dev port
            "http://frontend:80",      # Docker service name
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    app.include_router(health.router)
    app.include_router(qa.router)
    app.include_router(ingest.router)
    app.include_router(agent.router)

    return app


app = create_app()
