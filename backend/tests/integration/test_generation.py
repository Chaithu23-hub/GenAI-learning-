import json

import pytest

from legal_rag.application.workflows.generation import GenerationSettings, LLMGenerator
from legal_rag.domain.exceptions import SchemaValidationError
from legal_rag.infrastructure.errors import PermanentLLMError, TransientLLMError
from tests.fakes.fake_llm import FakeLLMClient


def _gen_settings(container):
    s = container.settings
    return GenerationSettings(
        min_relevant_score=s.min_relevant_score,
        out_of_scope_answer=s.out_of_scope_answer,
        llm_temperature=s.llm_temperature,
    )


def generator(container, llm):
    return LLMGenerator(
        retrieval=container.retrieval_service,
        vector_store=container.vector_store,
        llm=llm,
        settings=_gen_settings(container),
    )


def test_invalid_json_raises_after_one_correction(container):
    llm = FakeLLMClient(responses=[{"content": "not JSON"}, {"content": "still not JSON"}])
    with pytest.raises(SchemaValidationError):
        generator(container, llm).generate("late payment")
    assert len(llm.calls) == 2


def test_valid_llm_json_is_returned(container):
    chunk = container.retrieval_service.retrieve("late payment")[0]
    answer = {
        "answer": "Late payment interest is 1.5% per month per Amendment 1.",
        "reasoning": "The retrieved amendment supports the rate.",
        "sources": [
            {"document": chunk.document, "chunk_id": chunk.chunk_id, "excerpt": chunk.text[:100]}
        ],
        "confidence": "high",
        "out_of_scope": False,
    }
    llm = FakeLLMClient(responses=[{"content": json.dumps(answer)}])
    assert (
        generator(container, llm).generate("What is late payment interest?")["answer"]
        == answer["answer"]
    )
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    "error", [TransientLLMError("rate limited"), PermanentLLMError("invalid key")]
)
def test_provider_failure_propagates_without_substitute_answer(container, error):
    class FailedLLM(FakeLLMClient):
        def chat(self, **kwargs):
            self.calls.append(kwargs)
            raise error

    llm = FailedLLM()
    with pytest.raises(type(error), match=str(error)):
        generator(container, llm).generate("late payment")
    # The provider adapter owns retries; generation does not multiply calls.
    assert len(llm.calls) == 1


def test_failure_during_correction_propagates(container):
    class FailedCorrection(FakeLLMClient):
        def chat(self, **kwargs):
            if self.calls:
                raise TransientLLMError("correction failed")
            return super().chat(**kwargs)

    with pytest.raises(TransientLLMError, match="correction failed"):
        generator(container, FailedCorrection()).generate("late payment")


def test_failure_after_tool_rounds_propagates(container):
    class FailedFinal(FakeLLMClient):
        def chat(self, **kwargs):
            if kwargs.get("tools") is None:
                raise TransientLLMError("final call failed")
            return super().chat(**kwargs)

    llm = FailedFinal(
        responses=[
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "lookup",
                        "name": "retrieve_chunks",
                        "arguments": '{"query":"late payment"}',
                    }
                ],
            }
        ]
    )
    gen = generator(container, llm)
    gen._settings.max_tool_rounds = 1
    with pytest.raises(TransientLLMError, match="final call failed"):
        gen.generate("late payment")
