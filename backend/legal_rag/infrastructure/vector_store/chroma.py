"""Chroma-backed ``VectorStore`` adapter.

Handles both dense (embedding) and local BM25-style lexical retrieval.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from legal_rag.domain.entities import IndexedChunk
from legal_rag.infrastructure.errors import VectorStoreError
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
COLLECTION_NAME = "legal_docs"


class ChromaVectorStore:
    """Concrete ``VectorStore`` using Chroma's PersistentClient."""

    def __init__(self, chroma_dir: Path, collection_name: str = COLLECTION_NAME):
        self._chroma_dir = Path(chroma_dir)
        self._collection_name = collection_name
        self._client = None
        self._collection = None
        self._lock = Lock()

    # ── lifecycle ───────────────────────────────────────────────────────
    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        with self._lock:
            if self._collection is None:
                try:
                    import chromadb
                except ImportError as exc:  # pragma: no cover
                    raise VectorStoreError("chromadb not installed") from exc
                self._chroma_dir.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=str(self._chroma_dir))
                self._collection = self._client.get_or_create_collection(
                    name=self._collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
        return self._collection

    # ── writes ──────────────────────────────────────────────────────────
    def upsert(self, indexed: Iterable[IndexedChunk], embeddings: list[list[float]]) -> None:
        indexed_list = list(indexed)
        if len(indexed_list) != len(embeddings):
            raise VectorStoreError("indexed / embeddings length mismatch")
        if not indexed_list:
            return
        try:
            self._get_collection().upsert(
                ids=[c.id for c in indexed_list],
                documents=[c.text for c in indexed_list],
                embeddings=embeddings,
                metadatas=[
                    {
                        "document": c.document,
                        "document_type": c.document_type,
                        "heading": c.heading,
                        "chunk_index": c.chunk_index,
                    }
                    for c in indexed_list
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"upsert failed: {exc}") from exc
        log.info("upserted chunks", extra={"count": len(indexed_list)})

    # ── reads ───────────────────────────────────────────────────────────
    def dense_search(
        self, query_embedding: list[float], *, k: int, where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            return self._get_collection().query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"dense_search failed: {exc}") from exc

    def keyword_search(
        self, query: str, *, k: int, where: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        collection = self._get_collection()
        try:
            stored = collection.get(include=["documents", "metadatas"], where=where)
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"keyword_search failed: {exc}") from exc

        documents = stored.get("documents", [])
        if not documents:
            return []
        query_terms = _TOKEN_RE.findall(query.lower())
        if not query_terms:
            return []

        term_frequency: list[dict[str, int]] = []
        document_frequency: dict[str, int] = {}
        lengths: list[int] = []
        for document in documents:
            terms = _TOKEN_RE.findall(document.lower())
            lengths.append(len(terms))
            freqs: dict[str, int] = {}
            for term in terms:
                freqs[term] = freqs.get(term, 0) + 1
            term_frequency.append(freqs)
            for term in set(terms):
                document_frequency[term] = document_frequency.get(term, 0) + 1

        average_length = sum(lengths) / len(lengths) or 1
        scored: list[tuple[float, int]] = []
        for index, freqs in enumerate(term_frequency):
            score = 0.0
            for term in query_terms:
                frequency = freqs.get(term, 0)
                if not frequency:
                    continue
                idf = math.log(
                    1 + (len(documents) - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                normalization = frequency + 1.5 * (0.25 + 0.75 * lengths[index] / average_length)
                score += idf * frequency * 2.5 / normalization
            if score:
                scored.append((score, index))
        scored.sort(reverse=True)
        return [
            {
                "id": stored["ids"][index],
                "document": documents[index],
                "metadata": stored["metadatas"][index],
            }
            for _, index in scored[:k]
        ]

    def get_document_text(self, chunk_id: str) -> str | None:
        try:
            result = self._get_collection().get(ids=[chunk_id], include=["documents"])
        except Exception:  # noqa: BLE001
            return None
        if not result.get("ids"):
            return None
        docs = result.get("documents", [])
        return (docs[0] if docs else "") or None

    def get_all(self, *, where: dict[str, Any] | None = None) -> dict[str, list[Any]]:
        try:
            return self._get_collection().get(include=["documents", "metadatas"], where=where)
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"get_all failed: {exc}") from exc
