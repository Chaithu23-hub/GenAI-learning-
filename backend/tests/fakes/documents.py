"""In-memory document ports for upload boundary tests."""

from pathlib import Path

from legal_rag.infrastructure.errors import DocumentConflictError


class MemoryDocumentSource:
    def __init__(self):
        self.documents: dict[str, str] = {}

    def iter_documents(self, docs_dir=None):
        return iter(())

    def write_document(self, name, text):
        if name in self.documents:
            raise DocumentConflictError("Document already exists.")
        self.documents[name] = text
        return Path(name)

    def write_documents(self, documents):
        names = [name for name, _ in documents]
        if len(set(names)) != len(names) or any(name in self.documents for name in names):
            raise DocumentConflictError("Document already exists.")
        self.documents.update(documents)
        return [Path(name) for name in names]


class FakePDFTextExtractor:
    def __init__(self, *, text="Test document", error=None):
        self.text = text
        self.error = error

    def extract(self, data):
        if self.error is not None:
            raise self.error
        return self.text
