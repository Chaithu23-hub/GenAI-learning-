"""Greetings use the configured LLM adapter, without retrieving legal documents."""

import json

import pytest

from legal_rag.application.workflows.qa import QaService
from legal_rag.domain.exceptions import (
    ConversationUnavailableError,
    InvalidConversationResponseError,
)
from legal_rag.infrastructure.errors import TransientLLMError
from legal_rag.infrastructure.llm.conversation import LLMConversation
from tests.fakes.fake_llm import FakeLLMClient


class NoRetrieval:
    def __getattr__(self, name):
        raise AssertionError(f"Greeting unexpectedly called retrieval/generation: {name}")


def service(llm):
    return QaService(
        retrieval=NoRetrieval(),
        generator=NoRetrieval(),
        conversation=LLMConversation(llm),
        guardrail_answer="Blocked",
        no_drafting_answer="No drafting",
        out_of_scope_answer="Not in documents",
    )


@pytest.mark.parametrize(
    "query", ["Hello", "Hi!", "Hey there", "Good morning!", "GOOD AFTERNOON", "Good evening"]
)
def test_greeting_returns_llm_answer_without_retrieval(query):
    expected = "A distinctive model-generated welcome."
    llm = FakeLLMClient(
        responses=[{"content": json.dumps({"route": "general", "answer": expected})}]
    )
    result = service(llm).answer(query)
    assert result["answer"] == expected
    assert result["sources"] == []
    assert result["confidence"] == "high"
    assert result["out_of_scope"] is False
    assert len(llm.calls) == 1
    assert llm.calls[0]["messages"][-1] == {"role": "user", "content": query}
    assert llm.calls[0]["tools"] is None


def test_repeated_greetings_each_call_llm_instead_of_reusing_static_text():
    llm = FakeLLMClient(
        responses=[
            {"content": json.dumps({"route": "general", "answer": reply})}
            for reply in ("First model welcome", "Second model welcome")
        ]
    )
    qa = service(llm)
    assert qa.answer("Hi")["answer"] == "First model welcome"
    assert qa.answer("Hi")["answer"] == "Second model welcome"
    assert len(llm.calls) == 2


@pytest.mark.parametrize(
    "content",
    ["not json", '{"route":"general","answer":""}', '{"route":"documents","answer":""}', "{}"],
)
def test_invalid_llm_greeting_raises_without_static_or_document_fallback(content):
    llm = FakeLLMClient(responses=[{"content": content}])
    with pytest.raises(InvalidConversationResponseError):
        service(llm).answer("Hello")


def test_llm_failure_propagates_without_canned_reply():
    class UnavailableLLM:
        def chat(self, **kwargs):
            raise TransientLLMError("provider unavailable")

    with pytest.raises(TransientLLMError):
        service(UnavailableLLM()).answer("Good morning")


def test_missing_conversation_configuration_never_returns_static_text():
    qa = QaService(
        retrieval=NoRetrieval(),
        generator=NoRetrieval(),
        guardrail_answer="Blocked",
        no_drafting_answer="No drafting",
        out_of_scope_answer="Not in documents",
    )
    with pytest.raises(ConversationUnavailableError, match="configured LLM"):
        qa.answer("Hi")
