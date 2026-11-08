"""Run pytest with content-safe aggregate output, including on collection failure."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def summarize(result: subprocess.CompletedProcess, suite: str) -> dict:
    counts = {}
    for category in ("passed", "failed", "error", "errors", "skipped", "deselected"):
        matches = re.findall(rf"\b(\d+) {category}\b", result.stdout or "")
        if matches:
            counts[category] = int(matches[-1])
    return {
        "event": "pytest",
        "suite": suite,
        "status": "passed" if result.returncode == 0 and counts.get("passed", 0) else "failed",
        **counts,
    }


def run(suite: str = "backend") -> dict:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-m",
        "not slow",
        "-q",
        "--tb=no",
        "--show-capture=no",
        "--no-summary",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
    )
    return summarize(result, suite)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["backend"], default="backend")
    args = parser.parse_args()
    try:
        summary = run(args.suite)
    except Exception:
        summary = {"event": "pytest", "suite": args.suite, "status": "failed"}
    sys.stdout.write(json.dumps(summary) + "\n")
    raise SystemExit(0 if summary["status"] == "passed" else 1)
