from __future__ import annotations

import copy
from pathlib import Path

import pytest

from faultwitness_dev.changes import infer_iteration_id, validate_change_record
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import (
    _check_cross_references,
    _check_evidence_invariants,
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


def test_iteration_inference_ignores_planned_bootstrap_records() -> None:
    paths = [
        "governance/iterations/I-0001.yaml",
        "governance/iterations/I-0002.yaml",
        *[f"governance/iterations/I-{number:04d}.yaml" for number in range(4, 7)],
    ]
    assert infer_iteration_id(ROOT, paths) == "I-0002"


def test_iteration_inference_selects_current_in_progress_record() -> None:
    paths = [f"governance/iterations/I-{number:04d}.yaml" for number in range(1, 7)]
    assert infer_iteration_id(ROOT, paths) == "I-0003"


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
