"""Port interfaces (Protocols). Services depend on these; adapters implement them."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from legal_rag.domain.entities import Chunk, Document, IndexedChunk

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

    def delete_chunks(self, ids: list[str]) -> None:
        """Remove obsolete chunks after successful replacement upsert; empty IDs are a no-op."""

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
    """Normalized chat and tool client, independent of the provider SDK."""

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


ConversationIntent = Literal["social", "documents", "unsupported"]


class Conversation(Protocol):
    def classify(self, query: str) -> ConversationIntent:
        """Infer conversational intent with the LLM; uncertainty must retain document QA."""

    def reply(self, query: str) -> str:
        """Generate a fresh conversational reply without retrieving documents."""


UnsupportedReason = Literal["outside_document_qa", "insufficient_evidence"]


class UnsupportedResponses(Protocol):
    def reply(self, reason: UnsupportedReason) -> str:
        """Generate a fresh refusal from a controlled reason, without document context."""


# ─── Documents ────────────────────────────────────────────────────────────


@runtime_checkable
class DocumentSource(Protocol):
    def iter_documents(self, docs_dir: Path | None = None) -> Iterable[Document]:
        """Yield parsed documents and metadata from the selected source directory."""

    def write_document(self, name: str, text: str) -> Path:
        """Persist a new source document; return its path."""

    def write_documents(self, documents: list[tuple[str, str]]) -> list[Path]:
        """Create an upload batch exclusively; roll back new files on failure."""


class PDFTextExtractor(Protocol):
    def extract(self, pdf_bytes: bytes) -> str:
        """Extract text within configured input, output and process resource limits."""


class WorkExecutor(Protocol):
    async def run[T](self, operation: Callable[[], T], *, exclusive: bool = False) -> T:
        """Run blocking work with bounded admission and a response deadline."""

    def close(self) -> None:
        """Stop accepting work and release execution resources after completion."""


@runtime_checkable
class Chunker(Protocol):
    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[Chunk]: ...


# ─── MCP ──────────────────────────────────────────────────────────────────


@runtime_checkable
class MCPHostPort(Protocol):
    async def discover(self) -> dict[str, list[str]]: ...
    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ContractLookup(Protocol):
    def lookup_contract(self, contract_id: str) -> dict[str, Any]:
        """Perform a bounded contract lookup through the configured MCP transport."""


class EvaluationFiles(Protocol):
    def read_labels(self) -> bytes:
        """Read the configured evaluation fixture without exposing filesystem details."""

    def write_artifact(self, name: str, text: str) -> None:
        """Persist a local evaluation artifact under its configured directory."""


# ─── Clock ────────────────────────────────────────────────────────────────


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float:
        """Monotonic seconds for latency measurement."""
