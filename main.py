import argparse
import json

from legal_assistant import config
from legal_assistant.evaluation import compare_retrieval
from legal_assistant.vector_store import ingest_documents


def cmd_ingest(args):
    count = ingest_documents()
    print(f"Ingested {count} chunks into {config.CHROMA_DIR}")


def cmd_evaluate(args):
    print(json.dumps(compare_retrieval(k=args.k), indent=2))


def main():
    parser = argparse.ArgumentParser(description="Legal document RAG assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Chunk, embed, and store all docs in data/legal/")
    p_ingest.set_defaults(func=cmd_ingest)

    p_evaluate = sub.add_parser("evaluate", help="Compare dense and hybrid hit-rate@k")
    p_evaluate.add_argument("--k", type=int, default=3)
    p_evaluate.set_defaults(func=cmd_evaluate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
