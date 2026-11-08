"""LLM adapter that reviews grounded answers for source-stated conditions."""

from __future__ import annotations

import json
from typing import Any

from legal_rag.application.ports import LLMClient
from legal_rag.domain.response_schema import validate_response
from legal_rag.infrastructure.errors import PermanentLLMError
from legal_rag.infrastructure.prompts.evidence_review import EVIDENCE_REVIEW_PROMPT_V1


class EvidenceReviewClient:
    """Refine answer wording while leaving the validated evidence payload intact."""

    def __init__(self, inner: LLMClient):
        self._inner = inner

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        response = self._inner.chat(messages=messages, tools=tools, temperature=temperature)
        if response.get("tool_calls"):
            return response
        try:
            payload = json.loads(response.get("content") or "")
        except (TypeError, json.JSONDecodeError):
            return response
        if (
            not isinstance(payload, dict)
            or validate_response(payload)
            or payload["out_of_scope"]
            or not payload["sources"]
        ):
            return response

        review_input = {
            "candidate_answer": payload["answer"],
            "question_context": messages,
            "evidence": payload["sources"],
        }
        review = self._inner.chat(
            messages=[
                {"role": "system", "content": EVIDENCE_REVIEW_PROMPT_V1.text},
                {"role": "user", "content": json.dumps(review_input, ensure_ascii=False)},
            ],
            tools=None,
            temperature=0.0,
        )
        try:
            selection = json.loads(review.get("content") or "")
            conditions = selection.get("conditions") if isinstance(selection, dict) else None
            if (
                review.get("tool_calls")
                or not isinstance(selection, dict)
                or set(selection) != {"conditions"}
                or not isinstance(conditions, list)
                or len(conditions) > len(payload["sources"])
            ):
                raise ValueError
            source_by_id = {source["chunk_id"]: source for source in payload["sources"]}
            seen: set[str] = set()
            quoted_conditions: list[tuple[str, str]] = []
            for chunk_id in conditions:
                if not isinstance(chunk_id, str) or chunk_id in seen:
                    raise ValueError
                source = source_by_id.get(chunk_id)
                if source is None or not source["excerpt"].strip():
                    raise ValueError
                seen.add(chunk_id)
                quoted_conditions.append((source["document"], source["excerpt"]))
        except (KeyError, TypeError, json.JSONDecodeError, ValueError):
            raise PermanentLLMError("Evidence review returned an invalid response.") from None

        answer = payload["answer"]
        if quoted_conditions:
            blockquotes = []
            for document, excerpt in quoted_conditions:
                quoted = "\n".join(f"> {line}" for line in excerpt.splitlines())
                blockquotes.append(f"[{document}]\n{quoted}")
            answer += "\n\nAdditional conditions stated in the cited evidence:\n\n"
            answer += "\n\n".join(blockquotes)
        updated = {**payload, "answer": answer}
        original_usage = response.get("usage", {})
        review_usage = review.get("usage", {})
        usage = {
            key: original_usage.get(key, 0) + review_usage.get(key, 0)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        return {**response, "content": json.dumps(updated), "usage": usage}
