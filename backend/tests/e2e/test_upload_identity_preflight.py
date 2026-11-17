"""Upload persistence preflight for parsed legal document identities."""

from pathlib import Path

import pytest

from legal_rag.infrastructure.documents.shared_corpus_loader import (
    SharedCorpusDocumentSource,
)
from legal_rag.infrastructure.errors import DocumentConflictError, DocumentSourceError


def markdown(document_no: str, title: str = "Master Services Agreement") -> str:
    return f"# {title}\n\n**Agreement No.:** {document_no}\n\nContract text.\n"


def test_batch_with_duplicate_source_ids_writes_no_files(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    source = SharedCorpusDocumentSource(docs_dir)

    with pytest.raises(DocumentConflictError):
        source.write_documents(
            [
                ("first.md", markdown("MSA-2026-014")),
                ("second.md", markdown("MSA-2026-014")),
            ]
        )

    assert not docs_dir.exists()


def test_existing_duplicate_source_id_writes_no_new_file(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    existing = docs_dir / "existing.md"
    existing.write_text(markdown("MSA-2026-014"), encoding="utf-8")
    source = SharedCorpusDocumentSource(docs_dir)

    with pytest.raises(DocumentConflictError):
        source.write_document("incoming.md", markdown("MSA-2026-014"))

    assert sorted(path.name for path in docs_dir.iterdir()) == ["existing.md"]
    assert existing.read_text(encoding="utf-8") == markdown("MSA-2026-014")


def test_existing_invalid_corpus_leaves_no_upload_files(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    existing = docs_dir / "schedule.md"
    existing.write_text(
        "# Schedules to Master Services Agreement\n\nDocument text without a table.\n",
        encoding="utf-8",
    )
    source = SharedCorpusDocumentSource(docs_dir)

    with pytest.raises(DocumentSourceError):
        source.write_document("incoming.md", markdown("MSA-2026-015"))

    assert sorted(path.name for path in docs_dir.iterdir()) == ["schedule.md"]


def test_existing_filename_conflict_remains_a_conflict(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    existing = docs_dir / "existing.md"
    existing.write_text("Original contents\n", encoding="utf-8")
    source = SharedCorpusDocumentSource(docs_dir)

    with pytest.raises(DocumentConflictError, match="filename already exists"):
        source.write_document("existing.md", markdown("MSA-2026-014"))

    assert existing.read_text(encoding="utf-8") == "Original contents\n"
