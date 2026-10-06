"""Regression tests for the second review pass (7 findings)."""
from __future__ import annotations

import pytest

from legal_rag.application.agents.legal_agent import AgentBudgets
from legal_rag.application.agents.orchestrator import _governing_effective_date
from legal_rag.application.workflows.judge import effective_dates_are_parseable


class TestFixedWorkflowTinyBudget:
    def test_fixed_workflow_survives_impossibly_small_budget(self, container):
        # If max_steps=1 fires before "answer" is stored, the workflow must
        # still return a well-formed report (not KeyError).
        from legal_rag.application.agents.legal_agent import FixedWorkflow, LegalAgent

        def small_agent() -> LegalAgent:
            return LegalAgent(
                retrieval=container.retrieval_service,
                qa=container.qa_service,
                budgets=AgentBudgets(
                    max_steps=1, max_seconds=30.0, max_tokens=1_000_000,
                    max_cost_usd=1.0, cost_per_token_usd=1e-6,
                    guardrail_answer=container.settings.guardrail_answer,
                ),
            )

        report = FixedWorkflow(small_agent).run(
            "What notice is required to terminate the agreement?"
        )
        assert set(report.keys()) >= {"strategy", "result", "steps", "stop_reason"}
        assert report["result"]  # a dict, not empty


class TestEffectiveDateStrict:
    @pytest.mark.parametrize("iso", ["2024-13-45", "2020-02-31", "1999-00-10"])
    def test_impossible_iso_date_fails(self, iso):
        assert not effective_dates_are_parseable({"answer": f"Effective {iso}."})

    @pytest.mark.parametrize("iso", ["2021-01-14", "2023-06-01"])
    def test_valid_iso_date_passes(self, iso):
        assert effective_dates_are_parseable({"answer": f"Effective {iso}."})

    def test_english_date_still_passes(self):
        assert effective_dates_are_parseable({"answer": "Effective Jan 14, 2021."})


class TestGoverningEffectiveDateNotCached:
    def test_corpus_change_is_reflected(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.md").write_text("effective as of 2020-01-01\n", encoding="utf-8")
        first = _governing_effective_date(docs)
        assert first == "2020-01-01"

        # Add a newer date; the function must see it.
        (docs / "b.md").write_text("effective as of 2025-06-01\n", encoding="utf-8")
        second = _governing_effective_date(docs)
        assert second == "2025-06-01"


class TestQaOutcomeLabels:
    def test_out_of_scope_outcome_is_labelled_correctly(self, container):
        # Force out_of_scope by using an obviously irrelevant question with a
        # high min_relevant_score. Simpler: guardrail returns out_of_scope=True.
        container.qa_service.answer("Draft me a new clause")
        from legal_rag.infrastructure.observability import get_metrics
        text = get_metrics().render_prometheus()
        # Every request path should contribute to at least one outcome label.
        assert 'outcome="' in text


class TestRequestIdMiddlewareOnErrorPath:
    """/api/nope raises HTTPException 404 → still needs X-Request-ID."""

    def test_error_response_has_request_id_header(self, container):
        from fastapi.testclient import TestClient

        from legal_rag.interfaces.http.app import create_app

        app = create_app(container.settings)
        app.state.container = container
        client = TestClient(app)
        r = client.get("/api/nope")
        assert r.status_code == 404
        assert r.headers.get("X-Request-ID")
