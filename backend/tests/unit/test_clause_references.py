import pytest

from legal_rag.domain.clauses import clause_excerpt, parse_clause_request
from legal_rag.domain.entities import RetrievedChunk


@pytest.mark.parametrize("label", ["clause", "Clause", "section", "ARTICLE"])
def test_explicit_reference_parsing(label):
    request = parse_clause_request(f"Quote {label} 3.4 and 7.3 of msa-2026-014.")
    assert request.numbers == ("3.4", "7.3")
    assert request.documents == ("MSA-2026-014",)


def test_rates_and_dates_are_not_clause_requests():
    assert parse_clause_request("Interest is 1.5% on 2026-10-31") is None


@pytest.mark.parametrize("number", ["3", "3.40", "99.99"])
def test_similar_numbers_and_prose_mentions_are_not_definitions(number):
    chunk = RetrievedChunk("a", "MSA-2026-014", "contract", "Section 3.4 Late Payment",
                           "3.4 Late Payment. See Section 99.99 for an example.", 0)
    assert clause_excerpt(chunk, number) is None


def test_quoted_amendment_replacement_is_found_verbatim():
    text = '1.1 Section 7.3 is replaced:\n\n> "7.3 Notice. Fifteen Business Days."\n\n1.2 Other terms.'
    chunk = RetrievedChunk("a", "AMD-2026-014-02", "amendment", "Section 1.1", text, 0)
    quote = clause_excerpt(chunk, "7.3")
    assert quote == '> "7.3 Notice. Fifteen Business Days."'
    assert quote in text


def test_cross_reference_at_start_of_line_is_not_a_clause_definition():
    chunk = RetrievedChunk("a", "MSA-2026-014", "contract", "Section 2.2",
                           "Section 99.99 of the Agreement is mentioned here.", 0)
    assert clause_excerpt(chunk, "99.99") is None
