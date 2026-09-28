"""Race the single LegalAgent against the orchestrator on the labelled eval cases."""
import json
import math
import re
import statistics
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from .. import config
from ..evaluation.judge_validation import LABELS_PATH, load_labels
from ..evaluation.race_judge import judge_answer
from ..generation.generator import RETRIEVE_TOOL, SYSTEM_PROMPT
from ..retrieval.retrieval import retrieve
from .legal_agent import LegalAgent
from .orchestrator import GET_DEFINITIONS_TOOL, HandoffLog, run_orchestrator

EVAL_CASE_IDS = tuple(range(1, 11))
FAILURE_CASE_ID = 10
ARTIFACT_DIR = config.PROJECT_ROOT.parent / "eval" / "week10"

SINGLE_AGENT_TOOLS = [
    RETRIEVE_TOOL,
    {"type": "function", "function": {"name": "check_amendments", "description": "Compare original and amendment passages already retrieved.", "parameters": {"type": "object", "properties": {}}}},
    GET_DEFINITIONS_TOOL,
    {"type": "function", "function": {"name": "answer", "description": "Produce the grounded answer from the observations.", "parameters": {"type": "object", "properties": {}}}},
]


class MeteredLegalAgent(LegalAgent):
    """The unchanged single agent, metered as one model turn per step that re-reads its transcript."""

    def run(self, query):
        self.log = HandoffLog()
        report = super().run(query)
        report["handoffs"] = self.log.entries
        report["token_count"] = self.log.total_tokens
        report["estimated_cost_usd"] = round(self.log.total_tokens * config.AGENT_COST_PER_TOKEN_USD, 8)
        return report

    def _step(self, state, tool_name, reason, arguments=None):
        transcript = [SYSTEM_PROMPT, SINGLE_AGENT_TOOLS, state.query, list(state.observations.values())]
        steps_before = len(state.steps)
        super()._step(state, tool_name, reason, arguments)
        if len(state.steps) > steps_before:
            output = state.observations[tool_name] if tool_name == "answer" else {"tool": tool_name, "arguments": arguments or {}}
            self.log.record(f"single_agent turn -> {tool_name} (transcript re-read)", transcript, output)


def load_eval_cases() -> list[dict[str, Any]]:
    labels = {label["id"]: label for label in load_labels()}
    return [labels[case_id] for case_id in EVAL_CASE_IDS]


def _nearest_rank(values, percentile):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile / 100 * len(ordered)) - 1)]


def summarize(reports, verdicts) -> dict[str, Any]:
    latencies = [report["elapsed_seconds"] for report in reports]
    total_tokens = sum(report["token_count"] for report in reports)
    return {
        "pass_rate": sum(verdict["passed"] for verdict in verdicts) / len(reports),
        "p50_latency_seconds": statistics.median(latencies),
        "p99_latency_seconds": _nearest_rank(latencies, 99),
        "total_tokens": total_tokens,
        "cost_per_question_usd": total_tokens * config.AGENT_COST_PER_TOKEN_USD / len(reports),
    }


def hop_shares(reports) -> list[dict[str, Any]]:
    totals = defaultdict(int)
    for report in reports:
        for entry in report["handoffs"]:
            totals[entry["hop"]] += entry["tokens"]
    grand_total = sum(totals.values())
    return sorted(
        ({"hop": hop, "tokens": tokens, "share": tokens / grand_total} for hop, tokens in totals.items()),
        key=lambda item: item["tokens"],
        reverse=True,
    )


def classify_failure(report, terms) -> dict[str, Any]:
    """Name what the orchestrator did after the injected 500: retried, degraded, or lied."""
    attempts = [entry for entry in report["handoffs"] if entry["hop"].startswith("orchestrator -> defined_terms_worker")]
    answer = report["result"]["answer"]
    defined_sources = [source for source in report["result"]["sources"] if any(term.lower() in source["excerpt"].lower() for term in terms)]
    lied = any(
        re.search(rf"{re.escape(term)}\"?\s+(?:means|is defined as|refers to)", answer, re.IGNORECASE) for term in terms
    ) and not defined_sources
    degraded = "[Partial answer]" in report["result"]["reasoning"]
    behaviour = "lied" if lied else ("degraded" if degraded else "unknown")
    return {
        "attempts": len(attempts),
        "statuses": [entry["status"] for entry in attempts],
        "retried": len(attempts) > 1,
        "degraded": degraded,
        "lied": lied,
        "behaviour": behaviour,
    }


