import pytest

from legal_rag.infrastructure.llm.openai_compatible import OpenAICompatibleClient
from tests.fakes.openai_sdk import FakeOpenAISDK


@pytest.mark.parametrize("effort, has_temperature", [(None, True), ("none", True), ("low", False)])
def test_reasoning_compatibility_and_normalized_reply(effort, has_temperature):
    sdk = FakeOpenAISDK()
    client = object.__new__(OpenAICompatibleClient)
    client._client = sdk
    client._model = "gpt-6-luna"
    client._reasoning_effort = effort
    tools = [{"type": "function", "function": {"name": "retrieve_chunks"}}]
    result = client.chat(messages=[{"role": "user", "content": "Hello"}], tools=tools)
    request = sdk.calls[0]
    assert ("temperature" in request) is has_temperature
    assert request.get("reasoning_effort") == effort
    assert request["tools"] == tools
    assert result["content"] == "Hello"
    assert result["usage"]["total_tokens"] == 12
