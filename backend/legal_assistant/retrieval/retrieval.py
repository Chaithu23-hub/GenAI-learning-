from dataclasses import dataclass, field
from functools import lru_cache

from .. import config
from ..ingestion.vector_store import keyword_store, query_store

# [Similarity search & top-K] [Bi-encoder vs cross-encoder]
# Stage 1: dense recall (bi-encoder) fused with BM25 via reciprocal rank fusion.
# Stage 2: cross-encoder re-ranks the fused candidate set and keeps top-N.


@dataclass
class RetrievedChunk:
    chunk_id: str
    document: str
    document_type: str
    heading: str
    text: str
    distance: float   # cosine distance from the bi-encoder (lower = closer)
    score: float = field(default=0.0)  # cross-encoder relevance score (higher = better)


@lru_cache(maxsize=1)
def _get_reranker():
    """Load and cache the cross-encoder re-ranker model."""
    from sentence_transformers import CrossEncoder
    return CrossEncoder(config.RERANK_MODEL)


def _rrf_ranks(*ranked_lists):
    """Reciprocal Rank Fusion — combines multiple ranked lists into a single score dict."""
    fused = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (config.RRF_K + rank)
    return fused


def retrieve(query, k=config.TOP_K_CANDIDATES, n=config.TOP_N_ANSWERS, where=None,
             client=None, hybrid=config.HYBRID_ENABLED):
    """Hybrid retrieve: dense + BM25 → RRF → cross-encoder re-rank → top-N."""
    raw = query_store(query, k=k, where=where, client=client)
    dense_candidates = [
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
    candidates_by_id = {candidate.chunk_id: candidate for candidate in dense_candidates}
    ranked_lists = [[candidate.chunk_id for candidate in dense_candidates]]

    if hybrid:
        lexical_candidates = keyword_store(query, k=k, where=where, client=client)
        ranked_lists.append([candidate["id"] for candidate in lexical_candidates])
        for candidate in lexical_candidates:
            candidates_by_id.setdefault(candidate["id"], RetrievedChunk(
                chunk_id=candidate["id"],
                document=candidate["metadata"]["document"],
                document_type=candidate["metadata"]["document_type"],
                heading=candidate["metadata"]["heading"],
                text=candidate["document"],
                distance=1.0,
            ))

    rrf_scores = _rrf_ranks(*ranked_lists)
    candidates = sorted(
        (candidates_by_id[chunk_id] for chunk_id in rrf_scores),
        key=lambda candidate: rrf_scores[candidate.chunk_id],
        reverse=True,
    )
    if not candidates:
        return []

    # Cross-encoder re-ranks and keeps the n most relevant chunks for generation.
    reranker = _get_reranker()
    scores = reranker.predict([(query, c.text) for c in candidates])
    for candidate, score in zip(candidates, scores):
        candidate.score = float(score)
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:n]
