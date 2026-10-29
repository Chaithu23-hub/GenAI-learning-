"""Ingestion service — read → chunk → embed → upsert."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from legal_rag.application.ports import Chunker, DocumentSource, Embedder, VectorStore
from legal_rag.domain.entities import IndexedChunk
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
            for chunk in chunks:
                metadata = dict(document.metadata)
                metadata["clause_ref"] = chunk.heading or "Preamble"
                indexed.append(IndexedChunk(
                    id=f"{metadata['source_doc']}::{chunk.index:03d}",
                    text=chunk.text,
                    heading=chunk.heading,
                    chunk_index=chunk.index,
                    document=document.name,
                    document_type=document.document_type,
                    metadata=metadata,
                ))
                texts.append(chunk.text)
        embeddings = self._embedder.embed(texts)
        self._vector_store.upsert(indexed, embeddings)
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
