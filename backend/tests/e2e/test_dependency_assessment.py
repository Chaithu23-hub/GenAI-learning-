"""Approved server-only applicability must never become a blanket audit bypass."""

import copy
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = [("chromadb", "1.5.9")]
TODAY = date(2026, 11, 8)
GROUPS = [
    ("PYSEC-2026-311", ["GHSA-f4j7-r4q5-qw2c", "CVE-2026-45829"]),
    ("PYSEC-2026-3813", ["GHSA-2wm9-hf6c-p5cr", "CVE-2026-45830"]),
    ("PYSEC-2026-3814", ["GHSA-36p7-vc44-83pf", "CVE-2026-45833"]),
    ("PYSEC-2026-3815", ["GHSA-xph7-9rjv-w5fr", "CVE-2026-45831"]),
]


@pytest.fixture
def tool(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "assessment_tool", ROOT / "scripts/ci/security_checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "scope_fingerprint", lambda root: module.REVIEWED_SCOPE_SHA256)
    return module


def report():
    return {
        "dependencies": [
            {
                "name": "chromadb",
                "version": "1.5.9",
                "vulns": [
                    {"id": identity, "aliases": aliases, "fix_versions": []}
                    for identity, aliases in GROUPS
                ],
            }
        ]
    }


def evaluate(tool, data=None, code=1, packages=None, today=TODAY):
    return tool.dependency_summary(
        report() if data is None else data,
        code,
        PACKAGES if packages is None else packages,
        today=today,
    )


def test_approved_assessment_keeps_all_four_findings_visible(tool):
    result = evaluate(tool)
    assert result["status"] == "passed"
    assert result["findings"] == result["assessed_non_applicable"] == 4
    assert result["blocking_findings"] == result["unassessed"] == 0
    assert result["assessment"]["owner"] == "Chaithu23-hub"
    assert result["assessment"]["expires"] == "2026-12-08"
    assert len(result["advisories"]) == 4
    assert {item["disposition"] for item in result["advisories"]} == {"assessed_non_applicable"}


@pytest.mark.parametrize("canonical", [False, True])
def test_duplicate_or_alias_reports_are_one_finding(tool, canonical):
    data = report()
    extra = copy.deepcopy(data["dependencies"][0]["vulns"][0])
    if canonical:
        extra["id"], extra["aliases"] = GROUPS[0][1][0], [GROUPS[0][0], GROUPS[0][1][1]]
    data["dependencies"][0]["vulns"].append(extra)
    assert evaluate(tool, data)["findings"] == 4


@pytest.mark.parametrize("today", [date(2026, 12, 8), date(2027, 1, 1)])
def test_assessment_expires_at_start_of_expiry_day(tool, today):
    result = evaluate(tool, today=today)
    assert result["status"] == "failed"
    assert result["assessed_non_applicable"] == 0
    assert result["blocking_findings"] == 4


def test_changed_runtime_scope_revokes_assessment(tool, monkeypatch):
    monkeypatch.setattr(tool, "scope_fingerprint", lambda root: "0" * 64)
    assert evaluate(tool)["blocking_findings"] == 4


def test_missing_runtime_scope_revokes_assessment(tool, monkeypatch):
    def missing(_):
        raise OSError("PRIVATE_PATH_CANARY")

    monkeypatch.setattr(tool, "scope_fingerprint", missing)
    result = evaluate(tool)
    assert result["status"] == "failed"
    assert "CANARY" not in json.dumps(result)


def test_other_chroma_versions_do_not_inherit_assessment(tool):
    data = report()
    data["dependencies"][0]["version"] = "1.5.10"
    assert evaluate(tool, data, packages=[("chromadb", "1.5.10")])["blocking_findings"] == 4


def test_published_fix_requires_upgrade_instead_of_reusing_exception(tool):
    data = report()
    data["dependencies"][0]["vulns"][0]["fix_versions"] = ["1.5.10"]
    result = evaluate(tool, data)
    assert result["status"] == "failed"
    assert result["blocking_findings"] == 1


@pytest.mark.parametrize("field", ["fix_versions", "aliases"])
def test_incomplete_known_advisory_metadata_cannot_receive_exception(tool, field):
    data = report()
    del data["dependencies"][0]["vulns"][0][field]
    assert evaluate(tool, data)["status"] == "failed"


@pytest.mark.parametrize(
    "identity,aliases",
    [
        ("PYSEC-2026-99999", []),
        ("PYSEC-2026-99999", GROUPS[0][1]),
        (GROUPS[0][0], ["CVE-2026-99999"]),
    ],
)
def test_unknown_findings_or_aliases_block_even_alongside_known_findings(tool, identity, aliases):
    data = report()
    data["dependencies"][0]["vulns"].append(
        {"id": identity, "aliases": aliases, "fix_versions": []}
    )
    result = evaluate(tool, data)
    assert result["status"] == "failed"
    assert result["blocking_findings"] >= 1


def test_other_package_cannot_borrow_chroma_advisory_exception(tool):
    data = report()
    data["dependencies"][0]["name"] = "another-library"
    result = evaluate(tool, data, packages=[("another-library", "1.5.9")])
    assert result["blocking_findings"] == 4


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"dependencies": None},
        {"dependencies": []},
        {"dependencies": [{"name": "chromadb", "version": "1.5.9"}]},
    ],
)
def test_malformed_or_incomplete_audit_never_passes(tool, data):
    assert tool.dependency_summary(data, 0, PACKAGES, today=TODAY)["status"] == "failed"