def run_multi_agent_race() -> dict[str, Any]:
    retrieve("warm-up")
    rows = []
    for case in load_eval_cases():
        single = MeteredLegalAgent().run(case["question"])
        multi = run_orchestrator(case["question"])
        rows.append({
            "case": case,
            "single": single,
            "multi": multi,
            "single_judge": judge_answer(case["question"], single["result"]),
            "multi_judge": judge_answer(case["question"], multi["result"]),
        })

    failure_case = next(row for row in rows if row["case"]["id"] == FAILURE_CASE_ID)
    failure = run_orchestrator(failure_case["case"]["question"], fail_worker="defined_terms")
    terms = next(step["arguments"]["terms"] for step in failure["steps"] if step["action"] == "defined_terms_worker")

    single_summary = summarize([row["single"] for row in rows], [row["single_judge"] for row in rows])
    multi_summary = summarize([row["multi"] for row in rows], [row["multi_judge"] for row in rows])
    shares = hop_shares([row["multi"] for row in rows])
    return {
        "labels_sha256": sha256(LABELS_PATH.read_bytes()).hexdigest(),
        "case_ids": list(EVAL_CASE_IDS),
        "rows": rows,
        "single_agent": single_summary,
        "orchestrator": multi_summary,
        "multiplier": multi_summary["total_tokens"] / single_summary["total_tokens"],
        "hop_shares": shares,
        "single_hop_shares": hop_shares([row["single"] for row in rows]),
        "failure": {
            "case": failure_case["case"],
            "terms": terms,
            "report": failure,
            "clean_report": failure_case["multi"],
            "judge": judge_answer(failure_case["case"]["question"], failure["result"]),
            "classification": classify_failure(failure, terms),
        },
    }


def _race_table(race) -> str:
    single, multi = race["single_agent"], race["orchestrator"]
    dominant = race["hop_shares"][0]
    lines = [
        "# Race — single agent vs orchestrator",
        "",
        f"Cases: `eval/labels_25.json` ids {race['case_ids'][0]}–{race['case_ids'][-1]} (sha256 `{race['labels_sha256'][:12]}`), unchanged.",
        "Judge: `legal_assistant/evaluation/race_judge.py`, the same function for both arms.",
        f"Tokens: serialised payload per model call / {config.CHARS_PER_TOKEN} chars, same estimator both arms. "
        f"Cost: tokens x ${config.AGENT_COST_PER_TOKEN_USD:.6f} (`config.AGENT_COST_PER_TOKEN_USD`).",
        "Latency: warm models, arms interleaved per case, CPU. p99 is nearest-rank over 10 runs, so it is the slowest case.",
        "",
        "| metric | single_agent | orchestrator |",
        "|---|---:|---:|",
        f"| pass rate | {single['pass_rate']:.0%} ({round(single['pass_rate'] * 10)}/10) | {multi['pass_rate']:.0%} ({round(multi['pass_rate'] * 10)}/10) |",
        f"| p50 latency (s) | {single['p50_latency_seconds']:.3f} | {multi['p50_latency_seconds']:.3f} |",
        f"| p99 latency (s) | {single['p99_latency_seconds']:.3f} | {multi['p99_latency_seconds']:.3f} |",
        f"| total tokens | {single['total_tokens']:,} | {multi['total_tokens']:,} |",
        f"| cost per question (USD) | {single['cost_per_question_usd']:.6f} | {multi['cost_per_question_usd']:.6f} |",
        "",
        f"**Context re-send multiplier: {race['multiplier']:.1f}x** "
        f"({multi['total_tokens']:,} / {single['total_tokens']:,}). "
        f"Largest share: `{dominant['hop']}`, {dominant['share']:.0%} of all orchestrator tokens.",
        "",
        "## Orchestrator tokens by hand-off",
        "",
        "| hand-off | tokens | share |",
        "|---|---:|---:|",
        *[f"| {item['hop']} | {item['tokens']:,} | {item['share']:.1%} |" for item in race["hop_shares"]],
        "",
        "## Single-agent tokens by turn",
        "",
        "| turn | tokens | share |",
        "|---|---:|---:|",
        *[f"| {item['hop']} | {item['tokens']:,} | {item['share']:.1%} |" for item in race["single_hop_shares"]],
        "",
        "## Per case",
        "",
        "| id | question | human | single pass | orch pass | single tok | orch tok | single s | orch s | orch subtasks |",
        "|---:|---|:-:|:-:|:-:|---:|---:|---:|---:|---|",
    ]
    for row in race["rows"]:
        subtasks = "+".join(step["action"] for step in row["multi"]["steps"] if step["action"] != "plan")
        lines.append(
            f"| {row['case']['id']} | {row['case']['question']} | {'T' if row['case']['human_label'] else 'F'} "
            f"| {'PASS' if row['single_judge']['passed'] else 'fail'} | {'PASS' if row['multi_judge']['passed'] else 'fail'} "
            f"| {row['single']['token_count']:,} | {row['multi']['token_count']:,} "
            f"| {row['single']['elapsed_seconds']:.3f} | {row['multi']['elapsed_seconds']:.3f} | {subtasks} |"
        )
    single_agree = sum(row["single_judge"]["passed"] == row["case"]["human_label"] for row in race["rows"])
    multi_agree = sum(row["multi_judge"]["passed"] == row["case"]["human_label"] for row in race["rows"])
    lines += ["", f"Judge vs human label agreement: single {single_agree}/10, orchestrator {multi_agree}/10."]
    return "\n".join(lines) + "\n"


