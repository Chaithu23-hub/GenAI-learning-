import json

import pytest

from legal_rag.application.workflows.generation import (
    ExtractiveGenerator,
    GenerationSettings,
    LLMGenerator,
)
from tests.fakes.fake_llm import FakeLLMClient


def _gen_settings(container):
    s = container.settings
    return GenerationSettings(
        min_relevant_score=s.min_relevant_score,
        high_confidence_score=s.high_confidence_score,
        out_of_scope_answer=s.out_of_scope_answer,
        llm_temperature=s.llm_temperature,
    )


class TestExtractiveGenerator:
    def test_grounded_when_chunks_score(self, container):
        gen = ExtractiveGenerator(
            retrieval=container.retrieval_service, settings=_gen_settings(container),
        )
        payload = gen.generate("late payment interest")
        assert not payload["out_of_scope"]
        assert payload["sources"]

    def test_out_of_scope_when_no_relevance(self, container):
        # Use an artificially high threshold so nothing passes.
        s = _gen_settings(container)
        s.min_relevant_score = 999.0
        gen = ExtractiveGenerator(retrieval=container.retrieval_service, settings=s)
        payload = gen.generate("obscure irrelevant")
        assert payload["out_of_scope"]
        assert payload["sources"] == []


class TestLLMGenerator:
    def test_fallback_when_llm_response_bad_json(self, container):
        llm = FakeLLMClient(responses=[{"content": "not JSON at all"}])
        gen = LLMGenerator(
            retrieval=container.retrieval_service,
            vector_store=container.vector_store,
            llm=llm,
            settings=_gen_settings(container),
            fallback=ExtractiveGenerator(
                retrieval=container.retrieval_service, settings=_gen_settings(container),
            ),
        )
        payload = gen.generate("late payment")
        # Should fall through to extractive generator.
        assert "answer" in payload

    def test_valid_llm_json_is_returned(self, container):
        chunks = container.retrieval_service.retrieve("late payment")
        chunk = chunks[0]
        response_json = {
            "answer": "Late payment interest is 1.5% per month per Amendment 1.",
            "reasoning": "The retrieved amendment says so.",
            "sources": [{
                "document": chunk.document, "chunk_id": chunk.chunk_id,
                "excerpt": chunk.text[:100],
            }],
            "confidence": "high",
            "out_of_scope": False,
        }
        llm = FakeLLMClient(responses=[{"content": json.dumps(response_json)}])
        gen = LLMGenerator(
            retrieval=container.retrieval_service,
            vector_store=container.vector_store,
            llm=llm,
            settings=_gen_settings(container),
            fallback=ExtractiveGenerator(
                retrieval=container.retrieval_service, settings=_gen_settings(container),
            ),
        )
        payload = gen.generate("What is late payment interest?")
        assert payload["answer"].startswith("Late payment")
        assert payload["sources"]
