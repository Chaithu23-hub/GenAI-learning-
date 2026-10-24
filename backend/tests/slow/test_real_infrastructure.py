"""End-to-end tests against real Chroma + real SentenceTransformer.

Slow: downloads models on first run (~100 MB) and writes a Chroma directory
under tmp_path. Skip in normal CI: `pytest -m "not slow"`.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from legal_rag.composition import Container
from legal_rag.infrastructure.documents.shared_corpus_loader import load_document
from legal_rag.infrastructure.settings import Settings

pytestmark = pytest.mark.slow


@pytest.fixture()
def real_container(tmp_path: Path) -> Container:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "sample.md").write_text(
        "# Sample MSA\n\n"
        "## Section 3: Payment Terms\n"
        "Late payments accrue interest at a rate of 1.0% per month.\n\n"
        "## Section 5: Termination\n"
        "Either party may terminate with 30 days written notice.\n",
        encoding="utf-8",
    )
    settings = Settings(
        docs_dir=docs,
        chroma_dir=tmp_path / "chroma",
        mcp_config_path=tmp_path / "mcp.json",
        llm_provider="extractive",
        api_key=None,
    )
    return Container(settings)


@pytest.fixture()
def real_legal_container(tmp_path: Path) -> Container:
    docs = Path(__file__).resolve().parents[2] / "data" / "shared-corpus" / "contracts"
    settings = Settings(
        docs_dir=docs,
        chroma_dir=tmp_path / "legal-chroma",
        mcp_config_path=tmp_path / "mcp.json",
        llm_provider="extractive",
        api_key=None,
    )
    return Container(settings)


def test_real_chroma_ingest_and_retrieve(real_container):
    count = real_container.ingestion_service.ingest()
    assert count > 0
    chunks = real_container.retrieval_service.retrieve("late payment interest rate")
    assert chunks
    assert any("payment" in c.text.lower() for c in chunks)


def test_real_end_to_end_extractive_answer(real_container):
    real_container.ingestion_service.ingest()
    result = real_container.qa_service.answer("What is the late payment interest rate?")
    assert not result["out_of_scope"]
    assert result["sources"]
    assert any("payment" in s["excerpt"].lower() for s in result["sources"])


def test_real_shared_corpus_ingest_preserves_metadata_and_schedule_rows(real_legal_container):
    count = real_legal_container.ingestion_service.ingest()
    stored = real_legal_container.vector_store.get_all()
    metadatas = stored["metadatas"]
    required = {"source_doc", "counterparty", "effective_date", "doc_type", "clause_ref"}
    assert count == len(stored["ids"]) > 0
    assert {meta["source_doc"] for meta in metadatas} == {
        "MSA-2026-014",
        "AMD-2026-014-01",
        "AMD-2026-014-02",
        "SCH-2026-014",
        "MSA-2026-022",
        "NDA-2026-007",
    }
    assert all(required <= set(meta) for meta in metadatas)
    assert all(all(meta[key] for key in required) for meta in metadatas)
    assert any(
        "20 October 2026" in text and "Deepavali" in text
        for text in stored["documents"]
    )
    vertex_filter = real_legal_container.retrieval_service.detect_metadata_filter(
        "What is Section 8.3 under the Vertex agreement?"
    )
    assert vertex_filter == {"counterparty": "Vertex Retail"}
    vertex_chunks = real_legal_container.retrieval_service.retrieve(
        "What is Section 8.3 liability?", where=vertex_filter,
    )
    assert vertex_chunks
    assert all(chunk.document == "MSA-2026-022" for chunk in vertex_chunks)
    logging.getLogger(__name__).info(
        "shared corpus ingested", extra={"documents": 6, "chunks": count}
    )


def test_shared_corpus_loader_supports_all_formats_with_parity():
    corpus = Path(__file__).resolve().parents[2] / "data" / "shared-corpus"
    format_dirs = [
        corpus / "contracts",
        corpus / "contracts-docx",
        corpus / "contracts-pdf",
    ]
    loaded = [
        {doc.metadata["source_doc"]: doc for doc in map(load_document, sorted(folder.iterdir()))}
        for folder in format_dirs
    ]

    assert all(set(docs) == set(loaded[0]) for docs in loaded[1:])
    required_facts = {
        "MSA-2026-014": ("1.5%", "Chennai", "72"),
        "AMD-2026-014-01": ("forty-five (45) days",),
        "AMD-2026-014-02": ("fifteen (15) Business Days", "5,000,000"),
        "SCH-2026-014": (
            "20 October 2026", "Deepavali", "15 Business Days", "81,100", "42,000", "99.9%",
        ),
        "MSA-2026-022": ("500,000", "SIAC", "twenty (20) days"),
        "NDA-2026-007": ("50,000", "England and Wales"),
    }
    for source_doc in loaded[0]:
        baseline = loaded[0][source_doc]
        for fact in required_facts[source_doc]:
            assert fact.casefold() in baseline.text.casefold()
        for docs in loaded[1:]:
            assert docs[source_doc].metadata == baseline.metadata
            for fact in required_facts[source_doc]:
                assert fact.casefold() in docs[source_doc].text.casefold()
