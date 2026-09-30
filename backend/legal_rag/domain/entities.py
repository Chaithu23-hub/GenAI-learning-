"""Domain entities and value objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Chunk:
    text: str
    heading: str
    index: int


@dataclass(frozen=True)
class Document:
    name: str
    text: str
    document_type: Literal["contract", "amendment"]


@dataclass(frozen=True)
class IndexedChunk:
    id: str
    text: str
    heading: str
    chunk_index: int
    document: str
    document_type: str


@dataclass(frozen=True)
class Query:
    text: str
    document_type: Literal["contract", "amendment"] | None = None


@dataclass
class RetrievedChunk:
    """Mutable so the reranker can enrich ``score`` after retrieval."""

    chunk_id: str
    document: str
    document_type: str
    heading: str
    text: str
    distance: float
    score: float = 0.0


@dataclass(frozen=True)
class Citation:
    document: str
    chunk_id: str
    excerpt: str


@dataclass(frozen=True)
class Answer:
    answer: str
    reasoning: str
    sources: tuple[Citation, ...]
    confidence: Literal["high", "medium", "low"]
    out_of_scope: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "reasoning": self.reasoning,
            "sources": [{"document": s.document, "chunk_id": s.chunk_id, "excerpt": s.excerpt}
                        for s in self.sources],
            "confidence": self.confidence,
            "out_of_scope": self.out_of_scope,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Answer":
        return cls(
            answer=payload["answer"],
            reasoning=payload["reasoning"],
            sources=tuple(
                Citation(document=s["document"], chunk_id=s["chunk_id"], excerpt=s["excerpt"])
                for s in payload.get("sources", [])
            ),
            confidence=payload["confidence"],
            out_of_scope=payload["out_of_scope"],
        )


@dataclass
class AgentStep:
    step: int
    action: str
    reason: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentState:
    query: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    tool_calls: int = 0
    status: str = "running"
    token_count: int = 0
    estimated_cost_usd: float = 0.0
    budget_log: list[str] = field(default_factory=list)
