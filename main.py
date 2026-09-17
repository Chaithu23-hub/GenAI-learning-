import argparse
import json

from legal_assistant import config
from legal_assistant.evaluation import compare_retrieval
from legal_assistant.vector_store import ingest_documents
from legal_assistant.legal_agent import LegalAgent, compare_strategies
from legal_assistant.agent_failure_modes import compare_injection_defense, evaluate_trajectory


def cmd_ingest(args):
    count = ingest_documents()
    print(f"Ingested {count} chunks into {config.CHROMA_DIR}")


def cmd_evaluate(args):
    print(json.dumps(compare_retrieval(k=args.k), indent=2))


def cmd_agent(args):
    if args.strategy == "agent":
        report = LegalAgent().run(args.question)
    elif args.strategy == "fixed":
        from legal_assistant.legal_agent import run_fixed_workflow

        report = run_fixed_workflow(args.question)
    else:
        report = compare_strategies(args.question, runs=args.runs)
    print(json.dumps(report, indent=2))


def cmd_agent_safety_check(args):
    trajectory = LegalAgent().run("What is the late payment fee?")
    before, after = compare_injection_defense()
    print(json.dumps({
        "trajectory": evaluate_trajectory(trajectory),
        "trajectory_report": trajectory,
        "injection_before": before,
        "injection_after": after,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Legal document RAG assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Chunk, embed, and store all docs in data/legal/")
    p_ingest.set_defaults(func=cmd_ingest)

    p_evaluate = sub.add_parser("evaluate", help="Compare dense and hybrid hit-rate@k")
    p_evaluate.add_argument("--k", type=int, default=3)
    p_evaluate.set_defaults(func=cmd_evaluate)

    p_agent = sub.add_parser("agent", help="Run or compare the legal agent loop")
    p_agent.add_argument("question")
    p_agent.add_argument("--strategy", choices=["agent", "fixed", "compare"], default="compare")
    p_agent.add_argument("--runs", type=int, default=3)
    p_agent.set_defaults(func=cmd_agent)

    p_safety = sub.add_parser(
        "agent-safety-check",
        help="Measure agent trajectories and document injection defense",
    )
    p_safety.set_defaults(func=cmd_agent_safety_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
