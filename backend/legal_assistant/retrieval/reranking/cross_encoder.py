"""Cross-encoder reranking for retrieved chunks."""

from functools import lru_cache

from ... import config


@lru_cache(maxsize=1)
def _get_reranker():
    """Load and cache the configured cross-encoder model."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(config.RERANK_MODEL)


def rerank(query, candidates, n=config.TOP_N_ANSWERS):
    """Score candidates for query relevance and return the top ``n``."""
    if not candidates:
        return []

    scores = _get_reranker().predict([(query, candidate.text) for candidate in candidates])
    for candidate, score in zip(candidates, scores):
        candidate.score = float(score)
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates[:n]