"""Retrieval service — dense + lexical → RRF → cross-encoder rerank."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from legal_rag.application.ports import Embedder, Reranker, VectorStore
from legal_rag.domain.clauses import DOCUMENT_ID_RE
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
        # A document ID is a constraint even when a caller bypasses QaService.
        documents = {match.group().upper() for match in DOCUMENT_ID_RE.finditer(query)}
        if len(documents) == 1:
            document = next(iter(documents))
            if where and where.get("source_doc", document) != document:
                return []
            where = {**(where or {}), "source_doc": document}
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
                metadata=dict(meta),
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
                candidates_by_id.setdefault(
                    hit["id"],
                    RetrievedChunk(
                        chunk_id=hit["id"],
                        document=hit["metadata"]["document"],
                        document_type=hit["metadata"]["document_type"],
                        heading=hit["metadata"]["heading"],
                        text=hit["document"],
                        distance=1.0,
                        metadata=dict(hit["metadata"]),
                    ),
                )

        rrf_scores = reciprocal_rank_fusion(*ranked_lists, rrf_k=self._settings.rrf_k)
        candidates = sorted(
            (candidates_by_id[cid] for cid in rrf_scores),
            key=lambda c: rrf_scores[c.chunk_id],
            reverse=True,
        )
        if not candidates:
            return []

        score_inputs = [
            f"{c.heading}\n{c.text}" if c.heading and c.heading != "Preamble" else c.text
            for c in candidates
        ]
        scores = self._reranker.score(query, score_inputs)
        for candidate, score in zip(candidates, scores, strict=True):
            # An amendment's identifier does not establish applicability to a
            # particular clause, requested date, or historical document version.
            candidate.score = float(score)
        candidates.sort(key=lambda c: c.score, reverse=True)
        top = candidates[:n]
        log.debug(
            "retrieved",
            extra={
                "query": query[:80],
                "returned": len(top),
                "top_score": top[0].score if top else None,
            },
        )
        return top

    def detect_metadata_filter(self, query: str) -> dict[str, str] | None:
        """Filter only when the user explicitly requests one document type."""
        q = query.lower()
        where: dict[str, str] = {}
        counterparties = {
            "northwind": "Northwind Logistics",
            "vertex retail": "Vertex Retail",
            "vertex": "Vertex Retail",
            "halcyon analytics": "Halcyon Analytics",
            "halcyon": "Halcyon Analytics",
            "apex": "Apex Industries",
        }
        matching = {value for name, value in counterparties.items() if name in q}
        if len(matching) == 1:
            where["counterparty"] = next(iter(matching))
        source_docs = {m.group().upper() for m in DOCUMENT_ID_RE.finditer(query)}
        if len(source_docs) == 1:
            where["source_doc"] = next(iter(source_docs))
        # Incidents, holidays and "as of" dates are not document effective dates.
        # Temporal applicability requires the full amendment chain, not equality.
        effective_date = re.search(
            r"\beffective(?:\s+date)?\s*(?:(?:on|of|is|was)\s+|[:=]\s*)?"
            r"(20\d{2}-\d{2}-\d{2})\b",
            query,
            re.IGNORECASE,
        )
        if effective_date:
            where["effective_date"] = effective_date.group(1)
        if re.search(
            r"\bonly\s+(?:the\s+)?amendments?(?:\s+documents?)?\b|"
            r"\bamendments?\s+documents?\s+only\b",
            q,
        ):
            where["document_type"] = "amendment"
        if re.search(
            r"\bonly\s+(?:the\s+)?(?:contracts?|agreements?)(?:\s+documents?)?\b|"
            r"\b(?:contracts?|agreements?)\s+documents?\s+only\b",
            q,
        ):
            where["document_type"] = "contract"
        return where or None
