import pytest

from legal_rag.domain.query import normalize_document_query


@pytest.mark.parametrize("query, expected", [
    ("what are the avaialble admendments", "what are the available amendments"),
    ("What is the agrement term?", "What is the agreement term?"),
    ("MSA-2026-014 AMD-2026-014-02 2026-08-01", "MSA-2026-014 AMD-2026-014-02 2026-08-01"),
    ("Who is Rajamouli?", "Who is Rajamouli?"),
    ("What are the available amendments?", "What are the available amendments?"),
])
def test_normalization(query, expected):
    assert normalize_document_query(query) == expected
