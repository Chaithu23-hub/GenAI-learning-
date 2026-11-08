"""CI regression checks execute policy and evaluation tools with synthetic data."""

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import time
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load_tool(name):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"ci_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "paths,expected",
    [
        (["README.md"], set()),
        (["backend/legal_rag/domain/entities.py"], {"backend", "rag", "security"}),
        (["frontend/src/app/app.component.ts"], {"frontend"}),
        ([".github/workflows/ci.yml"], {"backend", "frontend", "workflows", "security", "rag"}),
        (["backend/requirements.txt"], {"backend", "rag", "security"}),
        (["scripts/evaluation/measure_retrieval.py"], {"backend", "rag", "security"}),
    ],
)
def test_changed_paths_selects_required_jobs_without_exposing_filenames(paths, expected):
    selected = load_tool("changed_paths").select_jobs(paths)
    assert {name for name, enabled in selected.items() if enabled} == expected


def minimal_workflow():
    return {
        "on": {"pull_request": {}},
        "permissions": {"contents": "read"},
        "concurrency": {"group": "ci", "cancel-in-progress": True},
        "jobs": {
            "test": {
                "runs-on": "ubuntu-24.04",
                "timeout-minutes": 10,
                "steps": [
                    {
                        "uses": "actions/checkout@" + "a" * 40,
                        "with": {"persist-credentials": False},
                    },
                ],
            }
        },
    }


@pytest.mark.parametrize(
    "mutation,rule",
    [
        (lambda data: data.update({"on": {"pull_request_target": {}}}), "privileged-trigger"),
        (lambda data: data.update({"permissions": {"contents": "write"}}), "write-permission"),
        (
            lambda data: data["jobs"]["test"]["steps"][0].update({"uses": "actions/checkout@v4"}),
            "unpinned-action",
        ),
        (lambda data: data["jobs"]["test"].update({"runs-on": "self-hosted"}), "persistent-runner"),
    ],
)
def test_workflow_policy_rejects_real_trust_boundary_regressions(mutation, rule):
    workflow = minimal_workflow()
    mutation(workflow)
    assert rule in load_tool("check_workflows").inspect_workflow(workflow)


def test_hardened_workflow_is_accepted():
    assert load_tool("check_workflows").inspect_workflow(minimal_workflow()) == []


def test_main_ci_cannot_omit_the_always_on_lightweight_credential_gate():
    workflow = minimal_workflow()
    workflow["name"] = "CI"
    workflow["jobs"]["changes"] = workflow["jobs"].pop("test")
    assert "missing-credential-gate" in load_tool("check_workflows").inspect_workflow(workflow)


@pytest.mark.parametrize("filename", ["README.md", ".env", "frontend/environment.ts"])
def test_credentials_are_detected_outside_backend_paths(tmp_path, filename):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
    target = tmp_path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("gsk_" + "SYNTHETIC" * 5, encoding="utf-8")
    subprocess.run(["git", "add", "--", filename], cwd=tmp_path, check=True, capture_output=True)
    tool = load_tool("security_checks")
    tool.ROOT = tmp_path
    assert tool.credential_findings() >= 1


def test_cpu_wheels_are_mapped_to_public_advisory_versions_not_skipped():
    requirements, mapped = load_tool("security_checks").auditable_requirements(
        [("torch", "2.15.0+cpu"), ("chromadb", "1.5.9")]
    )
    assert requirements == ["torch==2.15.0", "chromadb==1.5.9"]
    assert mapped == 1


def test_dependency_metadata_cannot_inject_a_requirement_option():
    with pytest.raises(ValueError):
        load_tool("security_checks").auditable_requirements([("unsafe\n--index-url", "1.0")])


def test_synthetic_rag_evaluation_gates_all_three_requirements():
    tool = load_tool("evaluate_rag")
    metrics = tool.evaluate()
    assert metrics["retrieval_recall_at_3"] == 1
    assert metrics["groundedness_pass_rate"] == 1
    assert metrics["citation_accuracy"] == 1
    assert tool.passes(metrics)
    assert not tool.passes({**metrics, "citation_accuracy": 0.5})


def test_rag_gate_rejects_corrupted_indexed_facts_instead_of_using_them_as_ground_truth():
    from dataclasses import replace

    tool = load_tool("evaluate_rag")
    original_chunker = tool.SectionChunker

    class CorruptingChunker:
        def chunk(self, *args, **kwargs):
            return [
                replace(chunk, text=chunk.text.replace("1.0%", "9.0%"))
                for chunk in original_chunker().chunk(*args, **kwargs)
            ]

    tool.SectionChunker = CorruptingChunker
    assert not tool.passes(tool.evaluate())


