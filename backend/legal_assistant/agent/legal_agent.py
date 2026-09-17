import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .. import config
from ..generation.pipeline import answer_question, detect_metadata_filter
from ..retrieval.retrieval import retrieve
from ..safety.agent_failure_modes import detect_prompt_injection, sanitize_document_text


@dataclass
class AgentState:
    query: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    tool_calls: int = 0
    status: str = "running"
    token_count: int = 0
    estimated_cost_usd: float = 0.0
    budget_log: list[str] = field(default_factory=list)


class LegalAgent:
    """Hand-built legal agent with configurable step, time, token, and cost budgets."""

    def __init__(self, max_steps=None, max_seconds=None, max_tokens=None, max_cost_usd=None):
        self.max_steps = config.AGENT_MAX_STEPS if max_steps is None else max_steps
        self.max_seconds = config.AGENT_MAX_SECONDS if max_seconds is None else max_seconds
        self.max_tokens = config.AGENT_MAX_TOKENS if max_tokens is None else max_tokens
        self.max_cost_usd = config.AGENT_MAX_COST_USD if max_cost_usd is None else max_cost_usd
        self.tools: dict[str, Callable[..., Any]] = {
            "retrieve": self._retrieve,
            "check_amendments": self._check_amendments,
            "get_definitions": self._get_definitions,
            "answer": self._answer,
        }

    def run(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        state = AgentState(query=query)
        self._step(state, "retrieve", "Find the strongest passages for the question.")

        while state.status == "running":
            if len(state.steps) >= self.max_steps:
                self._stop_for_budget(state, "max_iterations")
                break
            if time.perf_counter() - started >= self.max_seconds:
                self._stop_for_budget(state, "wall_clock")
                break
            if state.token_count >= self.max_tokens:
                self._stop_for_budget(state, "max_tokens")
                break
            if state.estimated_cost_usd >= self.max_cost_usd:
                self._stop_for_budget(state, "max_cost")
                break

            documents = state.observations["retrieve"]["documents"]
            has_amendment = any(
                item["document"].lower().startswith("amendment") for item in documents
            )
            has_contract = any(
                not item["document"].lower().startswith("amendment") for item in documents
            )

            if has_amendment and has_contract and "check_amendments" not in state.observations:
                self._step(state, "check_amendments", "Compare contract and amendment passages.")
            elif self._needs_definitions(query) and "get_definitions" not in state.observations:
                self._step(state, "get_definitions", "Resolve the defined terms used by the clause.", {"version": "amended" if has_amendment else "original"})
            else:
                self._step(state, "answer", "Produce a grounded answer from the observations.")
                state.status = "completed"

        elapsed = time.perf_counter() - started
        result = state.observations.get("answer", {}).get("payload", self._budget_result(state))
        return self._report(result, state, elapsed, "agent")

    def _step(self, state, tool_name, reason, arguments=None):
        if len(state.steps) >= self.max_steps:
            self._stop_for_budget(state, "max_iterations")
            return
        arguments = arguments or {}
        state.steps.append({"step": len(state.steps) + 1, "action": tool_name, "reason": reason, "arguments": arguments})
        state.tool_calls += 1
        state.observations[tool_name] = self.tools[tool_name](state, **arguments)
        state.token_count += self._estimate_tokens(state.observations[tool_name])
        state.estimated_cost_usd = state.token_count * config.AGENT_COST_PER_TOKEN_USD

    def _retrieve(self, state):
        """Retrieve passages relevant to the user's contract question."""
        chunks = retrieve(state.query, where=detect_metadata_filter(state.query))
        injection_detected = any(detect_prompt_injection(chunk.text) for chunk in chunks)
        return {
            "documents": [
                {
                    "document": chunk.document,
                    "chunk_id": chunk.chunk_id,
                    "score": chunk.score,
                    "text": sanitize_document_text(chunk.text),
                }
                for chunk in chunks
            ],
            "injection_detected": injection_detected,
        }

    def _check_amendments(self, state):
        """Compare original and amendment passages already retrieved."""
        documents = state.observations["retrieve"]["documents"]
        return {
            "contract_documents": [
                item["document"] for item in documents
                if not item["document"].lower().startswith("amendment")
            ],
            "amendment_documents": [
                item["document"] for item in documents
                if item["document"].lower().startswith("amendment")
            ],
        }

    def _get_definitions(self, state, version: Literal["original", "amended"]):
        """Resolve defined terms for exactly one selected contract version."""
        documents = state.observations["retrieve"]["documents"]
        return {
            "version": version,
            "references": [item["chunk_id"] for item in documents if version in item["document"].lower() or version == "original"],
        }

    def _answer(self, state):
        """Produce the grounded answer from the observations."""
        if state.observations["retrieve"].get("injection_detected"):
            return {
                "payload": {
                    "answer": config.GUARDRAIL_ANSWER,
                    "reasoning": "A retrieved document contained an instruction-like passage and was excluded from answer generation.",
                    "sources": [],
                    "confidence": "high",
                    "out_of_scope": True,
                }
            }
        return {"payload": answer_question(state.query, backend="extractive")}

    @staticmethod
    def _estimate_tokens(value):
        return max(1, len(str(value).split()))

    @staticmethod
    def _needs_definitions(query):
        return any(term in query.lower() for term in ("termination", "terminate", "renewal", "defined term"))

    @staticmethod
    def _stop_for_budget(state, budget_name):
        status_names = {
            "max_iterations": "step_budget_exceeded",
            "max_tokens": "token_budget_exceeded",
            "max_cost": "cost_budget_exceeded",
            "wall_clock": "time_budget_exceeded",
        }
        state.status = status_names[budget_name]
        state.budget_log.append(f"terminated cleanly: {budget_name} budget exceeded")

    def _budget_result(self, state):
        return {
            "answer": "The agent stopped before producing an answer.",
            "reasoning": f"The {state.status} limit was reached.",
            "sources": [],
            "confidence": "low",
            "out_of_scope": True,
        }

    @staticmethod
    def _report(result, state, elapsed, strategy):
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


def run_fixed_workflow(query: str) -> dict[str, Any]:
    """Deterministic fixed workflow: retrieve → (check amendments) → (definitions) → answer."""
    started = time.perf_counter()
    agent = LegalAgent()
    state = AgentState(query=query)
    agent._step(state, "retrieve", "Run the standard retrieval path.")
    documents = state.observations["retrieve"]["documents"]
    has_amendment = any(item["document"].lower().startswith("amendment") for item in documents)
    has_contract = any(not item["document"].lower().startswith("amendment") for item in documents)
    if has_amendment and has_contract:
        agent._step(state, "check_amendments", "Compare original and amendment passages.")
    if agent._needs_definitions(query):
        agent._step(state, "get_definitions", "Resolve the defined terms used by the clause.", {"version": "amended" if has_amendment else "original"})
    agent._step(state, "answer", "Generate the grounded extractive answer.")
    state.status = "completed"
    return agent._report(state.observations["answer"]["payload"], state, time.perf_counter() - started, "fixed_workflow")


def compare_strategies(query: str, runs=3) -> dict[str, Any]:
    """Run both agent and fixed workflow N times and return a comparative summary."""
    agent_runs = [LegalAgent().run(query) for _ in range(runs)]
    fixed_runs = [run_fixed_workflow(query) for _ in range(runs)]

    def summarize(results):
        successful = sum(item["completed"] for item in results)
        return {
            "runs": len(results),
            "successful_runs": successful,
            "reliability": successful / len(results),
            "average_seconds": round(sum(item["elapsed_seconds"] for item in results) / len(results), 4),
            "average_tool_calls": round(sum(item["tool_calls"] for item in results) / len(results), 2),
            "estimated_cost_usd": round(sum(item["estimated_cost_usd"] for item in results), 4),
            "runs_detail": results,
        }

    return {
        "query": query,
        "agent": summarize(agent_runs),
        "fixed_workflow": summarize(fixed_runs),
        "ship_recommendation": "fixed_workflow",
        "recommendation_reason": "The fixed path has a known sequence and is easier to budget and test for this task.",
    }
