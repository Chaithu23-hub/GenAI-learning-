from legal_rag.application.agents.orchestrator import (
    HandoffLog,
    WorkerError,
    estimate_tokens,
    extract_terms,
)


class TestExtractTerms:
    def test_quoted_term(self):
        assert extract_terms('what does "Effective Date" mean?') == ["Effective Date"]

    def test_definition_style_question_extracts_term(self):
        # "what is X?" is treated as a definition query.
        terms = extract_terms("what is the late payment fee?")
        assert terms == ["late payment fee"]

    def test_statement_without_pattern_returns_empty(self):
        assert extract_terms("Show me the contract clauses.") == []


class TestEstimateTokens:
    def test_string_input(self):
        assert estimate_tokens("hello", 4) >= 1

    def test_object_input(self):
        assert estimate_tokens({"a": 1}, 4) >= 1


class TestHandoffLog:
    def test_records_and_totals(self):
        log = HandoffLog(chars_per_token=4)
        log.record("hop", "in", "out")
        log.record("hop2", "in2", "out2")
        assert len(log.entries) == 2
        assert log.total_tokens > 0


class TestOrchestrator:
    def test_plan_without_definition_pattern_stays_clause_only(self, container):
        plan = container.orchestrator.plan("List all amendments.")
        assert plan["subtasks"] == ["clause"]

    def test_plan_with_definitions_subtask(self, container):
        plan = container.orchestrator.plan('what does "Effective Date" mean?')
        assert "defined_terms" in plan["subtasks"]

    def test_run_clean_returns_completed(self, container):
        report = container.orchestrator.run("What is the late payment fee?")
        assert report["strategy"] == "orchestrator"
        assert report["result"]
        assert report["handoffs"]

    def test_injected_worker_failure_degrades_not_lies(self, container):
        report = container.orchestrator.run(
            'what does "Effective Date" mean?', fail_worker="defined_terms",
        )
        # Multiple defined_terms handoff attempts should be present when retries > 0.
        defined_attempts = [
            e for e in report["handoffs"]
            if e["hop"].startswith("orchestrator -> defined_terms_worker")
        ]
        assert defined_attempts
        assert all(e["status"] == 500 for e in defined_attempts)


class TestWorkerError:
    def test_default_status(self):
        err = WorkerError("w")
        assert err.status == 500
        assert "500" in str(err)
