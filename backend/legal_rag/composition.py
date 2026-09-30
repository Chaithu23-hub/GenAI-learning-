"""DI container — every service built lazily from a single Settings object."""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

from legal_rag.application.agents import (FixedWorkflow, LegalAgent, Orchestrator)
from legal_rag.application.workflows import (
    EvaluationService, ExtractiveGenerator, IngestionService, JudgeService,
    LLMGenerator, MCPLookupService, QaService, RetrievalService,
)
from legal_rag.application.workflows.race import (
    AgentRace, MeteredLegalAgent, MultiAgentRace,
)
from legal_rag.application.agents.legal_agent import AgentBudgets
from legal_rag.application.workflows.generation import GenerationSettings, Generator
from legal_rag.application.workflows.ingestion import IngestionSettings
from legal_rag.application.workflows.judge import JudgeSettings
from legal_rag.application.agents.orchestrator import OrchestratorSettings
from legal_rag.application.workflows.retrieval import RetrievalSettings
from legal_rag.infrastructure.embeddings import (
    CrossEncoderReranker,
    SentenceTransformerEmbedder,
)
from legal_rag.infrastructure.llm import OpenAICompatibleClient, detect_llm_model
from legal_rag.infrastructure.vector_store import ChromaVectorStore
from legal_rag.infrastructure.settings import Settings, get_settings


