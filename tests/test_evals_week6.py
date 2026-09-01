import json
import pytest

from legal_assistant import config
from legal_assistant.pipeline import answer_question, inspect_question
from legal_assistant.judges import score_answer_on_problem_type, evaluate_answer_completeness
from legal_assistant.schema import validate_response

class TestShallowAnswers:
    """Problem 1: Answers correct but incomplete — missing legal nuances."""

    def test_trace_2_takings_clause_shallow(self):
        """Trace 2: Fifth Amendment Takings Clause — omits 'just compensation' requirement."""
        payload = answer_question(
            "Can the government take my property?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        assert payload["sources"]
        
        # Should mention BOTH "public use" AND "just compensation"
        answer_lower = payload["answer"].lower()
        has_public = "public" in answer_lower
        has_compensation = "compensation" in answer_lower
        
        # BASELINE: This will likely fail (answer is shallow)
        # After fix: Should either include both or mark confidence as "low"
        if not (has_public and has_compensation):
            # Shallow answer detected — confidence should be "low" or "medium"
            assert payload["confidence"] in ["low", "medium"], \
                f"Shallow answer marked as {payload['confidence']}: {payload['answer']}"
        
        score = score_answer_on_problem_type(payload, "shallow_answer")
        print(f"\nTrace 2 score: {score['score']}/10")
        return score["score"]

    def test_trace_6_right_to_remain_silent_shallow(self):
        """Trace 6: Right to remain silent — uses legal jargon without plain explanation."""
        payload = answer_question(
            "What is the right to remain silent?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        assert payload["sources"]
        
        # Should explain BOTH legal definition and practical meaning
        answer = payload["answer"]
        has_practical = any(w in answer.lower() for w in ["must tell", "don't have to", "can refuse", "tell police"])
        
        score = score_answer_on_problem_type(payload, "shallow_answer")
        print(f"\nTrace 6 score: {score['score']}/10")
        return score["score"]

    def test_trace_11_reconstruction_amendments_shallow(self):
        """Trace 11: Reconstruction amendments — names them but not what each did."""
        payload = answer_question(
            "What did the Reconstruction era amendments accomplish?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should explain what 13th, 14th, and 15th did
        answer_lower = payload["answer"].lower()
        
        # Check for specific accomplishments
        has_13th = any(w in answer_lower for w in ["slavery", "abolish", "servitude"])
        has_14th = any(w in answer_lower for w in ["equal", "citizenship", "due process"])
        has_15th = any(w in answer_lower for w in ["vote", "color", "race"])
        
        # Should mention at least 2 of 3
        accomplishments_mentioned = sum([has_13th, has_14th, has_15th])
        if accomplishments_mentioned < 2:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "shallow_answer")
        print(f"\nTrace 11 score: {score['score']}/10")
        return score["score"]

    def test_trace_14_anti_federalists_shallow(self):
        """Trace 14: Anti-Federalist concerns — factual but lacks historical context."""
        payload = answer_question(
            "Why did Anti-Federalists demand the Bill of Rights?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should explain the tension: Anti-Federalists feared strong national govt
        answer = payload["answer"]
        reasoning = payload.get("reasoning", "")
        
        # Shallow if it just lists rights, not the WHY
        if len(answer) < 150:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "shallow_answer")
        print(f"\nTrace 14 score: {score['score']}/10")
        return score["score"]

    def test_trace_15_reserved_powers_shallow(self):
        """Trace 15: Reserved powers under 10th Amendment — oversimplified."""
        payload = answer_question(
            "What powers do states keep under the Constitution?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should distinguish: reserved powers vs delegated powers vs prohibited powers
        answer_lower = payload["answer"].lower()
        
        if "reserved" not in answer_lower or "police" not in answer_lower:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "shallow_answer")
        print(f"\nTrace 15 score: {score['score']}/10")
        return score["score"]

    def test_trace_17_just_compensation_shallow(self):
        """Trace 17: 'Just compensation' definition — oversimplified as 'fair price'."""
        payload = answer_question(
            "What's a 'just compensation' in the Takings Clause?",
            backend="extractive"
        )
        
        # Document may not fully define this, so should mark as "low" confidence
        answer_lower = payload["answer"].lower()
        
        # If definition is shallow, confidence should reflect uncertainty
        if len(answer_lower) < 200 and "complex" not in answer_lower:
            assert payload["confidence"] == "low", \
                f"Shallow definition marked as {payload['confidence']}"
        
        score = score_answer_on_problem_type(payload, "shallow_answer")
        print(f"\nTrace 17 score: {score['score']}/10")
        return score["score"]





class TestHallucinations:
    """Problem 2: System invents facts not in documents."""

    def test_trace_12_privacy_hallucination(self):
        """Trace 12: Query about privacy rights — document doesn't discuss privacy."""
        payload = answer_question(
            "Is there a right to privacy in the Constitution?",
            backend="extractive"
        )
        
        # Should mark as out-of-scope (privacy not in provided docs)
        if payload["out_of_scope"]:
            assert payload["answer"] == config.OUT_OF_SCOPE_ANSWER
            assert payload["sources"] == []
            score = 9  # Correct refusal
        else:
            # Hallucination: system invented privacy discussion
            score = 2
        
        print(f"\nTrace 12 score: {score}/10")
        return score

    def test_trace_16_phone_search_out_of_scope(self):
        """Trace 16: Query about phone searches — modern tech not in documents."""
        payload = answer_question(
            "Can the government search my phone?",
            backend="extractive"
        )
        
        # Should mark as out-of-scope (modern tech not in 1791 doc)
        if payload["out_of_scope"]:
            assert payload["answer"] == config.OUT_OF_SCOPE_ANSWER
            score = 9
        else:
            # Hallucination: applied old law to modern context
            score = 2
        
        print(f"\nTrace 16 score: {score}/10")
        return score

    def test_trace_12_hallucination_confidence_check(self):
        """Trace 12b: If hallucination occurs, check confidence is NOT high."""
        payload = answer_question(
            "Is there a right to privacy in the Constitution?",
            backend="extractive"
        )
        
        score = score_answer_on_problem_type(payload, "hallucination")
        
        # If not out-of-scope, must be low-confidence to avoid false authority
        if not payload["out_of_scope"]:
            assert payload["confidence"] in ["low", "medium"], \
                f"Hallucination marked as {payload['confidence']}"
        
        print(f"\nTrace 12 hallucination check: {score['score']}/10")
        return score["score"]





class TestIncompleteRetrieval:
    """Problem 3: Multi-part questions only partially answered."""

    def test_trace_3_amendment_comparison_incomplete(self):
        """Trace 3: Compare First and Fourth Amendments — should fetch both."""
        payload = answer_question(
            "What is the difference between First and Fourth Amendments?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should cite both amendments
        cited_docs = {s.get("document") for s in payload.get("sources", [])}
        
        score = score_answer_on_problem_type(payload, "incomplete_retrieval")
        print(f"\nTrace 3 score: {score['score']}/10")
        return score["score"]

    def test_trace_19_amendment_gaps_incomplete(self):
        """Trace 19: All amendment gaps — should mention all three major gaps."""
        payload = answer_question(
            "What was the gap between amendments?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should mention: 60-year gap, 40+ year gap, 30-year gap
        answer_lower = payload["answer"].lower()
        
        gap_mentions = sum([
            "60" in answer_lower,
            "40" in answer_lower,
            "30" in answer_lower,
            "decade" in answer_lower or "decades" in answer_lower,
        ])
        
        if gap_mentions < 2:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "incomplete_retrieval")
        print(f"\nTrace 19 score: {score['score']}/10")
        return score["score"]




class TestRetrievalRanking:
    """Problem 4: Wrong chunk retrieved or wrong emphasis."""

    def test_trace_7_second_amendment_historical_context(self):
        """Trace 7: Second Amendment history — should prioritize Founding-era reasoning."""
        payload = answer_question(
            "Why did the founders create the Second Amendment?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should mention militia/standing armies, not just modern SCOTUS cases
        answer_lower = payload["answer"].lower()
        
        has_founding = any(w in answer_lower for w in ["militia", "standing army", "citizen", "found"])
        
        if not has_founding:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "retrieval_ranking")
        print(f"\nTrace 7 score: {score['score']}/10")
        return score["score"]

    def test_trace_20_incorporation_definition(self):
        """Trace 20: 'Incorporation' — should define the full concept, not just mention it."""
        payload = answer_question(
            "What does 'incorporation' mean?",
            backend="extractive"
        )
        
        # Document has only parenthetical mention; should mark as "low" confidence
        answer = payload.get("answer", "")
        
        if len(answer) < 150:
            assert payload["confidence"] == "low", \
                f"Shallow definition marked as {payload['confidence']}"
        
        score = score_answer_on_problem_type(payload, "retrieval_ranking")
        print(f"\nTrace 20 score: {score['score']}/10")
        return score["score"]


class TestPoorSynthesis:
    """Problem 5: Correct info, unclear presentation."""

    def test_trace_4_sovereign_immunity_clarity(self):
        """Trace 4: 11th Amendment sovereign immunity — explanation should be clear."""
        payload = answer_question(
            "What states can sue in national courts?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Answer should clearly state: states have sovereign immunity from citizen lawsuits
        answer_lower = payload["answer"].lower()
        
        has_clarity = any(w in answer_lower for w in ["cannot", "can't", "protected", "immunity", "lawsuit"])
        
        if not has_clarity:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "poor_synthesis")
        print(f"\nTrace 4 score: {score['score']}/10")
        return score["score"]

    def test_trace_8_double_jeopardy_isolation(self):
        """Trace 8: Double jeopardy clause — should isolate from other Fifth Amendment rights."""
        payload = answer_question(
            "Can I be tried twice for the same crime?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should focus on double jeopardy, not conflate with self-incrimination, etc.
        answer_lower = payload["answer"].lower()
        
        has_focus = "twice" in answer_lower or "twice" in answer_lower or "jeopardy" in answer_lower
        
        if not has_focus:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "poor_synthesis")
        print(f"\nTrace 8 score: {score['score']}/10")
        return score["score"]

    def test_trace_18_jury_trial_comparison(self):
        """Trace 18: 6th vs 7th Amendments — should clearly distinguish criminal vs civil."""
        payload = answer_question(
            "Compare the rights to jury trial in 6th and 7th Amendments.",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        
        # Should clearly say: 6th = criminal, 7th = civil
        answer_lower = payload["answer"].lower()
        
        has_distinction = ("criminal" in answer_lower and "civil" in answer_lower)
        
        if not has_distinction:
            assert payload["confidence"] in ["low", "medium"]
        
        score = score_answer_on_problem_type(payload, "poor_synthesis")
        print(f"\nTrace 18 score: {score['score']}/10")
        return score["score"]


class TestBaseline:
    """Control: These should work well (40% baseline from Week 5)."""

    def test_trace_1_first_amendment_good(self):
        """Trace 1: First Amendment — clear, correct answer."""
        payload = answer_question(
            "What does the First Amendment protect?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        assert payload["sources"]
        assert len(payload["answer"]) > 100
        assert payload["confidence"] in ["high", "medium"]
        print(f"\nTrace 1 (BASELINE GOOD): {len(payload['answer'])} chars, confidence={payload['confidence']}")

    def test_trace_5_bill_of_rights_timeline_good(self):
        """Trace 5: Bill of Rights timeline — correct date and context."""
        payload = answer_question(
            "When was the Bill of Rights added?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        assert payload["sources"]
        assert "1791" in payload["answer"] or "18" in payload["answer"]
        print(f"\nTrace 5 (BASELINE GOOD)")

    def test_trace_9_chisholm_case_good(self):
        """Trace 9: Chisholm v. Georgia — case correctly explained."""
        payload = answer_question(
            "What happened in Chisholm v. Georgia?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        assert payload["sources"]
        assert "Georgia" in payload["answer"] and "South Carolina" in payload["answer"]
        print(f"\nTrace 9 (BASELINE GOOD)")

    def test_trace_10_27_amendments_good(self):
        """Trace 10: Total amendments — factual answer."""
        payload = answer_question(
            "How many amendments have been ratified?",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        assert "27" in payload["answer"]
        print(f"\nTrace 10 (BASELINE GOOD)")

    def test_trace_13_third_amendment_good(self):
        """Trace 13: Third Amendment — correct with historical context."""
        payload = answer_question(
            "Amendment about soldiers quartering",
            backend="extractive"
        )
        assert payload["out_of_scope"] is False
        assert payload["sources"]
        assert "soldier" in payload["answer"].lower() or "quarter" in payload["answer"].lower()
        print(f"\nTrace 13 (BASELINE GOOD)")


@pytest.fixture(scope="session")
def eval_summary():
    """Collect and print before/after summary."""
    return {}


def pytest_sessionfinish(session, exitstatus):
    """Print summary at end of test run."""
    print("\n" + "=" * 70)
    print("EVAL SUMMARY — Week 6 Regression Tests")
    print("=" * 70)
    print("20 traces from Week 5 converted to permanent tests")
    print("Use this to measure before/after improvement")
    print("=" * 70)
