"""Central registry of the prompts currently in production.

Adding a new prompt version means (1) creating the v2 template in the same
module and (2) adding it to this registry so the version pin is visible in
one place. Old versions stay for rollback + A/B evaluation.
"""
from __future__ import annotations

from legal_rag.infrastructure.prompts.judge_prompts import (
    JUDGE_SYSTEM_PROMPT_V1,
    JUDGE_USER_TEMPLATE_V1,
)
from legal_rag.infrastructure.prompts.orchestrator_prompts import (
    DEFINED_TERMS_PROMPT_V1,
    ORCHESTRATOR_PROMPT_V1,
    SYNTHESIZER_PROMPT_V1,
)
from legal_rag.infrastructure.prompts.prompt import PromptTemplate
from legal_rag.infrastructure.prompts.qa_system import QA_SYSTEM_PROMPT

# `name` -> currently-active PromptTemplate.
ACTIVE_PROMPTS: dict[str, PromptTemplate] = {
    QA_SYSTEM_PROMPT.name: QA_SYSTEM_PROMPT,
    ORCHESTRATOR_PROMPT_V1.name: ORCHESTRATOR_PROMPT_V1,
    DEFINED_TERMS_PROMPT_V1.name: DEFINED_TERMS_PROMPT_V1,
    SYNTHESIZER_PROMPT_V1.name: SYNTHESIZER_PROMPT_V1,
    JUDGE_SYSTEM_PROMPT_V1.name: JUDGE_SYSTEM_PROMPT_V1,
    JUDGE_USER_TEMPLATE_V1.name: JUDGE_USER_TEMPLATE_V1,
}


def get(name: str) -> PromptTemplate:
    if name not in ACTIVE_PROMPTS:
        raise KeyError(f"unknown prompt: {name}")
    return ACTIVE_PROMPTS[name]


def snapshot() -> dict[str, str]:
    """Version pin — used by health / logging so a prod deploy records what shipped."""
    return {name: tmpl.version for name, tmpl in sorted(ACTIVE_PROMPTS.items())}
