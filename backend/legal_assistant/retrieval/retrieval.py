from dataclasses import dataclass, field
from .. import config
from .reranking.cross_encoder import rerank
from .retrievers.dense import retrieve_dense
from .retrievers.hybrid import reciprocal_rank_fusion
from .retrievers.sparse import retrieve_sparse

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


def retrieve(query, k=config.TOP_K_CANDIDATES, n=config.TOP_N_ANSWERS, where=None,
             client=None, hybrid=config.HYBRID_ENABLED):
    """Hybrid retrieve: dense + BM25 → RRF → cross-encoder re-rank → top-N."""
    raw = retrieve_dense(query, k=k, where=where, client=client)
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
        lexical_candidates = retrieve_sparse(query, k=k, where=where, client=client)
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

    rrf_scores = reciprocal_rank_fusion(*ranked_lists)
    candidates = sorted(
        (candidates_by_id[chunk_id] for chunk_id in rrf_scores),
        key=lambda candidate: rrf_scores[candidate.chunk_id],
        reverse=True,
    )
    if not candidates:
        return []

    return rerank(query, candidates, n=n)
