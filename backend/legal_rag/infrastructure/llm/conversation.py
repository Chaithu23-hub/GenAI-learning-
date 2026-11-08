"""LLM-backed routing and general conversation adapter."""

from legal_rag.application.ports import ConversationIntent, LLMClient
from legal_rag.domain.exceptions import InvalidConversationResponseError
from legal_rag.domain.response_schema import parse_json_response
from legal_rag.infrastructure.prompts.conversation import CONVERSATION_PROMPT, GREETING_PROMPT_V1


class LLMConversation:
    def __init__(self, llm: LLMClient, *, greeting_temperature: float = 0.8):
        self._llm = llm
        self._greeting_temperature = greeting_temperature

    def classify(self, query: str) -> ConversationIntent:
        response = self._llm.chat(
            messages=[
                {"role": "system", "content": CONVERSATION_PROMPT.text},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
        )
        try:
            payload = parse_json_response(response.get("content"))
        except (ValueError, TypeError):
            return "documents"
        if not isinstance(payload, dict) or set(payload) != {"route"} or response.get("tool_calls"):
            return "documents"
        route = payload["route"]
        if route == "social":
            return "social"
        if route == "unsupported":
            return "unsupported"
        return "documents"

    def reply(self, query: str) -> str:
        response = self._llm.chat(
            messages=[
                {"role": "system", "content": GREETING_PROMPT_V1.text},
                {"role": "user", "content": query},
            ],
            temperature=self._greeting_temperature,
        )
        try:
            payload = parse_json_response(response.get("content"))
        except (ValueError, TypeError):
            payload = None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"answer"}
            or not isinstance(payload["answer"], str)
            or not payload["answer"].strip()
            or response.get("tool_calls")
        ):
            raise InvalidConversationResponseError(
                ["The LLM did not return a valid conversational reply."]
            )
        return payload["answer"].strip()
