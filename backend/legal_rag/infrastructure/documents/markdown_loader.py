"""Filesystem-backed markdown document source."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from legal_rag.infrastructure.errors import DocumentSourceError


class MarkdownDocumentSource:
    """Loads ``*.md`` files from a directory. Implements ``DocumentSource``."""

    def __init__(self, docs_dir: Path):
        self._docs_dir = Path(docs_dir)

    def iter_documents(self) -> Iterable[tuple[Path, str]]:
        if not self._docs_dir.exists():
            raise DocumentSourceError(f"docs directory not found: {self._docs_dir}")
        paths = sorted(self._docs_dir.glob("*.md"))
        if not paths:
            raise DocumentSourceError(f"no .md documents found in {self._docs_dir}")
        for path in paths:
            yield path, path.read_text(encoding="utf-8")

    def write_document(self, name: str, text: str) -> Path:
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        target = self._docs_dir / name
        target.write_text(text, encoding="utf-8")
        return target


def document_type_for(filename: str) -> str:
    """Legal-domain convention: ``amendment_*.md`` are amendments; everything else is a contract."""
    return "amendment" if Path(filename).stem.lower().startswith("amendment") else "contract"
