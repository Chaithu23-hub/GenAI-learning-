import json
import logging

from legal_rag.application.workflows.generation import (
    ExtractiveGenerator,
    LLMGenerator,
)
from tests.fakes.fake_llm import FakeLLMClient
from tests.integration.test_generation import _gen_settings


class RateLimitedLLM:
    def chat(self, **kwargs):
        raise RuntimeError("provider returned HTTP 429")


def test_termination_answer_cannot_cite_a_different_section(container, caplog):
    caplog.set_level("INFO")
    query = "termination notice"
    termination_chunk = next(
        chunk
        for chunk in container.retrieval_service.retrieve(query)
        if chunk.heading == "Section 5: Termination"
    )
    wrong_answer = {
        "answer": "Section 3 permits either party to terminate with 30 days' notice.",
        "reasoning": "The contract permits termination.",
        "sources": [{
            "document": termination_chunk.document,
            "chunk_id": termination_chunk.chunk_id,
            "excerpt": termination_chunk.text,
        }],
        "confidence": "high",
        "out_of_scope": False,
    }
    llm = FakeLLMClient(responses=[{"content": json.dumps(wrong_answer)}])
    generator = LLMGenerator(
        retrieval=container.retrieval_service,
        vector_store=container.vector_store,
        llm=llm,
        settings=_gen_settings(container),
        fallback=ExtractiveGenerator(
            retrieval=container.retrieval_service,
            settings=_gen_settings(container),
        ),
    )

    result = generator.generate(query)

    assert "Section 3 permits" not in result["answer"]
    assert len(llm.calls) == 2
    trace = next(
        (record for record in caplog.records if record.getMessage() == "qa trace"),
        None,
    )
    assert trace is not None, [
        (record.getMessage(), getattr(record, "error", None))
        for record in caplog.records
    ]
    assert trace.prompt_version == "v2"
    assert "5" in trace.answer_clause_refs
    assert "3" in trace.spans[1]["candidate_clause_refs"]
    assert trace.spans[1]["validation_errors"]
    assert termination_chunk.chunk_id in trace.retrieved_context_ids
    assert trace.spans[0]["latency_ms"] >= 0
    assert trace.spans[1]["input_tokens"] == 10
    assert trace.spans[1]["output_tokens"] == 5
    assert trace.spans[1]["cost_usd"] is None
    logging.getLogger(__name__).info(
        "week11 controlled trace: %s",
        json.dumps({
            "case_id": 26,
            "prompt_version": trace.prompt_version,
            "retrieved_context_ids": trace.retrieved_context_ids,
            "answer_clause_refs": trace.answer_clause_refs,
            "candidate_clause_refs": [
                span.get("candidate_clause_refs", []) for span in trace.spans
            ],
            "spans": trace.spans,
            "total_latency_ms": trace.total_latency_ms,
            "cost_basis": "fake LLM usage; provider cost unavailable",
        }, sort_keys=True),
    )


def test_rate_limited_generation_emits_trace_before_fallback(container, caplog):
    caplog.set_level("INFO")
    generator = LLMGenerator(
        retrieval=container.retrieval_service,
        vector_store=container.vector_store,
        llm=RateLimitedLLM(),
        settings=_gen_settings(container),
        fallback=ExtractiveGenerator(
            retrieval=container.retrieval_service,
            settings=_gen_settings(container),
        ),
    )

    result = generator.generate("termination notice")

    assert result["sources"]
    trace = next(
        record for record in caplog.records if record.getMessage() == "qa trace"
    )
    assert trace.spans[-1]["error_type"] == "RuntimeError"
    assert trace.spans[-1]["input_tokens"] is None
    assert trace.retrieved_context_ids
