"""Exercise the Chroma adapter against in-memory collection responses."""

import re

import pytest

from legal_rag.infrastructure.errors import VectorStoreError
from legal_rag.infrastructure.vector_store import chroma


class MemoryCollection:
    def __init__(self):
        self.rows = {
            "ids": ["alpha", "beta"],
            "documents": ["alpha alpha", "beta"],
            "metadatas": [{"document": "first"}, {"document": "second"}],
        }

    def get(self, **kwargs):
        return self.rows


class CountedTokenizer:
    def __init__(self):
        self.calls = 0

    def findall(self, text):
        self.calls += 1
        return re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text)


def test_repeated_search_reuses_token_statistics_without_reusing_stale_rows(monkeypatch):
    tokenizer = CountedTokenizer()
    monkeypatch.setattr(chroma, "_TOKEN_RE", tokenizer)
    store = chroma.ChromaVectorStore("unused")
    collection = MemoryCollection()
    store._collection = collection
    assert [row["id"] for row in store.keyword_search("alpha", k=2)] == ["alpha"]
    assert [row["id"] for row in store.keyword_search("alpha", k=2)] == ["alpha"]
    # Two query tokenizations and one tokenization per document, not per query.
    assert tokenizer.calls == 4
    collection.rows = {
        "ids": ["replacement"],
        "documents": ["alpha revised"],
        "metadatas": [{"document": "revision"}],
    }
    assert store.keyword_search("alpha", k=2) == [
        {"id": "replacement", "document": "alpha revised", "metadata": {"document": "revision"}},
    ]


def test_citation_lookup_io_failure_is_not_misreported_as_missing_evidence():
    class UnavailableCollection:
        def get(self, **kwargs):
            raise OSError("storage unavailable")

    store = chroma.ChromaVectorStore("unused")
    store._collection = UnavailableCollection()
    with pytest.raises(VectorStoreError, match="get_document_text failed"):
        store.get_document_text("source::000")
