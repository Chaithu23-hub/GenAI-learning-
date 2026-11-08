"""Stateless LLM refusal wording, isolated from user questions and legal context."""

import json

from legal_rag.application.ports import LLMClient, UnsupportedReason
from legal_rag.domain.exceptions import InvalidConversationResponseError
from legal_rag.domain.refusals import is_refusal_wording
from legal_rag.infrastructure.prompts.registry import get as get_prompt


class LLMUnsupportedResponses:
    def __init__(self, llm: LLMClient, *, temperature: float = 0.7):
        self._llm = llm
        self._temperature = temperature

    def reply(self, reason: UnsupportedReason) -> str:
        if reason not in ("outside_document_qa", "insufficient_evidence"):
            raise ValueError("Unsupported refusal reason")
        for attempt in range(2):
            prompt = get_prompt("unsupported.reply").text
            if attempt:
                # Do not echo invalid model content into the correction request.
                prompt += (
                    "\nThe previous response failed validation. Return only the required JSON "
                    "with a clear limitation, no substantive answer and no prohibited detail."
                )
            response = self._llm.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": reason},
                ],
                temperature=self._temperature,
            )
            try:
                payload = json.loads(response.get("content") or "")
            except (ValueError, TypeError):
                payload = None
            if (
                isinstance(payload, dict)
                and set(payload) == {"reason", "answer"}
                and payload["reason"] == reason
                and isinstance(payload["answer"], str)
                and 1 <= len(payload["answer"].strip()) <= 600
                and is_refusal_wording(payload["answer"], reason)
                and not response.get("tool_calls")
            ):
                return payload["answer"].strip()
        raise InvalidConversationResponseError(
            ["The LLM did not return a valid unsupported-question response."]
        )
