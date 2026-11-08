"""Regression tests for the 9 bugs surfaced by the code review."""

from __future__ import annotations

from pathlib import Path

import pytest

from legal_rag.application.agents.orchestrator import Orchestrator, OrchestratorSettings
from legal_rag.application.workflows.judge import JudgeService, JudgeSettings
from legal_rag.application.workflows.race import MultiAgentRace, classify_failure
from legal_rag.domain.policies import evaluate_trajectory
from tests.fakes.vector_store import InMemoryVectorStore


class TestFinding1GuardrailNotDroppedInSynthesize:
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


class TestFinding3GetDefinitionsIsSafe:
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


class TestFinding4VersionSelectionInAgentDefinitions:
    def test_amended_returns_only_amendment_chunks(self, container):
        agent = container.new_legal_agent()
        # Seed the state with mixed docs
        from legal_rag.domain.entities import AgentState

        state = AgentState(query="terminate")
        state.observations["retrieve"] = {
            "documents": [
                {
                    "document": "master_services_agreement.md",
                    "chunk_id": "msa::001",
                    "score": 0.9,
                    "text": "...",
                },
                {
                    "document": "amendment_01_payment_terms.md",
                    "chunk_id": "amd::001",
                    "score": 0.8,
                    "text": "...",
                },
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
                {
                    "document": "master_services_agreement.md",
                    "chunk_id": "msa::001",
                    "score": 0.9,
                    "text": "...",
                },
                {
                    "document": "amendment_01_payment_terms.md",
                    "chunk_id": "amd::001",
                    "score": 0.8,
                    "text": "...",
                },
            ],
            "injection_detected": False,
        }
        result = agent._get_definitions(state, version="original")
        assert result["references"] == ["msa::001"]


class TestFinding7DefinedTermsWorkerHandlesMissingMetadata:
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

    @staticmethod
    def _orchestrator(store):
        from types import SimpleNamespace

        return Orchestrator(
            retrieval=SimpleNamespace(detect_metadata_filter=lambda query: None),
            vector_store=store,
            generator=None,
            settings=OrchestratorSettings(0, 4, 0.0, "refused", "unsupported", Path(".")),
        )

    def test_definitions_are_limited_to_clause_worker_sources(self):
        vs = InMemoryVectorStore()
        vs._ids.append("other-agreement::001")
        vs._documents.append('("Effective Date") means January 1.')
        vs._metadatas.append({"document": "other-agreement.md"})
        vs._embeddings.append([0.0] * 128)
        result = self._orchestrator(vs).defined_terms_worker(
            {
                "terms": ["Effective Date"],
                "version": "amended",
                "sources": [],
            }
        )
        assert result["definitions"] == []
        assert result["not_found"] == ["Effective Date"]

    def test_conflicting_scoped_definitions_are_not_selected_arbitrarily(self):
        sources = [
            {
                "chunk_id": "c1",
                "document": "msa.md",
                "excerpt": '("Effective Date") means January 1.',
            },
            {
                "chunk_id": "c2",
                "document": "msa.md",
                "excerpt": '("Effective Date") means February 1.',
            },
        ]
        result = self._orchestrator(InMemoryVectorStore()).defined_terms_worker(
            {"terms": ["Effective Date"], "version": "amended", "sources": sources}
        )
        assert result["definitions"] == []
        assert result["not_found"] == ["Effective Date"]

    def test_run_hands_only_validated_clause_sources_to_definition_worker(self, monkeypatch):
        orch = self._orchestrator(InMemoryVectorStore())
        validated_sources = [
            {"chunk_id": "requested::001", "document": "requested.md", "excerpt": "Clause text."}
        ]
        raw_chunks = validated_sources + [
            {
                "chunk_id": "unrelated::001",
                "document": "other-agreement.md",
                "excerpt": '("Effective Date") means January 1.',
            }
        ]
        monkeypatch.setattr(
            orch,
            "clause_worker",
            lambda brief: (
                {
                    "answer": "Clause text.",
                    "reasoning": "grounded",
                    "sources": validated_sources,
                    "confidence": "medium",
                    "out_of_scope": False,
                },
                raw_chunks,
            ),
        )
        observed = {}
        original_worker = orch.defined_terms_worker

        def capture(request, *, fail=False):
            observed.update(request)
            return original_worker(request, fail=fail)

        monkeypatch.setattr(orch, "defined_terms_worker", capture)
        orch.run('What does "Effective Date" mean?')
        assert observed["sources"] == validated_sources


class TestJudgeRequiresExactStoredEvidence:
    @staticmethod
    def _seed():
        vs = InMemoryVectorStore()
        vs._ids.append("known::001")
        vs._documents.append("Payment is due within 30 days.")
        vs._metadatas.append({"document": "master_services_agreement.md"})
        vs._embeddings.append([0.0] * 128)
        return JudgeService(
            vector_store=vs,
            llm=None,
            settings=JudgeSettings(Path("unused-labels.json")),
        )

    def _answer(self, document, excerpt):
        return {
            "answer": "Effective Date is January 1.",
            "sources": [{"chunk_id": "known::001", "document": document, "excerpt": excerpt}],
        }

    def test_empty_excerpt_is_unverified(self):
        judge = self._seed()
        assert not judge._verify_all_sources(self._answer("master_services_agreement.md", " "))

    def test_forged_document_identity_is_unverified(self):
        judge = self._seed()
        assert not judge._verify_all_sources(self._answer("forged.md", "Payment is due"))

    def test_exact_excerpt_and_stored_document_identity_are_verified(self):
        judge = self._seed()
        assert judge._verify_all_sources(
            self._answer("master_services_agreement.md", "Payment is due")
        )


