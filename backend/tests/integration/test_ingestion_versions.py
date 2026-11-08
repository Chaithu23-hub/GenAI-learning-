"""Successful re-ingestion removes obsolete passages without touching other sources."""

import pytest

from legal_rag.application.workflows.ingestion import IngestionService, IngestionSettings
from legal_rag.domain.entities import Document
from legal_rag.infrastructure.chunking.section_chunker import SectionChunker
from tests.fakes.embedder import HashEmbedder
from tests.fakes.vector_store import InMemoryVectorStore


class Documents:
    def __init__(self, documents):
        self.documents = documents

    def iter_documents(self, docs_dir=None):
        return iter(self.documents)


def document(text, source="MSA-2026-014", version="v1"):
    return Document(source, text, "contract", {"source_doc": source, "document_version": version})


def stack():
    source = Documents(
        [
            document("## Payment\nOld payment term.\n## Liability\nOld liability cap."),
            document("## Other\nAnother agreement.", source="MSA-2026-022"),
        ]
    )
    store, embedder = InMemoryVectorStore(), HashEmbedder()
    service = IngestionService(
        vector_store=store,
        embedder=embedder,
        document_source=source,
        chunker=SectionChunker(),
        settings=IngestionSettings(512, 50),
    )
    service.ingest()
    return source, store, service


def test_shorter_revision_removes_obsolete_chunks_and_preserves_other_documents():
    source, store, service = stack()
    source.documents = [document("## Payment\nRevised payment term.", version="v2")]
    assert service.ingest() == 1
    stored = store.get_all(where={"source_doc": "MSA-2026-014"})
    assert stored["ids"] == ["MSA-2026-014::000"]
    assert stored["documents"] == ["Revised payment term."]
    assert {meta["document_version"] for meta in stored["metadatas"]} == {"v2"}
    assert store.get_document_text("MSA-2026-022::000") == "Another agreement."


def test_embedding_failure_preserves_existing_revision():
    source, store, service = stack()
    before = store.get_all()
    source.documents = [document("## Payment\nChanged payment term.", version="v2")]

    class FailingEmbedder:
        def embed(self, texts):
            raise RuntimeError("embedding unavailable")

    service._embedder = FailingEmbedder()
    with pytest.raises(RuntimeError, match="embedding unavailable"):
        service.ingest()
    assert store.get_all() == before


def test_empty_revision_is_rejected_without_leaving_a_version_mixture():
    source, store, service = stack()
    before = store.get_all()
    source.documents = [document("", version="v2")]
    with pytest.raises(ValueError, match="no indexable text"):
        service.ingest()
    assert store.get_all() == before
