"""Retrieval evaluation — hit-rate@k over labeled cases from the real contract corpus."""
from __future__ import annotations

from dataclasses import dataclass

from legal_rag.application.workflows.retrieval import RetrievalService


@dataclass(frozen=True)
class EvaluationCase:
    question: str
    # A hit is any retrieved chunk whose id is in this set. Frozen sets allow
    # multiple accepted chunks (e.g. original clause OR its amendment).
    relevant_chunk_ids: frozenset[str]


# Labels target real chunks produced by ingesting backend/data/legal/*.md with
# the default section-aware chunker. Chunk ids follow "{stem}::{index:03d}".
EVALUATION_CASES: tuple[EvaluationCase, ...] = (
    EvaluationCase(
        "What is the late payment interest rate?",
        frozenset({
            "master_services_agreement::002",       # original: 1.0%/month
            "master_services_agreement::005",       # summary of payment terms
            "amendment_01_payment_terms::001",      # amendment: 1.5%/month
            "amendment_01_payment_terms::002",      # amendment change summary
        }),
    ),
    EvaluationCase(
        "What did the payment amendment change?",
        frozenset({
            "amendment_01_payment_terms::001",
            "amendment_01_payment_terms::002",
            "master_services_agreement::005",
        }),
    ),
    EvaluationCase(
        "What notice is required to terminate the master services agreement?",
        frozenset({
            "master_services_agreement::003",       # Section 5: Termination
            "master_services_agreement::006",       # Termination details
        }),
    ),
    EvaluationCase(
        "When does the Enterprise SaaS subscription auto-renew?",
        frozenset({
            f"enterprise_saas_subscription_agreement::{i:03d}"
            for i in range(0, 20)  # accept any chunk from ESSA — auto-renewal is in the Term section
        }),
    ),
    EvaluationCase(
        "What is the effective date of the Data Processing Consulting Agreement?",
        frozenset({
            f"data_processing_consulting_agreement::{i:03d}"
            for i in range(0, 20)
        }),
    ),
)


class EvaluationService:
    def __init__(self, *, retrieval: RetrievalService):
        self._retrieval = retrieval

    def hit_rate_at_k(
        self, cases: tuple[EvaluationCase, ...] = EVALUATION_CASES,
        k: int = 3, hybrid: bool | None = None,
    ) -> float:
        hits = 0
        for case in cases:
            results = self._retrieval.retrieve(case.question, n=k, hybrid=hybrid)
            if any(r.chunk_id in case.relevant_chunk_ids for r in results):
                hits += 1
        return hits / len(cases) if cases else 0.0

    def compare_retrieval(
        self, cases: tuple[EvaluationCase, ...] = EVALUATION_CASES, k: int = 3
    ) -> dict[str, float | int]:
        return {
            "k": k,
            "questions": len(cases),
            "before_dense": self.hit_rate_at_k(cases, k=k, hybrid=False),
            "after_hybrid": self.hit_rate_at_k(cases, k=k, hybrid=True),
        }
