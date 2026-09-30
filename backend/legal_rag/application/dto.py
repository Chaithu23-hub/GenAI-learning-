"""Framework-free DTOs — services take these; interfaces translate to/from transport DTOs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class AskCommand:
    question: str
    document_type: Literal["contract", "amendment"] | None = None
    backend: Literal["auto", "extractive", "llm"] | None = None


@dataclass(frozen=True)
class IngestCommand:
    docs_dir: str | None = None  # None → use configured default


@dataclass
class IngestResult:
    chunks_ingested: int
    message: str


@dataclass
class InspectResult:
    question: str
    retrieved: list[Any]  # list[RetrievedChunk]
    answer: dict[str, Any]


@dataclass(frozen=True)
class AgentCommand:
    question: str
    strategy: Literal["agent", "fixed", "compare"] = "compare"
    runs: int = 3


@dataclass
class AgentReport:
    strategy: str
    result: dict[str, Any]
    steps: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: int = 0
    elapsed_seconds: float = 0.0
    completed: bool = False
    stop_reason: str = ""
    estimated_cost_usd: float = 0.0
    token_count: int = 0
    budget_log: list[str] = field(default_factory=list)
