import pytest

from legal_rag.application.workflows.ingestion import IngestionService, IngestionSettings
from legal_rag.domain.entities import Document
from legal_rag.infrastructure.chunking.section_chunker import SectionChunker
from tests.fakes.embedder import HashEmbedder
from tests.fakes.vector_store import InMemoryVectorStore


class Documents:
    def __init__(self, document):
        self.document = document

    def iter_documents(self, docs_dir=None):
        return iter([self.document])


@pytest.mark.parametrize("pages, expected", [
    (("First page.", "3.4 Late Payment. Interest is 1.5%."), 2),
    (("3.4 Late Payment.", "Interest is 1.5%."), None),
    (("3.4 Late Payment. Interest is 1.5%.", "3.4 Late Payment. Interest is 1.5%."), None),
    ((), None),
])
def test_only_unique_whole_passage_page_matches_are_indexed(pages, expected):
    text = "3.4 Late Payment. Interest is 1.5%."
    document = Document("MSA-2026-014", text, "contract", {"source_doc": "MSA-2026-014"}, pages)
    store = InMemoryVectorStore()
    service = IngestionService(vector_store=store, embedder=HashEmbedder(), document_source=Documents(document),
                               chunker=SectionChunker(), settings=IngestionSettings(512, 50))
    service.ingest()
    metadata = store.get_all()["metadatas"][0]
    assert metadata.get("page_number") == expected
