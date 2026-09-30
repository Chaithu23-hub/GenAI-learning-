"""End-to-end tests against real Chroma + real SentenceTransformer.

Slow: downloads models on first run (~100 MB) and writes a Chroma directory
under tmp_path. Skip in normal CI: `pytest -m "not slow"`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from legal_rag.composition import Container
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
