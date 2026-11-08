"""Pure refusal wording policy; no provider or document access."""

import pytest

from legal_rag.domain.refusals import is_refusal_wording


@pytest.mark.parametrize(
    "answer,reason,expected",
    [
        ("I can only help with document questions.", "outside_document_qa", True),
        ("I don’t have enough document evidence to answer.", "insufficient_evidence", True),
        ("I need the relevant passage to answer reliably.", "insufficient_evidence", True),
        ("I need more details.", "insufficient_evidence", False),
        ("I need document evidence.", "unknown", False),
    ],
)
def test_refusal_needs_a_recognized_limitation_and_document_context(answer, reason, expected):
    assert is_refusal_wording(answer, reason) is expected
