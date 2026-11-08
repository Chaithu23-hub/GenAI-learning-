"""Development evaluation uses disposable in-memory indices and no model APIs."""

import json
import subprocess
import sys
from pathlib import Path


def test_offline_review_labels_exist_and_bm25_rankings_are_preserved(tmp_path):
    root = Path(__file__).resolve().parents[3]
    report = tmp_path / "review.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/evaluation/measure_retrieval.py"),
            "--output",
            str(report),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["basis"] == "offline hash embeddings and token-overlap reranker; no LLM"
    assert data["before"]["documents"] == data["after"]["documents"] == 6
    assert data["before"]["default_label_ids_found"] == 0
    assert data["after"]["validated_clause_targets"] == 7
    assert data["lexical_benchmark"]["identical_rankings"] is True
    assert data["lexical_benchmark"]["queries"] == 30
