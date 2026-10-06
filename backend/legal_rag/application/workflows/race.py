"""Agent-vs-fixed race and single-agent-vs-orchestrator multi-agent race."""
from __future__ import annotations

import json
import math
import re
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from legal_rag.application.agents.legal_agent import FixedWorkflow, LegalAgent
from legal_rag.application.agents.orchestrator import (
    GET_DEFINITIONS_TOOL,
    HandoffLog,
    Orchestrator,
)
from legal_rag.application.workflows.generation import RETRIEVE_TOOL, SYSTEM_PROMPT
from legal_rag.application.workflows.judge import JudgeService
from legal_rag.application.workflows.retrieval import RetrievalService

# ─── Simple race (Week 7) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class RaceCase:
    name: str
    question: str
    branches_on_prior_result: bool = False


RACE_CASES: tuple[RaceCase, ...] = (
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


def _passes(report: dict[str, Any]) -> bool:
    return bool(report.get("completed")) and not report.get("result", {}).get("out_of_scope", False)


def _summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [r["elapsed_seconds"] for r in reports]
    total_tokens = sum(r.get("token_count", 0) for r in reports)
    total_cost = sum(r.get("estimated_cost_usd", 0.0) for r in reports)
    return {
        "pass_rate": sum(_passes(r) for r in reports) / len(reports),
        "p50_latency_seconds": statistics.median(latencies),
        "total_tokens": total_tokens,
        "cost_per_question_usd": total_cost / len(reports),
        "run_count": len(reports),
    }


class AgentRace:
    """Week 7 race: single agent vs deterministic fixed workflow."""

    def __init__(
        self,
        *,
        agent_factory: Callable[[], LegalAgent],
        fixed_factory: Callable[[], FixedWorkflow],
    ):
        self._agent_factory = agent_factory
        self._fixed_factory = fixed_factory

    def run(self) -> dict[str, Any]:
        agent_reports = [self._agent_factory().run(case.question) for case in RACE_CASES]
        fixed_reports = [self._fixed_factory().run(case.question) for case in RACE_CASES]
        agent_summary = _summary(agent_reports)
        fixed_summary = _summary(fixed_reports)
        winner = self._select_winner(agent_summary, fixed_summary)
        verdict = (
            "The measured results are tied across reliability and efficiency."
            if winner == "tie"
            else f"The {winner} performed best based on pass rate, then latency, tokens, and cost."
        )
        # Trigger a clean budget termination for evidence.
        budget_log = LegalAgent(
            retrieval=self._agent_factory()._retrieval,
            qa=self._agent_factory()._qa,
            budgets=self._agent_factory()._budgets.__class__(
                max_steps=1,
                max_seconds=self._agent_factory()._budgets.max_seconds,
                max_tokens=self._agent_factory()._budgets.max_tokens,
                max_cost_usd=self._agent_factory()._budgets.max_cost_usd,
                cost_per_token_usd=self._agent_factory()._budgets.cost_per_token_usd,
                guardrail_answer=self._agent_factory()._budgets.guardrail_answer,
            ),
        ).run("What is the termination notice period?")["budget_log"]
        return {
            "questions": len(RACE_CASES),
            "branching_questions": sum(c.branches_on_prior_result for c in RACE_CASES),
            "table": [
                {"system": "agent",
                 **{k: agent_summary[k] for k in
                    ("pass_rate", "p50_latency_seconds", "total_tokens", "cost_per_question_usd")}},
                {"system": "fixed_workflow",
                 **{k: fixed_summary[k] for k in
                    ("pass_rate", "p50_latency_seconds", "total_tokens", "cost_per_question_usd")}},
            ],
            "agent": agent_summary,
            "fixed_workflow": fixed_summary,
            "winner": winner,
            "verdict": verdict,
            "budget_termination_log": budget_log,
            "third_tool": {
                "name": "get_definitions",
                "description": "Resolve defined terms for exactly one selected contract version.",
                "parameter": "version: Literal['original', 'amended']",
                "difference": (
                    "retrieve finds passages; check_amendments compares retrieved versions; "
                    "get_definitions resolves terms for one selected version."
                ),
            },
        }

    @staticmethod
    def _select_winner(a: dict[str, Any], f: dict[str, Any]) -> str:
        a_key = (a["pass_rate"], -a["p50_latency_seconds"],
                 -a["total_tokens"], -a["cost_per_question_usd"])
        f_key = (f["pass_rate"], -f["p50_latency_seconds"],
                 -f["total_tokens"], -f["cost_per_question_usd"])
        if a_key == f_key:
            return "tie"
        return "agent" if a_key > f_key else "fixed_workflow"


# ─── Multi-agent race (Week 10) ───────────────────────────────────────────


EVAL_CASE_IDS: tuple[int, ...] = tuple(range(1, 11))
FAILURE_CASE_ID = 10

SINGLE_AGENT_TOOLS: list[dict[str, Any]] = [
    RETRIEVE_TOOL,
    {"type": "function", "function": {
        "name": "check_amendments",
        "description": "Compare original and amendment passages already retrieved.",
        "parameters": {"type": "object", "properties": {}},
    }},
    GET_DEFINITIONS_TOOL,
    {"type": "function", "function": {
        "name": "answer",
        "description": "Produce the grounded answer from the observations.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


class MeteredLegalAgent(LegalAgent):
    """Single agent, metered as one model turn per step re-reading its transcript."""

    def __init__(self, *args, chars_per_token: int = 4, cost_per_token_usd: float = 1e-6, **kwargs):
        super().__init__(*args, **kwargs)
        self._chars_per_token = chars_per_token
        self._cost_per_token_usd = cost_per_token_usd
        self.log = HandoffLog(chars_per_token=chars_per_token)

    def run(self, query: str) -> dict[str, Any]:
        self.log = HandoffLog(chars_per_token=self._chars_per_token)
        report = super().run(query)
        report["handoffs"] = self.log.entries
        report["token_count"] = self.log.total_tokens
        report["estimated_cost_usd"] = round(
            self.log.total_tokens * self._cost_per_token_usd, 8
        )
        return report

    def _step(self, state, tool_name, reason, arguments=None):
        transcript = [SYSTEM_PROMPT, SINGLE_AGENT_TOOLS, state.query,
                      list(state.observations.values())]
        steps_before = len(state.steps)
        super()._step(state, tool_name, reason, arguments)
        if len(state.steps) > steps_before:
            output = (state.observations[tool_name] if tool_name == "answer"
                      else {"tool": tool_name, "arguments": arguments or {}})
            self.log.record(
                f"single_agent turn -> {tool_name} (transcript re-read)", transcript, output,
            )


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile / 100 * len(ordered)) - 1)]


def summarize_race(
    reports: list[dict[str, Any]], verdicts: list[dict[str, Any]],
    cost_per_token_usd: float,
) -> dict[str, Any]:
    latencies = [r["elapsed_seconds"] for r in reports]
    total_tokens = sum(r["token_count"] for r in reports)
    return {
        "pass_rate": sum(v["passed"] for v in verdicts) / len(reports),
        "p50_latency_seconds": statistics.median(latencies),
        "p99_latency_seconds": _nearest_rank(latencies, 99),
        "total_tokens": total_tokens,
        "cost_per_question_usd": total_tokens * cost_per_token_usd / len(reports),
    }


def hop_shares(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, int] = defaultdict(int)
    for report in reports:
        for entry in report["handoffs"]:
            totals[entry["hop"]] += entry["tokens"]
    grand_total = sum(totals.values())
    return sorted(
        ({"hop": hop, "tokens": tokens, "share": tokens / grand_total}
         for hop, tokens in totals.items()),
        key=lambda item: item["tokens"], reverse=True,
    )


def classify_failure(report: dict[str, Any], terms: list[str]) -> dict[str, Any]:
    attempts = [
        e for e in report["handoffs"]
        if e["hop"].startswith("orchestrator -> defined_terms_worker")
    ]
    answer = report["result"]["answer"]
    defined_sources = [
        s for s in report["result"]["sources"]
        if any(term.lower() in s.get("excerpt", "").lower() for term in terms)
    ]
    lied = any(
        re.search(rf"{re.escape(term)}\"?\s+(?:means|is defined as|refers to)",
                  answer, re.IGNORECASE)
        for term in terms
    ) and not defined_sources
    degraded = "[Partial answer]" in report["result"]["reasoning"]
    behaviour = "lied" if lied else ("degraded" if degraded else "unknown")
    return {
        "attempts": len(attempts),
        "statuses": [e["status"] for e in attempts],
        "retried": len(attempts) > 1,
        "degraded": degraded,
        "lied": lied,
        "behaviour": behaviour,
    }


class MultiAgentRace:
    """Week 10 race: single agent vs orchestrator over Week-6 eval cases."""

    def __init__(
        self,
        *,
        agent_factory: Callable[[], MeteredLegalAgent],
        orchestrator: Orchestrator,
        retrieval: RetrievalService,
        judge: JudgeService,
        labels_path: Path,
        cost_per_token_usd: float,
        chars_per_token: int,
        artifact_dir: Path,
    ):
        self._agent_factory = agent_factory
        self._orchestrator = orchestrator
        self._retrieval = retrieval
        self._judge = judge
        self._labels_path = labels_path
        self._cost_per_token_usd = cost_per_token_usd
        self._chars_per_token = chars_per_token
        self._artifact_dir = artifact_dir

    def load_eval_cases(self) -> list[dict[str, Any]]:
        labels = {label["id"]: label for label in self._judge.load_labels()}
        return [labels[case_id] for case_id in EVAL_CASE_IDS]

    def run(self) -> dict[str, Any]:
        self._retrieval.retrieve("warm-up")
        rows = []
        for case in self.load_eval_cases():
            single = self._agent_factory().run(case["question"])
            multi = self._orchestrator.run(case["question"])
            rows.append({
                "case": case, "single": single, "multi": multi,
                "single_judge": self._judge.judge_answer(case["question"], single["result"]),
                "multi_judge": self._judge.judge_answer(case["question"], multi["result"]),
            })

        failure_case = next(row for row in rows if row["case"]["id"] == FAILURE_CASE_ID)
        failure = self._orchestrator.run(
            failure_case["case"]["question"], fail_worker="defined_terms",
        )
        terms = next(
            step["arguments"]["terms"] for step in failure["steps"]
            if step["action"] == "defined_terms_worker"
        )

        single_summary = summarize_race(
            [r["single"] for r in rows], [r["single_judge"] for r in rows],
            self._cost_per_token_usd,
        )
        multi_summary = summarize_race(
            [r["multi"] for r in rows], [r["multi_judge"] for r in rows],
            self._cost_per_token_usd,
        )
        shares = hop_shares([r["multi"] for r in rows])
        return {
            "labels_sha256": sha256(self._labels_path.read_bytes()).hexdigest(),
            "case_ids": list(EVAL_CASE_IDS),
            "rows": rows,
            "single_agent": single_summary,
            "orchestrator": multi_summary,
            "multiplier": (
                multi_summary["total_tokens"] / single_summary["total_tokens"]
                if single_summary["total_tokens"] else float("inf")
            ),
            "hop_shares": shares,
            "single_hop_shares": hop_shares([r["single"] for r in rows]),
            "failure": {
                "case": failure_case["case"],
                "terms": terms,
                "report": failure,
                "clean_report": failure_case["multi"],
                "judge": self._judge.judge_answer(
                    failure_case["case"]["question"], failure["result"]
                ),
                "classification": classify_failure(failure, terms),
            },
        }

    # ── Artifact writers ─────────────────────────────────────────────
    def write_artifacts(self) -> dict[str, Any]:
        race = self.run()
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        dominant = race["hop_shares"][0]
        (self._artifact_dir / "race_table.md").write_text(
            self._race_table(race), encoding="utf-8",
        )
        (self._artifact_dir / "handoffs.log").write_text(
            self._handoffs_log(race), encoding="utf-8",
        )
        (self._artifact_dir / "multiplier.txt").write_text(
            f"Context re-send multiplier: {race['multiplier']:.1f}x "
            f"({race['orchestrator']['total_tokens']} / "
            f"{race['single_agent']['total_tokens']} tokens); "
            f"dominant hand-off: {dominant['hop']}, {dominant['share']:.0%} of tokens.\n",
            encoding="utf-8",
        )
        (self._artifact_dir / "failure_case.md").write_text(
            self._failure_case(race), encoding="utf-8",
        )
        return race

    def _race_table(self, race: dict[str, Any]) -> str:
        single, multi = race["single_agent"], race["orchestrator"]
        dominant = race["hop_shares"][0]
        lines = [
            "# Race — single agent vs orchestrator",
            "",
            f"Cases: `eval/labels_25.json` ids {race['case_ids'][0]}"
            f"–{race['case_ids'][-1]} (sha256 `{race['labels_sha256'][:12]}`), unchanged.",
            "Judge: race_judge.py, same function for both arms.",
            f"Tokens: serialised payload / {self._chars_per_token} chars, same estimator.",
            f"Cost: tokens x ${self._cost_per_token_usd:.6f}.",
            "",
            "| metric | single_agent | orchestrator |",
            "|---|---:|---:|",
            f"| pass rate | {single['pass_rate']:.0%} "
            f"({round(single['pass_rate'] * 10)}/10) "
            f"| {multi['pass_rate']:.0%} ({round(multi['pass_rate'] * 10)}/10) |",
            f"| p50 latency (s) | {single['p50_latency_seconds']:.3f} "
            f"| {multi['p50_latency_seconds']:.3f} |",
            f"| p99 latency (s) | {single['p99_latency_seconds']:.3f} "
            f"| {multi['p99_latency_seconds']:.3f} |",
            f"| total tokens | {single['total_tokens']:,} | {multi['total_tokens']:,} |",
            f"| cost per question (USD) | {single['cost_per_question_usd']:.6f} "
            f"| {multi['cost_per_question_usd']:.6f} |",
            "",
            f"**Context re-send multiplier: {race['multiplier']:.1f}x** "
            f"({multi['total_tokens']:,} / {single['total_tokens']:,}). "
            f"Largest share: `{dominant['hop']}`, {dominant['share']:.0%} of all orchestrator tokens.",
            "",
            "## Orchestrator tokens by hand-off",
            "",
            "| hand-off | tokens | share |",
            "|---|---:|---:|",
            *[f"| {i['hop']} | {i['tokens']:,} | {i['share']:.1%} |" for i in race["hop_shares"]],
        ]
        return "\n".join(lines) + "\n"

    def _handoffs_log(self, race: dict[str, Any]) -> str:
        lines = ["# arm\tcase\thop\tinput_tokens\toutput_tokens\ttokens\tstatus\tattempt"]
        runs = [
            (arm, f"{row['case']['id']:02d}", row[key])
            for row in race["rows"]
            for arm, key in (("single_agent", "single"), ("orchestrator", "multi"))
        ]
        runs.append((
            "orchestrator", f"{race['failure']['case']['id']:02d}-fault", race["failure"]["report"],
        ))
        for arm, case, report in runs:
            for entry in report["handoffs"]:
                lines.append(
                    f"{arm}\t{case}\t{entry['hop']}\t{entry['input_tokens']}\t"
                    f"{entry['output_tokens']}\t{entry['tokens']}\t"
                    f"{entry['status']}\t{entry['attempt']}"
                )
        return "\n".join(lines) + "\n"

    def _failure_case(self, race: dict[str, Any]) -> str:
        failure = race["failure"]
        cls, report, clean = failure["classification"], failure["report"], failure["clean_report"]
        one_line = {
            "degraded": (
                f"retried {cls['attempts'] - 1}x, then degraded to a partial answer."
                if cls["retried"] else
                "degraded to a partial answer without retrying."
            ),
            "lied": "LIED: interpreted a defined term it never looked up.",
        }.get(cls["behaviour"], "did not match retry/degrade/lie; inspect evidence below.")
        return "\n".join([
            "# Worker failure case",
            "",
            f"Case: id {failure['case']['id']}: \"{failure['case']['question']}\" "
            f"(human label: {failure['case']['human_label']})",
            f"Injected: defined_terms_worker raises HTTP 500. Terms: {failure['terms']}.",
            "",
            f"**Actual behaviour: {one_line}**",
            "",
            f"- attempts: {cls['attempts']} (statuses {cls['statuses']}); "
            f"retried={cls['retried']}, degraded={cls['degraded']}, lied={cls['lied']}",
            f"- judge: {'PASS' if failure['judge']['passed'] else 'fail'} "
            f"(checks {failure['judge']['checks']})",
            f"- tokens: faulted {report['token_count']:,} vs clean {clean['token_count']:,}; "
            f"latency {report['elapsed_seconds']:.3f}s vs {clean['elapsed_seconds']:.3f}s",
            "",
            "## Final answer (faulted run)",
            "",
            "```json",
            json.dumps(report["result"], indent=2, ensure_ascii=False),
            "```",
        ])
