"""Chroma vector store: persistence, ingestion, and similarity queries."""

from pathlib import Path

from . import config
from .chunking import chunk_document
from .embeddings import embed, embed_query

COLLECTION_NAME = "legal_docs"


def document_type_for(filename):
    """Derive the document_type metadata value from the filename convention.

    Files named `amendment_*` are amendments; everything else is a contract.
    """
    return "amendment" if Path(filename).stem.lower().startswith("amendment") else "contract"


def get_collection(client=None):
    """Return (creating if needed) the persisted Chroma collection."""
    import chromadb

    # [TOPIC: Qdrant / Chroma / pgvector] — Chroma for local dev; swap the
    # client for Qdrant in production, or pgvector if the stack already runs
    # on Postgres.
    # [TOPIC: Vector databases (HNSW)] — Chroma persists chunk vectors on disk
    # and indexes them with HNSW, so nearest-neighbour search stays fast as
    # the corpus grows. Cosine space matches our normalized embeddings.
    client = client or chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_documents(docs_dir=None, client=None):
    """Chunk, embed, and upsert every markdown document in `docs_dir`.

    Returns the total number of chunks stored.
    """
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

    # [TOPIC: Embeddings & dense retrieval] — embed every chunk in one batch
    # and store the vectors alongside metadata for later filtering.
    collection.upsert(ids=ids, documents=texts, embeddings=embed(texts), metadatas=metadatas)
    return len(ids)


def query_store(query, k=config.TOP_K_CANDIDATES, where=None, client=None):
    """Run similarity search for `query` and return raw Chroma results."""
    collection = get_collection(client)
    # [TOPIC: Similarity search & top-K] — ask the HNSW index for the k
    # nearest-neighbour chunks of the question embedding.
    # [TOPIC: Metadata filtering] — `where` (e.g. {"document_type":
    # "amendment"}) narrows the candidate set before/alongside the ANN search.
    return collection.query(
        query_embeddings=[embed_query(query)],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
