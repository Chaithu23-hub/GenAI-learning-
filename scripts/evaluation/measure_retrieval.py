"""Offline developer comparison; no model downloads, API calls, or persistent index.

Run: .venv/Scripts/python.exe scripts/evaluation/measure_retrieval.py --output <report.json>
The baseline loads the committed retrieval/chunking/lexical implementations.
Those three files were unchanged at the start of the 2026-11-08 review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from legal_rag.application.workflows.evaluation import EVALUATION_CASES, EvaluationService  # noqa: E402
from legal_rag.application.workflows.retrieval import RetrievalService, RetrievalSettings  # noqa: E402
from legal_rag.domain.clauses import DOCUMENT_ID_RE  # noqa: E402
from legal_rag.domain.entities import IndexedChunk  # noqa: E402
from legal_rag.infrastructure.chunking.section_chunker import chunk_document  # noqa: E402
from legal_rag.infrastructure.documents.shared_corpus_loader import load_document  # noqa: E402
from legal_rag.infrastructure.observability.logging import configure_logging, get_logger  # noqa: E402
from legal_rag.infrastructure.vector_store.chroma import ChromaVectorStore  # noqa: E402
from tests.fakes.embedder import HashEmbedder  # noqa: E402
from tests.fakes.reranker import ScoringReranker  # noqa: E402
from tests.fakes.vector_store import InMemoryVectorStore  # noqa: E402

log = get_logger(__name__)
PATHS = {
    "retrieval": "backend/legal_rag/application/workflows/retrieval.py",
    "chunking": "backend/legal_rag/infrastructure/chunking/section_chunker.py",
    "lexical": "backend/legal_rag/infrastructure/vector_store/chroma.py",
    "evaluation": "backend/legal_rag/application/workflows/evaluation.py",
}


def baseline_module(name: str, revision: str):
    source = subprocess.run(
        ["git", "show", f"{revision}:{PATHS[name]}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout
    module_name = f"_review_baseline_{name}"
    module = types.ModuleType(module_name)
    module.__file__ = f"{revision}:{PATHS[name]}"
    sys.modules[module_name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module, hashlib.sha256(source.encode()).hexdigest()


class OfflineStore(InMemoryVectorStore):
    """Real BM25 adapter over in-memory persistence, hash-vector dense search."""

    def __init__(self, adapter_class):
        super().__init__()
        self.lexical = adapter_class(Path("unused-offline-index"))
        self.lexical._collection = self

    def get(self, *, include, where=None):
        if where and "$and" in where:
            where = {key: value for condition in where["$and"] for key, value in condition.items()}
        return self.get_all(where=where)

    def keyword_search(self, query, *, k, where=None):
        return self.lexical.keyword_search(query, k=k, where=where)


def pipeline(documents, chunker, retrieval_class, settings_class, adapter_class):
    embedder = HashEmbedder()
    store = OfflineStore(adapter_class)
    indexed = []
    for document in documents:
        source = document.metadata["source_doc"]
        for chunk in chunker(document.text):
            indexed.append(
                IndexedChunk(
                    f"{source}::{chunk.index:03d}",
                    chunk.text,
                    chunk.heading,
                    chunk.index,
                    document.name,
                    document.document_type,
                    {**document.metadata, "clause_ref": chunk.heading},
                )
            )
    store.upsert(indexed, embedder.embed([row.text for row in indexed]))
    retrieval = retrieval_class(
        vector_store=store,
        embedder=embedder,
        reranker=ScoringReranker(),
        settings=settings_class(20, 8, True, 60),
    )
    return store, retrieval


def golden_source_metrics(retrieval):
    golden = json.loads(
        (ROOT / "backend/data/shared-corpus/eval/golden_set.json").read_text(encoding="utf-8")
    )
    rows = []
    for case in golden["cases"]:
        expected = {
            match.group().upper() for match in DOCUMENT_ID_RE.finditer(case.get("source_doc") or "")
        }
        if case.get("refusal_expected") or not expected:
            continue
        query = case["question"]
        hits = retrieval.retrieve(query, n=8, where=retrieval.detect_metadata_filter(query))
        sources = {hit.document for hit in hits}
        rows.append(
            {
                "id": case["id"],
                "source_recall": len(expected & sources) / len(expected),
                "all_sources_found": expected <= sources,
                "returned_chunk_ids": [hit.chunk_id for hit in hits],
            }
        )
    return {
        "positive_cases": len(rows),
        "mean_source_recall_at_8": statistics.mean(row["source_recall"] for row in rows),
        "all_sources_rate_at_8": statistics.mean(row["all_sources_found"] for row in rows),
        "cases": rows,
    }


def lexical_benchmark(before_class):
    documents = [
        f"document {index} " + "payment interest liability insurance notice " * 36
        for index in range(400)
    ]

    class Collection:
        def get(self, **kwargs):
            return {
                "ids": [str(index) for index in range(len(documents))],
                "documents": documents,
                "metadatas": [{} for _ in documents],
            }

    outcomes = []
    for adapter_class in (before_class, ChromaVectorStore):
        adapter = adapter_class(Path("unused-offline-index"))
        adapter._collection = Collection()
        adapter.keyword_search("payment notice", k=20)  # Warmup outside timings.
        durations, rankings = [], []
        for _ in range(30):
            started = time.perf_counter()
            rankings.append([hit["id"] for hit in adapter.keyword_search("payment notice", k=20)])
            durations.append((time.perf_counter() - started) * 1000)
        outcomes.append((statistics.median(durations), rankings))
    return {
        "documents": 400,
        "queries": 30,
        "basis": "adapter CPU only; in-memory collection",
        "before_median_ms": outcomes[0][0],
        "after_median_ms": outcomes[1][0],
        "identical_rankings": outcomes[0][1] == outcomes[1][1],
    }


def run(output: Path, baseline: str = "HEAD"):
    revision = subprocess.run(
        ["git", "rev-parse", baseline], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    modules, hashes = {}, {}
    for name in PATHS:
        modules[name], hashes[name] = baseline_module(name, revision)
    documents = [
        load_document(path).to_entity()
        for path in sorted(
            (ROOT / "backend/data/shared-corpus/contracts").glob("*.md"),
        )
    ]
    old_store, old_retrieval = pipeline(
        documents,
        modules["chunking"].chunk_document,
        modules["retrieval"].RetrievalService,
        modules["retrieval"].RetrievalSettings,
        modules["lexical"].ChromaVectorStore,
    )
    new_store, new_retrieval = pipeline(
        documents,
        chunk_document,
        RetrievalService,
        RetrievalSettings,
        ChromaVectorStore,
    )
    legacy_ids = set().union(
        *(case.relevant_chunk_ids for case in modules["evaluation"].EVALUATION_CASES)
    )
    target_count = sum(len(case.relevant_clauses) for case in EVALUATION_CASES)
    report = {
        "basis": "offline hash embeddings and token-overlap reranker; no LLM",
        "baseline_revision": revision,
        "baseline_code_sha256": hashes,
        "current_code_sha256": {
            name: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for name, path in PATHS.items()
        },
        "corpus_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "backend/data/shared-corpus/contracts").glob("*.md"))
        },
        "quality_warning": "Source retrieval coverage is not answer correctness or real-model quality.",
        "before": {
            "documents": len(documents),
            "chunks": len(old_store.get_all()["ids"]),
            "default_label_ids_found": len(legacy_ids & set(old_store.get_all()["ids"])),
            "same_current_clause_labels": EvaluationService(
                retrieval=old_retrieval,
                vector_store=old_store,
            ).compare_retrieval(k=8),
            "golden_sources": golden_source_metrics(old_retrieval),
        },
        "after": {
            "documents": len(documents),
            "chunks": len(new_store.get_all()["ids"]),
            "validated_clause_targets": target_count,
            "same_current_clause_labels": EvaluationService(
                retrieval=new_retrieval,
                vector_store=new_store,
            ).compare_retrieval(k=8),
            "golden_sources": golden_source_metrics(new_retrieval),
        },
        "lexical_benchmark": lexical_benchmark(modules["lexical"].ChromaVectorStore),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log.info("offline retrieval review written", extra={"output": str(output)})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--baseline", default="HEAD", help="Commit supplying original retrieval code"
    )
    arguments = parser.parse_args()
    configure_logging(level="INFO")
    run(arguments.output, arguments.baseline)
