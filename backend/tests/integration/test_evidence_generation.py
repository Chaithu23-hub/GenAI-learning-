import json

import pytest

from legal_rag.application.workflows.generation import (
    GenerationSettings,
    LLMGenerator,
)
from legal_rag.application.workflows.retrieval import RetrievalService, RetrievalSettings
from legal_rag.domain.entities import IndexedChunk
from legal_rag.domain.response_schema import validate_response
from tests.fakes.embedder import HashEmbedder
from tests.fakes.fake_llm import FakeLLMClient
from tests.fakes.reranker import ScoringReranker
from tests.fakes.vector_store import InMemoryVectorStore

MSA = "MSA-2026-014"
OTHER = "MSA-2026-022"
RATE = "3.4 Late Payment. Undisputed overdue amounts accrue interest at 1.5% per month, or the legal maximum, whichever is lower."


@pytest.fixture()
def stack():
    store = InMemoryVectorStore()
    embedder = HashEmbedder()
    retrieval = RetrievalService(vector_store=store, embedder=embedder, reranker=ScoringReranker(),
                                 settings=RetrievalSettings(1, 1, True, 60))
    settings = GenerationSettings(-6.5, "No grounded answer.", 0)

    def seed(document=MSA, text=RATE, heading="Section 3.4 Late Payment", index=0, **metadata):
        chunk = IndexedChunk(f"{document}::{index}", text, heading, index, document,
                             metadata.pop("document_type", "contract"),
                             {"source_doc": document, "tenant_id": "allowed", **metadata})
        store.upsert([chunk], embedder.embed([text]))
        return chunk

    return store, retrieval, settings, seed


@pytest.mark.parametrize("query", [
    f"Quote clause 3.4 of {MSA}.",
    f"What is the late payment interest under {MSA}?",
])
def test_contract_questions_return_llm_answer(stack, query):
    store, retrieval, settings, seed = stack
    chunk = seed(page_number=7, document_version="v2")
    answer = {
        "answer": 'Clause 3.4 states: "Undisputed overdue amounts accrue interest at 1.5% per month, or the legal maximum, whichever is lower." Page 7.',
        "reasoning": "The retrieved passage supports the rate and its qualification.",
        "sources": [{"document": MSA, "chunk_id": chunk.id, "excerpt": RATE}],
        "confidence": "medium", "out_of_scope": False,
    }
    llm = FakeLLMClient(responses=[{"content": json.dumps(answer)}])
    generator = LLMGenerator(retrieval=retrieval, vector_store=store, llm=llm,
                             settings=settings)
    result = generator.generate(query)
    assert result["answer"] == answer["answer"]
    assert len(llm.calls) == 1
    context = llm.calls[0]["messages"][1]["content"]
    assert RATE in context
    assert '"page_number": 7' in context
    assert '"document_version": "v2"' in context
    assert not validate_response(result, settings.out_of_scope_answer)


def test_numbered_request_uses_ranked_retrieval(stack):
    _, retrieval, _, seed = stack
    seed()
    seed(text="8.1 Other terms.", heading="Section 8.1", index=1)
    # A nonexistent number no longer invokes an exhaustive exact lookup.
    hits = retrieval.retrieve(f"Late Payment clause 99.99 of {MSA}")
    assert len(hits) == 1  # configured top_n_answers
    assert hits[0].text == RATE
    assert hits[0].score > 0
    assert retrieval.detect_metadata_filter(f"Clause 3.4 of {MSA}") == {"source_doc": MSA}


def test_missing_clause_uses_llm_and_validates_its_response(stack):
    store, retrieval, settings, seed = stack
    seed()
    answer = {"answer": settings.out_of_scope_answer,
              "reasoning": "The retrieved passage does not establish the requested provision.",
              "sources": [], "confidence": "low", "out_of_scope": True}
    llm = FakeLLMClient(responses=[{"content": json.dumps(answer)}])
    generator = LLMGenerator(retrieval=retrieval, vector_store=store, llm=llm,
                             settings=settings)
    result = generator.generate(f"Quote clause 99.99 of {MSA}")
    assert result == answer
    assert len(llm.calls) == 1
    assert RATE in llm.calls[0]["messages"][1]["content"]


def test_invalid_numbered_answer_is_retried_before_return(stack):
    store, retrieval, settings, seed = stack
    chunk = seed()
    bad = {"answer": "Clause 99.99 requires interest at 1.5%.",
           "reasoning": "Payment terms.", "confidence": "high", "out_of_scope": False,
           "sources": [{"document": MSA, "chunk_id": chunk.id, "excerpt": RATE}]}
    corrected = {"answer": settings.out_of_scope_answer,
                 "reasoning": "The cited evidence does not verify the requested provision.",
                 "sources": [], "confidence": "low", "out_of_scope": True}
    llm = FakeLLMClient(responses=[{"content": json.dumps(bad)}, {"content": json.dumps(corrected)}])
    generator = LLMGenerator(retrieval=retrieval, vector_store=store, llm=llm,
                             settings=settings)
    assert generator.generate(f"Quote clause 99.99 of {MSA}") == corrected
    assert len(llm.calls) == 2
    assert "not present in its cited sources" in llm.calls[1]["messages"][-1]["content"]