def _handoffs_log(race) -> str:
    lines = ["# arm\tcase\thop\tinput_tokens\toutput_tokens\ttokens\tstatus\tattempt"]
    runs = [(arm, f"{row['case']['id']:02d}", row[key]) for row in race["rows"] for arm, key in (("single_agent", "single"), ("orchestrator", "multi"))]
    runs.append(("orchestrator", f"{race['failure']['case']['id']:02d}-fault", race["failure"]["report"]))
    for arm, case, report in runs:
        for entry in report["handoffs"]:
            lines.append(f"{arm}\t{case}\t{entry['hop']}\t{entry['input_tokens']}\t{entry['output_tokens']}\t{entry['tokens']}\t{entry['status']}\t{entry['attempt']}")
    return "\n".join(lines) + "\n"


def _failure_case(race) -> str:
    failure = race["failure"]
    cls, report, clean = failure["classification"], failure["report"], failure["clean_report"]
    one_line = {
        "degraded": f"retried {cls['attempts'] - 1}x, then degraded to a partial answer and stated no meaning for the unverified term."
        if cls["retried"] else "degraded to a partial answer without retrying and stated no meaning for the unverified term.",
        "lied": "LIED: interpreted a defined term it never looked up.",
    }.get(cls["behaviour"], "did not match retry/degrade/lie; inspect the evidence below.")
    return "\n".join([
        "# Worker failure case",
        "",
        f"Case: id {failure['case']['id']}: \"{failure['case']['question']}\" (human label: {failure['case']['human_label']})",
        f"Injected: `defined_terms_worker` raises HTTP 500 on every call for this case (`run_orchestrator(..., fail_worker=\"defined_terms\")`). Terms requested: {failure['terms']}.",
        f"Retry policy under test: `config.ORCHESTRATOR_WORKER_RETRIES = {config.ORCHESTRATOR_WORKER_RETRIES}`.",
        "",
        f"**What the orchestrator actually did: {one_line}**",
        "",
        f"- defined-terms attempts: {cls['attempts']} (statuses {cls['statuses']}); retried={cls['retried']}, degraded={cls['degraded']}, lied={cls['lied']}",
        f"- judge on the faulted run: {'PASS' if failure['judge']['passed'] else 'fail'} (checks {failure['judge']['checks']})",
        f"- tokens: faulted run {report['token_count']:,} vs clean run {clean['token_count']:,}; latency {report['elapsed_seconds']:.3f}s vs {clean['elapsed_seconds']:.3f}s",
        "",
        "## Final answer returned (faulted run)",
        "",
        "```json",
        json.dumps(report["result"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Hand-offs (faulted run)",
        "",
        "| hop | tokens | status | attempt |",
        "|---|---:|---:|---:|",
        *[f"| {entry['hop']} | {entry['tokens']} | {entry['status']} | {entry['attempt']} |" for entry in report["handoffs"]],
        "",
    ])


def write_race_artifacts(out_dir: Path = ARTIFACT_DIR) -> dict[str, Any]:
    race = run_multi_agent_race()
    out_dir.mkdir(parents=True, exist_ok=True)
    dominant = race["hop_shares"][0]
    (out_dir / "race_table.md").write_text(_race_table(race), encoding="utf-8")
    (out_dir / "handoffs.log").write_text(_handoffs_log(race), encoding="utf-8")
    (out_dir / "multiplier.txt").write_text(
        f"Context re-send multiplier: {race['multiplier']:.1f}x "
        f"({race['orchestrator']['total_tokens']} / {race['single_agent']['total_tokens']} tokens); "
        f"dominant hand-off: {dominant['hop']}, {dominant['share']:.0%} of all orchestrator tokens.\n",
        encoding="utf-8",
    )
    (out_dir / "failure_case.md").write_text(_failure_case(race), encoding="utf-8")
    return race
