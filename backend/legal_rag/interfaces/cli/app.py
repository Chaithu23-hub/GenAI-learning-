"""CLI (Typer). Uses the same composition container as the HTTP app."""
from __future__ import annotations

import json
import sys

import typer

from legal_rag.composition import Container
from legal_rag.domain.policies import compare_injection_defense, evaluate_trajectory
from legal_rag.infrastructure.mcp import run_lookup
from legal_rag.infrastructure.observability.logging import configure_logging
from legal_rag.infrastructure.settings import get_settings

app = typer.Typer(help="LegalRAG command-line interface", no_args_is_help=True)


def _container() -> Container:
    settings = get_settings()
    configure_logging(level=settings.log_level, format=settings.log_format)
    return Container(settings)


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


@app.command()
def ingest():
    """Chunk, embed, and store all docs in data/legal/."""
    container = _container()
    count = container.ingestion_service.ingest()
    typer.echo(f"Ingested {count} chunks into {container.settings.chroma_dir}")


@app.command()
def evaluate(k: int = typer.Option(3, "--k", help="Top-k value for hit rate")):
    """Compare dense-only and hybrid hit-rate@k."""
    _echo_json(_container().evaluation_service.compare_retrieval(k=k))


@app.command()
def agent(
    question: str,
    strategy: str = typer.Option("compare", help="agent|fixed|compare"),
    runs: int = typer.Option(3, help="Runs for the 'compare' strategy"),
):
    """Run or compare the legal agent loop."""
    from legal_rag.application.agents.legal_agent import compare_strategies

    c = _container()
    if strategy == "agent":
        report = c.new_legal_agent().run(question)
    elif strategy == "fixed":
        report = c.new_fixed_workflow().run(question)
    elif strategy == "compare":
        report = compare_strategies(
            question, agent_factory=c.new_legal_agent,
            fixed_factory=c.new_fixed_workflow, runs=runs,
        )
    else:
        typer.echo(f"Unknown strategy: {strategy}", err=True)
        raise typer.Exit(code=2)
    _echo_json(report)


@app.command("agent-safety-check")
def agent_safety_check():
    """Measure agent trajectories and document injection defense."""
    c = _container()
    trajectory = c.new_legal_agent().run("What is the late payment fee?")
    before, after = compare_injection_defense()
    _echo_json({
        "trajectory": evaluate_trajectory(trajectory),
        "trajectory_report": trajectory,
        "injection_before": before,
        "injection_after": after,
    })


@app.command("validate-judge")
def validate_judge():
    """Run the 25-case judge validation report."""
    _echo_json(_container().judge_service.build_report())


@app.command("race-agent")
def race_agent():
    """Race the agent against the fixed legal workflow."""
    _echo_json(_container().agent_race.run())


@app.command("race-orchestrator")
def race_orchestrator():
    """Race the single agent against the orchestrator on the labelled cases."""
    race = _container().multi_agent_race.write_artifacts()
    _echo_json({
        "cases": race["case_ids"],
        "single_agent": race["single_agent"],
        "orchestrator": race["orchestrator"],
        "multiplier": round(race["multiplier"], 1),
        "dominant_handoff": race["hop_shares"][0],
        "failure_behaviour": race["failure"]["classification"],
    })


@app.command("mcp-lookup")
def mcp_lookup(contract_id: str):
    """Discover and call the contract repository over MCP."""
    settings = get_settings()
    configure_logging(level=settings.log_level, format=settings.log_format)
    _echo_json(run_lookup(settings.mcp_config_path, contract_id))


def main() -> None:
    try:
        app()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
