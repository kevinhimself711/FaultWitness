from __future__ import annotations

import copy
from pathlib import Path

import pytest

from faultwitness_dev.checks import validate_current_state
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import (
    _check_adr_invariants,
    _check_architecture_invariants,
    _check_evidence_invariants,
    _check_unique_ids,
    load_data,
    validate_document,
    validate_repository_schemas,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "governance"
SCHEMAS = ROOT / "schemas" / "governance"


def test_active_governance_assets_are_valid_without_legacy_epoch() -> None:
    loaded = validate_repository_schemas(ROOT)
    assert "PROJECT_STATE.yaml" in loaded
    assert not any(path.startswith("governance/iterations/") for path in loaded)
    assert not any(path.startswith("governance/gates/") for path in loaded)
    assert not any(path.startswith("docs/evals/") for path in loaded)


def test_current_state_references_real_plan_report_and_release() -> None:
    validate_current_state(ROOT)


def test_project_state_has_one_small_v2_shape() -> None:
    state = load_data(ROOT / "PROJECT_STATE.yaml")
    assert set(state) == {
        "governance_version",
        "active_gate",
        "active_gate_status",
        "last_closed_gate",
        "active_plan",
        "active_report",
        "latest_release",
    }
    assert "active_iteration" not in state
    assert "next_iteration" not in state


def test_missing_required_project_field_is_rejected() -> None:
    state = load_data(ROOT / "PROJECT_STATE.yaml")
    state.pop("active_plan")
    schema = load_data(SCHEMAS / "project-state.schema.json")
    with pytest.raises(GovernanceError, match="required property"):
        validate_document(state, schema, "missing-active-plan")


def test_duplicate_identifier_is_rejected() -> None:
    document = load_data(FIXTURES / "duplicate_requirements.yaml")
    with pytest.raises(GovernanceError, match="duplicate IDs"):
        _check_unique_ids(document, "duplicate_requirements")


def _evidence_assets() -> tuple[list[dict], dict, dict]:
    requirements = load_data(ROOT / "docs/requirements/REQUIREMENTS.yaml")
    sources = load_data(ROOT / "docs/requirements/SOURCE_CATALOG.yaml")
    matrix = load_data(ROOT / "docs/requirements/EVIDENCE_MATRIX.yaml")
    return requirements["requirements"], sources, matrix


def test_mandatory_requirement_cannot_rely_only_on_tier_c() -> None:
    requirements, sources, matrix = _evidence_assets()
    mutated = copy.deepcopy(requirements)
    mutated[0]["source_ids"] = ["SRC-UPSTREAM-001"]
    with pytest.raises(GovernanceError, match="supported only by Tier C"):
        _check_evidence_invariants(mutated, sources, matrix)


def test_unknown_requirement_source_is_rejected() -> None:
    requirements, sources, matrix = _evidence_assets()
    mutated = copy.deepcopy(requirements)
    mutated[0]["source_ids"].append("SRC-NOT-REAL")
    with pytest.raises(GovernanceError, match="unknown sources"):
        _check_evidence_invariants(mutated, sources, matrix)


def test_architecture_retains_three_engineering_planes() -> None:
    architecture = load_data(ROOT / "docs/architecture/ARCHITECTURE.yaml")
    mutated = copy.deepcopy(architecture)
    mutated["engineering_planes"].remove("data_eval_training")
    with pytest.raises(GovernanceError, match="three mandatory engineering planes"):
        _check_architecture_invariants(mutated)


def test_cross_owner_state_write_is_rejected() -> None:
    architecture = load_data(ROOT / "docs/architecture/ARCHITECTURE.yaml")
    mutated = copy.deepcopy(architecture)
    component = next(item for item in mutated["components"] if item["id"] == "CMP-INCIDENT-CONSOLE")
    component["writes_states"].append("Incident Lifecycle")
    with pytest.raises(GovernanceError, match="cross-owner state write"):
        _check_architecture_invariants(mutated)


def test_mandatory_prohibited_path_cannot_be_removed() -> None:
    architecture = load_data(ROOT / "docs/architecture/ARCHITECTURE.yaml")
    mutated = copy.deepcopy(architecture)
    mutated["prohibited_paths"] = [
        item
        for item in mutated["prohibited_paths"]
        if item["id"] != "DENY-AGENT-DIRECT-ACTION"
    ]
    with pytest.raises(GovernanceError, match="mandatory prohibited path"):
        _check_architecture_invariants(mutated)


def test_accepted_adr_must_resolve_to_a_file() -> None:
    index = load_data(ROOT / "docs/adr/INDEX.yaml")
    mutated = copy.deepcopy(index)
    mutated["adrs"][0]["path"] = "docs/adr/ADR-NOT-REAL.md"
    with pytest.raises(GovernanceError, match="accepted ADR path does not exist"):
        _check_adr_invariants(ROOT, mutated)
