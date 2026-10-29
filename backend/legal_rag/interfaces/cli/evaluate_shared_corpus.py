"""Run the shared 32-case golden set against the selected corpus format.

By default uses the LLM provider configured in backend/.env (google / openai / groq).
Pass --provider extractive to force the keyword-extractive fallback path.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from legal_rag.composition import Container
from legal_rag.infrastructure.observability.logging import configure_logging
from legal_rag.infrastructure.settings import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[3]
ROOT = BACKEND_ROOT.parent
CORPUS_ROOT = BACKEND_ROOT / "data" / "shared-corpus"

FORMAT_DIRS = {
    "md": CORPUS_ROOT / "contracts",
    "docx": CORPUS_ROOT / "contracts-docx",
    "pdf": CORPUS_ROOT / "contracts-pdf",
}
_SOURCE_ID = re.compile(r"\b[A-Z]{2,4}-\d{4}-\d{3}(?:-\d{2})?\b")


def _contains_phrase(text: str, phrase: str) -> bool:
    words = " ".join(phrase.split()).split(" ")
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in words) + r"(?!\w)"
    return bool(re.search(pattern, text, re.IGNORECASE))


def _expected_sources(case: dict[str, Any]) -> set[str]:
    return set(_SOURCE_ID.findall(case.get("source_doc") or ""))


def _score(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    answer = result["answer"]
    sources = result.get("sources", [])
    source_ids = {source.get("document", "") for source in sources}
    expected_sources = _expected_sources(case)
    values = case.get("expected_values", [])
    matched_values = [value for value in values if _contains_phrase(answer, value)]
    missing_values = [value for value in values if value not in matched_values]
    source_match = expected_sources <= source_ids
    refusal_expected = case.get("refusal_expected", False)

    if refusal_expected and result.get("out_of_scope"):
        passed = True
    elif refusal_expected and not expected_sources and not values:
        passed = False
    else:
        passed = (
            not result.get("out_of_scope")
            and not missing_values
            and source_match
        )

    distractor_ids = set(_SOURCE_ID.findall(case.get("distractor_doc", "")))
    if passed:
        failure_type = None
    elif result.get("out_of_scope") and not refusal_expected:
        failure_type = "fail_false_refusal"
    elif distractor_ids.intersection(source_ids):
        failure_type = "fail_wrong_counterparty"
    elif (
        case.get("class") == "amendment_supersession"
        and case.get("superseded_value")
        and _contains_phrase(answer, case["superseded_value"])
        and missing_values
    ):
        failure_type = "fail_wrong_version"
    else:
        failure_type = "fail_hallucination"

    return {
        "id": case["id"],
        "class": case["class"],
        "passed": passed,
        "failure_type": failure_type,
        "matched_values": matched_values,
        "missing_values": missing_values,
        "expected_source_docs": sorted(expected_sources),
        "cited_source_docs": sorted(source_ids),
        "out_of_scope": result.get("out_of_scope", False),
        "answer": answer,
    }


def run(format_name: str, output_path: Path, force_provider: str | None = None) -> dict[str, Any]:
    corpus_dir = FORMAT_DIRS[format_name]
    golden_path = CORPUS_ROOT / "eval" / "golden_set.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = golden["cases"]
    if len(cases) != 32:
        raise ValueError(f"expected 32 golden cases, found {len(cases)}")

    configure_logging(level="WARNING")
    # Build Settings from .env so google_api_key is picked up automatically.
    # Override only the paths and — optionally — the provider.
    with TemporaryDirectory(prefix="legal-rag-shared-corpus-", ignore_cleanup_errors=True) as temp:
        settings_kwargs: dict[str, Any] = {
            "docs_dir": corpus_dir,
            "chroma_dir": Path(temp) / "chroma",
            "mcp_config_path": Path(temp) / "mcp.json",
            "api_key": None,
        }
        if force_provider is not None:
            settings_kwargs["llm_provider"] = force_provider
        settings = Settings(**settings_kwargs)
        container = Container(settings)
        chunk_count = container.ingestion_service.ingest()
        stored = container.vector_store.get_all()
        source_docs = sorted({meta["source_doc"] for meta in stored["metadatas"]})
        rows = []
        for i, case in enumerate(cases, 1):
            print(f"[{i:02d}/32] {case['id']}...", flush=True)
            answer = container.qa_service.answer(case["question"])
            score = _score(case, answer)
            status = "PASS" if score["passed"] else f"FAIL ({score['failure_type']})"
            print(f"[{i:02d}/32] {case['id']}: {status}", flush=True)
            rows.append(score)
            time.sleep(2.0)
        # Capture provider name BEFORE releasing the container (fixes use-after-delete bug).
        if container.llm_client is not None:
            provider_name = container.settings.llm_provider or "google"
        else:
            provider_name = "extractive"

    class_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        counts = class_counts.setdefault(row["class"], {"passed": 0, "total": 0})
        counts["total"] += 1
        counts["passed"] += int(row["passed"])
    failure_counts = {
        name: sum(row["failure_type"] == name for row in rows)
        for name in (
            "fail_wrong_version",
            "fail_wrong_counterparty",
            "fail_hallucination",
            "fail_false_refusal",
        )
    }
    report = {
        "corpus_format": format_name,
        "corpus_dir": str(corpus_dir.relative_to(ROOT)),
        "documents_ingested": len(source_docs),
        "source_docs": source_docs,
        "chunks_ingested": chunk_count,
        "provider": provider_name,
        "overall_pass_rate": {
            "passed": sum(row["passed"] for row in rows),
            "total": len(rows),
        },
        "by_class": class_counts,
        "failure_breakdown": failure_counts,
        "cases": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path = output_path.with_suffix(".md")
    class_order = (
        "direct_lookup",
        "amendment_supersession",
        "counterparty_disambiguation",
        "out_of_scope",
        "defined_term_chase",
        "multi_hop_dependent",
        "computation",
        "version_comparison",
        "cross_document",
    )
    lines = [
        "# Shared Corpus Golden Evaluation",
        "",
        f"Format: `{format_name}`; provider: `{report['provider']}`; documents: {report['documents_ingested']}; chunks: {chunk_count}.",
        f"Overall pass rate: **{report['overall_pass_rate']['passed']}/{report['overall_pass_rate']['total']}**",
        "",
        "## By class",
        "",
        "| Class | Passed | Total |",
        "|---|---:|---:|",
    ]
    for class_name in class_order:
        counts = class_counts.get(class_name, {"passed": 0, "total": 0})
        lines.append(f"| {class_name} | {counts['passed']} | {counts['total']} |")
    lines.extend([
        "",
        "## Failure breakdown",
        "",
        "| Failure | Count |",
        "|---|---:|",
    ])
    lines.extend(f"| {name} | {count} |" for name, count in failure_counts.items())
    lines.extend([
        "",
        "## Cases",
        "",
        "| Case | Class | Result | Failure | Answer |",
        "|---|---|---|---|---|",
    ])
    lines.extend(
        f"| {row['id']} | {row['class']} | {'PASS' if row['passed'] else 'FAIL'} | {row['failure_type'] or ''} | {row['answer'].replace('|', '\\|').replace(chr(10), '<br>')} |"
        for row in rows
    )
    lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Provider: {provider_name}")
    print(f"Overall pass rate: {report['overall_pass_rate']['passed']}/{report['overall_pass_rate']['total']}")
    for row in rows:
        status = "PASS" if row["passed"] else "FAIL"
        print(f"{row['id']} {status} {row['failure_type'] or ''}".rstrip())
    print(f"Report: {output_path}")
    print(f"Markdown: {markdown_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=sorted(FORMAT_DIRS), default="md")
    parser.add_argument(
        "--output", type=Path, default=BACKEND_ROOT / "data" / "evaluation" / "generated" / "shared_corpus_report.json"
    )
    parser.add_argument(
        "--provider",
        choices=["google", "openai", "groq", "extractive"],
        default=None,
        help=(
            "Override the LLM provider from .env. "
            "Omit to use whatever is set in backend/.env (default: google). "
            "Pass 'extractive' to force the keyword-only path."
        ),
    )
    args = parser.parse_args()
    run(args.format, args.output, force_provider=args.provider)


if __name__ == "__main__":
    main()
