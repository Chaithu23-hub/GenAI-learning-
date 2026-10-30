import pytest

from legal_rag.domain.policies import apply_completeness_adjustment, normalize_legal_numbers


@pytest.mark.parametrize("text, expected", [
    ("an additional two (2) years", "an additional 2 years"),
    ("seventy-two (72) hours", "72 hours"),
    ("thirty (30) Business Days", "30 Business Days"),
    ("2 years and two (2) years", "2 years and 2 years"),
    ("USD 1,000,000 per claim", "USD 1,000,000 per claim"),
])
def test_legal_duration_is_not_duplicated(text, expected):
    assert normalize_legal_numbers(text) == expected
    assert normalize_legal_numbers(expected) == expected


def test_only_answer_prose_is_normalized():
    source = {"excerpt": "Maintain insurance for two (2) years."}
    payload = {
        "answer": "Maintain insurance for two (2) years.",
        "sources": [source], "confidence": "high", "out_of_scope": False,
    }
    result = apply_completeness_adjustment(payload, "How long is insurance required?")
    assert result["answer"] == "Maintain insurance for 2 years."
    assert result["sources"] == [source]
    assert payload["answer"] == "Maintain insurance for two (2) years."