def test_nonexistent_document_cannot_use_other_agreements(stack):
    _, retrieval, _, seed = stack
    seed(document=OTHER)
    query = f"Quote clause 3.4 of {MSA}"
    assert not retrieval.retrieve(query)


def test_document_and_tenant_scope_are_preserved(stack):
    _, retrieval, _, seed = stack
    seed()
    seed(document=OTHER, text="3.4 Private terms.", tenant_id="forbidden")
    query = f"Quote clause 3.4 of {MSA}"
    hits = retrieval.retrieve(query, where={"tenant_id": "allowed"})
    assert {hit.document for hit in hits} == {MSA}
    assert not retrieval.retrieve(query, where={"tenant_id": "forbidden"})
    assert not retrieval.retrieve(query, where={"source_doc": OTHER})



@pytest.mark.parametrize("modification", ["document", "empty_excerpt", "quote", "page", "clause", "no_sources"])
def test_invalid_llm_citations_are_rejected(stack, modification):
    store, retrieval, settings, seed = stack
    chunk = seed()
    hits = retrieval.retrieve("late payment")
    generator = LLMGenerator(retrieval=retrieval, vector_store=store, llm=FakeLLMClient(),
                             settings=settings)
    payload = {"answer": "Interest is 1.5%.", "sources": [
        {"document": MSA, "chunk_id": chunk.id, "excerpt": RATE}], "out_of_scope": False}
    if modification == "document":
        payload["sources"][0]["document"] = OTHER
    elif modification == "empty_excerpt":
        payload["sources"][0]["excerpt"] = ""
    elif modification == "quote":
        payload["answer"] = 'The clause says "interest is five percent".'
    elif modification == "page":
        payload["answer"] = "Interest is 1.5%, Page 99."
    elif modification == "clause":
        payload["answer"] = "Clause 99.99 requires interest."
    else:
        payload["sources"] = []
    assert generator._verify_sources(payload, {hit.chunk_id: hit for hit in hits})


def test_tool_cannot_remove_document_or_tenant_constraint(stack):
    store, retrieval, settings, seed = stack
    correct = seed()
    seed(document=OTHER, text="Other payment rules.")
    answer = {"answer": "The interest rate is 1.5%.", "reasoning": "Verified payment terms.",
              "sources": [{"document": MSA, "chunk_id": correct.id, "excerpt": RATE}],
              "confidence": "high", "out_of_scope": False}
    llm = FakeLLMClient(responses=[
        {"content": None, "tool_calls": [{"id": "one", "name": "retrieve_chunks",
         "arguments": json.dumps({"query": "payment", "document_type": "contract"})}]},
        {"content": json.dumps(answer)},
    ])
    generator = LLMGenerator(retrieval=retrieval, vector_store=store, llm=llm, settings=settings)
    result = generator.generate(f"What is the payment fee under {MSA}?", where={"tenant_id": "allowed"})
    assert result["sources"][0]["document"] == MSA
    tool_result = next(m for m in llm.calls[1]["messages"] if m["role"] == "tool")
    assert {hit["document"] for hit in json.loads(tool_result["content"])} == {MSA}


@pytest.mark.parametrize("quotation", ['"{}"', '“{}”'])
def test_multiline_fabricated_quotation_is_rejected(stack, quotation):
    store, retrieval, settings, seed = stack
    chunk = seed()
    generator = LLMGenerator(retrieval=retrieval, vector_store=store, llm=FakeLLMClient(), settings=settings)
    hits = retrieval.retrieve("late payment")
    payload = {"answer": quotation.format("Interest is five percent.\nNo statutory cap applies."),
               "sources": [{"document": MSA, "chunk_id": chunk.id, "excerpt": RATE}],
               "out_of_scope": False}
    assert "answer quotation is not present verbatim in its cited excerpts" in generator._verify_sources(
        payload, {hit.chunk_id: hit for hit in hits},
    )


@pytest.mark.parametrize("quotation", ['"{}"', '“{}”'])
def test_legal_duration_quotation_remains_verbatim_in_final_answer(stack, quotation):
    store, retrieval, settings, seed = stack
    text = "7.3 Notice. Either party must give thirty (30) days written notice."
    chunk = seed(text=text, heading="Section 7.3")
    answer = {"answer": "Clause 7.3 states: " + quotation.format("Either party must give thirty (30) days written notice."),
              "reasoning": "The cited notice provision supports the quotation.",
              "sources": [{"document": MSA, "chunk_id": chunk.id, "excerpt": text}],
              "confidence": "medium", "out_of_scope": False}
    llm = FakeLLMClient(responses=[{"content": json.dumps(answer)}])
    generator = LLMGenerator(retrieval=retrieval, vector_store=store, llm=llm, settings=settings)
    result = generator.generate(f"Quote clause 7.3 of {MSA}")
    assert result["answer"] == answer["answer"]
    assert len(llm.calls) == 1
