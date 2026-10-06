"""Orchestrator: plan → clause worker + defined-terms worker → synthesise, all metered per hop."""
from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from legal_rag.application.ports import VectorStore
from legal_rag.application.workflows.generation import (
    RETRIEVE_TOOL,
    SYSTEM_PROMPT,
    ExtractiveGenerator,
    chunks_payload,
)
from legal_rag.application.workflows.retrieval import RetrievalService
from legal_rag.domain.policies import detect_prompt_injection, screen_query
from legal_rag.domain.response_schema import validate_response
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)

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

GET_DEFINITIONS_TOOL: dict[str, Any] = {
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


class WorkerError(Exception):
    def __init__(self, worker: str, status: int = 500):
        super().__init__(f"{worker} returned HTTP {status}")
        self.worker, self.status = worker, status


def estimate_tokens(value: Any, chars_per_token: int = 4) -> int:
    """Shared estimator: serialised chars / chars_per_token."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return max(1, math.ceil(len(text) / chars_per_token))


@dataclass
class HandoffLog:
    entries: list[dict[str, Any]] = field(default_factory=list)
    chars_per_token: int = 4

    def record(
        self, hop: str, input_payload: Any, output_payload: Any,
        status: int = 200, attempt: int = 1,
    ) -> None:
        i_tokens = estimate_tokens(input_payload, self.chars_per_token)
        o_tokens = estimate_tokens(output_payload, self.chars_per_token)
        self.entries.append({
            "hop": hop,
            "input_tokens": i_tokens,
            "output_tokens": o_tokens,
            "tokens": i_tokens + o_tokens,
            "status": status,
            "attempt": attempt,
        })

    @property
    def total_tokens(self) -> int:
        return sum(entry["tokens"] for entry in self.entries)


def extract_terms(query: str) -> list[str]:
    """Terms the question asks the meaning of; empty means no defined-terms subtask."""
    for pattern in _TERM_PATTERNS:
        match = pattern.search(query)
        if match:
            return [match.group(1).strip()]
    return []


def _governing_effective_date(docs_dir: str | Path) -> str:
    """Latest 'effective as of' date found in the corpus.

    Not cached: corpus files can be added, replaced, or removed at any time
    (re-ingestion, tests using tmp dirs). Cost is a handful of small file reads
    — acceptable given how rarely the orchestrator is on the hot path.
    """
    path = Path(docs_dir)
    if not path.exists():
        return ""
    dates = [
        d for p in path.glob("*.md")
        for d in _EFFECTIVE_DATE.findall(p.read_text(encoding="utf-8"))
    ]
    return max(dates, default="")


@dataclass
class OrchestratorSettings:
    worker_retries: int
    chars_per_token: int
    cost_per_token_usd: float
    guardrail_answer: str
    no_drafting_answer: str
    docs_dir: Path


class Orchestrator:
    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        vector_store: VectorStore,
        extractive_generator: ExtractiveGenerator,
        settings: OrchestratorSettings,
    ):
        self._retrieval = retrieval
        self._vector_store = vector_store
        self._extractive = extractive_generator
        self._settings = settings

    def plan(self, query: str) -> dict[str, Any]:
        terms = extract_terms(query)
        return {
            "subtasks": ["clause", "defined_terms"] if terms else ["clause"],
            "terms": terms,
            "governing_version": "amended",
            "effective_date": _governing_effective_date(str(self._settings.docs_dir)),
        }

    def clause_worker(
        self, brief: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        query = brief["question"]
        allowed, reason = screen_query(query)
        if not allowed:
            answer = (
                self._settings.guardrail_answer
                if reason == "injection" else self._settings.no_drafting_answer
            )
            return {
                "answer": answer,
                "reasoning": (
                    "The question was rejected by the input guardrails before "
                    f"retrieval: {reason}."
                ),
                "sources": [], "confidence": "high", "out_of_scope": True,
            }, []
        where = self._retrieval.detect_metadata_filter(query)
        chunks = self._retrieval.retrieve(query, where=where)
        if any(detect_prompt_injection(c.text) for c in chunks):
            return {
                "answer": self._settings.guardrail_answer,
                "reasoning": ("A retrieved document contained instruction-like content "
                              "and was excluded from answer generation."),
                "sources": [], "confidence": "high", "out_of_scope": True,
            }, chunks_payload(chunks)
        return self._extractive.generate(query, where=where, chunks=chunks), chunks_payload(chunks)

    def defined_terms_worker(
        self, request: dict[str, Any], *, fail: bool = False
    ) -> dict[str, Any]:
        if fail:
            raise WorkerError("defined_terms_worker")
        stored = self._vector_store.get_all()
        definitions, not_found = [], []
        for term in request["terms"]:
            hit = None
            for chunk_id, text, meta in zip(
                stored["ids"], stored["documents"], stored["metadatas"], strict=False
            ):
                doc_type = (meta or {}).get("document_type", "contract")
                if request["version"] == "original" and doc_type == "amendment":
                    continue
                for sentence in re.split(r"(?<=[.;])\s+", text):
                    if any(found.lower() == term.lower()
                           for found in _DEFINED_TERM.findall(sentence)):
                        hit = {
                            "term": term,
                            "document": (meta or {}).get("document", "unknown"),
                            "chunk_id": chunk_id,
                            "excerpt": sentence.strip(),
                        }
                        break
                if hit:
                    break
            if hit:
                definitions.append(hit)
            else:
                not_found.append(term)
        return {
            "status": 200, "version": request["version"],
            "definitions": definitions, "not_found": not_found,
        }

    def synthesize(
        self, query: str, clause: dict[str, Any],
        definitions: dict[str, Any], terms: list[str],
    ) -> dict[str, Any]:
        # If the clause worker was blocked (guardrail / out-of-scope), preserve
        # that verdict unchanged — never merge over a refusal.
        if clause.get("out_of_scope"):
            return dict(clause)
        result = dict(clause)
        if definitions.get("status") != 200:
            note = (
                f'The meaning of "{", ".join(terms)}" could not be verified: the defined-terms '
                f'worker returned HTTP {definitions.get("status")}, so no definition is given.'
            )
            result["reasoning"] = f'{clause.get("reasoning", "")} [Partial answer] {note}'
            result["answer"] = f'{clause["answer"]} {note}'
            result["confidence"] = "low"
            return result
        if not definitions["definitions"]:
            result["reasoning"] = (
                f'{clause.get("reasoning", "")} No Definitions-clause entry for: '
                f'{", ".join(definitions["not_found"])}.'
            )
            return result
        quoted = " ".join(
            f'"{item["term"]}" is defined in {item["document"]}: "{item["excerpt"]}"'
            for item in definitions["definitions"]
        )
        return {
            "answer": f"{quoted} {clause['answer']}",
            "reasoning": (
                f'Defined-terms worker resolved {len(definitions["definitions"])} term(s); '
                f'clause worker supplied the clause text. {clause.get("reasoning", "")}'
            ).strip(),
            "sources": [
                {k: item[k] for k in ("document", "chunk_id", "excerpt")}
                for item in definitions["definitions"]
            ] + list(clause.get("sources", [])),
            "confidence": clause.get("confidence", "medium"),
            "out_of_scope": False,
        }

    def run(self, query: str, *, fail_worker: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        log_ = HandoffLog(chars_per_token=self._settings.chars_per_token)

        task_plan = self.plan(query)
        log_.record("user -> orchestrator (plan)", [ORCHESTRATOR_PROMPT, query], task_plan)
        steps = [{"step": 1, "action": "plan",
                  "reason": "Decompose the question into worker subtasks.", "arguments": {}}]

        brief = {
            "question": query,
            "governing_version": task_plan["governing_version"],
            "effective_date": task_plan["effective_date"],
        }
        clause, chunks = self.clause_worker(brief)
        log_.record(
            "orchestrator -> clause_worker (brief + retrieved chunks)",
            [SYSTEM_PROMPT, RETRIEVE_TOOL, brief, chunks], clause,
        )
        steps.append({"step": 2, "action": "clause_worker",
                      "reason": "Retrieve and quote the governing clause.", "arguments": brief})

        result = clause
        if "defined_terms" in task_plan["subtasks"]:
            request = {"terms": task_plan["terms"], "version": task_plan["governing_version"]}
            definitions: dict[str, Any] = {"status": 500}
            for attempt in range(1, self._settings.worker_retries + 2):
                try:
                    definitions = self.defined_terms_worker(
                        request, fail=fail_worker == "defined_terms"
                    )
                    log_.record(
                        "orchestrator -> defined_terms_worker",
                        [DEFINED_TERMS_PROMPT, GET_DEFINITIONS_TOOL, request],
                        definitions, attempt=attempt,
                    )
                    break
                except WorkerError as error:
                    definitions = {"status": error.status, "error": str(error)}
                    log_.record(
                        "orchestrator -> defined_terms_worker",
                        [DEFINED_TERMS_PROMPT, GET_DEFINITIONS_TOOL, request],
                        definitions, status=error.status, attempt=attempt,
                    )
            steps.append({"step": 3, "action": "defined_terms_worker",
                          "reason": "Resolve the defined terms the question asks about.",
                          "arguments": request})

            result = self.synthesize(query, clause, definitions, task_plan["terms"])
            log_.record(
                "workers -> synthesizer (clause answer + definitions)",
                [SYNTHESIZER_PROMPT, query, clause, definitions], result,
            )
            steps.append({"step": 4, "action": "synthesizer",
                          "reason": "Merge both worker outputs into one answer.", "arguments": {}})

        schema_errors = validate_response(result)
        total_tokens = log_.total_tokens
        return {
            "strategy": "orchestrator",
            "result": result,
            "steps": steps,
            "tool_calls": len(steps),
            "handoffs": log_.entries,
            "token_count": total_tokens,
            "estimated_cost_usd": round(total_tokens * self._settings.cost_per_token_usd, 8),
            "elapsed_seconds": round(time.perf_counter() - started, 4),
            "completed": not schema_errors,
            "schema_errors": schema_errors,
            "stop_reason": "answer_ready",
        }