class Container:
    """Lazy, cached DI container. Services are built on first access."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()

    @property
    def settings(self) -> Settings:
        return self._settings

    # ── infrastructure ────────────────────────────────────────────────
    @cached_property
    def vector_store(self) -> ChromaVectorStore:
        return ChromaVectorStore(self._settings.chroma_dir)

    @cached_property
    def embedder(self) -> SentenceTransformerEmbedder:
        return SentenceTransformerEmbedder(self._settings.embedding_model)

    @cached_property
    def reranker(self) -> CrossEncoderReranker:
        return CrossEncoderReranker(self._settings.rerank_model)

    @cached_property
    def llm_client(self) -> OpenAICompatibleClient | None:
        s = self._settings
        if s.llm_provider == "extractive" or not s.google_api_key_value:
            return None
        return OpenAICompatibleClient(
            base_url=s.llm_base_url,
            api_key=s.google_api_key_value,
            model=s.google_model,
            timeout=s.llm_timeout_seconds,
            max_retries=s.llm_max_retries,
        )

    # ── application services ──────────────────────────────────────────
    @cached_property
    def ingestion_service(self) -> IngestionService:
        return IngestionService(
            vector_store=self.vector_store,
            embedder=self.embedder,
            settings=IngestionSettings(
                chunk_size_tokens=self._settings.chunk_size_tokens,
                chunk_overlap_tokens=self._settings.chunk_overlap_tokens,
            ),
            docs_dir=self._settings.docs_dir,
        )

    @cached_property
    def retrieval_service(self) -> RetrievalService:
        return RetrievalService(
            vector_store=self.vector_store,
            embedder=self.embedder,
            reranker=self.reranker,
            settings=RetrievalSettings(
                top_k_candidates=self._settings.top_k_candidates,
                top_n_answers=self._settings.top_n_answers,
                hybrid_enabled=self._settings.hybrid_enabled,
                rrf_k=self._settings.rrf_k,
            ),
        )

    @cached_property
    def _generation_settings(self) -> GenerationSettings:
        return GenerationSettings(
            min_relevant_score=self._settings.min_relevant_score,
            high_confidence_score=self._settings.high_confidence_score,
            out_of_scope_answer=self._settings.out_of_scope_answer,
            llm_temperature=self._settings.llm_temperature,
        )

    @cached_property
    def extractive_generator(self) -> ExtractiveGenerator:
        return ExtractiveGenerator(
            retrieval=self.retrieval_service, settings=self._generation_settings,
        )

    @cached_property
    def generator(self) -> Generator:
        if self.llm_client is None:
            return self.extractive_generator
        # Probe for available model; fall back to extractive if endpoint is unreachable.
        detected = detect_llm_model(self.llm_client)
        if detected is None:
            return self.extractive_generator
        return LLMGenerator(
            retrieval=self.retrieval_service,
            vector_store=self.vector_store,
            llm=self.llm_client,
            settings=self._generation_settings,
            fallback=self.extractive_generator,
        )

    @cached_property
    def qa_service(self) -> QaService:
        return QaService(
            retrieval=self.retrieval_service,
            generator=self.generator,
            guardrail_answer=self._settings.guardrail_answer,
            no_drafting_answer=self._settings.no_drafting_answer,
            greeting_answer=self._settings.greeting_answer,
        )

    @cached_property
    def _agent_budgets(self) -> AgentBudgets:
        return AgentBudgets(
            max_steps=self._settings.agent_max_steps,
            max_seconds=self._settings.agent_max_seconds,
            max_tokens=self._settings.agent_max_tokens,
            max_cost_usd=self._settings.agent_max_cost_usd,
            cost_per_token_usd=self._settings.agent_cost_per_token_usd,
            guardrail_answer=self._settings.guardrail_answer,
        )

    def new_legal_agent(self) -> LegalAgent:
        return LegalAgent(
            retrieval=self.retrieval_service, qa=self.qa_service, budgets=self._agent_budgets,
        )

    def new_fixed_workflow(self) -> FixedWorkflow:
        return FixedWorkflow(self.new_legal_agent)

    def new_metered_agent(self) -> MeteredLegalAgent:
        return MeteredLegalAgent(
            retrieval=self.retrieval_service, qa=self.qa_service, budgets=self._agent_budgets,
            chars_per_token=self._settings.chars_per_token,
            cost_per_token_usd=self._settings.agent_cost_per_token_usd,
        )

    @cached_property
    def orchestrator(self) -> Orchestrator:
        return Orchestrator(
            retrieval=self.retrieval_service,
            vector_store=self.vector_store,
            extractive_generator=self.extractive_generator,
            settings=OrchestratorSettings(
                worker_retries=self._settings.orchestrator_worker_retries,
                chars_per_token=self._settings.chars_per_token,
                cost_per_token_usd=self._settings.agent_cost_per_token_usd,
                guardrail_answer=self._settings.guardrail_answer,
                no_drafting_answer=self._settings.no_drafting_answer,
                docs_dir=self._settings.docs_dir,
            ),
        )

    @cached_property
    def judge_service(self) -> JudgeService:
        labels_path = Path(self._settings.project_root).parent / "eval" / "labels_25.json"
        return JudgeService(
            vector_store=self.vector_store,
            llm=self.llm_client,
            settings=JudgeSettings(labels_path=labels_path),
        )

    @cached_property
    def evaluation_service(self) -> EvaluationService:
        return EvaluationService(retrieval=self.retrieval_service)

    @cached_property
    def agent_race(self) -> AgentRace:
        return AgentRace(
            agent_factory=self.new_legal_agent, fixed_factory=self.new_fixed_workflow,
        )

    @cached_property
    def multi_agent_race(self) -> MultiAgentRace:
        artifact_dir = Path(self._settings.project_root).parent / "eval" / "week10"
        labels_path = Path(self._settings.project_root).parent / "eval" / "labels_25.json"
        return MultiAgentRace(
            agent_factory=self.new_metered_agent,
            orchestrator=self.orchestrator,
            retrieval=self.retrieval_service,
            judge=self.judge_service,
            labels_path=labels_path,
            cost_per_token_usd=self._settings.agent_cost_per_token_usd,
            chars_per_token=self._settings.chars_per_token,
            artifact_dir=artifact_dir,
        )

    @cached_property
    def mcp_lookup_service(self) -> MCPLookupService:
        return MCPLookupService(mcp_config_path=self._settings.mcp_config_path)


_container: Container | None = None


def get_container(settings: Settings | None = None) -> Container:
    """Return the process-wide container, building it on first call."""
    global _container
    if _container is None:
        _container = Container(settings)
    return _container


def reset_container() -> None:
    """Test helper — discard the cached container."""
    global _container
    _container = None
