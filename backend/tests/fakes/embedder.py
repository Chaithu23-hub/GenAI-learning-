"""Deterministic hash-bucket embedder for tests (no ML deps)."""
from __future__ import annotations

import hashlib
import re


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class HashEmbedder:
    """Bag-of-tokens hashed into a fixed-size vector; deterministic and fast."""

    def __init__(self, dim: int = 128):
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in _tokens(text):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % self._dim] += 1.0
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]
