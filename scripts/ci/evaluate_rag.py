"""Content-safe retrieval, grounded-evidence and citation gates on synthetic fixtures.

Scripted answers test deterministic evidence validation, not live LLM entailment.
No repository corpus, .env file or external model API is read.
"""
# ruff: noqa: E402 -- bootstrap the repository backend for a standalone developer CLI.

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from legal_rag.application.workflows.generation import GenerationSettings, LLMGenerator  # noqa: E402
from legal_rag.application.workflows.ingestion import (
    IngestionService,
    IngestionSettings,
)  # noqa: E402
from legal_rag.application.workflows.retrieval import (
    RetrievalService,
    RetrievalSettings,
)  # noqa: E402
from legal_rag.domain.entities import Document  # noqa: E402
from legal_rag.domain.exceptions import SchemaValidationError  # noqa: E402
from legal_rag.infrastructure.chunking.section_chunker import SectionChunker  # noqa: E402
from tests.fakes.embedder import HashEmbedder  # noqa: E402
from tests.fakes.fake_llm import FakeLLMClient  # noqa: E402
from tests.fakes.reranker import ScoringReranker  # noqa: E402
from tests.fakes.vector_store import InMemoryVectorStore  # noqa: E402

EXPECTED_TEXT = (
    "3.4 Payment. Synthetic amounts accrue interest at 1.0%.",
    "3.4 Payment. Synthetic amounts accrue interest at 2.0%.",
    "3.4 Payment. Synthetic amounts accrue interest at 3.0%.",
)


class SyntheticDocuments:
    def iter_documents(self, docs_dir=None):
        for number, expected in enumerate(EXPECTED_TEXT, 1):
            identity = f"MSA-2099-{number:03d}"
            text = f"## Section 3.4 Payment\n{expected}"
            yield Document(
                identity,
                text,
                "contract",
                {"source_doc": identity, "page_number": number},
                pages=tuple([""] * (number - 1) + [text]),
            )


def evaluate(real_models: bool = False) -> dict:
    with tempfile.TemporaryDirectory(
        prefix="legal-rag-synthetic-ci-", ignore_cleanup_errors=True
    ) as directory:
        store = InMemoryVectorStore()
        embedder, reranker = HashEmbedder(), ScoringReranker()
        if real_models:
            from legal_rag.infrastructure.embeddings import (
                CrossEncoderReranker,
                SentenceTransformerEmbedder,
            )
            from legal_rag.infrastructure.settings import Settings
            from legal_rag.infrastructure.vector_store.chroma import ChromaVectorStore

            settings = Settings(_env_file=None, chroma_dir=Path(directory))
            store = ChromaVectorStore(settings.chroma_dir)
            embedder = SentenceTransformerEmbedder(settings.embedding_model)
            reranker = CrossEncoderReranker(settings.rerank_model)
        ingestion = IngestionService(
            vector_store=store,
            embedder=embedder,
            document_source=SyntheticDocuments(),
            chunker=SectionChunker(),
            settings=IngestionSettings(512, 50),
        )
        ingestion.ingest()
        retrieval = RetrievalService(
            vector_store=store,
            embedder=embedder,
            reranker=reranker,
            settings=RetrievalSettings(10, 3, True, 60),
        )
        retrieval_hits, grounded, citations, negatives = 0, 0, 0, 0
        generation_settings = GenerationSettings(-100, "No synthetic evidence.", 0)
        for number, expected in enumerate(EXPECTED_TEXT, 1):
            identity = f"MSA-2099-{number:03d}"
            question = f"What payment interest does Section 3.4 of {identity} state?"
            hits = retrieval.retrieve(question, n=3)
            hit = next((hit for hit in hits if hit.document == identity), None)
            if hit is None or hit.text != expected:
                continue
            retrieval_hits += 1
            payload = {
                "answer": f'Clause 3.4 of {identity} states: "{expected}" Page {number}.',
                "reasoning": "The synthetic fixture supports this exact passage.",
                "sources": [
                    {
                        "document": identity,
                        "chunk_id": hit.chunk_id,
                        "excerpt": expected,
                    }
                ],
                "confidence": "high",
                "out_of_scope": False,
            }
            llm = FakeLLMClient(responses=[{"content": json.dumps(payload)}])
            generator = LLMGenerator(
                retrieval=retrieval,
                vector_store=store,
                llm=llm,
                settings=generation_settings,
            )
            result = generator.generate(question, chunks=hits)
            grounded += result["sources"][0]["excerpt"] == expected and expected in result["answer"]
            citations += result["sources"][0]["document"] == identity
            invalid = [
                {
                    **payload,
                    "sources": [
                        {
                            **payload["sources"][0],
                            "excerpt": "Invented synthetic evidence.",
                        }
                    ],
                },
                {
                    **payload,
                    "sources": [{**payload["sources"][0], "document": "MSA-2099-999"}],
                },
                {**payload, "answer": f"Clause 99.99 of {identity} applies."},
                {**payload, "answer": f"Page 999 of {identity} supports the answer."},
            ]
            for bad in invalid:
                generator = LLMGenerator(
                    retrieval=retrieval,
                    vector_store=store,
                    llm=FakeLLMClient(responses=[{"content": json.dumps(bad)}] * 2),
                    settings=generation_settings,
                )
                try:
                    generator.generate(question, chunks=hits)
                except SchemaValidationError:
                    negatives += 1
        return {
            "cases": 3,
            "negative_cases": 12,
            "retrieval_recall_at_3": retrieval_hits / 3,
            "groundedness_pass_rate": grounded / 3,
            "citation_accuracy": citations / 3,
            "unsupported_answer_rejection_rate": negatives / 12,
            "mode": "real_models_scripted_llm" if real_models else "deterministic",
        }


def passes(metrics: dict) -> bool:
    return (
        metrics.get("cases") == 3
        and metrics.get("negative_cases") == 12
        and all(
            metrics.get(key) == 1
            for key in (
                "retrieval_recall_at_3",
                "groundedness_pass_rate",
                "citation_accuracy",
                "unsupported_answer_rejection_rate",
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-models", action="store_true")
    args = parser.parse_args()
    try:
        # Capture third-party/model logs and diagnostics, including failures.
        with (
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            metrics = evaluate(args.real_models)
        success = passes(metrics)
        result = {
            "event": "rag_evaluation",
            "status": "passed" if success else "failed",
            **metrics,
        }
    except Exception:
        success = False
        result = {"event": "rag_evaluation", "status": "failed"}
    sys.stdout.write(json.dumps(result) + "\n")
    raise SystemExit(0 if success else 1)
