from types import SimpleNamespace

import pytest

from legal_rag.infrastructure.errors import PermanentLLMError, TransientLLMError
from legal_rag.infrastructure.llm import GroqClient
from tests.fakes.chat_sdk import FakeChatSDK


def client(sdk):
    adapter = object.__new__(GroqClient)
    adapter._client = sdk
    adapter._model = "openai/gpt-oss-20b"
    return adapter


def test_groq_request_and_normalized_reply():
    sdk = FakeChatSDK()
    tools = [{"type": "function", "function": {"name": "retrieve_chunks"}}]
    result = client(sdk).chat(
        messages=[{"role": "user", "content": "Hello"}], tools=tools, temperature=0.2
    )
    assert sdk.calls[0] == {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": tools,
        "temperature": 0.2,
    }
    assert result["content"] == "Hello"
    assert result["usage"]["total_tokens"] == 12
    assert result["tool_calls"] == []


def test_direct_chat_omits_tools():
    sdk = FakeChatSDK()
    client(sdk).chat(messages=[{"role": "user", "content": "Hello"}])
    assert "tools" not in sdk.calls[0]


def test_provider_error_does_not_expose_raw_diagnostics():
    private = "PRIVATE_DOCUMENT_AND_DUMMY_SECRET"

    def fail(**kwargs):
        raise RuntimeError(f"HTTP 503: {private}")

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(TransientLLMError) as error:
        client(sdk).chat(messages=[])
    assert private not in str(error.value)


@pytest.mark.parametrize("status,error", [(400, PermanentLLMError), (504, TransientLLMError)])
def test_structured_provider_status_takes_priority_over_response_body(status, error):
    class ProviderError(Exception):
        status_code = status

    def fail(**kwargs):
        raise ProviderError("Request text happened to mention HTTP 500")

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(error):
        client(sdk).chat(messages=[])


def test_sdk_connection_errors_are_retryable_without_private_diagnostics():
    import httpx
    from openai import APIConnectionError

    def fail(**kwargs):
        raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(TransientLLMError):
        client(sdk).chat(messages=[])


@pytest.mark.parametrize(
    "message,error",
    [
        ("HTTP 429 rate limit", TransientLLMError),
        ("timeout", TransientLLMError),
        ("HTTP 503", TransientLLMError),
        ("invalid API key", PermanentLLMError),
    ],
)
def test_sdk_errors_use_adapter_taxonomy(message, error):
    def fail(**kwargs):
        raise RuntimeError(message)

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(error):
        client(sdk).chat(messages=[])
