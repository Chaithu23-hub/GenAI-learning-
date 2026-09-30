"""Port interfaces (Protocols). Services depend on these; adapters implement them."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable

from legal_rag.domain.entities import IndexedChunk


# ─── Persistence ──────────────────────────────────────────────────────────


class DenseSearchResult(dict):
    """A dense-search hit set. Duck-typed shape:

        {
          "ids":        [[chunk_id, ...]],
          "documents":  [[text, ...]],
          "metadatas":  [[{document, document_type, heading, chunk_index}, ...]],
          "distances":  [[float, ...]],
        }
    """


class KeywordSearchHit(dict):
    """A lexical-search hit. Shape: ``{"id", "document", "metadata"}``."""


@runtime_checkable
class VectorStore(Protocol):
    """Combined dense + lexical persistence adapter."""

    def upsert(self, indexed: Iterable[IndexedChunk], embeddings: list[list[float]]) -> None: ...

    def dense_search(
        self, query_embedding: list[float], *, k: int, where: dict[str, Any] | None = None
    ) -> DenseSearchResult: ...

    def keyword_search(
        self, query: str, *, k: int, where: dict[str, Any] | None = None
    ) -> list[KeywordSearchHit]: ...

    def get_document_text(self, chunk_id: str) -> str | None:
        """Return the stored text for a chunk, or None. Used by citation verification."""

    def get_all(self, *, where: dict[str, Any] | None = None) -> dict[str, list[Any]]:
        """Return ``{ids, documents, metadatas}`` for all rows (used by defined-terms worker)."""


# ─── Embeddings ───────────────────────────────────────────────────────────


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


# ─── LLM ──────────────────────────────────────────────────────────────────


@runtime_checkable
class LLMClient(Protocol):
    """Minimal OpenAI-shaped chat + tool client."""

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Return a normalised response dict:

            {
              "content": str | None,
              "tool_calls": [ {"id": str, "name": str, "arguments": str}, ... ],
              "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
            }
        """

    def list_models(self) -> list[str]:
        """Return the available model ids, or an empty list if unknown."""


# ─── Documents ────────────────────────────────────────────────────────────


@runtime_checkable
class DocumentSource(Protocol):
    def iter_documents(self) -> Iterable[tuple[Path, str]]:
        """Yield ``(path, text)`` for every source document."""

    def write_document(self, name: str, text: str) -> Path:
        """Persist a new source document; return its path."""


# ─── MCP ──────────────────────────────────────────────────────────────────


@runtime_checkable
class MCPHostPort(Protocol):
    async def discover(self) -> dict[str, list[str]]: ...
    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


# ─── Clock ────────────────────────────────────────────────────────────────


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float:
        """Monotonic seconds for latency measurement."""
