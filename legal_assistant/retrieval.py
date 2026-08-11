"""Two-stage retrieval: fast bi-encoder recall, then precise cross-encoder re-ranking."""

from dataclasses import dataclass, field
from functools import lru_cache

from . import config
from .vector_store import query_store


@dataclass
class RetrievedChunk:
    chunk_id: str
    document: str
    document_type: str
    heading: str
    text: str
    distance: float  # cosine distance from the bi-encoder (lower = closer)
    score: float = field(default=0.0)  # cross-encoder relevance score


@lru_cache(maxsize=1)
def _get_reranker():
    # (question, chunk) pair jointly, which is far more precise than comparing
    # two independent embeddings — but too slow to run over the whole corpus,
    # so we only ever use it on the handful of bi-encoder candidates.
    from sentence_transformers import CrossEncoder

    return CrossEncoder(config.RERANK_MODEL)


def retrieve(query, k=config.TOP_K_CANDIDATES, n=config.TOP_N_ANSWERS, where=None, client=None):
    """Fetch k candidates from the vector store, re-rank, and return the top n."""
    raw = query_store(query, k=k, where=where, client=client)
    candidates = [
        RetrievedChunk(
            chunk_id=chunk_id,
            document=meta["document"],
            document_type=meta["document_type"],
            heading=meta["heading"],
            text=text,
            distance=dist,
        )
        for chunk_id, text, meta, dist in zip(
            raw["ids"][0], raw["documents"][0], raw["metadatas"][0], raw["distances"][0]
        )
    ]
    if not candidates:
        return []

    # cross-encoder and keep the n most relevant chunks for generation.
    reranker = _get_reranker()
    scores = reranker.predict([(query, c.text) for c in candidates])
    for candidate, score in zip(candidates, scores):
        candidate.score = float(score)
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:n]
