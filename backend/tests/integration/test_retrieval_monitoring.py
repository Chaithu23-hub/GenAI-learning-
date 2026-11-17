"""Retrieval monitoring remains a transparent application port decorator."""

import pytest

from legal_rag.application.workflows.retrieval import RetrievalService, RetrievalSettings
from tests.fakes.embedder import HashEmbedder
from tests.fakes.vector_store import InMemoryVectorStore


class ConstantReranker:
    def score(self, query, texts):
        return [1.0 for _ in texts]


class RecordingMonitoring:
    def __init__(self):
        self.calls = []

    def run(self, name, operation, *, as_type="span"):
        self.calls.append((name, as_type))
        return operation()


def make_retrieval(monitoring=None):
    return RetrievalService(
        vector_store=InMemoryVectorStore(),
        embedder=HashEmbedder(),
        reranker=ConstantReranker(),
        settings=RetrievalSettings(10, 5, True, 60),
        monitoring=monitoring,
    )


def test_retrieval_is_recorded_once_as_retriever_and_returns_results():
    monitoring = RecordingMonitoring()
    retrieval = make_retrieval(monitoring)

    assert retrieval.retrieve("a query") == []
    assert monitoring.calls == [("retrieve-context", "retriever")]


def test_retrieval_errors_propagate_through_monitoring():
    class FailingEmbedder:
        def embed_query(self, query):
            raise ValueError("embedding failed")

    monitoring = RecordingMonitoring()
    retrieval = RetrievalService(
        vector_store=InMemoryVectorStore(),
        embedder=FailingEmbedder(),
        reranker=ConstantReranker(),
        settings=RetrievalSettings(10, 5, True, 60),
        monitoring=monitoring,
    )

    with pytest.raises(ValueError, match="embedding failed"):
        retrieval.retrieve("a query")
    assert monitoring.calls == [("retrieve-context", "retriever")]


def test_retrieval_without_monitoring_remains_supported():
    assert make_retrieval().retrieve("a query") == []
