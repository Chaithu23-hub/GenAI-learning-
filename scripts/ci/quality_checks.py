"""Quality gate without logging source snippets, strings, or raw diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run() -> list[dict]:
    commands = {
        "lint": [
            "ruff",
            "check",
            "--config",
            "pyproject.toml",
            "legal_rag",
            "tests",
            "../scripts",
        ],
        "format": [
            "ruff",
            "format",
            "--config",
            "pyproject.toml",
            "--check",
            "legal_rag",
            "tests",
            "../scripts",
        ],
        "types": [
            "mypy",
            "legal_rag/domain",
            "legal_rag/application/ports.py",
            "--ignore-missing-imports",
            "--follow-imports=skip",
        ],
    }
    results = []
    for name, command in commands.items():
        process = subprocess.run(
            [sys.executable, "-m", *command],
            cwd=ROOT / "backend",
            capture_output=True,
            timeout=180,
        )
        results.append({"check": name, "status": "passed" if process.returncode == 0 else "failed"})
    return results


if __name__ == "__main__":
    try:
        results = run()
    except Exception:
        results = [{"check": "quality", "status": "failed"}]
    sys.stdout.write(json.dumps({"event": "quality_checks", "checks": results}) + "\n")
    raise SystemExit(0 if all(row["status"] == "passed" for row in results) else 1)
