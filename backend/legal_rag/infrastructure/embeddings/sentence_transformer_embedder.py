"""SentenceTransformers-backed embedder adapter."""
from __future__ import annotations

from threading import Lock

from legal_rag.infrastructure.errors import EmbeddingError
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class SentenceTransformerEmbedder:
    """Lazy-loading, thread-safe bi-encoder embedder implementing ``Embedder``."""

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None
        self._lock = Lock()

    def _model_or_load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise EmbeddingError("sentence-transformers not installed") from exc
                log.info("loading embedding model", extra={"model": self._model_name})
                self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = self._model_or_load().encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"embed failed: {exc}") from exc
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
