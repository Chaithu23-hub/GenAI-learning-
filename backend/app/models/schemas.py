from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared response types — mirror RESPONSE_SCHEMA from generation/schema.py
# ---------------------------------------------------------------------------

class SourceCitation(BaseModel):
    document: str
    chunk_id: str
    excerpt: str


class AnswerResponse(BaseModel):
    answer: str
    reasoning: str
    sources: list[SourceCitation]
    confidence: Literal["high", "medium", "low"]
    out_of_scope: bool


# ---------------------------------------------------------------------------
# QA endpoints
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="The legal question to answer.")
    document_type: Optional[Literal["contract", "amendment"]] = Field(
        None, description="Restrict retrieval to a specific document type."
    )
    backend: Optional[Literal["auto", "extractive", "llm"]] = Field(
        None, description="Generation backend. Defaults to auto-detection."
    )


class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    document: str
    document_type: str
    heading: str
    text: str
    distance: float
    score: float


class InspectResponse(BaseModel):
    question: str
    retrieved: list[RetrievedChunkResponse]
    answer: AnswerResponse


# ---------------------------------------------------------------------------
# Ingest endpoints
# ---------------------------------------------------------------------------

class IngestResponse(BaseModel):
    chunks_ingested: int
    message: str


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------

class AgentRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    strategy: Literal["agent", "fixed", "compare"] = Field(
        "compare", description="Which strategy to run."
    )
    runs: int = Field(3, ge=1, le=10, description="Number of runs for 'compare' strategy.")


class AgentResponse(BaseModel):
    strategy: str
    result: dict[str, Any]
    steps: list[dict[str, Any]] = []
    tool_calls: int = 0
    elapsed_seconds: float = 0.0
    completed: bool = False
    stop_reason: str = ""
    estimated_cost_usd: float = 0.0
    token_count: int = 0
    budget_log: list[str] = []


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    embedding_model: str
    rerank_model: str
    llm_provider: str
    llm_model: str
    vector_store_path: str
    api_key_configured: bool
