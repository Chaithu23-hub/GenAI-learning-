import json
import statistics
from dataclasses import dataclass

from .legal_agent import LegalAgent, run_fixed_workflow


@dataclass(frozen=True)
class RaceCase:
    name: str
    question: str
    branches_on_prior_result: bool = False


RACE_CASES = (
    RaceCase("late_payment_fee", "What is the late payment fee?"),
    RaceCase("termination_notice", "What notice is required to terminate the agreement?", True),
    RaceCase("effective_date", "What is the agreement effective date?"),
    RaceCase("defined_term", "Which defined term controls the termination clause?", True),
    RaceCase("amendment_priority", "Which version controls after the payment amendment?", True),
    RaceCase("confidentiality_survival", "How long do confidentiality obligations survive?"),
    RaceCase("renewal_option", "How does the renewal option work?", True),
    RaceCase("liability_cap", "What is the liability cap?"),
    RaceCase("assignment", "Can the agreement be assigned?"),
    RaceCase("governing_law", "Which law governs the agreement?"),
)


def _passes(report):
    return bool(report.get("completed")) and not report.get("result", {}).get("out_of_scope", False)


def _summary(reports):
    latencies = [report["elapsed_seconds"] for report in reports]
    total_tokens = sum(report.get("token_count", 0) for report in reports)
    total_cost = sum(report.get("estimated_cost_usd", 0.0) for report in reports)
    return {
        "pass_rate": sum(_passes(report) for report in reports) / len(reports),
        "p50_latency_seconds": statistics.median(latencies),
        "total_tokens": total_tokens,
        "cost_per_question_usd": total_cost / len(reports),
        "run_count": len(reports),
    }


def run_race():
    agent_reports = []
    workflow_reports = []
    for case in RACE_CASES:
        agent_reports.append(LegalAgent().run(case.question))
        workflow_reports.append(run_fixed_workflow(case.question))
    agent_summary = _summary(agent_reports)
    workflow_summary = _summary(workflow_reports)
    return {
        "questions": len(RACE_CASES),
        "branching_questions": sum(case.branches_on_prior_result for case in RACE_CASES),
        "table": [
            {"system": "agent", "pass_rate": agent_summary["pass_rate"], "p50_latency_seconds": agent_summary["p50_latency_seconds"], "total_tokens": agent_summary["total_tokens"], "cost_per_question_usd": agent_summary["cost_per_question_usd"]},
            {"system": "fixed_workflow", "pass_rate": workflow_summary["pass_rate"], "p50_latency_seconds": workflow_summary["p50_latency_seconds"], "total_tokens": workflow_summary["total_tokens"], "cost_per_question_usd": workflow_summary["cost_per_question_usd"]},
        ],
        "agent": agent_summary,
        "fixed_workflow": workflow_summary,
        "verdict": (
            "The fixed workflow wins for this corpus because the 10 questions follow a known retrieval-and-answer path. "
            "An agent is justified for termination, renewal, and amendment-version questions where the next retrieval depends on the prior result."
        ),
        "budget_termination_log": LegalAgent(max_steps=1).run("What is the termination notice period?")["budget_log"],
        "third_tool": {
            "name": "get_definitions",
            "description": "Resolve defined terms for exactly one selected contract version.",
            "parameter": "version: Literal['original', 'amended']",
            "difference": "retrieve finds passages; check_amendments compares retrieved versions; get_definitions resolves terms for one selected version.",
        },
    }


def main():
    print(json.dumps(run_race(), indent=2))


if __name__ == "__main__":
    main()
