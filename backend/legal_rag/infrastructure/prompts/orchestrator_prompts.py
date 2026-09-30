"""Orchestrator, defined-terms worker, and synthesiser prompts (v1)."""
from legal_rag.infrastructure.prompts.prompt import PromptTemplate

_ORCH_TEXT = """ROLE
You route one legal question to narrow workers; you never answer it yourself.
Return JSON: {"subtasks": ["clause", "defined_terms"?], "terms": [...], "governing_version": "original|amended", "effective_date": "YYYY-MM-DD"}.
Send the clause worker only the question, governing version and effective date. Send the defined-terms worker only the terms and version."""

_DT_TEXT = """ROLE
Return the Definitions-clause text for each requested term, for exactly one contract version.
Quote verbatim. If a term is not defined in that version, list it under not_found. Never paraphrase or infer a meaning."""

_SYN_TEXT = """ROLE
Merge worker outputs into one answer in the fixed response schema (answer, reasoning, sources, confidence, out_of_scope).
Use only worker outputs. If a worker failed, say which fact is unverified. Never state the meaning of a term the defined-terms worker did not return."""

ORCHESTRATOR_PROMPT = _ORCH_TEXT
DEFINED_TERMS_PROMPT = _DT_TEXT
SYNTHESIZER_PROMPT = _SYN_TEXT

ORCHESTRATOR_PROMPT_V1 = PromptTemplate(name="orchestrator.planner", version="v1", text=_ORCH_TEXT)
DEFINED_TERMS_PROMPT_V1 = PromptTemplate(name="orchestrator.defined_terms", version="v1", text=_DT_TEXT)
SYNTHESIZER_PROMPT_V1 = PromptTemplate(name="orchestrator.synthesizer", version="v1", text=_SYN_TEXT)

GET_DEFINITIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_definitions",
        "description": "Resolve defined terms for exactly one selected contract version.",
        "parameters": {
            "type": "object",
            "properties": {
                "terms": {"type": "array", "items": {"type": "string"}},
                "version": {"type": "string", "enum": ["original", "amended"]},
            },
            "required": ["terms", "version"],
        },
    },
}
