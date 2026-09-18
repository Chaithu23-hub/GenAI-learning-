"""Rank-fusion utilities for combining retrieval strategies."""

from ... import config


def reciprocal_rank_fusion(*ranked_lists, rrf_k=config.RRF_K):
    """Combine ranked chunk-id lists with reciprocal rank fusion."""
    fused = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (rrf_k + rank)
    return fused