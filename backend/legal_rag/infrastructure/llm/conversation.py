"""LLM-backed routing and general conversation adapter."""
from legal_rag.application.ports import LLMClient
from legal_rag.domain.response_schema import parse_json_response
from legal_rag.infrastructure.prompts.conversation import CONVERSATION_PROMPT


class LLMConversation:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def reply_if_general(self, query: str) -> str | None:
        response = self._llm.chat(messages=[
            {"role": "system", "content": CONVERSATION_PROMPT.text},
            {"role": "user", "content": query},
        ])
        try:
            payload = parse_json_response(response.get("content"))
        except (ValueError, TypeError):
            return None  # Uncertain routing must retain grounded document QA.
        if not isinstance(payload, dict) or payload.get("route") != "general":
            return None
        answer = payload.get("answer")
        return answer.strip() if isinstance(answer, str) and answer.strip() else None
