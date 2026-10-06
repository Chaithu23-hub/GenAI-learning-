"""Retrieval service — dense + lexical → RRF → cross-encoder rerank."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from legal_rag.application.ports import Embedder, Reranker, VectorStore
from legal_rag.domain.entities import RetrievedChunk
from legal_rag.infrastructure.observability.logging import get_logger
from legal_rag.infrastructure.retrieval import reciprocal_rank_fusion

log = get_logger(__name__)


@dataclass
class RetrievalSettings:
    top_k_candidates: int
    top_n_answers: int
    hybrid_enabled: bool
    rrf_k: int


class RetrievalService:
    """Hybrid retrieve → RRF → rerank → top-N."""

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedder: Embedder,
        reranker: Reranker,
        settings: RetrievalSettings,
    ):
        self._vector_store = vector_store
        self._embedder = embedder
        self._reranker = reranker
        self._settings = settings

    def retrieve(
        self,
        query: str,
        *,
        k: int | None = None,
        n: int | None = None,
        where: dict[str, Any] | None = None,
        hybrid: bool | None = None,
    ) -> list[RetrievedChunk]:
        k = k or self._settings.top_k_candidates
        n = n or self._settings.top_n_answers
        hybrid = self._settings.hybrid_enabled if hybrid is None else hybrid

        query_embedding = self._embedder.embed_query(query)
        raw = self._vector_store.dense_search(query_embedding, k=k, where=where)
        dense_candidates = [
            RetrievedChunk(
                chunk_id=chunk_id,
                document=meta["document"],
                document_type=meta["document_type"],
                heading=meta["heading"],
                text=text,
                distance=dist,
            )
            for chunk_id, text, meta, dist in zip(
                raw["ids"][0],
                raw["documents"][0],
                raw["metadatas"][0],
                raw["distances"][0],
                strict=True,
            )
        ]
        candidates_by_id = {c.chunk_id: c for c in dense_candidates}
        ranked_lists = [[c.chunk_id for c in dense_candidates]]

        if hybrid:
            lexical = self._vector_store.keyword_search(query, k=k, where=where)
            ranked_lists.append([hit["id"] for hit in lexical])
            for hit in lexical:
                candidates_by_id.setdefault(hit["id"], RetrievedChunk(
                    chunk_id=hit["id"],
                    document=hit["metadata"]["document"],
                    document_type=hit["metadata"]["document_type"],
                    heading=hit["metadata"]["heading"],
                    text=hit["document"],
                    distance=1.0,
                ))

        rrf_scores = reciprocal_rank_fusion(*ranked_lists, rrf_k=self._settings.rrf_k)
        candidates = sorted(
            (candidates_by_id[cid] for cid in rrf_scores),
            key=lambda c: rrf_scores[c.chunk_id],
            reverse=True,
        )
        if not candidates:
            return []

        scores = self._reranker.score(query, [c.text for c in candidates])
        for candidate, score in zip(candidates, scores, strict=True):
            candidate.score = float(score)
        candidates.sort(key=lambda c: c.score, reverse=True)
        top = candidates[:n]
        log.debug("retrieved", extra={
            "query": query[:80], "returned": len(top),
            "top_score": top[0].score if top else None,
        })
        return top

    def detect_metadata_filter(self, query: str) -> dict[str, str] | None:
        """Auto-detect a document_type filter from query keywords."""
        q = query.lower()
        if "amendment" in q:
            return {"document_type": "amendment"}
        if "contract" in q or "agreement" in q:
            return {"document_type": "contract"}
        return None
