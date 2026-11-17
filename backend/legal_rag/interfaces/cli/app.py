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


def _container(context: typer.Context) -> Container:
    settings = get_settings()
    configure_logging(level=settings.log_level, format=settings.log_format)
    container = Container(settings)
    context.call_on_close(container.close)
    return container


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


@app.command()
def ingest(ctx: typer.Context):
    """Chunk, embed, and store all docs in data/shared-corpus/."""
    container = _container(ctx)
    count = container.monitoring.run("cli.ingest", container.ingestion_service.ingest)
    typer.echo(f"Ingested {count} chunks into {container.settings.chroma_dir}")


@app.command()
def evaluate(ctx: typer.Context, k: int = typer.Option(3, "--k", help="Top-k value for hit rate")):
    """Compare dense-only and hybrid hit-rate@k."""
    container = _container(ctx)
    _echo_json(
        container.monitoring.run(
            "cli.evaluate", lambda: container.evaluation_service.compare_retrieval(k=k)
        )
    )


@app.command()
def agent(
    ctx: typer.Context,
    question: str,
    strategy: str = typer.Option("compare", help="agent|fixed|compare"),
    runs: int = typer.Option(3, help="Runs for the 'compare' strategy"),
):
    """Run or compare the legal agent loop."""
    from legal_rag.application.agents.legal_agent import compare_strategies

    c = _container(ctx)
    if strategy == "agent":
        report = c.monitoring.run("cli.agent", lambda: c.new_legal_agent().run(question))
    elif strategy == "fixed":
        report = c.monitoring.run("cli.fixed", lambda: c.new_fixed_workflow().run(question))
    elif strategy == "compare":
        report = c.monitoring.run(
            "cli.compare",
            lambda: compare_strategies(
                question,
                agent_factory=c.new_legal_agent,
                fixed_factory=c.new_fixed_workflow,
                runs=runs,
            ),
        )
    else:
        typer.echo(f"Unknown strategy: {strategy}", err=True)
        raise typer.Exit(code=2)
    _echo_json(report)


@app.command("agent-safety-check")
def agent_safety_check(ctx: typer.Context):
    """Measure agent trajectories and document injection defense."""
    c = _container(ctx)
    trajectory = c.monitoring.run(
        "cli.agent_safety_check", lambda: c.new_legal_agent().run("What is the late payment fee?")
    )
    before, after = compare_injection_defense()
    _echo_json(
        {
            "trajectory": evaluate_trajectory(trajectory),
            "trajectory_report": trajectory,
            "injection_before": before,
            "injection_after": after,
        }
    )


@app.command("validate-judge")
def validate_judge(ctx: typer.Context):
    """Run the 25-case judge validation report."""
    c = _container(ctx)
    _echo_json(c.monitoring.run("cli.validate_judge", c.judge_service.build_report))


@app.command("race-agent")
def race_agent(ctx: typer.Context):
    """Race the agent against the fixed legal workflow."""
    c = _container(ctx)
    _echo_json(c.monitoring.run("cli.race_agent", c.agent_race.run))


@app.command("race-orchestrator")
def race_orchestrator(ctx: typer.Context):
    """Race the single agent against the orchestrator on the labelled cases."""
    c = _container(ctx)
    race = c.monitoring.run("cli.race_orchestrator", c.multi_agent_race.write_artifacts)
    _echo_json(
        {
            "cases": race["case_ids"],
            "single_agent": race["single_agent"],
            "orchestrator": race["orchestrator"],
            "multiplier": round(race["multiplier"], 1),
            "dominant_handoff": race["hop_shares"][0],
            "failure_behaviour": race["failure"]["classification"],
        }
    )


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
