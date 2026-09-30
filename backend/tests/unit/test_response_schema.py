import json

import pytest

from legal_rag.domain.response_schema import parse_json_response, validate_response


class TestValidateResponse:
    def _valid(self):
        return {
            "answer": "some", "reasoning": "because", "sources": [],
            "confidence": "medium", "out_of_scope": False,
        }

    def test_valid_payload_ok(self):
        assert validate_response(self._valid()) == []

    def test_missing_field_errors(self):
        payload = self._valid()
        del payload["reasoning"]
        errors = validate_response(payload)
        assert errors and "reasoning" in errors[0]

    def test_invalid_confidence_errors(self):
        payload = self._valid()
        payload["confidence"] = "sky-high"
        assert validate_response(payload)

    def test_out_of_scope_must_use_sentinel(self):
        payload = self._valid()
        payload["out_of_scope"] = True
        payload["answer"] = "But I know this!"
        errors = validate_response(payload, out_of_scope_answer="I don't know")
        assert any("OUT_OF_SCOPE" in e for e in errors)

    def test_out_of_scope_must_have_no_sources(self):
        payload = self._valid()
        payload["out_of_scope"] = True
        payload["answer"] = "I don't know"
        payload["sources"] = [
            {"document": "d.md", "chunk_id": "x", "excerpt": "e"}
        ]
        errors = validate_response(payload, out_of_scope_answer="I don't know")
        assert any("empty sources" in e for e in errors)


class TestParseJsonResponse:
    def test_plain_json(self):
        payload = {"answer": "x"}
        assert parse_json_response(json.dumps(payload)) == payload

    def test_wrapped_in_markdown_fence(self):
        text = "```json\n{\"answer\": \"x\"}\n```"
        assert parse_json_response(text) == {"answer": "x"}

    def test_json_embedded_in_prose(self):
        text = "Sure! Here is the JSON:\n{\"answer\": \"x\"}\nThanks."
        assert parse_json_response(text) == {"answer": "x"}

    def test_missing_json_raises(self):
        with pytest.raises(ValueError):
            parse_json_response("no json here")

    def test_empty_input_raises(self):
        with pytest.raises(ValueError):
            parse_json_response("")

    def test_none_input_raises(self):
        with pytest.raises(ValueError):
            parse_json_response(None)
