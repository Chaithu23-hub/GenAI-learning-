"""End-to-end tests against real Chroma + real SentenceTransformer.

Slow: downloads models on first run (~100 MB) and writes a Chroma directory
under tmp_path. Skip in normal CI: `pytest -m "not slow"`.
"""
from __future__ import annotations

import logging
import statistics
import time
from pathlib import Path

import pytest

from legal_rag.application.workflows.evaluation import EVALUATION_CASES
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


@pytest.fixture()
def real_legal_container(tmp_path: Path) -> Container:
    docs = Path(__file__).resolve().parents[2] / "data" / "legal"
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


def test_real_legal_corpus_evaluation(real_legal_container):
    real_legal_container.ingestion_service.ingest()
    retrieval = real_legal_container.retrieval_service
    first_question = EVALUATION_CASES[0].question
    retrieval.retrieve(first_question, n=3, hybrid=False)
    retrieval.retrieve(first_question, n=3, hybrid=True)

    timings = {"dense": [], "hybrid": []}
    hits = {"dense": 0, "hybrid": 0}
    for case in EVALUATION_CASES:
        for mode, hybrid in (("dense", False), ("hybrid", True)):
            started = time.perf_counter()
            results = retrieval.retrieve(case.question, n=3, hybrid=hybrid)
            timings[mode].append((time.perf_counter() - started) * 1000)
            hits[mode] += any(
                result.chunk_id in case.relevant_chunk_ids for result in results
            )

    result = {
        "questions": len(EVALUATION_CASES),
        "k": 3,
        "dense_hits": hits["dense"],
        "dense_hit_rate": hits["dense"] / len(EVALUATION_CASES),
        "dense_p50_ms": round(statistics.median(timings["dense"]), 3),
        "dense_max_ms": round(max(timings["dense"]), 3),
        "hybrid_hits": hits["hybrid"],
        "hybrid_hit_rate": hits["hybrid"] / len(EVALUATION_CASES),
        "hybrid_p50_ms": round(statistics.median(timings["hybrid"]), 3),
        "hybrid_max_ms": round(max(timings["hybrid"]), 3),
        "retrieval_calls": len(EVALUATION_CASES) * 2,
        "llm_calls": 0,
        "tool_calls": 0,
    }

    assert result["questions"] == 10
    assert 0.0 <= result["dense_hit_rate"] <= 1.0
    assert 0.0 <= result["hybrid_hit_rate"] <= 1.0
    logging.getLogger(__name__).info("week11 retrieval evaluation: %s", result)
