"""Versioned prompt templates. Import prompts from here, never define inline."""

from .judge_prompts import (
    JUDGE_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT_V1,
    JUDGE_USER_TEMPLATE,
    JUDGE_USER_TEMPLATE_V1,
)
from .orchestrator_prompts import (
    DEFINED_TERMS_PROMPT,
    DEFINED_TERMS_PROMPT_V1,
    GET_DEFINITIONS_TOOL,
    ORCHESTRATOR_PROMPT,
    ORCHESTRATOR_PROMPT_V1,
    SYNTHESIZER_PROMPT,
    SYNTHESIZER_PROMPT_V1,
)
from .prompt import PromptTemplate
from .qa_system import QA_SYSTEM_PROMPT, RETRIEVE_TOOL, SYSTEM_PROMPT
from .registry import ACTIVE_PROMPTS, get, snapshot

__all__ = [
    "PromptTemplate", "ACTIVE_PROMPTS", "get", "snapshot",
    # string constants (backward-compatible)
    "SYSTEM_PROMPT", "RETRIEVE_TOOL",
    "ORCHESTRATOR_PROMPT", "DEFINED_TERMS_PROMPT", "SYNTHESIZER_PROMPT",
    "GET_DEFINITIONS_TOOL",
    "JUDGE_SYSTEM_PROMPT", "JUDGE_USER_TEMPLATE",
    # versioned templates
    "QA_SYSTEM_PROMPT",
    "ORCHESTRATOR_PROMPT_V1", "DEFINED_TERMS_PROMPT_V1", "SYNTHESIZER_PROMPT_V1",
    "JUDGE_SYSTEM_PROMPT_V1", "JUDGE_USER_TEMPLATE_V1",
]
