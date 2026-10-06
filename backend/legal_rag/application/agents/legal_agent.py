"""Legal agent: budget-limited retrieve/check/definitions/answer loop and its fixed-workflow twin."""
from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from legal_rag.application.workflows.qa import QaService
from legal_rag.application.workflows.retrieval import RetrievalService
from legal_rag.domain.entities import AgentState
from legal_rag.domain.policies import detect_prompt_injection, sanitize_document_text
from legal_rag.infrastructure.observability import get_logger, get_metrics

log = get_logger(__name__)
_metrics = get_metrics()


@dataclass
class AgentBudgets:
    max_steps: int
    max_seconds: float
    max_tokens: int
    max_cost_usd: float
    cost_per_token_usd: float
    guardrail_answer: str


class LegalAgent:
    """Hand-built legal agent with configurable step/time/token/cost budgets."""

    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        qa: QaService,
        budgets: AgentBudgets,
    ):
        self._retrieval = retrieval
        self._qa = qa
        self._budgets = budgets
        self.tools: dict[str, Callable[..., Any]] = {
            "retrieve": self._retrieve,
            "check_amendments": self._check_amendments,
            "get_definitions": self._get_definitions,
            "answer": self._answer,
        }

    # ── public ─────────────────────────────────────────────────────────
    def run(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        state = AgentState(query=query)
        self._step(state, "retrieve", "Find the strongest passages for the question.")

        while state.status == "running":
            if len(state.steps) >= self._budgets.max_steps:
                self._stop_for_budget(state, "max_iterations")
                break
            if time.perf_counter() - started >= self._budgets.max_seconds:
                self._stop_for_budget(state, "wall_clock")
                break
            if state.token_count >= self._budgets.max_tokens:
                self._stop_for_budget(state, "max_tokens")
                break
            if state.estimated_cost_usd >= self._budgets.max_cost_usd:
                self._stop_for_budget(state, "max_cost")
                break

            docs = state.observations["retrieve"]["documents"]
            has_amendment = any(d["document"].lower().startswith("amendment") for d in docs)
            has_contract = any(not d["document"].lower().startswith("amendment") for d in docs)

            if has_amendment and has_contract and "check_amendments" not in state.observations:
                self._step(state, "check_amendments", "Compare contract and amendment passages.")
            elif self._needs_definitions(query) and "get_definitions" not in state.observations:
                self._step(
                    state, "get_definitions",
                    "Resolve the defined terms used by the clause.",
                    {"version": "amended" if has_amendment else "original"},
                )
            else:
                self._step(state, "answer", "Produce a grounded answer from the observations.")
                state.status = "completed"

        elapsed = time.perf_counter() - started
        result = state.observations.get("answer", {}).get("payload", self._budget_result(state))
        report = self._report(result, state, elapsed, "agent")
        _metrics.agent_stops.inc(stop_reason=report["stop_reason"])
        _metrics.tokens.inc(state.token_count, component="agent")
        return report

    # ── tools ──────────────────────────────────────────────────────────
    def _retrieve(self, state: AgentState) -> dict[str, Any]:
        chunks = self._retrieval.retrieve(
            state.query, where=self._retrieval.detect_metadata_filter(state.query)
        )
        injection_detected = any(detect_prompt_injection(c.text) for c in chunks)
        return {
            "documents": [
                {"document": c.document, "chunk_id": c.chunk_id, "score": c.score,
                 "text": sanitize_document_text(c.text)}
                for c in chunks
            ],
            "injection_detected": injection_detected,
        }

    def _check_amendments(self, state: AgentState) -> dict[str, Any]:
        docs = state.observations["retrieve"]["documents"]
        return {
            "contract_documents": [
                d["document"] for d in docs
                if not d["document"].lower().startswith("amendment")
            ],
            "amendment_documents": [
                d["document"] for d in docs
                if d["document"].lower().startswith("amendment")
            ],
        }

    def _get_definitions(
        self, state: AgentState, version: Literal["original", "amended"]
    ) -> dict[str, Any]:
        docs = state.observations["retrieve"]["documents"]
        def _matches(doc_name: str) -> bool:
            is_amendment = doc_name.lower().startswith("amendment")
            return is_amendment if version == "amended" else not is_amendment
        return {
            "version": version,
            "references": [d["chunk_id"] for d in docs if _matches(d["document"])],
        }

    def _answer(self, state: AgentState) -> dict[str, Any]:
        if state.observations["retrieve"].get("injection_detected"):
            return {"payload": {
                "answer": self._budgets.guardrail_answer,
                "reasoning": ("A retrieved document contained an instruction-like passage "
                              "and was excluded from answer generation."),
                "sources": [],
                "confidence": "high",
                "out_of_scope": True,
            }}
        return {"payload": self._qa.answer(state.query)}

    # ── helpers ────────────────────────────────────────────────────────
    def _step(
        self, state: AgentState, tool_name: str, reason: str,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        if len(state.steps) >= self._budgets.max_steps:
            self._stop_for_budget(state, "max_iterations")
            return
        arguments = arguments or {}
        state.steps.append({
            "step": len(state.steps) + 1, "action": tool_name,
            "reason": reason, "arguments": arguments,
        })
        state.tool_calls += 1
        state.observations[tool_name] = self.tools[tool_name](state, **arguments)
        state.token_count += self._estimate_tokens(state.observations[tool_name])
        state.estimated_cost_usd = state.token_count * self._budgets.cost_per_token_usd

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        return max(1, len(str(value).split()))

    @staticmethod
    def _needs_definitions(query: str) -> bool:
        return any(term in query.lower()
                   for term in ("termination", "terminate", "renewal", "defined term"))

    @staticmethod
    def _stop_for_budget(state: AgentState, budget_name: str) -> None:
        status_names = {
            "max_iterations": "step_budget_exceeded",
            "max_tokens": "token_budget_exceeded",
            "max_cost": "cost_budget_exceeded",
            "wall_clock": "time_budget_exceeded",
        }
        state.status = status_names[budget_name]
        state.budget_log.append(f"terminated cleanly: {budget_name} budget exceeded")

    def _budget_result(self, state: AgentState) -> dict[str, Any]:
        return {
            "answer": "The agent stopped before producing an answer.",
            "reasoning": f"The {state.status} limit was reached.",
            "sources": [], "confidence": "low", "out_of_scope": True,
        }

    @staticmethod
    def _report(
        result: dict[str, Any], state: AgentState, elapsed: float, strategy: str
    ) -> dict[str, Any]:
        return {
            "strategy": strategy,
            "result": result,
            "steps": state.steps,
            "tool_calls": state.tool_calls,
            "estimated_cost_usd": round(state.estimated_cost_usd, 8),
            "token_count": state.token_count,
            "budget_log": state.budget_log,
            "elapsed_seconds": round(elapsed, 4),
            "completed": state.status == "completed" and "answer" in state.observations,
            "stop_reason": state.status if state.status != "running" else "answer_ready",
        }


class FixedWorkflow:
    """Deterministic fixed workflow: retrieve → (check amendments) → (definitions) → answer."""

    def __init__(self, agent_factory: Callable[[], LegalAgent]):
        self._agent_factory = agent_factory

    def run(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        agent = self._agent_factory()
        state = AgentState(query=query)
        agent._step(state, "retrieve", "Run the standard retrieval path.")
        docs = state.observations["retrieve"]["documents"]
        has_amendment = any(d["document"].lower().startswith("amendment") for d in docs)
        has_contract = any(not d["document"].lower().startswith("amendment") for d in docs)
        if has_amendment and has_contract:
            agent._step(state, "check_amendments", "Compare original and amendment passages.")
        if agent._needs_definitions(query):
            agent._step(
                state, "get_definitions",
                "Resolve the defined terms used by the clause.",
                {"version": "amended" if has_amendment else "original"},
            )
        agent._step(state, "answer", "Generate the grounded extractive answer.")
        # Preserve the budget stop_reason if the answer step was rejected because
        # a budget fired (e.g. small max_steps); otherwise mark completed.
        if "answer" in state.observations:
            state.status = "completed"
            result = state.observations["answer"]["payload"]
        else:
            result = agent._budget_result(state)
        return agent._report(result, state, time.perf_counter() - started, "fixed_workflow")


def compare_strategies(
    query: str, *, agent_factory: Callable[[], LegalAgent],
    fixed_factory: Callable[[], FixedWorkflow], runs: int = 3,
) -> dict[str, Any]:
    """Run both strategies N times and return a comparative summary."""
    agent_runs = [agent_factory().run(query) for _ in range(runs)]
    fixed_runs = [fixed_factory().run(query) for _ in range(runs)]

    def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
        successful = sum(item["completed"] for item in results)
        return {
            "runs": len(results),
            "successful_runs": successful,
            "reliability": successful / len(results),
            "average_seconds": round(
                statistics.mean(item["elapsed_seconds"] for item in results), 4
            ),
            "average_tool_calls": round(
                statistics.mean(item["tool_calls"] for item in results), 2
            ),
            "estimated_cost_usd": round(
                sum(item["estimated_cost_usd"] for item in results), 4
            ),
            "runs_detail": results,
        }

    return {
        "query": query,
        "agent": summarize(agent_runs),
        "fixed_workflow": summarize(fixed_runs),
        "ship_recommendation": "fixed_workflow",
        "recommendation_reason": (
            "The fixed path has a known sequence and is easier to budget and test for this task."
        ),
    }
