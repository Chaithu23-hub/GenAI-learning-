"""Shared fixtures: a Container wired against in-memory fakes, plus a seeded corpus."""
from __future__ import annotations

from pathlib import Path

import pytest

from legal_rag.application.agents import (LegalAgent, Orchestrator)
from legal_rag.application.workflows import (EvaluationService, ExtractiveGenerator, IngestionService, JudgeService, MCPLookupService, QaService, RetrievalService)
from legal_rag.application.agents.legal_agent import AgentBudgets, FixedWorkflow
from legal_rag.application.workflows.generation import GenerationSettings
from legal_rag.application.workflows.ingestion import IngestionSettings
from legal_rag.application.workflows.judge import JudgeSettings
from legal_rag.application.agents.orchestrator import OrchestratorSettings
from legal_rag.application.workflows.race import MeteredLegalAgent
from legal_rag.application.workflows.retrieval import RetrievalSettings
from legal_rag.composition import Container
from legal_rag.infrastructure.settings import Settings

from tests.fakes.embedder import HashEmbedder
from tests.fakes.reranker import ScoringReranker
from tests.fakes.vector_store import InMemoryVectorStore

FIXTURE_DOCS = {
    "master_services_agreement.md": (
        "# Master Services Agreement\n\n"
        "This Master Services Agreement is effective as of 2021-01-14.\n\n"
        "## Section 3: Payment Terms\n"
        "Late payments shall accrue interest at a rate of 1.0% per month.\n\n"
        "## Section 5: Termination\n"
        "Either party may terminate this agreement with 30 days written notice.\n\n"
        "## Section 7: Governing Law\n"
        "This Agreement is governed by the laws of the State of California.\n"
    ),
    "amendment_01_payment_terms.md": (
        "# Amendment 1 to Master Services Agreement\n\n"
        "**Effective date:** 2021-03-15\n\n"
        "## Section 3: Payment Terms\n"
        "Section 3 is hereby deleted and replaced. Late payments shall accrue interest "
        "at a rate of 1.5% per month.\n\n"
        "## Changes made by this amendment\n"
        "This Amendment replaces the original Section 3 rate of 1.0% per month with 1.5%.\n"
    ),
    "enterprise_saas_subscription_agreement.md": (
        "# Enterprise SaaS Subscription Agreement\n\n"
        "**Effective date:** 2022-06-01\n\n"
        "## Section 2 — Subscription Term\n"
        "Auto-renews for one-year periods unless either Party gives 60 days written "
        "notice of non-renewal before the end of the then-current Term.\n\n"
        "## Section 9 — Confidentiality\n"
        "Confidentiality obligations survive for 3 years after termination.\n"
    ),
}


@pytest.fixture()
def corpus_dir(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    for name, text in FIXTURE_DOCS.items():
        (docs / name).write_text(text, encoding="utf-8")
    return docs


@pytest.fixture()
def settings(tmp_path: Path, corpus_dir: Path) -> Settings:
    return Settings(
        docs_dir=corpus_dir,
        chroma_dir=tmp_path / "chroma",
        mcp_config_path=tmp_path / "mcp.json",
        llm_provider="extractive",
        api_key=None,
    )


class FakeContainer(Container):
    """Container that ignores real infra and uses in-memory fakes."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._vector_store_fake = InMemoryVectorStore()
        self._embedder_fake = HashEmbedder()
        self._reranker_fake = ScoringReranker()

    @property
    def vector_store(self):  # type: ignore[override]
        return self._vector_store_fake

    @property
    def embedder(self):  # type: ignore[override]
        return self._embedder_fake

    @property
    def reranker(self):  # type: ignore[override]
        return self._reranker_fake

    @property
    def llm_client(self):  # type: ignore[override]
        return None


@pytest.fixture()
def container(settings: Settings) -> Container:
    c = FakeContainer(settings)
    # Seed the store so retrieval-dependent tests have data.
    c.ingestion_service.ingest()
    return c
