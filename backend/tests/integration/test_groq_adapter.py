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
    result = client(sdk).chat(messages=[{"role": "user", "content": "Hello"}], tools=tools, temperature=0.2)
    assert sdk.calls[0] == {
        "model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "Hello"}],
        "tools": tools, "temperature": 0.2,
    }
    assert result["content"] == "Hello"
    assert result["usage"]["total_tokens"] == 12
    assert result["tool_calls"] == []


def test_direct_chat_omits_tools():
    sdk = FakeChatSDK()
    client(sdk).chat(messages=[{"role": "user", "content": "Hello"}])
    assert "tools" not in sdk.calls[0]


@pytest.mark.parametrize("message,error", [
    ("HTTP 429 rate limit", TransientLLMError),
    ("timeout", TransientLLMError),
    ("HTTP 503", TransientLLMError),
    ("invalid API key", PermanentLLMError),
])
def test_sdk_errors_use_adapter_taxonomy(message, error):
    def fail(**kwargs):
        raise RuntimeError(message)

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(error, match=message):
        client(sdk).chat(messages=[])
