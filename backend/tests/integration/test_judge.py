from legal_rag.application.workflows.judge import (
    clause_references_exist,
    effective_dates_are_parseable,
    notice_periods_are_numeric,
    run_assertions,
)


class TestDeterministicAssertions:
    def test_clause_ranges_require_every_member(self):
        answer = {
            "answer": "Sections 3.4–3.6 apply.",
            "sources": [{"excerpt": "Section 3.4 applies."}],
        }
        assert not clause_references_exist(answer, retrieved_sources=[])

    def test_section_number_cannot_match_inside_another_number(self):
        answer = {
            "answer": "Section 7.2 applies.",
            "sources": [{"excerpt": "Section 17.2 applies."}],
        }
        assert not clause_references_exist(answer, retrieved_sources=[])

    def test_reference_followed_by_sentence_punctuation_still_matches(self):
        answer = {"answer": "Section 7.2 applies.", "sources": [{"excerpt": "See Section 7.2."}]}
        assert clause_references_exist(answer, retrieved_sources=[])

    def test_clause_reference_matches_source_text(self):
        answer = {
            "answer": "Section 7.2 controls",
            "sources": [{"excerpt": "Section 7.2 controls"}],
        }
        assert clause_references_exist(answer, retrieved_sources=[])

    def test_no_references_is_vacuously_true(self):
        assert clause_references_exist({"answer": "no clause mentioned"}, retrieved_sources=[])

    def test_missing_reference_fails(self):
        answer = {"answer": "Section 7.2 controls", "sources": [{"excerpt": "unrelated"}]}
        assert not clause_references_exist(answer, retrieved_sources=[])

    def test_date_parseable_iso(self):
        answer = {"answer": "Effective 2021-01-14"}
        assert effective_dates_are_parseable(answer)

    def test_date_parseable_english(self):
        answer = {"answer": "Effective Jan 14, 2021"}
        assert effective_dates_are_parseable(answer)

    def test_notice_period_numeric(self):
        answer = {"answer": "30 days notice required"}
        assert notice_periods_are_numeric(answer)

    def test_notice_period_missing_number_fails(self):
        answer = {"answer": "notice is required after a period of days"}
        assert not notice_periods_are_numeric(answer)

    def test_run_assertions_returns_all_keys(self):
        keys = run_assertions({"answer": "a", "sources": []}, [])
        assert set(keys) == {
            "clause_references_exist",
            "effective_dates_parseable",
            "notice_periods_numeric",
        }


class TestScoreAnswerOnProblemType:
    def test_shallow_answer_short(self, container):
        result = container.judge_service.score_answer_on_problem_type(
            {"answer": "x", "reasoning": "y"},
            "shallow_answer",
        )
        assert result["score"] == 3

    def test_hallucination_out_of_scope_correct(self, container):
        result = container.judge_service.score_answer_on_problem_type(
            {"answer": "IDK", "out_of_scope": True},
            "hallucination",
            out_of_scope_sentinel="IDK",
        )
        assert result["score"] == 9
