"""Amendments may define a base clause without lending it their physical page."""

from legal_rag.domain.entities import RetrievedChunk
from legal_rag.domain.evidence import reference_association_errors


def amendment():
    return RetrievedChunk(
        "amendment::000",
        "AMD-2026-014-02",
        "amendment",
        "Section 2.1",
        '2.1 The original clause is replaced.\n"8.3 Liability Cap. A limit applies."',
        0,
        metadata={"source_doc": "AMD-2026-014-02", "amends": "MSA-2026-014", "page_number": 2},
    )


def test_explicit_amendment_relationship_can_support_a_base_clause_reference():
    answer = "Section 8.3 of MSA-2026-014, as replaced by AMD-2026-014-02, sets the cap."
    assert reference_association_errors(answer, [amendment()]) == []


def test_amendment_page_cannot_be_assigned_to_the_base_document():
    answer = "Section 8.3 of MSA-2026-014 on page 2, as replaced by AMD-2026-014-02."
    assert any(
        "page reference" in error for error in reference_association_errors(answer, [amendment()])
    )
