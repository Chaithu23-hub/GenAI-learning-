"""Dense retrieval adapter."""

from ... import config
from ...stores.vector_store import dense_search


def retrieve_dense(query, k=config.TOP_K_CANDIDATES, where=None, client=None):
    """Retrieve candidates from the embedding index."""
    return dense_search(query, k=k, where=where, client=client)