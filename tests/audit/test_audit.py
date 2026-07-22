from __future__ import annotations

import copy
from pathlib import Path

import pytest

from faultwitness_dev.audit import (
    Component,
    audit_repository,
    build_sbom,
    scan_publication_boundary,
    validate_action_pins,
    validate_g00_closure_documents,
    validate_licenses,
    validate_sbom,
)
from faultwitness_dev.errors import GovernanceError

ROOT = Path(__file__).resolve().parents[2]


def test_private_key_is_rejected(tmp_path: Path) -> None:
    fixture = tmp_path / "secret.txt"
    fixture.write_text("-----BEGIN " + "PRIVATE " + "KEY-----\n", encoding="utf-8")
    with pytest.raises(GovernanceError, match="private-key"):
        scan_publication_boundary(tmp_path, [fixture])


def test_absolute_local_source_path_is_rejected(tmp_path: Path) -> None:
    fixture = tmp_path / "source.md"
    fixture.write_text("source: C:\\Users\\candidate\\interviews\n", encoding="utf-8")
    with pytest.raises(GovernanceError, match="absolute-local-path"):
        scan_publication_boundary(tmp_path, [fixture])


def test_unpinned_github_action_is_rejected(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bad.yml").write_text(
        "steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8"
    )
    with pytest.raises(GovernanceError, match="full commit SHAs"):
        validate_action_pins(tmp_path)


def test_incompatible_license_is_rejected() -> None:
    with pytest.raises(GovernanceError, match="GPL-3.0"):
        validate_licenses([Component("npm", "unsafe", "1.0.0", "GPL-3.0")])


def test_sbom_requires_unique_components() -> None:
    component = Component("pypi", "example", "1.0.0", "MIT")
    with pytest.raises(GovernanceError, match="duplicate SBOM"):
        build_sbom([component, component], "a" * 40)


def test_sbom_validation_rejects_missing_license() -> None:
    sbom = build_sbom([Component("pypi", "example", "1.0.0", "MIT")], "a" * 40)
    mutated = copy.deepcopy(sbom)
    mutated["components"][0]["licenses"] = []
    with pytest.raises(GovernanceError, match="version and license"):
        validate_sbom(mutated)


def test_repository_audit_generates_valid_cyclonedx(tmp_path: Path) -> None:
    summary = audit_repository(ROOT, tmp_path)
    assert summary["status"] == "pass"
    assert summary["component_count"] > 0
    assert (tmp_path / "sbom.cdx.json").is_file()
    assert (tmp_path / "audit-summary.json").is_file()


def _closure_documents() -> tuple[dict, dict, list[dict], list[dict]]:
    state = {
        "active_gate": "G00",
        "active_gate_status": "in_progress",
        "active_iteration": None,
        "next_iteration": None,
    }
    gate = {
        "status": "in_progress",
        "iterations": ["I-0001", "I-0002"],
        "waivers": [],
    }
    iterations = [
        {"id": "I-0001", "status": "completed", "commit": "a" * 40},
        {"id": "I-0002", "status": "completed", "commit": "b" * 40},
    ]
    manifests = [
        {"iteration": "I-0001", "status": "pass", "open_evidence": []},
        {"iteration": "I-0002", "status": "pass", "open_evidence": []},
    ]
    return state, gate, iterations, manifests


def test_g00_closure_readiness_accepts_complete_evidence() -> None:
    validate_g00_closure_documents(*_closure_documents())


@pytest.mark.parametrize("failure_kind", ["iteration", "eval", "open_evidence", "waiver"])
def test_g00_closure_readiness_rejects_unresolved_evidence(failure_kind: str) -> None:
    state, gate, iterations, manifests = _closure_documents()
    if failure_kind == "iteration":
        iterations[1]["status"] = "in_progress"
    elif failure_kind == "eval":
        manifests[1]["status"] = "fail"
    elif failure_kind == "open_evidence":
        manifests[1]["open_evidence"] = ["missing CI"]
    else:
        gate["waivers"] = ["temporary waiver"]
    with pytest.raises(GovernanceError):
        validate_g00_closure_documents(state, gate, iterations, manifests)