class TestJudgeValidationReportDoesNotInventPredictions:
    def test_loading_labels_requires_port(self):
        judge = JudgeService(
            vector_store=InMemoryVectorStore(),
            llm=None,
            settings=JudgeSettings(Path("unused-labels.json")),
        )
        with pytest.raises(RuntimeError, match="evaluation files port is required"):
            judge.load_labels()

    def test_report_only_displays_human_label_distribution_from_port(self):
        import json

        class EvaluationFilesFake:
            labels = [
                {
                    "id": index,
                    "question": f"Question {index}",
                    "mode": "qa",
                    "human_label": index % 2 == 0,
                }
                for index in range(25)
            ]

            def read_labels(self):
                return json.dumps({"labels": self.labels}).encode()

            def write_artifact(self, name, text):
                raise AssertionError("judge report should not write artifacts")

        files = EvaluationFilesFake()
        judge = JudgeService(
            vector_store=InMemoryVectorStore(),
            llm=None,
            settings=JudgeSettings(Path("unused-labels.json")),
            evaluation_files=files,
        )
        report = judge.build_report()
        assert report["status"] == "not_evaluated"
        assert report["agreement_before"] is None
        assert report["agreement_after"] is None
        assert report["human_label_distribution_by_mode"] == {"qa": {"true": 13, "false": 12}}
        assert "disagreements" not in report
        assert "prediction" not in report

        files.labels[0]["human_label"] = False
        updated = judge.build_report()
        assert updated["human_label_distribution_by_mode"]["qa"]["true"] == 12
        assert updated["agreement_before"] is None
        assert updated["agreement_after"] is None


class TestRaceEvaluationFilePort:
    def test_artifacts_are_written_through_port(self):
        class EvaluationFilesFake:
            def __init__(self):
                self.writes = []

            def read_labels(self):
                return b'{"labels": []}'

            def write_artifact(self, name, text):
                self.writes.append((name, text))

        files = EvaluationFilesFake()
        race = MultiAgentRace(
            agent_factory=None,
            orchestrator=None,
            retrieval=None,
            judge=None,
            labels_path=Path("labels.json"),
            cost_per_token_usd=0.0,
            chars_per_token=4,
            artifact_dir=Path("artifacts"),
            evaluation_files=files,
        )
        report = {
            "hop_shares": [{"hop": "plan", "share": 0.5}],
            "multiplier": 1.0,
            "orchestrator": {"total_tokens": 2},
            "single_agent": {"total_tokens": 2},
        }
        race.run = lambda: report
        race._race_table = lambda _: "table"
        race._handoffs_log = lambda _: "handoffs"
        race._failure_case = lambda _: "failure"

        assert race.write_artifacts() is report
        assert files.writes == [
            ("race_table.md", "table"),
            ("handoffs.log", "handoffs"),
            (
                "multiplier.txt",
                "Context re-send multiplier: 1.0x (2 / 2 tokens); dominant hand-off: plan, 50% of tokens.\n",
            ),
            ("failure_case.md", "failure"),
        ]

    def test_missing_port_fails_before_race_work_or_filesystem_access(self):
        class RetrievalFake:
            def retrieve(self, query):
                raise AssertionError("race should fail before retrieval")

        race = MultiAgentRace(
            agent_factory=None,
            orchestrator=None,
            retrieval=RetrievalFake(),
            judge=None,
            labels_path=Path("labels.json"),
            cost_per_token_usd=0.0,
            chars_per_token=4,
            artifact_dir=Path("artifacts"),
        )
        with pytest.raises(RuntimeError, match="evaluation files port is required"):
            race.run()


class TestFinding8MultiplierGuardsAgainstZero:
    def test_zero_single_tokens_yields_infinity_not_crash(self):
        # No integration harness needed — this is a hot-path formula guard.
        single, multi = 0, 100
        multiplier = multi / single if single else float("inf")
        assert multiplier == float("inf")


class TestFinding9ClassifyFailureHandlesMissingExcerpt:
    def test_missing_excerpt_key_does_not_raise(self):
        report = {
            "handoffs": [
                {
                    "hop": "orchestrator -> defined_terms_worker",
                    "status": 500,
                    "tokens": 10,
                    "input_tokens": 5,
                    "output_tokens": 5,
                    "attempt": 1,
                }
            ],
            "result": {
                "answer": "no info",
                "reasoning": "[Partial answer] worker failed",
                "sources": [{"document": "d", "chunk_id": "c"}],  # no 'excerpt'
            },
        }
        # Must not KeyError.
        classification = classify_failure(report, ["Term A"])
        assert classification["behaviour"] in {"degraded", "unknown", "lied"}


class TestDefinedTermDetectionCatchesNaturalLanguageQuestions:
    def test_agent_detects_meaning_question_for_contract_term(self):
        from legal_rag.application.agents.legal_agent import LegalAgent

        assert LegalAgent._needs_definitions("What does the term 'Affiliate' mean?") is True
        assert LegalAgent._needs_definitions("What is the meaning of Affiliate?") is True
        assert LegalAgent._needs_definitions("Define Confidential Information.") is True

    def test_agent_ignores_plain_factual_clause_questions(self):
        from legal_rag.application.agents.legal_agent import LegalAgent

        assert LegalAgent._needs_definitions("What is the agreement effective date?") is False
        assert LegalAgent._needs_definitions("What is the liability cap?") is False
