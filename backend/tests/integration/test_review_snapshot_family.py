"""Regression coverage for current evidence identity and explicit family scope."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from legal_rag.application.workflows.generation import GenerationSettings, LLMGenerator
from legal_rag.application.workflows.retrieval import RetrievalService, RetrievalSettings
from legal_rag.domain.entities import IndexedChunk
from legal_rag.domain.exceptions import SchemaValidationError
from legal_rag.infrastructure.vector_store.chroma import ChromaVectorStore
from tests.fakes.embedder import HashEmbedder
from tests.fakes.fake_llm import ContextLLMClient, FakeLLMClient
from tests.fakes.reranker import IdentityReranker
from tests.fakes.vector_store import InMemoryVectorStore


def _chunk(identifier="MSA-2024-001", **metadata):
    return IndexedChunk(
        id=identifier + "::000",
        text="Payment is due within thirty days.",
        heading="Section 3: Payment",
        chunk_index=0,
        document=identifier + ".md",
        document_type="contract" if identifier.startswith("MSA") else "amendment",
        metadata={
            "source_doc": identifier,
            "page_number": 2,
            "document_version": "v1",
            "counterparty": "Allowed",
            **metadata,
        },
    )


def _services(chunks, llm=None):
    store = InMemoryVectorStore()
    embedder = HashEmbedder()
    store.upsert(chunks, embedder.embed([chunk.text for chunk in chunks]))
    retrieval = RetrievalService(
        vector_store=store,
        embedder=embedder,
        reranker=IdentityReranker(),
        settings=RetrievalSettings(20, 20, True, 60),
    )
    generator = LLMGenerator(
        vector_store=store,
        retrieval=retrieval,
        llm=llm or ContextLLMClient("No supporting evidence."),
        settings=GenerationSettings(0, "No supporting evidence.", 0),
    )
    return store, retrieval, generator


@pytest.mark.parametrize(
    "field,value",
    [
        ("page_number", 9),
        ("document_version", "v2"),
        ("source_doc", "MSA-2024-999"),
        ("amends", "MSA-2024-999"),
        ("clause_ref", "7"),
        ("effective_date", "2025-01-01"),
        ("status", "superseded"),
    ],
)
def test_metadata_replacement_during_generation_is_rejected(field, value):
    original = _chunk()
    store, retrieval, generator = _services([original])
    hits = retrieval.retrieve("payment")
    answer = {
        "answer": "Payment is due within thirty days.",
        "reasoning": "The source states the term.",
        "sources": [
            {"document": original.document, "chunk_id": original.id, "excerpt": original.text}
        ],
        "confidence": "high",
        "out_of_scope": False,
    }

    class ReplacingLLM(FakeLLMClient):
        def chat(self, **kwargs):
            store.upsert([replace(original, metadata={**original.metadata, field: value})], [[1.0]])
            return {"content": json.dumps(answer), "tool_calls": []}

    generator._llm = ReplacingLLM()
    with pytest.raises(SchemaValidationError):
        generator.generate("payment", chunks=hits)


@pytest.mark.parametrize(
    "field,value",
    [
        ("document", "other.md"),
        ("heading", "Section 9"),
        ("document_type", "amendment"),
        ("text", "Payment is due within thirty days. Updated."),
    ],
)
def test_replaced_chunk_record_is_not_valid_citation(field, value):
    original = _chunk()
    store, retrieval, generator = _services([original])
    hits = retrieval.retrieve("payment")
    store.upsert([replace(original, **{field: value})], [[1.0]])
    payload = {
        "answer": "Payment is due within thirty days.",
        "sources": [
            {"document": original.document, "chunk_id": original.id, "excerpt": original.text}
        ],
        "out_of_scope": False,
    }
    assert generator._verify_sources(payload, {hit.chunk_id: hit for hit in hits})


def _family():
    return [
        _chunk(),
        _chunk("AMD-2024-002", amends="MSA-2024-001"),
        _chunk("AMD-2024-003", amends="MSA-2024-999"),
        _chunk("AMD-2024-004", amends="MSA-2024-001", counterparty="Forbidden"),
    ]


def test_positive_family_query_includes_linked_amendments_preserving_restrictions():
    _, retrieval, generator = _services(_family())
    query = "Payment in MSA-2024-001 including amendments"
    where = {"source_doc": "MSA-2024-001", "counterparty": "Allowed"}
    hits = retrieval.retrieve(query, where=where)
    assert {hit.metadata["source_doc"] for hit in hits} == {"MSA-2024-001", "AMD-2024-002"}
    result = generator.generate(query, where=where, chunks=hits)
    assert {source["document"] for source in result["sources"]} == {
        "MSA-2024-001.md",
        "AMD-2024-002.md",
    }


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "excluding amendments",
        "without amendments",
        "not including amendments",
        "do not include amendments",
    ],
)
def test_family_expansion_requires_clear_positive_request(suffix):
    _, retrieval, _ = _services(_family())
    hits = retrieval.retrieve("Payment in MSA-2024-001 " + suffix)
    assert {hit.metadata["source_doc"] for hit in hits} == {"MSA-2024-001"}


def test_conflicting_explicit_scope_cannot_expand_family():
    _, retrieval, _ = _services(_family())
    assert (
        retrieval.retrieve(
            "MSA-2024-001 including amendments", where={"source_doc": "MSA-2024-999"}
        )
        == []
    )


@pytest.mark.parametrize(
    "query",
    [
        "MSA-2024-001 including amendments: what happens without notice?",
        "MSA-2024-001 including amendments but not schedules",
    ],
)
def test_unrelated_negation_does_not_suppress_explicit_family_request(query):
    _, retrieval, _ = _services(_family())
    hits = retrieval.retrieve(query, where={"counterparty": "Allowed"})
    assert {hit.metadata["source_doc"] for hit in hits} == {"MSA-2024-001", "AMD-2024-002"}


@pytest.mark.parametrize(
    "name,args",
    [
        ("other_tool", '{"query":"payment"}'),
        ("retrieve_chunks", "[1]"),
        ("retrieve_chunks", "null"),
        ("retrieve_chunks", "{private-broken-json"),
        ("retrieve_chunks", "{}"),
        ("retrieve_chunks", '{"query":null}'),
        ("retrieve_chunks", '{"query":123}'),
        ("retrieve_chunks", '{"query":"   "}'),
        ("retrieve_chunks", json.dumps({"query": "x" * 10001})),
        ("retrieve_chunks", '{"query":"payment","document_type":"private-unknown"}'),
        ("retrieve_chunks", '{"query":"payment","document_type":[]}'),
    ],
)
def test_malformed_model_retrieval_calls_raise_safe_schema_error(name, args):
    llm = FakeLLMClient(
        responses=[
            {"content": None, "tool_calls": [{"id": "lookup", "name": name, "arguments": args}]}
        ]
    )
    _, _, generator = _services([_chunk()], llm)
    with pytest.raises(SchemaValidationError) as caught:
        generator.generate("payment")
    assert "private" not in str(caught.value)
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    "document_type,documents",
    [
        (None, {"MSA-2024-001.md", "AMD-2024-002.md"}),
        ("contract", {"MSA-2024-001.md"}),
        ("amendment", {"AMD-2024-002.md"}),
    ],
)
def test_valid_model_tool_types_retain_retrieval_behavior(document_type, documents):
    chunks = [_chunk(), _chunk("AMD-2024-002", amends="MSA-2024-001")]
    refusal = {
        "answer": "No supporting evidence.",
        "reasoning": "Insufficient support.",
        "sources": [],
        "confidence": "low",
        "out_of_scope": True,
    }
    llm = FakeLLMClient(
        responses=[
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "lookup",
                        "name": "retrieve_chunks",
                        "arguments": json.dumps(
                            {"query": "payment", "document_type": document_type}
                        ),
                    }
                ],
            },
            {"content": json.dumps(refusal)},
        ]
    )
    _, _, generator = _services(chunks, llm)
    generator.generate("payment")
    tool_message = next(
        message for message in llm.calls[1]["messages"] if message["role"] == "tool"
    )
    assert {chunk["document"] for chunk in json.loads(tool_message["content"])} == documents


def test_unknown_metadata_operator_fails_closed():
    store, _, _ = _services([_chunk()])
    assert store.get_all(where={"source_doc": {"$unknown": ["MSA-2024-001"]}})["ids"] == []


def test_chroma_reads_text_and_metadata_in_one_chunk_lookup():
    class Collection:
        def get(self, *, ids, include):
            assert ids == ["chunk"]
            assert set(include) == {"documents", "metadatas"}
            return {
                "ids": ids,
                "documents": ["Payment term."],
                "metadatas": [
                    {
                        "document": "agreement.md",
                        "document_type": "contract",
                        "heading": "Section 3",
                        "chunk_index": 0,
                        "page_number": 4,
                        "document_version": "v2",
                    }
                ],
            }

    store = ChromaVectorStore(Path("unused"))
    store._collection = Collection()
    chunk = store.get_chunk("chunk")
    assert chunk.text == "Payment term."
    assert chunk.metadata["page_number"] == 4
    assert chunk.metadata["document_version"] == "v2"
