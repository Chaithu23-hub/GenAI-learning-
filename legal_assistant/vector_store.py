import math
import re
from pathlib import Path
import chromadb

from . import config
from .chunking import chunk_document
from .embeddings import embed, embed_query

COLLECTION_NAME = "legal_docs"
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def document_type_for(filename):
    return "amendment" if Path(filename).stem.lower().startswith("amendment") else "contract"


def get_collection(client=None):
 
    client = client or chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_documents(docs_dir=None, client=None):

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


def query_store(query, k=config.TOP_K_CANDIDATES, where=None, client=None):
    collection = get_collection(client)
    return collection.query(
        query_embeddings=[embed_query(query)],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )


def keyword_store(query, k=config.TOP_K_CANDIDATES, where=None, client=None):
    collection = get_collection(client)
    stored = collection.get(include=["documents", "metadatas"], where=where)
    documents = stored.get("documents", [])
    if not documents:
        return []

    query_terms = TOKEN_RE.findall(query.lower())
    if not query_terms:
        return []
    term_frequency = []
    document_frequency = {}
    lengths = []
    for document in documents:
        terms = TOKEN_RE.findall(document.lower())
        lengths.append(len(terms))
        frequencies = {}
        for term in terms:
            frequencies[term] = frequencies.get(term, 0) + 1
        term_frequency.append(frequencies)
        for term in set(terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    average_length = sum(lengths) / len(lengths) or 1
    scored = []
    for index, frequencies in enumerate(term_frequency):
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (len(documents) - document_frequency[term] + 0.5)
                           / (document_frequency[term] + 0.5))
            normalization = frequency + 1.5 * (0.25 + 0.75 * lengths[index] / average_length)
            score += idf * frequency * 2.5 / normalization
        if score:
            scored.append((score, index))

    scored.sort(reverse=True)
    return [
        {
            "id": stored["ids"][index],
            "document": documents[index],
            "metadata": stored["metadatas"][index],
        }
        for _, index in scored[:k]
    ]
    