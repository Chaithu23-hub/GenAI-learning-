import pytest

from legal_rag.infrastructure.errors import DocumentSourceError


def test_ingest_returns_positive_count(container):
    count = container.ingestion_service.ingest()
    assert count > 0


def test_missing_docs_dir_raises(container, tmp_path):
    with pytest.raises(DocumentSourceError):
        container.ingestion_service.ingest(docs_dir=tmp_path / "missing")


def test_empty_docs_dir_raises(container, tmp_path):
    empty = tmp_path / "emptydir"
    empty.mkdir()
    with pytest.raises(DocumentSourceError):
        container.ingestion_service.ingest(docs_dir=empty)
