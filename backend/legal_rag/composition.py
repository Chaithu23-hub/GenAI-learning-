"""DI container — every service built lazily from a single Settings object."""

from __future__ import annotations

from functools import cached_property

from legal_rag.application.agents import FixedWorkflow, LegalAgent, Orchestrator
from legal_rag.application.agents.legal_agent import AgentBudgets
from legal_rag.application.agents.orchestrator import OrchestratorSettings
from legal_rag.application.workflows import (
    EvaluationService,
    IngestionService,
    JudgeService,
    LLMGenerator,
    MCPLookupService,
    QaService,
    RetrievalService,
)
from legal_rag.application.workflows.corpus_lookup import CorpusLookupService
from legal_rag.application.workflows.generation import GenerationSettings, Generator
from legal_rag.application.workflows.ingestion import IngestionSettings
from legal_rag.application.workflows.judge import JudgeSettings
from legal_rag.application.workflows.race import AgentRace, MeteredLegalAgent, MultiAgentRace
from legal_rag.application.workflows.retrieval import RetrievalSettings
from legal_rag.infrastructure.chunking.section_chunker import SectionChunker
from legal_rag.infrastructure.documents.pdf_loader import IsolatedPDFTextExtractor
from legal_rag.infrastructure.documents.shared_corpus_loader import SharedCorpusDocumentSource
from legal_rag.infrastructure.embeddings import CrossEncoderReranker, SentenceTransformerEmbedder
from legal_rag.infrastructure.errors import PermanentLLMError
from legal_rag.infrastructure.evaluation_files import FilesystemEvaluationFiles
from legal_rag.infrastructure.execution import BoundedWorkExecutor
from legal_rag.infrastructure.llm import GroqClient
from legal_rag.infrastructure.llm.conversation import LLMConversation
from legal_rag.infrastructure.llm.evidence_review import EvidenceReviewClient
from legal_rag.infrastructure.llm.unsupported import LLMUnsupportedResponses
from legal_rag.infrastructure.mcp.stdio_host import StdioContractLookup
from legal_rag.infrastructure.settings import Settings, get_settings
from legal_rag.infrastructure.vector_store import ChromaVectorStore


