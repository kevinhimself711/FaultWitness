from __future__ import annotations

import copy
from pathlib import Path

import pytest

from faultwitness_dev.changes import (
    G00_CLOSURE_PATHS,
    infer_iteration_id,
    validate_change_record,
    validate_g00_closure_change,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import (
    _check_adr_invariants,
    _check_architecture_invariants,
    _check_cross_references,
    _check_evidence_invariants,
    _check_gate_walkthroughs,
    _check_ruleset_invariants,
    _check_unique_ids,
    load_data,
    validate_document,
    validate_repository_schemas,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "governance"
SCHEMAS = ROOT / "schemas" / "governance"


def test_repository_governance_assets_are_valid() -> None:
    loaded = validate_repository_schemas(ROOT)
    assert "PROJECT_STATE.yaml" in loaded
    assert "governance/iterations/I-0002.yaml" in loaded


def test_missing_required_field_is_rejected() -> None:
    document = load_data(FIXTURES / "missing_project_field.yaml")
    schema = load_data(SCHEMAS / "project-state.schema.json")
    with pytest.raises(GovernanceError, match="required property"):
        validate_document(document, schema, "missing_project_field")


def test_project_state_allows_frozen_not_started_gate_handoff() -> None:
    document = load_data(ROOT / "PROJECT_STATE.yaml")
    schema = load_data(SCHEMAS / "project-state.schema.json")
    mutated = copy.deepcopy(document)
    mutated["active_gate_status"] = "not_started"
    validate_document(mutated, schema, "not_started_gate_handoff")


def test_duplicate_identifier_is_rejected() -> None:
    document = load_data(FIXTURES / "duplicate_requirements.yaml")
    with pytest.raises(GovernanceError, match="duplicate IDs"):
        _check_unique_ids(document, "duplicate_requirements")


def test_unknown_gate_and_iteration_are_rejected() -> None:
    loaded = validate_repository_schemas(ROOT)
    mutated = copy.deepcopy(loaded)
    mutated["docs/evals/EVAL-G99-001/manifest.json"] = load_data(
        FIXTURES / "unknown_eval_refs.json"
    )
    with pytest.raises(GovernanceError, match="unknown eval gate"):
        _check_cross_references(mutated)


def test_behavior_change_without_documentation_is_rejected() -> None:
    record = load_data(FIXTURES / "behavior_without_docs.yaml")
    with pytest.raises(GovernanceError, match="must update documentation"):
        validate_change_record(record)


def test_illegal_iteration_status_is_rejected() -> None:
    document = load_data(FIXTURES / "illegal_iteration_status.yaml")
    schema = load_data(SCHEMAS / "iteration.schema.json")
    with pytest.raises(GovernanceError, match="silently_skipped"):
        validate_document(document, schema, "illegal_iteration_status")


def test_threshold_decrease_is_rejected() -> None:
    record = load_data(FIXTURES / "threshold_decrease.yaml")
    with pytest.raises(GovernanceError, match="threshold decrease"):
        validate_change_record(record)


def test_ruleset_cannot_drop_a_required_platform() -> None:
    ruleset = load_data(ROOT / ".github" / "rulesets" / "main.json")
    mutated = copy.deepcopy(ruleset)
    status_rule = next(
        rule for rule in mutated["rules"] if rule["type"] == "required_status_checks"
    )
    status_rule["parameters"]["required_status_checks"].pop()
    with pytest.raises(GovernanceError, match="status checks drifted"):
        _check_ruleset_invariants(mutated)


def test_ruleset_requires_cross_platform_and_audit_checks() -> None:
    ruleset = load_data(ROOT / ".github" / "rulesets" / "main.json")
    status_rule = next(
        rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks"
    )
    contexts = {
        item["context"]
        for item in status_rule["parameters"]["required_status_checks"]
    }
    assert contexts == {
        "audit (ubuntu-latest)",
        "verify (ubuntu-latest)",
        "verify (windows-latest)",
    }


def test_iteration_inference_ignores_planned_bootstrap_records() -> None:
    paths = [f"governance/iterations/I-{number:04d}.yaml" for number in range(1, 7)]
    planned = [path for path in paths if load_data(ROOT / path)["status"] == "planned"]
    assert infer_iteration_id(ROOT, planned) is None


def test_iteration_inference_selects_current_in_progress_record() -> None:
    paths = [f"governance/iterations/I-{number:04d}.yaml" for number in range(1, 7)]
    eligible = [
        load_data(ROOT / path)["id"]
        for path in paths
        if load_data(ROOT / path)["status"] in {"in_progress", "completed"}
        and load_data(ROOT / path)["docs_updated"]
    ]
    assert infer_iteration_id(ROOT, paths) == max(eligible)


def _g00_closure_records() -> tuple[dict, dict, dict]:
    state = {
        "active_gate": "G01",
        "active_gate_status": "not_started",
        "active_iteration": None,
        "next_iteration": None,
        "last_closed_gate": "G00",
        "active_gate_plan": "docs/gates/G01/PLAN.md",
        "active_gate_report": "docs/gates/G01/REPORT.md",
    }
    return state, {"id": "G00", "status": "passed", "waivers": []}, {
        "id": "G01",
        "status": "planned",
    }


def test_asset_only_g00_closure_is_accepted() -> None:
    validate_g00_closure_change(*_g00_closure_records(), sorted(G00_CLOSURE_PATHS))


def test_g00_closure_rejects_source_code() -> None:
    paths = sorted(G00_CLOSURE_PATHS | {"src/faultwitness_dev/runtime.py"})
    with pytest.raises(GovernanceError, match="unexpected"):
        validate_g00_closure_change(*_g00_closure_records(), paths)


def test_g00_closure_rejects_inexact_handoff_state() -> None:
    state, g00, g01 = _g00_closure_records()
    state["active_gate_status"] = "planned"
    with pytest.raises(GovernanceError, match="project-state drift"):
        validate_g00_closure_change(state, g00, g01, sorted(G00_CLOSURE_PATHS))


def _load_evidence_assets() -> tuple[list[dict], dict, dict]:
    requirements = load_data(ROOT / "docs" / "requirements" / "REQUIREMENTS.yaml")
    sources = load_data(ROOT / "docs" / "requirements" / "SOURCE_CATALOG.yaml")
    matrix = load_data(ROOT / "docs" / "requirements" / "EVIDENCE_MATRIX.yaml")
    return requirements["requirements"], sources, matrix


def test_mandatory_requirement_cannot_rely_only_on_tier_c() -> None:
    requirements, sources, matrix = _load_evidence_assets()
    mutated = copy.deepcopy(requirements)
    mutated[0]["source_ids"] = ["SRC-UPSTREAM-001"]
    with pytest.raises(GovernanceError, match="supported only by Tier C"):
        _check_evidence_invariants(mutated, sources, matrix)


def test_source_count_drift_is_rejected() -> None:
    requirements, sources, matrix = _load_evidence_assets()
    mutated = copy.deepcopy(sources)
    source = next(item for item in mutated["sources"] if item["kind"] == "interview")
    source["included"] = False
    source["indexed"] = False
    source["exclusion_reason"] = "synthetic drift fixture"
    with pytest.raises(GovernanceError, match="source catalog count drift"):
        _check_evidence_invariants(requirements, mutated, matrix)


def test_unknown_requirement_source_is_rejected() -> None:
    requirements, sources, matrix = _load_evidence_assets()
    mutated = copy.deepcopy(requirements)
    mutated[0]["source_ids"].append("SRC-JD-999")
    with pytest.raises(GovernanceError, match="unknown sources"):
        _check_evidence_invariants(mutated, sources, matrix)


def test_duplicate_evidence_matrix_coverage_is_rejected() -> None:
    requirements, sources, matrix = _load_evidence_assets()
    mutated = copy.deepcopy(matrix)
    mutated["entries"][1]["requirement_ids"].append("REQ-BUS-001")
    with pytest.raises(GovernanceError, match="duplicates requirement coverage"):
        _check_evidence_invariants(requirements, sources, mutated)


def _load_architecture() -> dict:
    return load_data(ROOT / "docs" / "architecture" / "ARCHITECTURE.yaml")


def test_missing_mandatory_engineering_plane_is_rejected() -> None:
    architecture = _load_architecture()
    mutated = copy.deepcopy(architecture)
    mutated["engineering_planes"].remove("data_eval_training")
    with pytest.raises(GovernanceError, match="three mandatory engineering planes"):
        _check_architecture_invariants(mutated)


def test_cross_owner_state_write_is_rejected() -> None:
    architecture = _load_architecture()
    mutated = copy.deepcopy(architecture)
    console = next(item for item in mutated["components"] if item["id"] == "CMP-INCIDENT-CONSOLE")
    console["writes_states"].append("Incident Lifecycle")
    with pytest.raises(GovernanceError, match="cross-owner state write"):
        _check_architecture_invariants(mutated)


def test_unknown_walkthrough_component_is_rejected() -> None:
    architecture = _load_architecture()
    mutated = copy.deepcopy(architecture)
    mutated["walkthroughs"][0]["component_path"].append("CMP-NOT-REAL")
    with pytest.raises(GovernanceError, match="unknown components"):
        _check_architecture_invariants(mutated)


def test_mandatory_prohibited_path_cannot_be_removed() -> None:
    architecture = _load_architecture()
    mutated = copy.deepcopy(architecture)
    mutated["prohibited_paths"] = [
        item
        for item in mutated["prohibited_paths"]
        if item["id"] != "DENY-AGENT-DIRECT-ACTION"
    ]
    with pytest.raises(GovernanceError, match="mandatory prohibited path"):
        _check_architecture_invariants(mutated)


def test_accepted_adr_must_resolve_to_a_file() -> None:
    index = load_data(ROOT / "docs" / "adr" / "INDEX.yaml")
    mutated = copy.deepcopy(index)
    mutated["adrs"][0]["path"] = "docs/adr/ADR-NOT-REAL.md"
    with pytest.raises(GovernanceError, match="accepted ADR path does not exist"):
        _check_adr_invariants(ROOT, mutated)


def test_g00_walkthrough_set_cannot_be_reduced() -> None:
    walkthroughs = load_data(ROOT / "docs" / "evals" / "EVAL-G00-006" / "WALKTHROUGHS.yaml")
    bindings = load_data(ROOT / "docs" / "contracts" / "WALKTHROUGH_BINDINGS.yaml")
    mutated = copy.deepcopy(walkthroughs)
    mutated["walkthroughs"].pop()
    with pytest.raises(GovernanceError, match="exactly W-G00-001 through 014"):
        _check_gate_walkthroughs(mutated, bindings)


def test_g00_walkthrough_requires_known_contract_binding() -> None:
    walkthroughs = load_data(ROOT / "docs" / "evals" / "EVAL-G00-006" / "WALKTHROUGHS.yaml")
    bindings = load_data(ROOT / "docs" / "contracts" / "WALKTHROUGH_BINDINGS.yaml")
    mutated = copy.deepcopy(walkthroughs)
    mutated["walkthroughs"][0]["source_binding"] = "W-ARCH-999"
    with pytest.raises(GovernanceError, match="unknown contract bindings"):
        _check_gate_walkthroughs(mutated, bindings)
