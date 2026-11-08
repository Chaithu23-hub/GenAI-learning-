"""Ingestion service — read → chunk → embed → upsert."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from legal_rag.application.ports import Chunker, DocumentSource, Embedder, VectorStore
from legal_rag.domain.entities import IndexedChunk
from legal_rag.domain.exceptions import InvalidDocumentError
from legal_rag.infrastructure.observability import get_logger, get_metrics

log = get_logger(__name__)
_metrics = get_metrics()


@dataclass
class IngestionSettings:
    chunk_size_tokens: int
    chunk_overlap_tokens: int


class IngestionService:
    """Orchestrates document ingestion. Depends only on ports."""

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedder: Embedder,
        document_source: DocumentSource,
        chunker: Chunker,
        settings: IngestionSettings,
    ):
        self._vector_store = vector_store
        self._embedder = embedder
        self._document_source = document_source
        self._chunker = chunker
        self._settings = settings

    def ingest(self, docs_dir: Path | None = None) -> int:
        indexed: list[IndexedChunk] = []
        texts: list[str] = []
        documents = list(self._document_source.iter_documents(docs_dir))
        for document in documents:
            chunks = self._chunker.chunk(
                document.text,
                chunk_size=self._settings.chunk_size_tokens,
                overlap=self._settings.chunk_overlap_tokens,
            )
            if not chunks:
                raise InvalidDocumentError(f"Document {document.name} has no indexable text.")
            for chunk in chunks:
                metadata = dict(document.metadata)
                metadata["clause_ref"] = chunk.heading or "Preamble"
                # Assign a physical PDF page only when the whole indexed passage
                # maps uniquely to that page. Cross-page or ambiguous chunks stay
                # unnumbered; Markdown/DOCX have no stable physical pagination.
                normalized = " ".join(chunk.text.split())
                page_matches = [
                    number
                    for number, text in enumerate(document.pages, start=1)
                    if normalized and normalized in " ".join(text.split())
                ]
                if document.pages:
                    metadata.pop("page_number", None)
                    if len(page_matches) == 1:
                        metadata["page_number"] = page_matches[0]
                indexed.append(
                    IndexedChunk(
                        id=f"{metadata['source_doc']}::{chunk.index:03d}",
                        text=chunk.text,
                        heading=chunk.heading,
                        chunk_index=chunk.index,
                        document=document.name,
                        document_type=document.document_type,
                        metadata=metadata,
                    )
                )
                texts.append(chunk.text)
        embeddings = self._embedder.embed(texts)
        # Missing files are not an implicit request to revoke unrelated sources.
        current_ids = {chunk.id for chunk in indexed}
        obsolete_ids = [
            chunk_id
            for source in {chunk.metadata["source_doc"] for chunk in indexed}
            for chunk_id in self._vector_store.get_all(where={"source_doc": source})["ids"]
            if chunk_id not in current_ids
        ]
        self._vector_store.upsert(indexed, embeddings)
        # Chroma has no atomic upsert+delete transaction. Preserve old evidence
        # if staging/upsert fails; propagate cleanup failures to the caller.
        self._vector_store.delete_chunks(obsolete_ids)
        log.info(
            "ingestion complete",
            extra={
                "chunks": len(indexed),
                "documents": len(documents),
                "docs_dir": str(docs_dir) if docs_dir else None,
            },
        )
        _metrics.ingested_chunks.inc(len(indexed))
        return len(indexed)
