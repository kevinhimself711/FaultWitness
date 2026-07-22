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
