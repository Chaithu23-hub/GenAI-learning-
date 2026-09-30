"""Cross-encoder reranker adapter."""
from __future__ import annotations

from threading import Lock

from legal_rag.infrastructure.errors import EmbeddingError
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class CrossEncoderReranker:
    """Lazy-loading cross-encoder implementing ``Reranker``."""

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
                    from sentence_transformers import CrossEncoder
                except ImportError as exc:
                    raise EmbeddingError("sentence-transformers not installed") from exc
                log.info("loading rerank model", extra={"model": self._model_name})
                self._model = CrossEncoder(self._model_name)
        return self._model

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        try:
            scores = self._model_or_load().predict([(query, text) for text in texts])
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"rerank failed: {exc}") from exc
        return [float(s) for s in scores]
