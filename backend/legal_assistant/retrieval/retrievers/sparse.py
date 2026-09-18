"""Sparse lexical retrieval adapter."""

from ... import config
from ...stores.vector_store import keyword_search


def retrieve_sparse(query, k=config.TOP_K_CANDIDATES, where=None, client=None):
    """Retrieve candidates from the local lexical index."""
    return keyword_search(query, k=k, where=where, client=client)