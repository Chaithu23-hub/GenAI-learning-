"""Static, installed-dependency and high-confidence credential gates; no raw reports."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = (
    rb"\b(?:gsk_|gh[pousr]_)[A-Za-z0-9_]{25,}\b",
    rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b",
    rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)


def auditable_requirements(packages: list[tuple[str, str]]) -> tuple[list[str], int]:
    from packaging.version import Version

    requirements, mapped = [], 0
    for name, version in packages:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ValueError("Invalid dependency metadata")
        parsed = Version(version)
        mapped += parsed.local is not None
        requirements.append(f"{name}=={parsed.public}")
    return requirements, mapped


def credential_findings() -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, timeout=30
    )
    count = 0
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        # Training/reference skills contain deliberate security examples.
        if name.startswith(".agents/skills/"):
            continue
        path = ROOT / name
        if path.name == ".env" or (
            path.name.startswith(".env.") and not path.name.endswith(".example")
        ):
            count += 1
        if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
            data = path.read_bytes()
            count += any(re.search(pattern, data) for pattern in PATTERNS)
    return count


def run() -> list[dict]:
    checks = []
    static = subprocess.run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            "legal_rag",
            "-ll",
            "-ii",
            "-q",
            "-f",
            "json",
        ],
        cwd=ROOT / "backend",
        capture_output=True,
        timeout=180,
    )
    checks.append({"check": "bandit", "status": "passed" if static.returncode == 0 else "failed"})
    requirements, local_versions = auditable_requirements(
        [
            (distribution.metadata["Name"], distribution.version)
            for distribution in importlib.metadata.distributions()
        ]
    )
    # Audit the installed package versions without resolving/installing an
    # alternate environment. Local wheel suffixes (e.g. +cpu) map to the public
    # release's advisory identity; this does not attest a custom wheel's bytes.
    with tempfile.TemporaryDirectory(prefix="ci-audit-") as directory:
        manifest = Path(directory) / "requirements.txt"
        manifest.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        audit = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--requirement",
                str(manifest),
                "--no-deps",
                "--disable-pip",
                "--progress-spinner",
                "off",
                "--format",
                "json",
            ],
            cwd=ROOT,
            capture_output=True,
            timeout=600,
        )
    vulnerabilities = json.loads(audit.stdout).get("dependencies", [])
    findings = {
        (dependency["name"], vulnerability["id"])
        for dependency in vulnerabilities
        for vulnerability in dependency.get("vulns", [])
    }
    skipped = sum(bool(dependency.get("skip_reason")) for dependency in vulnerabilities)
    checks.append(
        {
            "check": "dependency_advisories",
            "findings": len(findings),
            "unassessed": skipped,
            "local_version_mappings": local_versions,
            "status": "passed" if audit.returncode == 0 and not skipped else "failed",
        }
    )
    secrets = credential_findings()
    checks.append(
        {
            "check": "credential_patterns",
            "findings": secrets,
            "status": "passed" if secrets == 0 else "failed",
        }
    )
    return checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.credentials_only:
            findings = credential_findings()
            checks = [
                {
                    "check": "credential_patterns",
                    "findings": findings,
                    "status": "passed" if findings == 0 else "failed",
                }
            ]
        else:
            checks = run()
    except Exception:
        checks = [{"check": "security", "status": "failed"}]
    sys.stdout.write(json.dumps({"event": "security_checks", "checks": checks}) + "\n")
    raise SystemExit(0 if all(check["status"] == "passed" for check in checks) else 1)
