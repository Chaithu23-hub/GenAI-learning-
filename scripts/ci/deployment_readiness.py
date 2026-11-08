"""Check local packaging prerequisites without inventing deployment infrastructure."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def readiness(validate_docker: bool = False) -> dict:
    required = (
        "backend/Dockerfile",
        "frontend/Dockerfile",
        "docker-compose.yml",
        "backend/.dockerignore",
        "frontend/.dockerignore",
    )
    packaging = all((ROOT / name).is_file() for name in required)
    checks = []
    if validate_docker and packaging:
        commands = {
            "compose": [
                "docker",
                "compose",
                "config",
                "--no-env-resolution",
                "--no-interpolate",
                "--quiet",
            ],
            "backend_dockerfile": ["docker", "build", "--check", "backend"],
            "frontend_dockerfile": ["docker", "build", "--check", "frontend"],
        }
        for name, command in commands.items():
            try:
                result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=180)
                passed = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                passed = False
            checks.append({"check": name, "status": "passed" if passed else "failed"})
    valid = packaging and all(check["status"] == "passed" for check in checks)
    return {
        "event": "deployment_readiness",
        "packaging_files_present": packaging,
        "deployment_enabled": False,
        "cloud_target_verified": False,
        "credentials_verified": False,
        "checks": checks,
        "status": "configuration_required" if valid else "failed",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-docker", action="store_true")
    args = parser.parse_args()
    result = readiness(args.validate_docker)
    sys.stdout.write(json.dumps(result) + "\n")
    raise SystemExit(0 if result["status"] == "configuration_required" else 1)
