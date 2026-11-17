"""Retrieval service — dense + lexical → RRF → cross-encoder rerank."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from legal_rag.application.ports import Embedder, Monitoring, Reranker, VectorStore
from legal_rag.domain.clauses import DOCUMENT_ID_RE
from legal_rag.domain.entities import RetrievedChunk
from legal_rag.domain.ranking import reciprocal_rank_fusion
from legal_rag.infrastructure.observability.logging import get_logger

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
        monitoring: Monitoring | None = None,
    ):
        self._vector_store = vector_store
        self._embedder = embedder
        self._reranker = reranker
        self._settings = settings
        self._monitoring = monitoring

    def resolve_scope(
        self, query: str, where: dict[str, Any] | None
    ) -> tuple[bool, dict[str, Any] | None]:
        """Constrain explicit identities, expanding only requested linked families."""
        documents = {match.group().upper() for match in DOCUMENT_ID_RE.finditer(query)}
        if len(documents) != 1:
            return True, where
        document = next(iter(documents))
        constraint = (where or {}).get("source_doc", document)
        if isinstance(constraint, dict):
            if (
                set(constraint) != {"$in"}
                or not isinstance(constraint["$in"], list)
                or document not in constraint["$in"]
            ):
                return False, where
        elif constraint != document:
            return False, where
        positive_family = re.search(
            r"\b(?:includ(?:e|ing)|together\s+with)\s+(?:(?:all|the)\s+)?amendments?\b",
            query,
            re.IGNORECASE,
        ) and not re.search(
            r"\b(?:not|never|don['\u2019]t|doesn['\u2019]t)\s+includ(?:e|ing)\s+"
            r"(?:(?:all|the|any)\s+)?amendments?\b|"
            r"\b(?:without|excluding|exclude)\s+(?:(?:all|the|any)\s+)?amendments?\b",
            query,
            re.IGNORECASE,
        )
        if not positive_family:
            return True, {**(where or {}), "source_doc": document}
        restrictions = {key: value for key, value in (where or {}).items() if key != "source_doc"}
        rows = self._vector_store.get_all(where=restrictions or None)
        family = {document}
        # Linkage comes only from stored metadata, never identifier similarity.
        links: list[tuple[str, str]] = []
        for metadata in rows["metadatas"]:
            source, amends = metadata.get("source_doc"), metadata.get("amends")
            if (
                isinstance(source, str)
                and DOCUMENT_ID_RE.fullmatch(source)
                and isinstance(amends, str)
                and DOCUMENT_ID_RE.fullmatch(amends)
            ):
                links.append((source.upper(), amends.upper()))
        # Include a chain only where an explicit amends edge joins the family.
        while True:
            expanded = family | {source for source, base in links if base in family}
            if expanded == family:
                break
            family = expanded
        if isinstance(constraint, dict):
            # An existing allowlist is an upper bound, including tool requests.
            family.intersection_update(constraint["$in"])
        return True, {**restrictions, "source_doc": {"$in": sorted(family)}}

    def retrieve(
        self,
        query: str,
        *,
        k: int | None = None,
        n: int | None = None,
        where: dict[str, Any] | None = None,
        hybrid: bool | None = None,
    ) -> list[RetrievedChunk]:
        if self._monitoring is None:
            return self._retrieve(query, k=k, n=n, where=where, hybrid=hybrid)
        return self._monitoring.run(
            "retrieve-context",
            lambda: self._retrieve(query, k=k, n=n, where=where, hybrid=hybrid),
            as_type="retriever",
        )

    def _retrieve(
        self,
        query: str,
        *,
        k: int | None = None,
        n: int | None = None,
        where: dict[str, Any] | None = None,
        hybrid: bool | None = None,
    ) -> list[RetrievedChunk]:
        allowed, where = self.resolve_scope(query, where)
        if not allowed:
            return []
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
