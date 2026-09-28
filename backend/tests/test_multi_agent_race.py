from legal_assistant import config
from legal_assistant.agent.orchestrator import extract_terms, run_orchestrator
from legal_assistant.agent.multi_agent_race import EVAL_CASE_IDS, MeteredLegalAgent, classify_failure, load_eval_cases
from legal_assistant.evaluation.judge_validation import load_labels
from legal_assistant.evaluation.race_judge import judge_answer
from legal_assistant.generation.schema import validate_response


def test_race_uses_the_unchanged_first_ten_eval_cases():
    labels = {label["id"]: label["question"] for label in load_labels()}
    cases = load_eval_cases()

    assert [case["id"] for case in cases] == list(range(1, 11)) == list(EVAL_CASE_IDS)
    assert all(case["question"] == labels[case["id"]] for case in cases)


def test_orchestrator_logs_every_handoff_and_token_total_matches():
    report = run_orchestrator("How long is the contract term?")

    assert [entry["hop"] for entry in report["handoffs"]] == [
        "user -> orchestrator (plan)",
        "orchestrator -> clause_worker (brief + retrieved chunks)",
    ]
    assert report["token_count"] == sum(entry["tokens"] for entry in report["handoffs"])
    assert report["steps"][1]["arguments"]["effective_date"] == "2021-01-14"
    assert report["completed"] and not validate_response(report["result"])


def test_defined_terms_worker_resolves_a_quoted_defined_term():
    report = run_orchestrator('What does "Agreement" mean?')

    assert extract_terms('What does "Agreement" mean?') == ["Agreement"]
    assert report["result"]["sources"][0]["document"] == "master_services_agreement.md"
    assert '("Agreement")' in report["result"]["sources"][0]["excerpt"]
    assert judge_answer('What does "Agreement" mean?', report["result"])["checks"]["sources_verified"]


def test_defined_terms_500_is_retried_then_degraded_without_inventing_a_meaning():
    report = run_orchestrator('What does "Agreement" mean?', fail_worker="defined_terms")
    outcome = classify_failure(report, ["Agreement"])

    assert outcome["attempts"] == config.ORCHESTRATOR_WORKER_RETRIES + 1
    assert set(outcome["statuses"]) == {500}
    assert outcome["behaviour"] == "degraded" and not outcome["lied"]
    assert "is defined in" not in report["result"]["answer"]
    assert "could not be verified" in report["result"]["answer"]
    assert not validate_response(report["result"])


def test_single_agent_metering_bills_each_turn_once():
    report = MeteredLegalAgent().run("What is the late payment fee?")

    assert len(report["handoffs"]) == len(report["steps"])
    assert report["token_count"] == sum(entry["tokens"] for entry in report["handoffs"])
    assert report["handoffs"][0]["output_tokens"] < report["handoffs"][-1]["input_tokens"]
