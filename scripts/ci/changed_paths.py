"""Select CI jobs without printing changed filenames or document contents."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOBS = ("backend", "frontend", "workflows", "security", "rag")


def select_jobs(paths: list[str]) -> dict[str, bool]:
    selected = dict.fromkeys(JOBS, False)
    for path in paths:
        if path.startswith((".github/", "scripts/ci/")):
            return dict.fromkeys(JOBS, True)
        if path.startswith(("backend/", "scripts/evaluation/")) or path in {
            "Makefile",
            "docker-compose.yml",
        }:
            for job in ("backend", "rag", "security"):
                selected[job] = True
        if path.startswith("frontend/") or path == "docker-compose.yml":
            selected["frontend"] = True
    return selected


def changed_jobs() -> dict[str, bool]:
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        return {name: name == "security" for name in JOBS}
    if os.environ.get("GITHUB_EVENT_NAME") in {"workflow_dispatch", "merge_group"}:
        return dict.fromkeys(JOBS, True)
    base = os.environ.get("BASE_SHA", "")
    if not re.fullmatch(r"[a-fA-F0-9]{40,64}", base) or set(base) == {"0"}:
        return dict.fromkeys(JOBS, True)
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", base, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        return dict.fromkeys(JOBS, True)  # Missing/shallow history must not bypass validation.
    return select_jobs(result.stdout.decode("utf-8", errors="replace").strip("\0").split("\0"))


if __name__ == "__main__":
    selected = changed_jobs()
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(
                "".join(f"{name}={str(enabled).lower()}\n" for name, enabled in selected.items())
            )
