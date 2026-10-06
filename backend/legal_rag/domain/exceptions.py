"""Domain exception hierarchy — business-rule failures only."""
from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-rule failures."""


class GuardrailBlockedError(DomainError):
    """Query was rejected by input guardrails (injection or drafting)."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason  # "injection" | "drafting"
        self.message = message


class OutOfScopeError(DomainError):
    """No retrieved chunk cleared the relevance threshold."""


class SchemaValidationError(DomainError):
    """Answer payload did not conform to the fixed response schema."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class AgentBudgetExceededError(DomainError):
    """Agent stopped cleanly because a budget was reached."""

    def __init__(self, budget: str):
        super().__init__(f"agent {budget} budget exceeded")
        self.budget = budget
