"""Backward-compatible imports for the pre-stores ingestion API."""

from ..stores.vector_store import dense_search, get_collection, keyword_search
from .pipeline import document_type_for, ingest_documents


def query_store(query, k=None, where=None, client=None):
    """Deprecated alias for the dense persistence adapter."""
    if k is None:
        return dense_search(query, where=where, client=client)
    return dense_search(query, k=k, where=where, client=client)


def keyword_store(query, k=None, where=None, client=None):
    """Deprecated alias for the lexical persistence adapter."""
    if k is None:
        return keyword_search(query, where=where, client=client)
    return keyword_search(query, k=k, where=where, client=client)


__all__ = [
    "document_type_for",
    "get_collection",
    "ingest_documents",
    "keyword_store",
    "query_store",
]
