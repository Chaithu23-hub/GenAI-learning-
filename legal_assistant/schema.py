"""Response schema definition and validation for grounded JSON answers."""

import json
import re

import jsonschema

from . import config

# assistant response must match, so the app can reliably parse answer+sources.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        # model to show its step-by-step logic before writing the answer;
        # this reduces errors on multi-clause contract questions.
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


def validate_response(payload):
    """Validate a candidate response dict; return a list of error strings (empty = valid)."""
    try:
        jsonschema.validate(payload, RESPONSE_SCHEMA)
    except jsonschema.ValidationError as exc:
        return [exc.message]

    errors = []
    # the fixed refusal string with no sources (the model had no grounded text).
    if payload["out_of_scope"]:
        if payload["answer"] != config.OUT_OF_SCOPE_ANSWER:
            errors.append("out_of_scope answers must use the fixed OUT_OF_SCOPE_ANSWER string")
        if payload["sources"]:
            errors.append("out_of_scope answers must have an empty sources array")
    return errors


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def parse_json_response(text):
    """Extract a JSON object from an LLM reply (tolerates ```json fences and prose)."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_FENCE_RE.search(text)
    if match:
        return json.loads(match.group(1))
    # Last resort: first '{' to last '}'.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON object found in response")
