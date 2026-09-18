"""Offline ingestion orchestration: read, chunk, embed, and index documents."""

from pathlib import Path

from .. import config
from ..stores.vector_store import get_collection
from .chunking import chunk_document
from .embeddings import embed


def document_type_for(filename):
    """Derive document type metadata from the filename convention."""
    return "amendment" if Path(filename).stem.lower().startswith("amendment") else "contract"


def ingest_documents(docs_dir=None, client=None):
    """Chunk, embed, and upsert all markdown documents in ``docs_dir``."""
    docs_dir = docs_dir or config.DOCS_DIR
    collection = get_collection(client)
    docs = sorted(Path(docs_dir).glob("*.md"))
    if not docs:
        raise FileNotFoundError(f"No .md documents found in {docs_dir}")

    ids, texts, metadatas = [], [], []
    for path in docs:
        chunks = chunk_document(path.read_text(encoding="utf-8"))
        for chunk in chunks:
            ids.append(f"{path.stem}::{chunk.index:03d}")
            texts.append(chunk.text)
            metadatas.append({
                "document": path.name,
                "document_type": document_type_for(path.name),
                "heading": chunk.heading,
                "chunk_index": chunk.index,
            })

    collection.upsert(ids=ids, documents=texts, embeddings=embed(texts), metadatas=metadatas)
    return len(ids)