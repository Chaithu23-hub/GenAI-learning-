from legal_rag.application.workflows.corpus_lookup import CorpusLookupService
from legal_rag.domain.entities import Chunk, Document
from legal_rag.interfaces.mcp_servers import clause_search, contract_repository


class Documents:
    def iter_documents(self, docs_dir=None):
        return iter(
            [
                Document(
                    "MSA-2026-014.md",
                    "## 1.1\nPayment is due within thirty days.",
                    "contract",
                    {
                        "source_doc": "MSA-2026-014",
                        "effective_date": "Unknown",
                        "status": "unknown",
                        "document_version": "v1.0",
                    },
                ),
                Document(
                    "AMD-2026-014-01.md",
                    "## 1.1\nPayment terms are amended as stated here.",
                    "amendment",
                    {
                        "source_doc": "AMD-2026-014-01",
                        "effective_date": "2026-04-01",
                        "status": "Executed",
                        "document_version": "v1.1",
                        "amends": "MSA-2026-014",
                    },
                ),
            ]
        )

    def write_document(self, name, text):
        raise NotImplementedError


class Chunker:
    def chunk(self, text, *, chunk_size, overlap):
        heading, _, body = text.partition("\n")
        number = heading.removeprefix("## ")
        return [Chunk(text=f"{number} {body}", heading=f"Section {number}", index=0)]


def setup_module():
    lookup = CorpusLookupService(Documents(), Chunker())
    clause_search.configure(lookup)
    contract_repository.configure(lookup)


def test_clause_tool_returns_exact_text_and_ambiguity_candidates():
    result = clause_search.get_contract_clause("MSA-2026-014", "1.1")

    assert result["error"] == "ambiguous_clause"
    assert {candidate["text"] for candidate in result["candidates"]} == {
        "1.1 Payment is due within thirty days.",
        "1.1 Payment terms are amended as stated here.",
    }


def test_contract_tools_use_corpus_metadata_and_preserve_unknown_values():
    result = contract_repository.lookup_contract("MSA-2026-014")

    assert result["document"] == "MSA-2026-014.md"
    assert result["effective_date"] == "Unknown"
    assert result["amendments"] == [
        {
            "document": "AMD-2026-014-01",
            "effective_date": "2026-04-01",
            "status": "Executed",
            "document_version": "v1.1",
        }
    ]
    assert contract_repository.get_effective_date("MSA-2026-014")["effective_date"] == "Unknown"
    assert contract_repository.get_amendment_chain("NO-SUCH-ID") == {"error": "contract_not_found"}


def test_clause_search_returns_exact_corpus_excerpt():
    results = clause_search.search_clauses("Payment due")

    assert results[0]["document"] == "MSA-2026-014"
    assert results[0]["text"] == "1.1 Payment is due within thirty days."
