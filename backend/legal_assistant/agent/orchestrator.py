"""Orchestrator: decompose → clause worker + defined-terms worker → synthesise.

Every hop is metered as the payload a model call at that hop would receive (input) and
emit (output), using one estimator shared with the single-agent arm of the race.
"""
import json
import math
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .. import config
from ..generation.generator import RETRIEVE_TOOL, SYSTEM_PROMPT, ExtractiveGenerator, _chunks_payload
from ..generation.pipeline import detect_metadata_filter
from ..generation.schema import validate_response
from ..retrieval.retrieval import retrieve
from ..safety.agent_failure_modes import detect_prompt_injection
from ..safety.guardrails import screen_query

ORCHESTRATOR_PROMPT = """ROLE
You route one legal question to narrow workers; you never answer it yourself.
Return JSON: {"subtasks": ["clause", "defined_terms"?], "terms": [...], "governing_version": "original|amended", "effective_date": "YYYY-MM-DD"}.
Send the clause worker only the question, governing version and effective date. Send the defined-terms worker only the terms and version."""

DEFINED_TERMS_PROMPT = """ROLE
Return the Definitions-clause text for each requested term, for exactly one contract version.
Quote verbatim. If a term is not defined in that version, list it under not_found. Never paraphrase or infer a meaning."""

SYNTHESIZER_PROMPT = """ROLE
Merge worker outputs into one answer in the fixed response schema (answer, reasoning, sources, confidence, out_of_scope).
Use only worker outputs. If a worker failed, say which fact is unverified. Never state the meaning of a term the defined-terms worker did not return."""

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

_TERM_PATTERNS = (
    re.compile(r'"([^"]+)"'),
    re.compile(r"\bwhat (?:does|do) (?:the )?([\w\s-]+?) mean\b", re.IGNORECASE),
    re.compile(r"\bwhat(?: is|'s) (?:a |an |the )?([\w\s'-]+?)(?:\s+(?:under|in|of)\b|\?|$)", re.IGNORECASE),
    re.compile(r"\bdefin(?:ition of|e)\s+([\w\s-]+?)(?:\?|$)", re.IGNORECASE),
)
_DEFINED_TERM = re.compile(r'\("([A-Z][^"]+)"\)')
_EFFECTIVE_DATE = re.compile(r"effective as of ((?:19|20)\d{2}-\d{2}-\d{2})", re.IGNORECASE)


def estimate_tokens(value: Any) -> int:
    """Shared token estimator for both race arms: serialised characters / CHARS_PER_TOKEN."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return max(1, math.ceil(len(text) / config.CHARS_PER_TOKEN))


@dataclass
class HandoffLog:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, hop, input_payload, output_payload, status=200, attempt=1):
        input_tokens, output_tokens = estimate_tokens(input_payload), estimate_tokens(output_payload)
        self.entries.append({
            "hop": hop,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens": input_tokens + output_tokens,
            "status": status,
            "attempt": attempt,
        })

    @property
    def total_tokens(self):
        return sum(entry["tokens"] for entry in self.entries)


class WorkerError(Exception):
    def __init__(self, worker, status=500):
        super().__init__(f"{worker} returned HTTP {status}")
        self.worker, self.status = worker, status


def extract_terms(query: str) -> list[str]:
    """Terms the question asks the meaning of; an empty list means no defined-terms subtask."""
    for pattern in _TERM_PATTERNS:
        match = pattern.search(query)
        if match:
            return [match.group(1).strip()]
    return []


@lru_cache(maxsize=1)
def governing_effective_date() -> str:
    """Latest 'effective as of' date in the corpus — the date the clause worker must answer as of."""
    dates = [date for path in config.DOCS_DIR.glob("*.md") for date in _EFFECTIVE_DATE.findall(path.read_text(encoding="utf-8"))]
    return max(dates, default="")


def plan(query: str) -> dict[str, Any]:
    terms = extract_terms(query)
    return {
        "subtasks": ["clause", "defined_terms"] if terms else ["clause"],
        "terms": terms,
        "governing_version": "amended",
        "effective_date": governing_effective_date(),
    }


def clause_worker(brief: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Narrow worker: one tool (retrieve), one retrieval, grounded extractive answer."""
    query = brief["question"]
    allowed, reason = screen_query(query)
    if not allowed:
        answer = config.GUARDRAIL_ANSWER if reason == "injection" else config.NO_DRAFTING_ANSWER
        return {
            "answer": answer,
            "reasoning": f"The question was rejected by the input guardrails before retrieval: {reason}.",
            "sources": [],
            "confidence": "high",
            "out_of_scope": True,
        }, []
    where = detect_metadata_filter(query)
    chunks = retrieve(query, where=where)
    if any(detect_prompt_injection(chunk.text) for chunk in chunks):
        return {
            "answer": config.GUARDRAIL_ANSWER,
            "reasoning": "A retrieved document contained instruction-like content and was excluded from answer generation.",
            "sources": [],
            "confidence": "high",
            "out_of_scope": True,
        }, _chunks_payload(chunks)
    return ExtractiveGenerator().generate(query, where=where, chunks=chunks), _chunks_payload(chunks)


