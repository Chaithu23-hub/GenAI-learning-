import json
import re

import jsonschema

from . import config


RESPONSE_SCHEMA = {
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


def validate_response(payload):
    try:
        jsonschema.validate(payload, RESPONSE_SCHEMA)
    except jsonschema.ValidationError as exc:
        return [exc.message]

    errors = []
    if payload["out_of_scope"]:
        if payload["answer"] != config.OUT_OF_SCOPE_ANSWER:
            errors.append("out_of_scope answers must use the fixed OUT_OF_SCOPE_ANSWER string")
        if payload["sources"]:
            errors.append("out_of_scope answers must have an empty sources array")
    return errors


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def parse_json_response(text):
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
