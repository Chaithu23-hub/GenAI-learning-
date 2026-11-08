"""Retrieval intent and ranking regressions using only in-memory ports."""

import pytest

from legal_rag.application.workflows.retrieval import RetrievalService, RetrievalSettings
from legal_rag.domain.entities import IndexedChunk
from tests.fakes.embedder import HashEmbedder
from tests.fakes.vector_store import InMemoryVectorStore


class ConstantReranker:
    def score(self, query, texts):
        return [2.0 if "original" in text else 1.8 for text in texts]


def make_retrieval():
    store = InMemoryVectorStore()
    embedder = HashEmbedder()
    rows = [
        IndexedChunk(
            "original",
            "original payment term",
            "Payment",
            0,
            "MSA-2026-014",
            "contract",
            {
                "source_doc": "MSA-2026-014",
                "counterparty": "Northwind Logistics",
                "effective_date": "2026-01-01",
            },
        ),
        IndexedChunk(
            "amendment",
            "revised payment term",
            "Payment",
            0,
            "AMD-2026-014-02",
            "amendment",
            {
                "source_doc": "AMD-2026-014-02",
                "counterparty": "Northwind Logistics",
                "effective_date": "2026-08-01",
            },
        ),
    ]
    store.upsert(rows, embedder.embed([row.text for row in rows]))
    return RetrievalService(
        vector_store=store,
        embedder=embedder,
        reranker=ConstantReranker(),
        settings=RetrievalSettings(10, 10, True, 60),
    )


@pytest.mark.parametrize(
    "question",
    [
        "What payment terms apply to Northwind as of 2026-09-01?",
        "What notice applies to the Northwind incident on 2026-09-01?",
        "Is 2026-09-01 a Northwind holiday?",
    ],
)
def test_incidental_dates_do_not_exclude_document_evidence(question):
    retrieval = make_retrieval()
    filters = retrieval.detect_metadata_filter(question)
    assert filters == {"counterparty": "Northwind Logistics"}
    assert {row.chunk_id for row in retrieval.retrieve(question, where=filters)} == {
        "original",
        "amendment",
    }


def test_explicit_effective_date_lookup_still_filters():
    retrieval = make_retrieval()
    question = "Find the Northwind document effective on 2026-08-01"
    filters = retrieval.detect_metadata_filter(question)
    assert filters == {"counterparty": "Northwind Logistics", "effective_date": "2026-08-01"}
    assert [row.chunk_id for row in retrieval.retrieve(question, where=filters)] == ["amendment"]


def test_filename_amendment_number_does_not_override_reranker():
    results = make_retrieval().retrieve("What is the original payment term?")
    assert results[0].chunk_id == "original"
    assert [row.score for row in results] == [2.0, 1.8]
