"""Install a checksum-pinned actionlint executable without extracting arbitrary paths."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.7.7"
ASSETS = {
    "Linux": (
        "linux_amd64.tar.gz",
        "023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757",
    ),
    "Windows": (
        "windows_amd64.zip",
        "7f12f1801bca3d480d67aaf7774f4c2a6359a3ca8eebe382c95c10c9704aa731",
    ),
}


def verify_archive(content: bytes, checksum: str) -> None:
    if hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError("actionlint archive checksum mismatch")


def download_archive(url: str) -> bytes:
    """Retry transient release-host failures; verification errors are never retried."""
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read(20 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == 3:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(attempt)
    raise RuntimeError("actionlint download retries exhausted")


def install(destination: Path) -> Path:
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("actionlint installer supports x86-64 hosts")
    asset, checksum = ASSETS[platform.system()]
    url = f"https://github.com/rhysd/actionlint/releases/download/v{VERSION}/actionlint_{VERSION}_{asset}"
    content = download_archive(url)
    verify_archive(content, checksum)
    binary = "actionlint.exe" if platform.system() == "Windows" else "actionlint"
    if binary.endswith(".exe"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            payload = archive.read(binary)
    else:
        with tarfile.open(fileobj=io.BytesIO(content)) as archive:
            member = archive.getmember(binary)
            if not member.isfile():
                raise ValueError("actionlint binary is not a regular file")
            payload = archive.extractfile(member).read()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / binary
    target.write_bytes(payload)
    target.chmod(0o755)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        install(args.destination)
    except Exception:
        sys.stdout.write(json.dumps({"event": "actionlint_install", "status": "failed"}) + "\n")
        raise SystemExit(1) from None
    sys.stdout.write(
        json.dumps({"event": "actionlint_install", "version": VERSION, "status": "verified"}) + "\n"
    )
