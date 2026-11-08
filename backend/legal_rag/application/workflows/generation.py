"""LLM answer generation with evidence validation and explicit failures."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from legal_rag.application.ports import LLMClient, VectorStore
from legal_rag.application.workflows.retrieval import RetrievalService
from legal_rag.domain.clauses import DOCUMENT_ID_RE, clause_excerpt, parse_clause_request
from legal_rag.domain.entities import RetrievedChunk
from legal_rag.domain.evidence import reference_association_errors
from legal_rag.domain.exceptions import SchemaValidationError
from legal_rag.domain.pages import page_references_supported
from legal_rag.domain.policies import (
    QUOTATION_RE,
    apply_completeness_adjustment,
    detect_prompt_injection,
)
from legal_rag.domain.response_schema import parse_json_response, validate_response
from legal_rag.infrastructure.observability.logging import get_logger
from legal_rag.infrastructure.prompts import RETRIEVE_TOOL
from legal_rag.infrastructure.prompts.registry import get as get_prompt

log = get_logger(__name__)

SYSTEM_PROMPT = get_prompt("qa.system").text


def _clause_refs(text: str) -> list[str]:
    return sorted(set(re.findall(r"\bsections?\s+(\d+(?:\.\d+)*)", text, re.IGNORECASE)))


@dataclass
class GenerationSettings:
    min_relevant_score: float
    out_of_scope_answer: str
    llm_temperature: float
    max_tool_rounds: int = 4


class Generator(Protocol):
    def generate(
        self,
        query: str,
        *,
        where: dict[str, Any] | None = None,
        chunks: list[RetrievedChunk] | None = None,
    ) -> dict[str, Any]: ...


def chunks_payload(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": c.chunk_id,
            "document": c.document,
            "heading": c.heading,
            "excerpt": c.text,
            "metadata": {
                key: c.metadata[key]
                for key in (
                    "source_doc",
                    "document_name",
                    "clause_ref",
                    "page_number",
                    "document_version",
                    "amends",
                    "effective_date",
                    "status",
                )
                if c.metadata.get(key) is not None
            },
        }
        for c in chunks
    ]


def _safe_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    # Do not rewrite legal passages: exclude detected instruction-bearing
    # evidence at the shared boundary for both initial and tool retrieval.
    return [
        chunk
        for chunk in chunks
        if not detect_prompt_injection(
            f"{chunk.heading}\n{chunk.text}\n{json.dumps(chunk.metadata)}"
        )
    ]


def _out_of_scope(out_of_scope_answer: str) -> dict[str, Any]:
    return {
        "answer": out_of_scope_answer,
        "reasoning": (
            "No retrieved chunk scored above the relevance threshold, so the "
            "knowledge base contains no grounded answer for this question."
        ),
        "sources": [],
        "confidence": "low",
        "out_of_scope": True,
    }


class LLMGenerator:
    """LLM-backed generator with tool calling, JSON validation, and one retry."""

    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        vector_store: VectorStore,
        llm: LLMClient,
        settings: GenerationSettings,
    ):
        self._retrieval = retrieval
        self._vector_store = vector_store
        self._llm = llm
        self._settings = settings

    def generate(
        self,
        query: str,
        *,
        where: dict[str, Any] | None = None,
        chunks: list[RetrievedChunk] | None = None,
    ) -> dict[str, Any]:
        documents = {match.group().upper() for match in DOCUMENT_ID_RE.finditer(query)}
        if len(documents) == 1:
            document = next(iter(documents))
            if where and where.get("source_doc", document) != document:
                return _out_of_scope(self._settings.out_of_scope_answer)
            where = {**(where or {}), "source_doc": document}
        return self._generate_llm(query, where=where, chunks=chunks)

    def _generate_llm(
        self,
        query: str,
        *,
        where: dict[str, Any] | None,
        chunks: list[RetrievedChunk] | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        spans: list[dict[str, Any]] = []

        def retrieve(query_text: str, query_where: dict[str, Any] | None):
            span_started = time.perf_counter()
            hits = [
                c
                for c in self._retrieval.retrieve(query_text, where=query_where)
                if c.score >= self._settings.min_relevant_score
            ]
            spans.append(
                {
                    "name": "retrieval",
                    "latency_ms": round((time.perf_counter() - span_started) * 1000, 3),
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost_usd": None,
                }
            )
            return _safe_chunks(hits)

        def chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
            span_started = time.perf_counter()
            try:
                response = self._llm.chat(
                    messages=messages,
                    tools=tools,
                    temperature=self._settings.llm_temperature,
                )
            except Exception as exc:
                spans.append(
                    {
                        "name": "generation",
                        "latency_ms": round((time.perf_counter() - span_started) * 1000, 3),
                        "input_tokens": None,
                        "output_tokens": None,
                        "cost_usd": None,
                        "error_type": type(exc).__name__,
                    }
                )
                raise
            usage = response.get("usage", {})
            spans.append(
                {
                    "name": "generation",
                    "latency_ms": round((time.perf_counter() - span_started) * 1000, 3),
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "cost_usd": None,
                    "candidate_clause_refs": _clause_refs(response.get("content") or ""),
                }
            )
            return response

        available_chunks: dict[str, RetrievedChunk] = {}
        try:
            # Supplied chunks must remain inside the request scope too.
            initial_hits = (
                retrieve(query, where)
                if chunks is None
                else [
                    c
                    for c in chunks
                    if c.score >= self._settings.min_relevant_score
                    and all(
                        c.metadata.get(key, getattr(c, key, None)) == value
                        for key, value in (where or {}).items()
                    )
                ]
            )
            initial_hits = _safe_chunks(initial_hits)
            available_chunks = {chunk.chunk_id: chunk for chunk in initial_hits}
            context = json.dumps(chunks_payload(initial_hits), indent=2)
            user_content = (
                f"{query}\n\n"
                f"Retrieved document chunks (cite ONLY these chunk_ids in sources):\n{context}\n\n"
                f"Answer using only these chunks. You may call retrieve_chunks for more."
            )
            messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                    + "\n\n"
                    + get_prompt("qa.out_of_scope").render(
                        answer_json=json.dumps(self._settings.out_of_scope_answer)
                    ),
                },
                {"role": "user", "content": user_content},
            ]

            message: dict[str, Any] | None = None
            for _ in range(self._settings.max_tool_rounds):
                response = chat(messages, tools=[RETRIEVE_TOOL])
                message = response
                if not response.get("tool_calls"):
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": response["content"],
                        "tool_calls": [
                            {
                                "id": c["id"],
                                "type": "function",
                                "function": {"name": c["name"], "arguments": c["arguments"]},
                            }
                            for c in response["tool_calls"]
                        ],
                    }
                )
                for call in response["tool_calls"]:
                    args = json.loads(call["arguments"] or "{}")
                    tool_where = dict(where or {})
                    requested_type = args.get("document_type")
                    conflict = (
                        requested_type
                        and "document_type" in tool_where
                        and tool_where["document_type"] != requested_type
                    )
                    if requested_type:
                        tool_where["document_type"] = requested_type
                    hits = (
                        [] if conflict else retrieve(args.get("query", query), tool_where or None)
                    )
                    available_chunks.update({chunk.chunk_id: chunk for chunk in hits})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(chunks_payload(hits)),
                        }
                    )
            else:
                message = chat(messages, tools=None)

            # Validate + retry once.
            for attempt in range(2):
                errors: list[str]
                try:
                    payload = parse_json_response(message["content"] or "")
                    errors = validate_response(payload, self._settings.out_of_scope_answer)
                    if not errors:
                        payload = apply_completeness_adjustment(payload, query)
                        errors += self._verify_sources(payload, available_chunks)
                    if errors:
                        spans[-1]["validation_errors"] = errors
                    if not errors:
                        self._log_trace(query, payload, available_chunks, spans, started_at)
                        return payload
                except (ValueError, json.JSONDecodeError) as exc:
                    errors = [f"response did not contain a JSON object ({exc})"]
                if attempt == 0:
                    messages.append({"role": "assistant", "content": message["content"]})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous reply did not match the required JSON schema: "
                                + "; ".join(errors)
                                + "\nReply again with ONLY the corrected JSON object."
                            ),
                        }
                    )
                    message = chat(messages)

            raise SchemaValidationError(errors)
        except Exception:
            self._log_trace(query, None, available_chunks, spans, started_at)
            raise

    def _log_trace(
        self,
        query: str,
        payload: dict[str, Any] | None,
        available_chunks: dict[str, RetrievedChunk],
        spans: list[dict[str, Any]],
        started_at: float,
    ) -> None:
        clause_refs = _clause_refs(payload["answer"]) if payload else []
        log.info(
            "qa trace",
            extra={
                "input_type": "text",
                "prompt_version": get_prompt("qa.system").version,
                "answer_clause_refs": clause_refs,
                "retrieved_context_ids": sorted(available_chunks),
                "spans": spans,
                "total_latency_ms": round((time.perf_counter() - started_at) * 1000, 3),
            },
        )

    def _verify_sources(
        self, payload: dict[str, Any], available_chunks: dict[str, RetrievedChunk]
    ) -> list[str]:
        errors: list[str] = []
        cited_chunks: list[RetrievedChunk] = []
        if not payload["out_of_scope"] and not payload["sources"]:
            errors.append("a substantive answer must cite retrieved evidence")
        for source in payload["sources"]:
            chunk_id = source["chunk_id"]
            chunk = available_chunks.get(chunk_id)
            if chunk is None:
                errors.append(f"cited chunk_id {chunk_id} was not retrieved for this request")
                continue
            if source["document"] != chunk.document:
                errors.append(f"document for {chunk_id} does not match the retrieved source")
            stored_text = self._vector_store.get_document_text(chunk_id)
            if stored_text is None:
                errors.append(f"cited chunk_id {chunk_id} does not exist in the knowledge base")
                continue
            excerpt = source["excerpt"].strip()
            if not excerpt or excerpt not in stored_text or excerpt not in chunk.text:
                errors.append(f"excerpt for {chunk_id} does not match the stored chunk text")
            cited_chunks.append(chunk)
        references = parse_clause_request(payload["answer"])
        if references and not references.valid:
            errors.append("answer contains a clause range that cannot be verified safely")
        cited_sections = set(references.numbers if references else ())
        supported_sections = {
            number
            for number in cited_sections
            if any(clause_excerpt(chunk, number) for chunk in cited_chunks)
        }
        unsupported_sections = cited_sections - supported_sections
        if unsupported_sections:
            errors.append(
                "answer cites section(s) not present in its cited sources: "
                + ", ".join(sorted(unsupported_sections))
            )
        for quotation in QUOTATION_RE.findall(payload["answer"]):
            quote = next(part for part in quotation if part)
            if not any(quote in source["excerpt"] for source in payload["sources"]):
                errors.append("answer quotation is not present verbatim in its cited excerpts")
        if not page_references_supported(
            payload["answer"],
            {str(chunk.metadata.get("page_number")) for chunk in cited_chunks},
        ):
            errors.append("answer page number is not present in cited metadata")
        supported_documents = {
            match.group().upper()
            for chunk in cited_chunks
            for match in DOCUMENT_ID_RE.finditer(f"{chunk.document}\n{chunk.text}")
        }
        if any(
            match.group().upper() not in supported_documents
            for match in DOCUMENT_ID_RE.finditer(payload["answer"])
        ):
            errors.append("answer document reference is not supported by cited evidence")
        errors.extend(reference_association_errors(payload["answer"], cited_chunks))
        return errors
