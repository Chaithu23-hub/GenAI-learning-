"""Chroma persistence adapter used by ingestion and retrieval."""

import math
import re

import chromadb

from .. import config

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
COLLECTION_NAME = "legal_docs"


def get_collection(client=None):
    """Return (or create) the Chroma collection with cosine distance."""
    client = client or chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def dense_search(query, k=config.TOP_K_CANDIDATES, where=None, client=None):
    """Run a dense similarity search against the configured collection."""
    from ..ingestion.embeddings import embed_query

    return get_collection(client).query(
        query_embeddings=[embed_query(query)],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )


def keyword_search(query, k=config.TOP_K_CANDIDATES, where=None, client=None):
    """Run the local BM25-style lexical search used by hybrid retrieval."""
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
            idf = math.log(
                1 + (len(documents) - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
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