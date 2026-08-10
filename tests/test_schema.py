"""Unit tests for the response schema and JSON parsing."""

import json

from legal_assistant import config
from legal_assistant.schema import parse_json_response, validate_response

VALID = {
    "answer": "Net-30 per the original MSA language.",
    "reasoning": "Chunk master_services_agreement::002 states the net-30 payment term verbatim.",
    "sources": [{
        "document": "master_services_agreement.md",
        "chunk_id": "master_services_agreement::002",
        "excerpt": "Client shall pay all undisputed invoices within thirty (30) days.",
    }],
    "confidence": "high",
    "out_of_scope": False,
}


def test_valid_payload_passes():
    assert validate_response(VALID) == []


def test_missing_required_field_fails():
    payload = {k: v for k, v in VALID.items() if k != "sources"}
    assert validate_response(payload)


def test_missing_reasoning_fails():
    payload = {k: v for k, v in VALID.items() if k != "reasoning"}
    assert validate_response(payload)


def test_bad_confidence_value_fails():
    assert validate_response({**VALID, "confidence": "kinda high"})


def test_source_missing_chunk_id_fails():
    payload = {**VALID, "sources": [{"document": "x.md", "excerpt": "y"}]}
    assert validate_response(payload)


def test_out_of_scope_consistency_rules():
    # Wrong answer text + non-empty sources must be rejected when out_of_scope.
    assert validate_response({**VALID, "out_of_scope": True})
    ok = {
        "answer": config.OUT_OF_SCOPE_ANSWER,
        "reasoning": "No retrieved chunk answered the question.",
        "sources": [],
        "confidence": "low",
        "out_of_scope": True,
    }
    assert validate_response(ok) == []


def test_parse_plain_json():
    assert parse_json_response(json.dumps(VALID))["confidence"] == "high"


def test_parse_json_inside_code_fence():
    text = "Here is the answer:\n```json\n" + json.dumps(VALID) + "\n```\nDone."
    assert parse_json_response(text)["confidence"] == "high"


def test_parse_json_embedded_in_prose():
    text = "Sure! " + json.dumps(VALID) + " — hope that helps."
    assert parse_json_response(text)["out_of_scope"] is False