def test_ci_output_does_not_forward_failure_text_or_document_content(tmp_path):
    tool = load_tool("run_tests")
    failed = subprocess.CompletedProcess(
        [], 1, stdout="SECRET_DOCUMENT_CANARY", stderr="PRIVATE_KEY_CANARY"
    )
    summary = tool.summarize(failed, "backend")
    assert summary["status"] == "failed"
    assert "CANARY" not in json.dumps(summary)


def test_frontend_diagnostics_do_not_forward_keys_or_console_messages():
    result = subprocess.CompletedProcess([], 1, "FRONTEND_KEY_CANARY", "DOC_CANARY")
    summary = load_tool("frontend_checks").summarize(result, "test")
    assert summary["status"] == "failed"
    assert "CANARY" not in json.dumps(summary)


def test_actionlint_download_rejects_tampered_binary_archive():
    with pytest.raises(ValueError, match="checksum"):
        load_tool("install_actionlint").verify_archive(b"modified executable", "0" * 64)


@pytest.mark.parametrize(
    "error,reason",
    [
        (urllib.error.HTTPError("SECRET_CANARY", 503, "SECRET_CANARY", {}, None), "http_error"),
        (urllib.error.URLError("SECRET_CANARY"), "network_error"),
        (TimeoutError("SECRET_CANARY"), "network_error"),
        (ValueError("SECRET_CANARY"), "validation_error"),
        (tarfile.ReadError("SECRET_CANARY"), "archive_error"),
        (PermissionError("SECRET_CANARY"), "filesystem_error"),
        (RuntimeError("SECRET_CANARY"), "unexpected_error"),
    ],
)
def test_actionlint_failure_diagnostics_explain_category_without_sensitive_text(error, reason):
    report = load_tool("install_actionlint").failure_summary(error)
    assert report["status"] == "failed"
    assert report["reason"] == reason
    assert "CANARY" not in json.dumps(report)
    if isinstance(error, urllib.error.HTTPError):
        assert report["http_status"] == 503


def test_actionlint_cli_reports_failure_category_and_returns_failure(monkeypatch, tmp_path, capsys):
    tool = load_tool("install_actionlint")

    def fail(_):
        raise urllib.error.URLError("SECRET_CANARY")

    monkeypatch.setattr(tool, "install", fail)
    assert tool.main(["--destination", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["reason"] == "network_error"
    assert "CANARY" not in captured.out
    assert captured.err == ""


def test_actionlint_install_retries_transient_download_and_extracts_linux_binary(
    monkeypatch, tmp_path
):
    tool = load_tool("install_actionlint")
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as archive:
        member = tarfile.TarInfo("actionlint")
        member.size = len(b"test executable")
        archive.addfile(member, io.BytesIO(b"test executable"))
    payload = content.getvalue()
    monkeypatch.setitem(
        tool.ASSETS, "Linux", ("linux_amd64.tar.gz", hashlib.sha256(payload).hexdigest())
    )
    monkeypatch.setattr(tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tool.platform, "machine", lambda: "x86_64")
    delays = []
    monkeypatch.setattr(time, "sleep", delays.append)
    calls = []

    def download(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 504, "Gateway timeout", {}, None)
        return io.BytesIO(payload)

    monkeypatch.setattr(tool.urllib.request, "urlopen", download)
    target = tool.install(tmp_path)
    assert target.name == "actionlint"
    assert target.read_bytes() == b"test executable"
    assert len(calls) == 2
    assert delays == [1]


@pytest.mark.parametrize("status,expected_calls", [(503, 3), (404, 1)])
def test_actionlint_download_retries_are_bounded_and_skip_permanent_errors(
    monkeypatch, tmp_path, status, expected_calls
):
    tool = load_tool("install_actionlint")
    monkeypatch.setattr(tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tool.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(time, "sleep", lambda _: None)
    calls = []

    def download(url, **kwargs):
        calls.append(url)
        raise urllib.error.HTTPError(url, status, "Download failure", {}, None)

    monkeypatch.setattr(tool.urllib.request, "urlopen", download)
    with pytest.raises(urllib.error.HTTPError):
        tool.install(tmp_path)
    assert len(calls) == expected_calls
    assert not list(tmp_path.iterdir())


def test_deployment_readiness_fails_closed_without_printing_docker_diagnostics(monkeypatch):
    tool = load_tool("deployment_readiness")
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 1, "CONFIDENTIAL_CANARY", "KEY_CANARY"
        ),
    )
    result = tool.readiness(validate_docker=True)
    assert result["status"] == "failed"
    assert result["deployment_enabled"] is False
    assert "CANARY" not in json.dumps(result)


def test_rag_cli_outputs_only_aggregate_metrics():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/evaluate_rag.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert completed.returncode == 0, completed.stderr
    metrics = json.loads(completed.stdout)
    assert metrics["status"] == "passed"
    assert "MSA-" not in completed.stdout
    assert "excerpt" not in completed.stdout
