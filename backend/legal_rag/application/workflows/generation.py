"""Answer generators — extractive (offline) and LLM-backed."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from legal_rag.application.ports import LLMClient, VectorStore
from legal_rag.application.workflows.retrieval import RetrievalService
from legal_rag.domain.entities import RetrievedChunk
from legal_rag.domain.policies import apply_completeness_adjustment
from legal_rag.domain.response_schema import parse_json_response, validate_response
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """ROLE
You are a precise, citation-first legal assistant for a law firm's internal knowledge base.

TASK
Answer the user's question using ONLY the retrieved document chunks. You never guess or invent.

CONTEXT
The retrieved chunks for the current question arrive in the user message as a JSON list with
fields chunk_id, document, heading, excerpt. They are the only facts you may rely on.

CONSTRAINTS
1. Every claim must trace back to a retrieved chunk; cite document and chunk_id in "sources", with a supporting "excerpt" copied verbatim from the chunk.
2. If multiple chunks are relevant, synthesise them but cite each one.
3. If retrieved chunks contradict each other (e.g. an amendment changes a contract clause), surface BOTH versions and note the conflict explicitly.
4. If the answer is not in the retrieved chunks, set out_of_scope to true and use the fixed out-of-scope sentence.
5. Never draft, modify, or invent contract language; retrieve and explain only.

OUTPUT FORMAT
Respond with a single JSON object and nothing else:
{
  "answer": "your grounded answer",
  "reasoning": "step-by-step explanation of how the retrieved chunks lead to the answer",
  "sources": [{"document": "filename", "chunk_id": "id", "excerpt": "exact supporting passage"}],
  "confidence": "high | medium | low",
  "out_of_scope": false
}

TONE
Formal, neutral, concise. Quote contract language verbatim where precision matters."""


RETRIEVE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "retrieve_chunks",
        "description": "Search the firm's legal document knowledge base for passages relevant to a question.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "document_type": {
                    "type": "string",
                    "enum": ["contract", "amendment"],
                    "description": "Optional: restrict the search to contracts or amendments.",
                },
            },
            "required": ["query"],
        },
    },
}

_EXCERPT_CHARS = 400


@dataclass
class GenerationSettings:
    min_relevant_score: float
    high_confidence_score: float
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
        {"chunk_id": c.chunk_id, "document": c.document, "heading": c.heading,
         "excerpt": c.text[:600]}
        for c in chunks
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


class ExtractiveGenerator:
    """Offline generator that quotes retrieved chunks verbatim — grounded by construction."""

    def __init__(self, *, retrieval: RetrievalService, settings: GenerationSettings):
        self._retrieval = retrieval
        self._settings = settings

    def generate(
        self,
        query: str,
        *,
        where: dict[str, Any] | None = None,
        chunks: list[RetrievedChunk] | None = None,
    ) -> dict[str, Any]:
        chunks = self._retrieval.retrieve(query, where=where) if chunks is None else chunks
        relevant = [c for c in chunks if c.score >= self._settings.min_relevant_score]
        if not relevant:
            return _out_of_scope(self._settings.out_of_scope_answer)

        confidence = (
            "high" if relevant[0].score >= self._settings.high_confidence_score else "medium"
        )
        parts, sources = [], []
        for c in relevant:
            location = (
                f'{c.document}, section "{c.heading}"' if c.heading != "Preamble" else c.document
            )
            parts.append(f'According to {location}: "{c.text[:_EXCERPT_CHARS]}"')
            sources.append({
                "document": c.document,
                "chunk_id": c.chunk_id,
                "excerpt": c.text[:_EXCERPT_CHARS],
            })
        payload = {
            "answer": "Based on the retrieved documents: " + " ".join(parts),
            "reasoning": (
                f"Retrieved {len(relevant)} relevant chunk(s); top cross-encoder "
                f"score {relevant[0].score:.2f}. The answer quotes each chunk "
                "verbatim, so every claim maps directly to a source below."
            ),
            "sources": sources,
            "confidence": confidence,
            "out_of_scope": False,
        }
        return apply_completeness_adjustment(payload, query)


class LLMGenerator:
    """LLM-backed generator with tool calling, JSON validation, and one retry."""

    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        vector_store: VectorStore,
        llm: LLMClient,
        settings: GenerationSettings,
        fallback: ExtractiveGenerator,
    ):
        self._retrieval = retrieval
        self._vector_store = vector_store
        self._llm = llm
        self._settings = settings
        self._fallback = fallback

    def generate(
        self,
        query: str,
        *,
        where: dict[str, Any] | None = None,
        chunks: list[RetrievedChunk] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._generate_llm(query, where=where)
        except Exception as exc:  # noqa: BLE001
            log.warning("llm generation failed; extractive fallback",
                        extra={"error": str(exc)})
            return self._fallback.generate(query, where=where, chunks=chunks)

    def _generate_llm(self, query: str, *, where: dict[str, Any] | None) -> dict[str, Any]:
        initial_hits = self._retrieval.retrieve(query, where=where)
        context = json.dumps(chunks_payload(initial_hits), indent=2)
        user_content = (
            f"{query}\n\n"
            f"Retrieved document chunks (cite ONLY these chunk_ids in sources):\n{context}\n\n"
            f"Answer using only these chunks. You may call retrieve_chunks for more."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        message: dict[str, Any] | None = None
        for _ in range(self._settings.max_tool_rounds):
            response = self._llm.chat(
                messages=messages,
                tools=[RETRIEVE_TOOL],
                temperature=self._settings.llm_temperature,
            )
            message = response
            if not response["tool_calls"]:
                break
            messages.append({
                "role": "assistant",
                "content": response["content"],
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in response["tool_calls"]
                ],
            })
            for call in response["tool_calls"]:
                args = json.loads(call["arguments"] or "{}")
                tool_where = (
                    {"document_type": args["document_type"]}
                    if args.get("document_type") else where
                )
                hits = self._retrieval.retrieve(args.get("query", query), where=tool_where)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(chunks_payload(hits)),
                })
        else:
            return self._fallback.generate(query, where=where)

        # Validate + retry once.
        for attempt in range(2):
            errors: list[str]
            try:
                payload = parse_json_response(message["content"] or "")
                errors = validate_response(payload, self._settings.out_of_scope_answer)
                errors += self._verify_sources(payload)
                if not errors:
                    return apply_completeness_adjustment(payload, query)
            except (ValueError, json.JSONDecodeError) as exc:
                errors = [f"response did not contain a JSON object ({exc})"]
            if attempt == 0:
                messages.append({"role": "assistant", "content": message["content"]})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous reply did not match the required JSON schema: "
                        + "; ".join(errors)
                        + "\nReply again with ONLY the corrected JSON object."
                    ),
                })
                retry = self._llm.chat(
                    messages=messages, temperature=self._settings.llm_temperature
                )
                message = retry

        log.warning("llm validation failed twice; extractive fallback")
        return self._fallback.generate(query, where=where)

    def _verify_sources(self, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for source in payload["sources"]:
            chunk_id = source["chunk_id"]
            stored_text = self._vector_store.get_document_text(chunk_id)
            if stored_text is None:
                errors.append(
                    f"cited chunk_id {chunk_id} does not exist in the knowledge base"
                )
                continue
            excerpt = source["excerpt"].strip()
            if excerpt and excerpt not in stored_text:
                errors.append(
                    f"excerpt for {chunk_id} does not match the stored chunk text"
                )
        return errors
