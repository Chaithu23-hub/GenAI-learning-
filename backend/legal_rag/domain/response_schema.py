"""Fixed answer schema. Field changes require coordinated updates to
interfaces/http/schemas.AnswerResponse, domain/entities.Answer, and README."""
from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "reasoning": {"type": "string", "minLength": 1},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "document": {"type": "string"},
                    "chunk_id": {"type": "string"},
                    "excerpt": {"type": "string"},
                },
                "required": ["document", "chunk_id", "excerpt"],
            },
        },
        "confidence": {"enum": ["high", "medium", "low"]},
        "out_of_scope": {"type": "boolean"},
    },
    "required": ["answer", "reasoning", "sources", "confidence", "out_of_scope"],
}


def validate_response(payload: dict[str, Any], out_of_scope_answer: str | None = None) -> list[str]:
    """Return a list of validation errors (empty = OK).

    When ``out_of_scope_answer`` is supplied, enforce the two extra invariants:
    an out-of-scope payload must use the fixed sentinel string and carry an
    empty sources list.
    """
    try:
        jsonschema.validate(payload, RESPONSE_SCHEMA)
    except jsonschema.ValidationError as exc:
        return [exc.message]

    errors: list[str] = []
    if payload["out_of_scope"]:
        if out_of_scope_answer is not None and payload["answer"] != out_of_scope_answer:
            errors.append("out_of_scope answers must use the fixed OUT_OF_SCOPE_ANSWER string")
        if payload["sources"]:
            errors.append("out_of_scope answers must have an empty sources array")
    return errors


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def parse_json_response(text: str | None) -> dict[str, Any]:
    """Parse a JSON object from an LLM response, tolerating markdown fences."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_FENCE_RE.search(text)
    if match:
        return json.loads(match.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON object found in response")
