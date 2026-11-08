from legal_rag.application.workflows.corpus_lookup import CorpusLookupService
from legal_rag.domain.entities import Chunk, Document


class MemoryDocuments:
    def __init__(self, documents):
        self.documents = documents

    def iter_documents(self, docs_dir=None):
        return iter(self.documents)

    def write_document(self, name, text):
        raise NotImplementedError


class MemoryChunker:
    def chunk(self, text, *, chunk_size, overlap):
        return [Chunk(text=text, heading="Terms", index=0)]


def service(*documents):
    return CorpusLookupService(MemoryDocuments(documents), MemoryChunker())


def test_filename_is_not_invented_as_a_legal_contract_identifier():
    lookup = service(Document("unidentified.md", "3.4 Payment is due.", "contract"))
    assert lookup.lookup_contract("unidentified.md") == {"error": "contract_not_found"}
    assert lookup.get_contract_clause("unidentified.md", "3.4") == {"error": "contract_not_found"}
    # Search may identify the actual local source filename without asserting a contract ID.
    assert lookup.search_clauses("Payment")[0]["document_name"] == "unidentified.md"


def test_clause_lookup_distinguishes_parent_number_from_subclause():
    lookup = service(
        Document(
            "msa.md", "3.4 Parent term.\n\n3.4(a) Child term.", "contract", {"source_doc": "MSA-1"}
        )
    )

    result = lookup.get_contract_clause("MSA-1", "3.4")

    assert result["text"] == "3.4 Parent term."


def test_clause_lookup_returns_exact_parenthetical_subclause():
    lookup = service(
        Document(
            "msa.md", "3.4 Parent term.\n\n3.4(a) Child term.", "contract", {"source_doc": "MSA-1"}
        )
    )

    result = lookup.get_contract_clause("MSA-1", "3.4(a)")

    assert result["text"] == "3.4(a) Child term."


def test_clause_lookup_does_not_treat_heading_cross_reference_as_clause_text():
    lookup = service(
        Document(
            "msa.md",
            "Section 3.4 of the Agreement governs this matter.",
            "contract",
            {"source_doc": "MSA-1"},
        )
    )

    assert lookup.get_contract_clause("MSA-1", "3.4") == {"error": "clause_not_found"}


def test_clause_lookup_extracts_quoted_replacement_clause():
    lookup = service(
        Document(
            "amendment.md",
            'Section 3.4 is deleted and replaced with:\n\n"3.4 The Provider shall maintain insurance.\n\n3.5 The Client shall cooperate."',
            "amendment",
            {"source_doc": "AMD-1", "amends": "MSA-1"},
        ),
        Document("msa.md", "Original agreement.", "contract", {"source_doc": "MSA-1"}),
    )

    result = lookup.get_contract_clause("MSA-1", "3.4")

    assert result["document"] == "AMD-1"
    assert result["text"] == '"3.4 The Provider shall maintain insurance.'


def test_clause_lookup_refuses_ambiguous_original_and_amendment_clauses():
    lookup = service(
        Document("msa.md", "3.4 Original term.", "contract", {"source_doc": "MSA-1"}),
        Document(
            "amendment.md",
            "3.4 Replacement term.",
            "amendment",
            {"source_doc": "AMD-1", "amends": "MSA-1"},
        ),
    )

    result = lookup.get_contract_clause("MSA-1", "3.4")

    assert result["error"] == "ambiguous_clause"
    assert {item["document"] for item in result["candidates"]} == {"MSA-1", "AMD-1"}
    assert {item["text"] for item in result["candidates"]} == {
        "3.4 Original term.",
        "3.4 Replacement term.",
    }


def test_contract_metadata_reports_unknown_dates_and_actual_amendment_metadata():
    lookup = service(
        Document(
            "msa.md",
            "Agreement body",
            "contract",
            {
                "source_doc": "MSA-1",
                "effective_date": "Unknown",
                "status": "unknown",
                "document_version": "unknown",
            },
        ),
        Document(
            "amendment.md",
            "Amendment body",
            "amendment",
            {
                "source_doc": "AMD-1",
                "effective_date": "2026-04-01",
                "status": "Executed",
                "document_version": "v1.1",
                "amends": "MSA-1",
            },
        ),
    )

    contract = lookup.lookup_contract("MSA-1")

    assert contract["effective_date"] == "Unknown"
    assert contract["amendments"] == [
        {
            "document": "AMD-1",
            "effective_date": "2026-04-01",
            "status": "Executed",
            "document_version": "v1.1",
        }
    ]
    assert lookup.get_amendment_chain("MSA-1")["amendments"][0]["status"] == "Executed"


def test_clause_lookup_returns_not_found_for_missing_source_and_clause():
    lookup = service(
        Document("msa.md", "## 1.1\nExact source clause", "contract", {"source_doc": "MSA-1"})
    )

    assert lookup.get_contract_clause("NOPE", "9") == {"error": "contract_not_found"}
    assert lookup.get_contract_clause("MSA-1", "9") == {"error": "clause_not_found"}
