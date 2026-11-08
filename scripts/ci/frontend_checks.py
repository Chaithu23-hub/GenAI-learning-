"""Run the existing npm checks without forwarding console output or build values."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def summarize(result: subprocess.CompletedProcess, check: str) -> dict:
    return {
        "event": "frontend_check",
        "check": check,
        "status": "passed" if result.returncode == 0 else "failed",
    }


def run(check: str) -> dict:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        raise RuntimeError("npm is unavailable")
    commands = {
        "install": ["ci"],
        "build": ["run", "build", "--", "--configuration", "production"],
        "test": ["test", "--", "--watch=false", "--browsers=ChromeHeadless"],
    }
    environment = {**os.environ, "LEGAL_RAG_API_KEY": ""}
    result = subprocess.run(
        [npm, *commands[check]],
        cwd=ROOT / "frontend",
        env=environment,
        capture_output=True,
        timeout=600,
    )
    return summarize(result, check)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=["install", "build", "test"], required=True)
    args = parser.parse_args()
    try:
        result = run(args.check)
    except Exception:
        result = {"event": "frontend_check", "check": args.check, "status": "failed"}
    sys.stdout.write(json.dumps(result) + "\n")
    raise SystemExit(0 if result["status"] == "passed" else 1)
