"""Social replies use model classification and fresh generated wording."""

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
        raise AssertionError(f"Social reply unexpectedly called retrieval/generation: {name}")


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
    "query", ["Hello", "Hi!", "Hii", "Helllo", "Heeelllooo", "Heyyy", "Good morning!"]
)
def test_model_classifies_informal_social_variants_and_reply_skips_retrieval(query):
    expected = "A distinctive model-generated welcome."
    llm = FakeLLMClient(
        responses=[{"content": '{"route":"social"}'}, {"content": json.dumps({"answer": expected})}]
    )
    result = service(llm).answer(query)
    assert result["answer"] == expected
    assert result["sources"] == []
    assert result["out_of_scope"] is False
    assert len(llm.calls) == 2
    assert [call["messages"][-1]["content"] for call in llm.calls] == [query, query]
    assert [call["temperature"] for call in llm.calls] == [0.0, 0.8]


def test_non_english_social_route_is_trusted_as_model_decision():
    query = "Hola, ¿cómo estás?"
    llm = FakeLLMClient(
        responses=[
            {"content": '{"route":"social"}'},
            {"content": '{"answer":"¡Hola! ¿En qué puedo ayudarte?"}'},
        ]
    )
    assert service(llm).answer(query)["answer"] == "¡Hola! ¿En qué puedo ayudarte?"
    assert len(llm.calls) == 2


def test_repeated_greetings_each_classify_and_generate_fresh_reply():
    llm = FakeLLMClient(
        responses=[
            {"content": '{"route":"social"}'},
            {"content": '{"answer":"First welcome"}'},
            {"content": '{"route":"social"}'},
            {"content": '{"answer":"Second welcome"}'},
        ]
    )
    qa = service(llm)
    assert qa.answer("Hello")["answer"] == "First welcome"
    assert qa.answer("Hello")["answer"] == "Second welcome"
    assert [call["temperature"] for call in llm.calls] == [0.0, 0.8, 0.0, 0.8]


def test_sampling_setting_applies_only_to_reply():
    llm = FakeLLMClient(
        responses=[{"content": '{"route":"social"}'}, {"content": '{"answer":"Welcome"}'}]
    )
    conversation = LLMConversation(llm, greeting_temperature=0.9)
    assert conversation.classify("Hii") == "social"
    assert conversation.reply("Hii") == "Welcome"
    assert [call["temperature"] for call in llm.calls] == [0.0, 0.9]


@pytest.mark.parametrize("content", ["not json", '{"answer":""}', "{}"])
def test_invalid_llm_social_reply_raises_without_fallback(content):
    llm = FakeLLMClient(responses=[{"content": '{"route":"social"}'}, {"content": content}])
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