def test_skipped_dependencies_cannot_pass(tool):
    data = report()
    data["dependencies"].append({"name": "unassessed-library", "skip_reason": "not supported"})
    result = evaluate(tool, data, packages=PACKAGES + [("unassessed-library", "1.0")])
    assert result["status"] == "failed"
    assert result["unassessed"] == 1


@pytest.mark.parametrize("code", [0, 2, -1])
def test_audit_exit_code_must_match_real_findings_not_tool_failure(tool, code):
    assert evaluate(tool, code=code)["status"] == "failed"


def test_clean_complete_report_passes_without_exception(tool):
    data = {"dependencies": [{"name": "safe-library", "version": "1.0", "vulns": []}]}
    result = evaluate(
        tool, data, code=0, packages=[("safe-library", "1.0")], today=date(2027, 1, 1)
    )
    assert result["status"] == "passed"
    assert result["findings"] == 0


def test_duplicate_packages_and_incorrect_audited_version_fail(tool):
    data = report()
    data["dependencies"].append(copy.deepcopy(data["dependencies"][0]))
    assert evaluate(tool, data)["status"] == "failed"
    data = report()
    data["dependencies"][0]["version"] = "1.5.8"
    assert evaluate(tool, data)["status"] == "failed"


def test_actual_reviewed_scope_matches_and_new_source_changes_it(tool, monkeypatch, tmp_path):
    monkeypatch.undo()
    digest = tool.scope_fingerprint(ROOT)
    assert digest == tool.REVIEWED_SCOPE_SHA256
    target = tmp_path / "backend/legal_rag"
    target.mkdir(parents=True)
    (target / "new_remote_server.py").write_text("pass\n", encoding="utf-8")
    # An incomplete runtime is never accepted as the reviewed deployment.
    with pytest.raises((OSError, ValueError)):
        tool.scope_fingerprint(tmp_path)


@pytest.mark.parametrize(
    "change",
    [
        "new_source",
        "deployment",
        "dependency",
        "remove_source",
        "line_endings",
        "compose.yaml",
        "compose.override.yaml",
        "docker-compose.override.yml",
    ],
)
def test_scope_fingerprint_detects_material_changes_across_checkouts(
    tool, monkeypatch, tmp_path, change
):
    monkeypatch.undo()
    for source in tool.scope_paths(ROOT):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    baseline = tool.scope_fingerprint(tmp_path)
    assert baseline == tool.REVIEWED_SCOPE_SHA256
    if change == "new_source":
        (tmp_path / "backend/legal_rag/new_remote_server.py").write_text("pass\n", encoding="utf-8")
    elif change in {"deployment", "dependency"}:
        name = "docker-compose.yml" if change == "deployment" else "backend/requirements.txt"
        target = tmp_path / name
        target.write_bytes(target.read_bytes() + b"\n# changed deployment\n")
    elif change == "remove_source":
        (tmp_path / "backend/legal_rag/domain/evidence.py").unlink()
    elif change.endswith((".yaml", ".yml")):
        (tmp_path / change).write_text("services: {}\n", encoding="utf-8")
    else:
        target = tmp_path / "backend/legal_rag/domain/evidence.py"
        target.write_bytes(target.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    changed = tool.scope_fingerprint(tmp_path)
    assert (changed == baseline) == (change == "line_endings")


def test_every_fingerprinted_file_selects_the_security_gate(tool, monkeypatch):
    monkeypatch.undo()
    spec = importlib.util.spec_from_file_location(
        "scope_paths_selector", ROOT / "scripts/ci/changed_paths.py"
    )
    selector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selector)
    paths = [path.relative_to(ROOT).as_posix() for path in tool.scope_paths(ROOT)]
    paths += ["compose.yaml", "compose.yml", "compose.override.yaml", "docker-compose.override.yml"]
    skipped = [path for path in paths if not selector.select_jobs([path])["security"]]
    assert skipped == []
