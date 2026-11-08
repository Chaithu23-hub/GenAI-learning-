"""Pure reciprocal rank fusion policy."""


def reciprocal_rank_fusion(*ranked_lists: list[str], rrf_k: int = 60) -> dict[str, float]:
    """Combine ranked IDs; higher scores represent stronger combined evidence."""
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (rrf_k + rank)
    return fused
