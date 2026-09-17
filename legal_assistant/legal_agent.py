import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import config
from .pipeline import answer_question, detect_metadata_filter
from .retrieval import retrieve
from .agent_failure_modes import detect_prompt_injection, sanitize_document_text


@dataclass
class AgentState:
    query: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    tool_calls: int = 0
    status: str = "running"


class LegalAgent:
    def __init__(self, max_steps=None, max_seconds=None):
        self.max_steps = config.AGENT_MAX_STEPS if max_steps is None else max_steps
        self.max_seconds = config.AGENT_MAX_SECONDS if max_seconds is None else max_seconds
        self.tools: dict[str, Callable[..., Any]] = {
            "retrieve": self._retrieve,
            "check_amendments": self._check_amendments,
            "answer": self._answer,
        }

    def run(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        state = AgentState(query=query)
        self._step(state, "retrieve", "Find the strongest passages for the question.")

        while state.status == "running":
            if len(state.steps) >= self.max_steps:
                state.status = "step_budget_exceeded"
                break
            if time.perf_counter() - started >= self.max_seconds:
                state.status = "time_budget_exceeded"
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
            else:
                self._step(state, "answer", "Produce a grounded answer from the observations.")
                state.status = "completed"

        elapsed = time.perf_counter() - started
        result = state.observations.get("answer", {}).get("payload", self._budget_result(state))
        return self._report(result, state, elapsed, "agent")

    def _step(self, state, tool_name, reason):
        if len(state.steps) >= self.max_steps:
            state.status = "step_budget_exceeded"
            return
        state.steps.append({"step": len(state.steps) + 1, "action": tool_name, "reason": reason})
        state.tool_calls += 1
        state.observations[tool_name] = self.tools[tool_name](state)

    def _retrieve(self, state):
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

    def _answer(self, state):
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
            "estimated_cost_usd": 0.0,
            "elapsed_seconds": round(elapsed, 4),
            "completed": state.status == "completed" and "answer" in state.observations,
            "stop_reason": state.status if state.status != "running" else "answer_ready",
        }


def run_fixed_workflow(query: str) -> dict[str, Any]:
    started = time.perf_counter()
    steps = [
        {"step": 1, "action": "retrieve", "reason": "Run the standard retrieval path."},
        {"step": 2, "action": "answer", "reason": "Generate the grounded extractive answer."},
    ]
    result = answer_question(query, backend="extractive")
    return {
        "strategy": "fixed_workflow",
        "result": result,
        "steps": steps,
        "tool_calls": 2,
        "estimated_cost_usd": 0.0,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "completed": True,
        "stop_reason": "answer_ready",
    }


def compare_strategies(query: str, runs=3) -> dict[str, Any]:
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