"""Persistence adapters used by the RAG application."""

from .vector_store import dense_search, get_collection, keyword_search

__all__ = ["dense_search", "get_collection", "keyword_search"]