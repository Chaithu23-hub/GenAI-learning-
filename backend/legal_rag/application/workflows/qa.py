"""QA orchestration — guardrails → filter → retrieve → generate."""
from __future__ import annotations

import time
from typing import Any

from legal_rag.application.workflows.generation import Generator
from legal_rag.application.workflows.retrieval import RetrievalService
from legal_rag.domain.policies import is_greeting, screen_query
from legal_rag.infrastructure.observability import get_logger, get_metrics

log = get_logger(__name__)
_metrics = get_metrics()


class QaService:
    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        generator: Generator,
        guardrail_answer: str,
        no_drafting_answer: str,
        greeting_answer: str,
    ):
        self._retrieval = retrieval
        self._generator = generator
        self._guardrail_answer = guardrail_answer
        self._no_drafting_answer = no_drafting_answer
        self._greeting_answer = greeting_answer

    def answer(
        self,
        query: str,
        *,
        document_type: str | None = None,
    ) -> dict[str, Any]:
        if is_greeting(query):
            log.info("greeting handled", extra={"query": query})
            _metrics.greetings.inc()
            _metrics.requests.inc(outcome="greeting")
            return {
                "answer": self._greeting_answer,
                "reasoning": (
                    "The message is a greeting or small-talk phrase and does not "
                    "require a retrieval — a friendly canned reply is returned."
                ),
                "sources": [],
                "confidence": "high",
                "out_of_scope": False,
            }
        allowed, reason = screen_query(query)
        if not allowed:
            answer = (
                self._guardrail_answer if reason == "injection" else self._no_drafting_answer
            )
            log.info("guardrail blocked", extra={"reason": reason})
            _metrics.guardrail_blocks.inc(reason=reason or "unknown")
            _metrics.requests.inc(outcome="guardrail_blocked")
            return {
                "answer": answer,
                "reasoning": (
                    "The question was rejected by the input guardrails before "
                    f"retrieval: {reason} requests are answered with a fixed safe "
                    "response and never passed to the model."
                ),
                "sources": [],
                "confidence": "high",
                "out_of_scope": True,
            }
        where = self._resolve_where(query, document_type)
        started = time.perf_counter()
        result = self._generator.generate(query, where=where)
        outcome = "out_of_scope" if result.get("out_of_scope") else "answered"
        _metrics.request_duration.observe(
            time.perf_counter() - started, outcome=outcome
        )
        _metrics.requests.inc(outcome=outcome)
        return result

    def inspect(
        self, query: str, *, document_type: str | None = None
    ) -> dict[str, Any]:
        where = self._resolve_where(query, document_type)
        return {
            "question": query,
            "retrieved": self._retrieval.retrieve(query, where=where),
            "answer": self.answer(query, document_type=document_type),
        }

    def _resolve_where(
        self, query: str, document_type: str | None
    ) -> dict[str, str] | None:
        if document_type:
            return {"document_type": document_type}
        return self._retrieval.detect_metadata_filter(query)
