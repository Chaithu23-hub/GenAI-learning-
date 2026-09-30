"""Reranker fakes."""
from __future__ import annotations


class IdentityReranker:
    """Every candidate gets score 1.0; preserves incoming order."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [1.0 for _ in texts]


class ScoringReranker:
    """Token-overlap score, useful for asserting relevance ordering."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        q_terms = set(query.lower().split())
        return [
            sum(1.0 for t in text.lower().split() if t in q_terms)
            for text in texts
        ]
