import json

import pytest

from legal_rag.infrastructure.errors import PermanentLLMError
from legal_rag.infrastructure.llm.evidence_review import EvidenceReviewClient


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, *, messages, tools=None, temperature=0.0):
        self.calls.append({"messages": messages, "tools": tools, "temperature": temperature})
        return self.responses.pop(0)


def _payload(**overrides):
    return {
        "answer": "The fee applies.",
        "reasoning": "Supported by the cited clause.",
        "sources": [
            {"document": "lease.md", "chunk_id": "c1", "excerpt": "Fee applies after notice."}
        ],
        "confidence": "high",
        "out_of_scope": False,
        **overrides,
    }


def _response(content, *, usage=(10, 4, 14), tool_calls=None):
    return {
        "content": content,
        "tool_calls": tool_calls or [],
        "usage": {
            "prompt_tokens": usage[0],
            "completion_tokens": usage[1],
            "total_tokens": usage[2],
        },
    }


def test_refines_substantive_payload_using_context_without_changing_evidence():
    messages = [{"role": "user", "content": "Does the fee apply before notice?"}]
    original = _payload()
    llm = ScriptedLLM(
        _response(json.dumps(original)),
        _response(
            json.dumps({"conditions": ["c1"]}),
            usage=(20, 7, 27),
        ),
    )

    result = EvidenceReviewClient(llm).chat(
        messages=messages, tools=[{"type": "function"}], temperature=0.3
    )

    expected_answer = (
        "The fee applies.\n\nAdditional conditions stated in the cited evidence:\n\n"
        "[lease.md]\n> Fee applies after notice."
    )
    assert json.loads(result["content"]) == {**original, "answer": expected_answer}
    assert result["tool_calls"] == []
    assert result["usage"] == {"prompt_tokens": 30, "completion_tokens": 11, "total_tokens": 41}
    assert llm.calls[0] == {
        "messages": messages,
        "tools": [{"type": "function"}],
        "temperature": 0.3,
    }
    review_call = llm.calls[1]
    assert review_call["tools"] is None and review_call["temperature"] == 0.0
    review_data = json.loads(review_call["messages"][1]["content"])
    assert review_data == {
        "candidate_answer": original["answer"],
        "question_context": messages,
        "evidence": original["sources"],
    }


@pytest.mark.parametrize(
    "first_response",
    [
        _response("not json"),
        _response(json.dumps(_payload(out_of_scope=True))),
        _response(json.dumps({**_payload(), "sources": []})),
        _response("", tool_calls=[{"id": "x", "name": "lookup", "arguments": "{}"}]),
    ],
)
def test_skips_review_when_initial_response_is_not_reviewable(first_response):
    llm = ScriptedLLM(first_response)
    assert EvidenceReviewClient(llm).chat(messages=[]) is first_response
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    "review", ["not json", "{}", '{"answer":" "}', '{"answer":"ok","extra":1}']
)
def test_invalid_review_fails_with_safe_error(review):
    llm = ScriptedLLM(
        _response(json.dumps(_payload())),
        _response(review),
    )

    with pytest.raises(
        PermanentLLMError, match="Evidence review returned an invalid response"
    ) as exc:
        EvidenceReviewClient(llm).chat(messages=[])

    assert "lease.md" not in str(exc.value)


@pytest.mark.parametrize(
    "conditions,tool_calls",
    [
        (["missing"], []),
        (["c1", "c1"], []),
        ([{"chunk_id": "c1", "excerpt": "Fee applies after notice."}], []),
        ([], [{"id": "x"}]),
    ],
)
def test_rejects_unverified_or_tool_based_condition_selection(conditions, tool_calls):
    llm = ScriptedLLM(
        _response(json.dumps(_payload())),
        _response(json.dumps({"conditions": conditions}), tool_calls=tool_calls),
    )
    with pytest.raises(PermanentLLMError, match="Evidence review returned an invalid response"):
        EvidenceReviewClient(llm).chat(messages=[])


def test_empty_conditions_preserves_original_answer_and_aggregates_usage():
    original = _payload()
    llm = ScriptedLLM(
        _response(json.dumps(original)),
        _response('{"conditions":[]}', usage=(1, 2, 3)),
    )
    result = EvidenceReviewClient(llm).chat(messages=[])
    assert json.loads(result["content"]) == original
    assert result["usage"] == {"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17}
