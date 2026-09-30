"""Application layer facade — agents + workflows re-exported."""

from legal_rag.application.agents import (
    AgentBudgets,
    FixedWorkflow,
    GET_DEFINITIONS_TOOL,
    HandoffLog,
    LegalAgent,
    Orchestrator,
    OrchestratorSettings,
    WorkerError,
    compare_strategies,
    estimate_tokens,
    extract_terms,
)
from legal_rag.application.workflows import (
    DETERMINISTIC_ASSERTION_COUNT, EVALUATION_CASES, EvaluationCase,
    EvaluationService, ExtractiveGenerator, GenerationSettings, Generator,
    IngestionService, IngestionSettings, JUDGED_CRITERION_COUNT, JudgeService,
    JudgeSettings, LLMGenerator, MCPLookupService, QaService, RETRIEVE_TOOL,
    RetrievalService, RetrievalSettings, SYSTEM_PROMPT, chunks_payload,
    clause_references_exist, effective_dates_are_parseable,
    notice_periods_are_numeric, run_assertions,
)
# race pulls in agents; import from its submodule after the agents facade is stable.
from legal_rag.application.workflows.race import (
    AgentRace, MeteredLegalAgent, MultiAgentRace, RACE_CASES, RaceCase,
    classify_failure, hop_shares, summarize_race,
)

__all__ = [
    # agents
    "AgentBudgets", "FixedWorkflow", "LegalAgent", "Orchestrator",
    "OrchestratorSettings", "WorkerError", "HandoffLog", "GET_DEFINITIONS_TOOL",
    "compare_strategies", "estimate_tokens", "extract_terms",
    # workflows
    "AgentRace", "MeteredLegalAgent", "MultiAgentRace", "RACE_CASES", "RaceCase",
    "classify_failure", "hop_shares", "summarize_race",
    "EvaluationService", "EvaluationCase", "EVALUATION_CASES",
    "ExtractiveGenerator", "LLMGenerator", "Generator", "GenerationSettings",
    "RETRIEVE_TOOL", "SYSTEM_PROMPT", "chunks_payload",
    "IngestionService", "IngestionSettings",
    "JudgeService", "JudgeSettings",
    "DETERMINISTIC_ASSERTION_COUNT", "JUDGED_CRITERION_COUNT",
    "clause_references_exist", "effective_dates_are_parseable",
    "notice_periods_are_numeric", "run_assertions",
    "MCPLookupService",
    "QaService",
    "RetrievalService", "RetrievalSettings",
]
