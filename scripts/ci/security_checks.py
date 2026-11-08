"""Static, installed-dependency and high-confidence credential gates; no raw reports."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = (
    rb"\b(?:gsk_|gh[pousr]_)[A-Za-z0-9_]{25,}\b",
    rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b",
    rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)

# User-approved on 2026-11-08: deployment applicability, not an upstream Chroma patch.
# Do not regenerate this fingerprint to make CI green without a fresh scope review.
REVIEWED_SCOPE_SHA256 = "f251522ac241e0fe581c166f588ef87e078ed95b8775b55f7b25a0ab906b6b42"
ASSESSMENT_EXPIRES = date(2026, 12, 8)
CHROMA_ADVISORY_GROUPS = (
    frozenset({"PYSEC-2026-311", "GHSA-f4j7-r4q5-qw2c", "CVE-2026-45829"}),
    frozenset({"PYSEC-2026-3813", "GHSA-2wm9-hf6c-p5cr", "CVE-2026-45830"}),
    frozenset({"PYSEC-2026-3814", "GHSA-36p7-vc44-83pf", "CVE-2026-45833"}),
    frozenset({"PYSEC-2026-3815", "GHSA-xph7-9rjv-w5fr", "CVE-2026-45831"}),
)
_ADVISORY_ID = re.compile(r"(?:PYSEC-\d{4}-\d+|CVE-\d{4}-\d+|GHSA-[a-z0-9]{4}(?:-[a-z0-9]{4}){2})")


def scope_paths(root: Path) -> set[Path]:
    """Enumerate runtime sources, dependencies and deployment entry points."""
    required = (
        "backend/Dockerfile",
        "backend/.dockerignore",
        "frontend/Dockerfile",
        "frontend/.dockerignore",
        "docker-compose.yml",
        "Makefile",
        "backend/mcp_servers.json",
        "backend/pyproject.toml",
        "backend/requirements.txt",
        "backend/requirements-dev.txt",
        "frontend/nginx.conf",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/angular.json",
        ".github/requirements-ci.txt",
        ".github/workflows/ci.yml",
        ".github/workflows/rag-evaluation.yml",
        ".github/actions/setup-backend/action.yml",
    )
    paths = {root / name for name in required}
    for directory in (
        "backend/legal_rag",
        ".github/workflows",
        ".github/actions",
        "frontend/scripts",
    ):
        base = root / directory
        if not base.is_dir():
            raise ValueError("Reviewed scope is missing")
        paths.update(
            path
            for path in base.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        )
    paths.update((root / "backend").glob("requirements*.txt"))
    paths.update((root / "backend").glob("*.py"))
    paths.update(
        path
        for path in root.iterdir()
        if path.is_file() and re.fullmatch(r"(?:docker-)?compose(?:\.override)?\.ya?ml", path.name)
    )
    return paths


def scope_fingerprint(root: Path) -> str:
    """Bind applicability to the exact reviewed topology across LF/CRLF checkouts."""
    digest = hashlib.sha256()
    for path in sorted(scope_paths(root), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def assessment_state(today: date) -> dict:
    assessment = {"owner": "Chaithu23-hub", "expires": ASSESSMENT_EXPIRES.isoformat()}
    if today >= ASSESSMENT_EXPIRES:
        assessment["scope_status"] = "expired"
    else:
        try:
            matches = scope_fingerprint(ROOT) == REVIEWED_SCOPE_SHA256
            assessment["scope_status"] = "verified" if matches else "scope_changed"
        except (OSError, ValueError):
            assessment["scope_status"] = "unavailable"
    return assessment


def dependency_summary(
    data: object, returncode: int, packages: list[tuple[str, str]], *, today: date | None = None
) -> dict:
    """Keep findings visible; fail closed outside the exact approved deployment."""
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    summary = {
        "check": "dependency_advisories",
        "findings": 0,
        "assessed_non_applicable": 0,
        "blocking_findings": 0,
        "unassessed": 0,
        "advisories": [],
        "status": "failed",
    }
    assessment = assessment_state(today if today is not None else datetime.now(UTC).date())
    summary["assessment"] = assessment
    try:
        if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
            raise ValueError("Invalid audit result")
        expected = {canonicalize_name(name): Version(version).public for name, version in packages}
        if not expected or len(expected) != len(packages):
            raise ValueError("Invalid installed manifest")
        seen = set()
        findings = {}
        for dependency in data["dependencies"]:
            if not isinstance(dependency, dict) or not isinstance(dependency.get("name"), str):
                raise ValueError("Invalid dependency result")
            name = canonicalize_name(dependency["name"])
            if name in seen or name not in expected:
                raise ValueError("Unexpected or duplicate dependency")
            seen.add(name)
            if dependency.get("skip_reason"):
                summary["unassessed"] += 1
                continue
            version = dependency.get("version")
            if version != expected[name] or not isinstance(dependency.get("vulns"), list):
                raise ValueError("Incomplete dependency result")
            for vulnerability in dependency["vulns"]:
                if not isinstance(vulnerability, dict):
                    raise ValueError("Invalid advisory")
                identity = vulnerability.get("id")
                aliases = vulnerability.get("aliases")
                fixes = vulnerability.get("fix_versions")
                if (
                    not isinstance(identity, str)
                    or not _ADVISORY_ID.fullmatch(identity)
                    or not isinstance(aliases, list)
                    or not all(isinstance(alias, str) for alias in aliases)
                    or not isinstance(fixes, list)
                    or not all(isinstance(fix, str) for fix in fixes)
                ):
                    raise ValueError("Invalid advisory metadata")
                group = next(
                    (
                        group
                        for group in CHROMA_ADVISORY_GROUPS
                        if identity in group and set(aliases) <= group
                    ),
                    None,
                )
                approved = (
                    name == "chromadb"
                    and version == "1.5.9"
                    and group is not None
                    and not fixes
                    and assessment["scope_status"] == "verified"
                )
                canonical_id = (
                    next((alias for alias in sorted(group) if alias.startswith("GHSA-")), identity)
                    if group
                    else identity
                )
                key = (name, canonical_id)
                disposition = "assessed_non_applicable" if approved else "blocking"
                if key in findings and findings[key]["disposition"] == "blocking":
                    disposition = "blocking"
                findings[key] = {
                    "package": name,
                    "version": version,
                    "id": canonical_id,
                    "disposition": disposition,
                }
        summary["advisories"] = [findings[key] for key in sorted(findings)]
        summary["findings"] = len(findings)
        summary["assessed_non_applicable"] = sum(
            row["disposition"] == "assessed_non_applicable" for row in findings.values()
        )
        summary["blocking_findings"] = len(findings) - summary["assessed_non_applicable"]
        # pip-audit uses 1 for findings, 0 for a clean report; other codes are errors.
        valid = (
            seen == set(expected)
            and not summary["unassessed"]
            and returncode == (1 if findings else 0)
            and not summary["blocking_findings"]
        )
        summary["status"] = "passed" if valid else "failed"
    except (TypeError, ValueError):
        summary["reason"] = "invalid_audit_result"
    return summary


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
    packages = [
        (distribution.metadata["Name"], distribution.version)
        for distribution in importlib.metadata.distributions()
    ]
    requirements, local_versions = auditable_requirements(packages)
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
    dependency_check = dependency_summary(json.loads(audit.stdout), audit.returncode, packages)
    dependency_check["local_version_mappings"] = local_versions
    checks.append(dependency_check)
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
