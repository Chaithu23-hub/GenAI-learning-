"""Evidence retrieval evaluation with validated corpus labels and rank metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from legal_rag.application.ports import VectorStore
from legal_rag.application.workflows.retrieval import RetrievalService
from legal_rag.domain.clauses import clause_excerpt
from legal_rag.domain.entities import RetrievedChunk
from legal_rag.domain.exceptions import InvalidEvaluationLabelsError


@dataclass(frozen=True)
class EvaluationCase:
    question: str
    relevant_chunk_ids: frozenset[str] = frozenset()
    # Each pair is required evidence. Stable labels survive re-chunking.
    relevant_clauses: tuple[tuple[str, str], ...] = ()


# A retrieval-only subset of supplied shared-corpus golden cases GS-001..006.
# Labels describe evidence identity and never generate legal answers.
EVALUATION_CASES: tuple[EvaluationCase, ...] = (
    EvaluationCase(
        "What is the late payment interest rate under the Northwind agreement?",
        relevant_clauses=(("MSA-2026-014", "3.4"),),
    ),
    EvaluationCase(
        "What law and jurisdiction govern the Northwind agreement?",
        relevant_clauses=(("MSA-2026-014", "15.1"), ("MSA-2026-014", "15.2")),
    ),
    EvaluationCase(
        "How long must Soft Suave maintain professional indemnity insurance under the Northwind agreement, and for what amount?",
        relevant_clauses=(("MSA-2026-014", "13.1"),),
    ),
    EvaluationCase(
        "Within how many hours must Provider notify Northwind of a personal data breach?",
        relevant_clauses=(("MSA-2026-014", "10.3"),),
    ),
    EvaluationCase(
        "What is the liability cap in Section 8.3 of the Northwind Master Services Agreement?",
        relevant_clauses=(("AMD-2026-014-02", "2.1"),),
    ),
    EvaluationCase(
        "What notice is required for termination for convenience under the Northwind agreement as currently amended?",
        relevant_clauses=(("AMD-2026-014-02", "1.1"),),
    ),
)


class EvaluationService:
    def __init__(self, *, retrieval: RetrievalService, vector_store: VectorStore):
        self._retrieval = retrieval
        self._vector_store = vector_store

    def _label_groups(self, cases: tuple[EvaluationCase, ...]) -> list[list[set[str]]]:
        stored = self._vector_store.get_all()
        chunks = [
            RetrievedChunk(
                identifier,
                meta["document"],
                meta["document_type"],
                meta["heading"],
                text,
                0,
                metadata=meta,
            )
            for identifier, text, meta in zip(
                stored["ids"],
                stored["documents"],
                stored["metadatas"],
                strict=True,
            )
        ]
        existing = set(stored["ids"])
        groups = []
        for case in cases:
            targets = []
            if case.relevant_chunk_ids:
                if not case.relevant_chunk_ids <= existing:
                    raise InvalidEvaluationLabelsError(
                        "Evaluation label is not in the current index."
                    )
                targets.append(set(case.relevant_chunk_ids))
            for document, number in case.relevant_clauses:
                ids = {
                    chunk.chunk_id
                    for chunk in chunks
                    if chunk.document == document and clause_excerpt(chunk, number)
                }
                if not ids:
                    raise InvalidEvaluationLabelsError(
                        f"Evaluation label {document} clause {number} is not in the current index."
                    )
                targets.append(ids)
            if not targets:
                raise InvalidEvaluationLabelsError(
                    "Evaluation case has no evidence labels in the index."
                )
            groups.append(targets)
        return groups

    def measure(
        self,
        cases: tuple[EvaluationCase, ...] = EVALUATION_CASES,
        *,
        k: int = 3,
        hybrid: bool | None = None,
    ) -> dict[str, float | int]:
        if k < 1:
            raise ValueError("k must be positive")
        groups = self._label_groups(cases)
        hits, reciprocal_ranks, recall, complete = 0, 0.0, 0.0, 0
        for case, targets in zip(cases, groups, strict=True):
            filters = self._retrieval.detect_metadata_filter(case.question)
            results = self._retrieval.retrieve(case.question, n=k, hybrid=hybrid, where=filters)
            ids = {row.chunk_id for row in results}
            supported = sum(bool(target & ids) for target in targets)
            hits += supported > 0
            complete += supported == len(targets)
            recall += supported / len(targets)
            accepted = set().union(*targets)
            reciprocal_ranks += next(
                (1 / rank for rank, row in enumerate(results, 1) if row.chunk_id in accepted),
                0,
            )
        count = len(cases)
        return {
            "questions": count,
            "k": k,
            "hit_rate": hits / count if count else 0.0,
            "mean_reciprocal_rank": reciprocal_ranks / count if count else 0.0,
            "evidence_recall": recall / count if count else 0.0,
            "all_evidence_rate": complete / count if count else 0.0,
        }

    def hit_rate_at_k(
        self,
        cases: tuple[EvaluationCase, ...] = EVALUATION_CASES,
        k: int = 3,
        hybrid: bool | None = None,
    ) -> float:
        return float(self.measure(cases, k=k, hybrid=hybrid)["hit_rate"])

    def compare_retrieval(
        self,
        cases: tuple[EvaluationCase, ...] = EVALUATION_CASES,
        k: int = 3,
    ) -> dict[str, Any]:
        dense = self.measure(cases, k=k, hybrid=False)
        hybrid = self.measure(cases, k=k, hybrid=True)
        return {
            "k": k,
            "questions": len(cases),
            "before_dense": dense["hit_rate"],
            "after_hybrid": hybrid["hit_rate"],
            "dense_metrics": dense,
            "hybrid_metrics": hybrid,
        }