def defined_terms_worker(request: dict[str, Any], fail: bool = False) -> dict[str, Any]:
    """Narrow worker: one tool (get_definitions) over parenthetical definitions in the chosen version."""
    if fail:
        raise WorkerError("defined_terms_worker")
    from ..stores.vector_store import get_collection

    stored = get_collection().get(include=["documents", "metadatas"])
    definitions, not_found = [], []
    for term in request["terms"]:
        hit = None
        for chunk_id, text, meta in zip(stored["ids"], stored["documents"], stored["metadatas"]):
            if request["version"] == "original" and meta["document_type"] == "amendment":
                continue
            for sentence in re.split(r"(?<=[.;])\s+", text):
                if any(found.lower() == term.lower() for found in _DEFINED_TERM.findall(sentence)):
                    hit = {"term": term, "document": meta["document"], "chunk_id": chunk_id, "excerpt": sentence.strip()}
                    break
            if hit:
                break
        if hit:
            definitions.append(hit)
        else:
            not_found.append(term)
    return {"status": 200, "version": request["version"], "definitions": definitions, "not_found": not_found}


def synthesize(query, clause, definitions, terms):
    """Merge worker outputs; on a failed defined-terms worker, degrade instead of inventing a meaning."""
    result = dict(clause)
    if definitions.get("status") != 200:
        note = f'The meaning of "{", ".join(terms)}" could not be verified: the defined-terms worker returned HTTP {definitions.get("status")}, so no definition is given.'
        result["reasoning"] = f'{clause.get("reasoning", "")} [Partial answer] {note}'
        if not clause.get("out_of_scope"):
            result["answer"] = f'{clause["answer"]} {note}'
            result["confidence"] = "low"
        return result
    if not definitions["definitions"]:
        result["reasoning"] = f'{clause.get("reasoning", "")} No Definitions-clause entry for: {", ".join(definitions["not_found"])}.'
        return result
    quoted = " ".join(f'"{item["term"]}" is defined in {item["document"]}: "{item["excerpt"]}"' for item in definitions["definitions"])
    grounded_clause = "" if clause.get("out_of_scope") else f' {clause["answer"]}'
    return {
        "answer": f"{quoted}{grounded_clause}",
        "reasoning": f'Defined-terms worker resolved {len(definitions["definitions"])} term(s); clause worker supplied the clause text. {clause.get("reasoning", "")}'.strip(),
        "sources": [{k: item[k] for k in ("document", "chunk_id", "excerpt")} for item in definitions["definitions"]] + list(clause.get("sources", [])),
        "confidence": clause.get("confidence", "medium") if not clause.get("out_of_scope") else "medium",
        "out_of_scope": False,
    }


def run_orchestrator(query: str, fail_worker: str | None = None) -> dict[str, Any]:
    """Run the orchestrator; ``fail_worker="defined_terms"`` injects an HTTP 500 from that worker."""
    started = time.perf_counter()
    log = HandoffLog()

    task_plan = plan(query)
    log.record("user -> orchestrator (plan)", [ORCHESTRATOR_PROMPT, query], task_plan)
    steps = [{"step": 1, "action": "plan", "reason": "Decompose the question into worker subtasks.", "arguments": {}}]

    brief = {"question": query, "governing_version": task_plan["governing_version"], "effective_date": task_plan["effective_date"]}
    clause, chunks = clause_worker(brief)
    log.record("orchestrator -> clause_worker (brief + retrieved chunks)", [SYSTEM_PROMPT, RETRIEVE_TOOL, brief, chunks], clause)
    steps.append({"step": 2, "action": "clause_worker", "reason": "Retrieve and quote the governing clause.", "arguments": brief})

    result = clause
    if "defined_terms" in task_plan["subtasks"]:
        request = {"terms": task_plan["terms"], "version": task_plan["governing_version"]}
        definitions = {"status": 500}
        for attempt in range(1, config.ORCHESTRATOR_WORKER_RETRIES + 2):
            try:
                definitions = defined_terms_worker(request, fail=fail_worker == "defined_terms")
                log.record("orchestrator -> defined_terms_worker", [DEFINED_TERMS_PROMPT, GET_DEFINITIONS_TOOL, request], definitions, attempt=attempt)
                break
            except WorkerError as error:
                definitions = {"status": error.status, "error": str(error)}
                log.record("orchestrator -> defined_terms_worker", [DEFINED_TERMS_PROMPT, GET_DEFINITIONS_TOOL, request], definitions, status=error.status, attempt=attempt)
        steps.append({"step": 3, "action": "defined_terms_worker", "reason": "Resolve the defined terms the question asks about.", "arguments": request})

        result = synthesize(query, clause, definitions, task_plan["terms"])
        log.record("workers -> synthesizer (clause answer + definitions)", [SYNTHESIZER_PROMPT, query, clause, definitions], result)
        steps.append({"step": 4, "action": "synthesizer", "reason": "Merge both worker outputs into one answer.", "arguments": {}})

    schema_errors = validate_response(result)
    total_tokens = log.total_tokens
    return {
        "strategy": "orchestrator",
        "result": result,
        "steps": steps,
        "tool_calls": len(steps),
        "handoffs": log.entries,
        "token_count": total_tokens,
        "estimated_cost_usd": round(total_tokens * config.AGENT_COST_PER_TOKEN_USD, 8),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "completed": not schema_errors,
        "schema_errors": schema_errors,
        "stop_reason": "answer_ready",
    }
