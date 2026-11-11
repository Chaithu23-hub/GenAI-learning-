import pytest

from legal_rag.domain.clauses import parse_clause_request


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Sections 3.4, 3.5, and 99.99 apply.", ("3.4", "3.5", "99.99")),
        ("Clauses 3.4, 3.5, and 3.6-3.7 apply.", ("3.4", "3.5", "3.6", "3.7")),
    ],
)
def test_oxford_comma_lists_preserve_every_reference(text, expected):
    result = parse_clause_request(text)
    assert result is not None and result.valid
    assert result.numbers == expected
