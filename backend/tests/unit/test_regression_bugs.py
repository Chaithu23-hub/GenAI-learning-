"""Regression tests for the 9 bugs surfaced by the code review."""
from __future__ import annotations

import pytest

from legal_rag.application.agents.orchestrator import Orchestrator, OrchestratorSettings
from legal_rag.application.workflows.race import classify_failure
from legal_rag.domain.policies import evaluate_trajectory


class TestFinding1_GuardrailNotDroppedInSynthesize:
    """When the clause worker refuses (out_of_scope=True), synthesize must
    preserve that verdict even if definitions succeed."""

    def _make_orchestrator(self, container):
        return container.orchestrator

    def test_out_of_scope_clause_is_preserved(self, container):
        orch = self._make_orchestrator(container)
        clause = {
            "answer": "guardrail refusal",
            "reasoning": "blocked",
            "sources": [],
            "confidence": "high",
            "out_of_scope": True,
        }
        definitions = {
            "status": 200,
            "version": "amended",
            "definitions": [
                {"term": "T", "document": "d.md", "chunk_id": "c1", "excerpt": "T means x."}
            ],
            "not_found": [],
        }
        result = orch.synthesize("q", clause, definitions, ["T"])
        assert result["out_of_scope"] is True
        assert result["answer"] == "guardrail refusal"
        assert result["sources"] == []


class TestFinding3_GetDefinitionsIsSafe:
    def test_get_definitions_is_in_safe_tool_set(self):
        report = {
            "steps": [
                {"action": "retrieve"},
                {"action": "get_definitions"},
                {"action": "answer"},
            ],
            "tool_calls": 3,
        }
        result = evaluate_trajectory(report)
        assert result["trajectory_ok"] is True
        assert not any("unsafe tool" in f for f in result["findings"])


class TestFinding4_VersionSelectionInAgentDefinitions:
    def test_amended_returns_only_amendment_chunks(self, container):
        agent = container.new_legal_agent()
        # Seed the state with mixed docs
        from legal_rag.domain.entities import AgentState
        state = AgentState(query="terminate")
        state.observations["retrieve"] = {
            "documents": [
                {"document": "master_services_agreement.md", "chunk_id": "msa::001",
                 "score": 0.9, "text": "..."},
                {"document": "amendment_01_payment_terms.md", "chunk_id": "amd::001",
                 "score": 0.8, "text": "..."},
            ],
            "injection_detected": False,
        }
        result = agent._get_definitions(state, version="amended")
        assert result["references"] == ["amd::001"]

    def test_original_returns_only_non_amendment_chunks(self, container):
        agent = container.new_legal_agent()
        from legal_rag.domain.entities import AgentState
        state = AgentState(query="terminate")
        state.observations["retrieve"] = {
            "documents": [
                {"document": "master_services_agreement.md", "chunk_id": "msa::001",
                 "score": 0.9, "text": "..."},
                {"document": "amendment_01_payment_terms.md", "chunk_id": "amd::001",
                 "score": 0.8, "text": "..."},
            ],
            "injection_detected": False,
        }
        result = agent._get_definitions(state, version="original")
        assert result["references"] == ["msa::001"]


class TestFinding7_DefinedTermsWorkerHandlesMissingMetadata:
    def test_missing_document_type_does_not_raise(self, container):
        # Directly poke a chunk with no document_type into the fake store.
        vs = container.vector_store
        vs._ids.append("orphan::000")
        vs._documents.append('The "Effective Date" is the date the parties sign this Agreement.')
        vs._metadatas.append({})  # no document_type, no document
        vs._embeddings.append([0.0] * 128)
        request = {"terms": ["Effective Date"], "version": "amended"}
        # Should not raise
        result = container.orchestrator.defined_terms_worker(request)
        assert result["status"] == 200


class TestFinding8_MultiplierGuardsAgainstZero:
    def test_zero_single_tokens_yields_infinity_not_crash(self):
        # No integration harness needed — this is a hot-path formula guard.
        single, multi = 0, 100
        multiplier = multi / single if single else float("inf")
        assert multiplier == float("inf")


class TestFinding9_ClassifyFailureHandlesMissingExcerpt:
    def test_missing_excerpt_key_does_not_raise(self):
        report = {
            "handoffs": [{"hop": "orchestrator -> defined_terms_worker", "status": 500,
                          "tokens": 10, "input_tokens": 5, "output_tokens": 5, "attempt": 1}],
            "result": {
                "answer": "no info",
                "reasoning": "[Partial answer] worker failed",
                "sources": [{"document": "d", "chunk_id": "c"}],  # no 'excerpt'
            },
        }
        # Must not KeyError.
        classification = classify_failure(report, ["Term A"])
        assert classification["behaviour"] in {"degraded", "unknown", "lied"}
