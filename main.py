"""CLI entry point: ingest documents, ask one question, or run an interactive loop."""

import argparse
import json

from legal_assistant import config
from legal_assistant.pipeline import answer_question
from legal_assistant.vector_store import ingest_documents


def cmd_ingest(args):
    count = ingest_documents()
    print(f"Ingested {count} chunks into {config.CHROMA_DIR}")


def _print_response(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    print(f"\nAnswer ({payload['confidence']} confidence):")
    print(f"  {payload['answer']}\n")
    if payload.get("reasoning"):
        print(f"Reasoning:\n  {payload['reasoning']}\n")
    if payload["sources"]:
        print("Sources:")
        for source in payload["sources"]:
            excerpt = source["excerpt"].replace("\n", " ")[:120]
            print(f"  - {source['document']} [{source['chunk_id']}]: {excerpt}...")
    print()


def cmd_ask(args):
    payload = answer_question(args.question, document_type=args.filter, backend=args.backend)
    _print_response(payload, args.json)


def cmd_chat(args):
    print("Legal document assistant. Type a question ('quit' to exit).")
    while True:
        try:
            question = input("\nQ> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question.lower() in {"quit", "exit", "q"}:
            break
        payload = answer_question(question, backend=args.backend)
        _print_response(payload, args.json)


def main():
    parser = argparse.ArgumentParser(description="Legal document RAG assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Chunk, embed, and store all docs in data/legal/")
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser("ask", help="Ask a question about the documents")
    p_ask.add_argument("question")
    p_ask.add_argument("--filter", choices=["contract", "amendment"], default=None,
                       help="Restrict the search to one document type")
    p_ask.add_argument("--backend", choices=["llm", "extractive", "auto"], default="auto")
    p_ask.add_argument("--json", action="store_true", help="Print the raw JSON response")
    p_ask.set_defaults(func=cmd_ask)

    p_chat = sub.add_parser("chat", help="Interactive question loop")
    p_chat.add_argument("--backend", choices=["llm", "extractive", "auto"], default="auto")
    p_chat.add_argument("--json", action="store_true")
    p_chat.set_defaults(func=cmd_chat)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