class Container:
    """Lazy, cached DI container. Services are built on first access."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()

    @property
    def settings(self) -> Settings:
        return self._settings

    @cached_property
    def work_executor(self) -> BoundedWorkExecutor:
        return BoundedWorkExecutor(
            max_workers=self._settings.http_max_concurrent_jobs,
            timeout_seconds=self._settings.http_request_timeout_seconds,
        )

    @cached_property
    def pdf_extractor(self) -> IsolatedPDFTextExtractor:
        return IsolatedPDFTextExtractor(
            max_pages=self._settings.pdf_max_pages,
            max_characters=self._settings.pdf_max_characters,
            timeout_seconds=self._settings.pdf_timeout_seconds,
            memory_mb=self._settings.pdf_memory_mb,
            max_input_bytes=self._settings.upload_max_file_bytes,
        )

    @cached_property
    def upload_document_source(self) -> SharedCorpusDocumentSource:
        return SharedCorpusDocumentSource(self._settings.docs_dir)

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
    def llm_client(self) -> GroqClient:
        s = self._settings
        if not s.llm_api_key:
            raise PermanentLLMError(
                f"An API key is required for the {s.llm_provider} LLM provider."
            )
        return GroqClient(
            base_url=s.effective_llm_base_url,
            api_key=s.llm_api_key,
            model=s.llm_model,
            timeout=s.llm_timeout_seconds,
            max_retries=s.llm_max_retries,
        )

    # ── application services ──────────────────────────────────────────
    @cached_property
    def ingestion_service(self) -> IngestionService:
        return IngestionService(
            vector_store=self.vector_store,
            embedder=self.embedder,
            document_source=SharedCorpusDocumentSource(self._settings.docs_dir),
            chunker=SectionChunker(),
            settings=IngestionSettings(
                chunk_size_tokens=self._settings.chunk_size_tokens,
                chunk_overlap_tokens=self._settings.chunk_overlap_tokens,
            ),
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
            out_of_scope_answer=self._settings.out_of_scope_answer,
            llm_temperature=self._settings.llm_temperature,
        )

    @cached_property
    def generator(self) -> Generator:
        # Use the configured model. Provider/access failures propagate to the interface.
        return LLMGenerator(
            retrieval=self.retrieval_service,
            vector_store=self.vector_store,
            llm=EvidenceReviewClient(self.llm_client),
            settings=self._generation_settings,
        )

    @cached_property
    def conversation(self) -> LLMConversation:
        return LLMConversation(
            self.llm_client, greeting_temperature=self._settings.greeting_temperature
        )

    @cached_property
    def unsupported_responses(self) -> LLMUnsupportedResponses:
        return LLMUnsupportedResponses(
            self.llm_client, temperature=self._settings.unsupported_response_temperature
        )

    @cached_property
    def qa_service(self) -> QaService:
        return QaService(
            retrieval=self.retrieval_service,
            generator=self.generator,
            guardrail_answer=self._settings.guardrail_answer,
            no_drafting_answer=self._settings.no_drafting_answer,
            out_of_scope_answer=self._settings.out_of_scope_answer,
            conversation=self.conversation,
            unsupported_responses=self.unsupported_responses,
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
            retrieval=self.retrieval_service,
            qa=self.qa_service,
            budgets=self._agent_budgets,
        )

    def new_fixed_workflow(self) -> FixedWorkflow:
        return FixedWorkflow(self.new_legal_agent)

    def new_metered_agent(self) -> MeteredLegalAgent:
        return MeteredLegalAgent(
            retrieval=self.retrieval_service,
            qa=self.qa_service,
            budgets=self._agent_budgets,
            chars_per_token=self._settings.chars_per_token,
            cost_per_token_usd=self._settings.agent_cost_per_token_usd,
        )

    @cached_property
    def orchestrator(self) -> Orchestrator:
        return Orchestrator(
            retrieval=self.retrieval_service,
            vector_store=self.vector_store,
            generator=self.generator,
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
    def evaluation_files(self) -> FilesystemEvaluationFiles:
        return FilesystemEvaluationFiles(
            self._settings.evaluation_labels_path, self._settings.evaluation_artifact_dir
        )

    @cached_property
    def judge_service(self) -> JudgeService:
        labels_path = self._settings.evaluation_labels_path
        return JudgeService(
            vector_store=self.vector_store,
            llm=self.llm_client,
            settings=JudgeSettings(labels_path=labels_path),
            evaluation_files=self.evaluation_files,
        )

    @cached_property
    def evaluation_service(self) -> EvaluationService:
        return EvaluationService(retrieval=self.retrieval_service, vector_store=self.vector_store)

    @cached_property
    def agent_race(self) -> AgentRace:
        return AgentRace(
            agent_factory=self.new_legal_agent,
            fixed_factory=self.new_fixed_workflow,
        )

    @cached_property
    def multi_agent_race(self) -> MultiAgentRace:
        artifact_dir = self._settings.evaluation_artifact_dir
        labels_path = self._settings.evaluation_labels_path
        return MultiAgentRace(
            agent_factory=self.new_metered_agent,
            orchestrator=self.orchestrator,
            retrieval=self.retrieval_service,
            judge=self.judge_service,
            labels_path=labels_path,
            cost_per_token_usd=self._settings.agent_cost_per_token_usd,
            chars_per_token=self._settings.chars_per_token,
            artifact_dir=artifact_dir,
            evaluation_files=self.evaluation_files,
        )

    @cached_property
    def corpus_lookup_service(self) -> CorpusLookupService:
        return CorpusLookupService(
            document_source=SharedCorpusDocumentSource(self._settings.docs_dir),
            chunker=SectionChunker(),
            chunk_size=self._settings.chunk_size_tokens,
            overlap=self._settings.chunk_overlap_tokens,
        )

    @cached_property
    def mcp_lookup_service(self) -> MCPLookupService:
        return MCPLookupService(
            lookup=StdioContractLookup(
                self._settings.mcp_config_path, timeout_seconds=self._settings.mcp_timeout_seconds
            )
        )
