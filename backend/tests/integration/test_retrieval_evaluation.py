"""Evaluation measures observed evidence coverage and rank, never fabricated labels."""

import pytest

from legal_rag.application.workflows.evaluation import EvaluationCase, EvaluationService
from legal_rag.domain.entities import IndexedChunk, RetrievedChunk
from tests.fakes.vector_store import InMemoryVectorStore


class RankedRetrieval:
    def __init__(self, rows):
        self.rows = rows

    def detect_metadata_filter(self, question):
        return None

    def retrieve(self, question, *, n, hybrid=None, where=None):
        return self.rows[:n]


def test_current_source_clause_labels_are_independent_of_chunk_index():
    store = InMemoryVectorStore()
    rows = [
        IndexedChunk("irrelevant", "Unrelated text.", "Other", 0, "MSA-2026-022", "contract"),
        IndexedChunk(
            "MSA-2026-014::037",
            "3.4 Payment. Interest applies.",
            "Section 3.4",
            37,
            "MSA-2026-014",
            "contract",
        ),
    ]
    store.upsert(rows, [[1], [1]])
    hits = [
        RetrievedChunk(row.id, row.document, row.document_type, row.heading, row.text, 0)
        for row in rows
    ]
    evaluation = EvaluationService(retrieval=RankedRetrieval(hits), vector_store=store)
    case = EvaluationCase("What interest applies?", relevant_clauses=(("MSA-2026-014", "3.4"),))
    metrics = evaluation.measure((case,), k=2)
    assert metrics["hit_rate"] == 1
    assert metrics["mean_reciprocal_rank"] == 0.5
    assert metrics["evidence_recall"] == 1


def test_missing_labels_fail_instead_of_reporting_misleading_zero_quality():
    store = InMemoryVectorStore()
    evaluation = EvaluationService(retrieval=RankedRetrieval([]), vector_store=store)
    case = EvaluationCase("Payment?", frozenset({"retired-corpus::002"}))
    with pytest.raises(ValueError, match="label.*not.*index"):
        evaluation.hit_rate_at_k((case,))


def test_multisource_recall_requires_every_labeled_source():
    store = InMemoryVectorStore()
    rows = [
        IndexedChunk(name, "3.4 Payment.", "Section 3.4", 0, name, "contract")
        for name in ("MSA-2026-014", "MSA-2026-022")
    ]
    store.upsert(rows, [[1], [1]])
    first = rows[0]
    retrieval = RankedRetrieval(
        [
            RetrievedChunk(
                first.id, first.document, first.document_type, first.heading, first.text, 0
            )
        ]
    )
    evaluation = EvaluationService(retrieval=retrieval, vector_store=store)
    case = EvaluationCase(
        "Compare payment.",
        relevant_clauses=(
            ("MSA-2026-014", "3.4"),
            ("MSA-2026-022", "3.4"),
        ),
    )
    metrics = evaluation.measure((case,), k=2)
    assert metrics["hit_rate"] == 1
    assert metrics["evidence_recall"] == 0.5
    assert metrics["all_evidence_rate"] == 0
