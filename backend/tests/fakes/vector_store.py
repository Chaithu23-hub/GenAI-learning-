"""In-memory VectorStore fake — deterministic, no I/O."""
from __future__ import annotations

import math
from typing import Any, Iterable

from legal_rag.domain.entities import IndexedChunk


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return 1.0 - dot / (na * nb)


class InMemoryVectorStore:
    """Deterministic VectorStore with pluggable embedding storage for tests."""

    def __init__(self):
        self._ids: list[str] = []
        self._documents: list[str] = []
        self._metadatas: list[dict[str, Any]] = []
        self._embeddings: list[list[float]] = []

    def upsert(
        self, indexed: Iterable[IndexedChunk], embeddings: list[list[float]]
    ) -> None:
        indexed_list = list(indexed)
        assert len(indexed_list) == len(embeddings)
        for chunk, emb in zip(indexed_list, embeddings):
            if chunk.id in self._ids:
                index = self._ids.index(chunk.id)
                self._documents[index] = chunk.text
                self._metadatas[index] = {
                    "document": chunk.document,
                    "document_type": chunk.document_type,
                    "heading": chunk.heading,
                    "chunk_index": chunk.chunk_index,
                }
                self._embeddings[index] = list(emb)
                continue
            self._ids.append(chunk.id)
            self._documents.append(chunk.text)
            self._metadatas.append({
                "document": chunk.document,
                "document_type": chunk.document_type,
                "heading": chunk.heading,
                "chunk_index": chunk.chunk_index,
            })
            self._embeddings.append(list(emb))

    def _filtered_indexes(self, where: dict[str, Any] | None) -> list[int]:
        if not where:
            return list(range(len(self._ids)))
        return [
            i for i, meta in enumerate(self._metadatas)
            if all(meta.get(k) == v for k, v in where.items())
        ]

    def dense_search(
        self, query_embedding: list[float], *, k: int, where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        indexes = self._filtered_indexes(where)
        scored = sorted(
            ((_cosine_distance(query_embedding, self._embeddings[i]), i) for i in indexes),
            key=lambda pair: pair[0],
        )[:k]
        return {
            "ids": [[self._ids[i] for _, i in scored]],
            "documents": [[self._documents[i] for _, i in scored]],
            "metadatas": [[self._metadatas[i] for _, i in scored]],
            "distances": [[dist for dist, _ in scored]],
        }

    def keyword_search(
        self, query: str, *, k: int, where: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        indexes = self._filtered_indexes(where)
        terms = set(query.lower().split())
        if not terms:
            return []
        scored: list[tuple[int, int]] = []
        for i in indexes:
            score = sum(self._documents[i].lower().count(term) for term in terms)
            if score:
                scored.append((score, i))
        scored.sort(reverse=True)
        return [
            {"id": self._ids[i], "document": self._documents[i],
             "metadata": self._metadatas[i]}
            for _, i in scored[:k]
        ]

    def get_document_text(self, chunk_id: str) -> str | None:
        try:
            return self._documents[self._ids.index(chunk_id)]
        except ValueError:
            return None

    def get_all(self, *, where: dict[str, Any] | None = None) -> dict[str, list[Any]]:
        indexes = self._filtered_indexes(where)
        return {
            "ids": [self._ids[i] for i in indexes],
            "documents": [self._documents[i] for i in indexes],
            "metadatas": [self._metadatas[i] for i in indexes],
        }
