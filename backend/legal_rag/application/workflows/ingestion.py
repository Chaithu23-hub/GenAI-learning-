"""Ingestion service — read → chunk → embed → upsert."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from legal_rag.application.ports import Embedder, VectorStore
from legal_rag.domain.entities import IndexedChunk
from legal_rag.infrastructure.chunking import chunk_document
from legal_rag.infrastructure.documents.markdown_loader import (
    MarkdownDocumentSource,
    document_type_for,
)
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
        settings: IngestionSettings,
        docs_dir: Path,
    ):
        self._vector_store = vector_store
        self._embedder = embedder
        self._settings = settings
        self._docs_dir = Path(docs_dir)

    def ingest(self, docs_dir: Path | None = None) -> int:
        source_dir = Path(docs_dir) if docs_dir else self._docs_dir
        source = MarkdownDocumentSource(source_dir)
        indexed: list[IndexedChunk] = []
        texts: list[str] = []
        for path, text in source.iter_documents():
            chunks = chunk_document(
                text,
                chunk_size=self._settings.chunk_size_tokens,
                overlap=self._settings.chunk_overlap_tokens,
            )
            for chunk in chunks:
                indexed.append(IndexedChunk(
                    id=f"{path.stem}::{chunk.index:03d}",
                    text=chunk.text,
                    heading=chunk.heading,
                    chunk_index=chunk.index,
                    document=path.name,
                    document_type=document_type_for(path.name),
                ))
                texts.append(chunk.text)
        embeddings = self._embedder.embed(texts)
        self._vector_store.upsert(indexed, embeddings)
        log.info("ingestion complete",
                 extra={"chunks": len(indexed), "docs_dir": str(source_dir)})
        _metrics.ingested_chunks.inc(len(indexed))
        return len(indexed)
