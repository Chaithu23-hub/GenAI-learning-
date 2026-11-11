"""Synthetic evidence only: none of these clauses represents a real agreement."""

import json

import pytest

from legal_rag.application.workflows.generation import GenerationSettings, LLMGenerator
from legal_rag.application.workflows.retrieval import RetrievalService, RetrievalSettings
from legal_rag.domain.entities import IndexedChunk, RetrievedChunk
from tests.fakes.embedder import HashEmbedder
from tests.fakes.fake_llm import FakeLLMClient
from tests.fakes.reranker import ScoringReranker
from tests.fakes.vector_store import InMemoryVectorStore

A = "MSA-2099-001"
B = "MSA-2099-002"


def generate(initial, corrected):
    store = InMemoryVectorStore()
    embedder = HashEmbedder()
    indexed = [
        IndexedChunk(
            "a",
            "3.4 Alpha obligation.\n3.5 Alpha procedure.",
            "Section 3.4",
            0,
            A,
            "contract",
            {"source_doc": A},
        ),
        IndexedChunk(
            "b",
            "3.4 Beta obligation.\n3.5 Beta procedure.",
            "Section 3.4",
            0,
            B,
            "contract",
            {"source_doc": B},
        ),
    ]
    store.upsert(indexed, embedder.embed([row.text for row in indexed]))
    chunks = [
        RetrievedChunk(
            row.id,
            row.document,
            row.document_type,
            row.heading,
            row.text,
            0,
            score=5,
            metadata=row.metadata,
        )
        for row in indexed
    ]
    payload = {
        "answer": initial,
        "reasoning": "Synthetic comparison.",
        "sources": [
            {"document": row.document, "chunk_id": row.id, "excerpt": row.text} for row in indexed
        ],
        "confidence": "medium",
        "out_of_scope": False,
    }
    llm = FakeLLMClient(
        responses=[
            {"content": json.dumps(payload)},
            {"content": json.dumps({**payload, "answer": corrected})},
        ]
    )
    retrieval = RetrievalService(
        vector_store=store,
        embedder=embedder,
        reranker=ScoringReranker(),
        settings=RetrievalSettings(5, 5, True, 60),
    )
    generator = LLMGenerator(
        retrieval=retrieval,
        vector_store=store,
        llm=llm,
        settings=GenerationSettings(-6.5, "No evidence.", 0),
    )
    return generator.generate("Compare the synthetic documents.", chunks=chunks), llm


@pytest.mark.parametrize(
    "initial, corrected",
    [
        (f'{A} states: "Beta obligation."', f'{B} states: "Beta obligation."'),
        (
            f'{A.replace("-", chr(0x2011))} states: "Beta obligation."',
            f'{B} states: "Beta obligation."',
        ),
        ("Sections 3.4, 3.5, and 99.99 apply.", "Sections 3.4 and 3.5 apply."),
    ],
)
def test_invalid_reference_requires_correction(initial, corrected):
    answer, llm = generate(initial, corrected)
    assert answer["answer"] == corrected
    assert len(llm.calls) == 2


def test_separate_document_quotations_remain_valid():
    text = f'{A} states: "Alpha obligation." {B} states: "Beta obligation."'
    answer, llm = generate(text, text)
    assert answer["answer"] == text
    assert len(llm.calls) == 1
