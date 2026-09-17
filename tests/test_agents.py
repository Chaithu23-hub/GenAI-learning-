from legal_assistant.legal_agent import LegalAgent, compare_strategies, run_fixed_workflow
from legal_assistant.race_evaluation import RACE_CASES


def test_agent_exposes_steps_and_stops_with_answer():
    report = LegalAgent().run("What is the late payment fee?")

    assert report["completed"] is True
    assert report["steps"]
    assert report["steps"][0]["action"] == "retrieve"
    assert report["steps"][-1]["action"] == "answer"
    assert report["tool_calls"] <= 4
    assert report["estimated_cost_usd"] >= 0.0


def test_agent_has_safe_step_budget(monkeypatch):
    monkeypatch.setattr("legal_assistant.legal_agent.retrieve", lambda *args, **kwargs: [])
    report = LegalAgent(max_steps=1).run("What is the contract term?")

    assert report["completed"] is False
    assert report["stop_reason"] == "step_budget_exceeded"


def test_fixed_workflow_returns_same_response_contract():
    report = run_fixed_workflow("What is the contract term?")

    assert report["completed"] is True
    assert report["result"]["sources"]
    assert [step["action"] for step in report["steps"]] == ["retrieve", "answer"]


def test_comparison_contains_speed_cost_proxy_and_reliability():
    comparison = compare_strategies("What is the contract term?", runs=1)

    for strategy in ["agent", "fixed_workflow"]:
        summary = comparison[strategy]
        assert 0 <= summary["reliability"] <= 1
        assert summary["average_seconds"] >= 0
        assert summary["average_tool_calls"] > 0
        assert summary["estimated_cost_usd"] >= 0.0
    assert comparison["ship_recommendation"] == "fixed_workflow"


def test_agent_has_typed_definitions_tool_and_branching_race_cases():
    agent = LegalAgent()
    assert "get_definitions" in agent.tools
    assert "original" in str(agent.tools["get_definitions"].__annotations__["version"])
    assert len(RACE_CASES) == 10
    assert sum(case.branches_on_prior_result for case in RACE_CASES) >= 3


def test_agent_enforces_token_and_cost_budgets(monkeypatch):
    monkeypatch.setattr("legal_assistant.legal_agent.retrieve", lambda *args, **kwargs: [])
    token_limited = LegalAgent(max_tokens=1).run("What is the contract term?")
    cost_limited = LegalAgent(max_cost_usd=0.0).run("What is the contract term?")

    assert token_limited["completed"] is False
    assert token_limited["stop_reason"] == "token_budget_exceeded"
    assert cost_limited["completed"] is False
    assert cost_limited["stop_reason"] == "cost_budget_exceeded"