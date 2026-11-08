"""Fail closed on workflow privilege, cache and output-policy regressions."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class WorkflowLoader(yaml.SafeLoader):
    """YAML 1.2 booleans, so the Actions `on` key is never parsed as True."""


WorkflowLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for initial, resolvers in WorkflowLoader.yaml_implicit_resolvers.items():
    WorkflowLoader.yaml_implicit_resolvers[initial] = [
        item for item in resolvers if item[0] != "tag:yaml.org,2002:bool"
    ]
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF")
)


def inspect_workflow(data: dict) -> list[str]:
    failures = []
    if data.get("name") == "CI":
        changes = data.get("jobs", {}).get("changes", {})
        if changes.get("if") or not any(
            "security_checks.py --credentials-only" in step.get("run", "") and not step.get("if")
            for step in changes.get("steps", [])
        ):
            failures.append("missing-credential-gate")
    triggers = data.get("on", {})
    if isinstance(triggers, str):
        triggers = {triggers: {}}
    if set(triggers or {}) & {"pull_request_target", "workflow_run", "issue_comment"}:
        failures.append("privileged-trigger")
    if "permissions" not in data:
        failures.append("implicit-permissions")
    if "concurrency" not in data:
        failures.append("missing-concurrency")
    scopes = [data.get("permissions", {})]
    for job in data.get("jobs", {}).values():
        scopes.append(job.get("permissions", {}))
        if "uses" in job:
            continue
        if not isinstance(job.get("timeout-minutes"), int):
            failures.append("missing-timeout")
        runner = job.get("runs-on", "")
        if "self-hosted" in str(runner) or runner not in {
            "ubuntu-24.04",
            "ubuntu-latest",
        }:
            failures.append("persistent-runner")
        failures.extend(inspect_steps(job.get("steps", [])))
    for permissions in scopes:
        if isinstance(permissions, str) or any(value == "write" for value in permissions.values()):
            failures.append("write-permission")
    if re.search(r"\$\{\{\s*secrets\.", json.dumps(data)):
        failures.append("secret-binding")
    return sorted(set(failures))


def inspect_steps(steps: list[dict]) -> list[str]:
    failures = []
    for step in steps:
        action = step.get("uses", "")
        if (
            action
            and not action.startswith("./")
            and not re.fullmatch(r"[\w.-]+/[\w./-]+@[a-f0-9]{40}", action)
        ):
            failures.append("unpinned-action")
        if (
            action.startswith("actions/checkout@")
            and step.get("with", {}).get("persist-credentials") is not False
        ):
            failures.append("persisted-credentials")
        if action.startswith(("actions/upload-artifact@", "actions/download-artifact@")):
            failures.append("artifact-export")
        if action.startswith("actions/cache@") and re.search(
            r"data|document|chroma|huggingface|\.env",
            str(step.get("with", {}).get("path", "")),
            re.I,
        ):
            failures.append("sensitive-cache")
        if re.search(
            r"\$\{\{[^}]*\b(?:github\.event\.|github\.head_ref|inputs\.)",
            step.get("run", ""),
        ):
            failures.append("script-interpolation")
    return failures


def main() -> int:
    results = []
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        try:
            data = yaml.load(path.read_text(encoding="utf-8"), Loader=WorkflowLoader)
            failures = inspect_workflow(data)
        except Exception:
            failures = ["invalid-workflow"]
        results.append({"file": path.name, "rules": failures})
    for path in sorted((ROOT / ".github/actions").glob("*/action.yml")):
        try:
            data = yaml.load(path.read_text(encoding="utf-8"), Loader=WorkflowLoader)
            failures = inspect_steps(data.get("runs", {}).get("steps", []))
        except Exception:
            failures = ["invalid-action"]
        results.append({"file": path.parent.name, "rules": failures})
    sys.stdout.write(json.dumps({"event": "workflow_policy", "checks": results}) + "\n")
    return int(not results or any(row["rules"] for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
