from __future__ import annotations

import copy
from pathlib import Path

import pytest

from faultwitness_dev.changes import validate_change_record
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import (
    _check_cross_references,
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
