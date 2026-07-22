from __future__ import annotations

import copy
from pathlib import Path

import pytest

from faultwitness_dev.contracts import (
    _validate_asyncapi,
    _validate_error_references,
    _validate_failure_semantics,
    _validate_openapi,
    _validate_safety_paths,
    _validate_state_machine,
    _validate_walkthrough_bindings,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data, validate_document, validate_repository_schemas

ROOT = Path(__file__).resolve().parents[2]


def _architecture() -> dict:
    return load_data(ROOT / "docs" / "architecture" / "ARCHITECTURE.yaml")


def _catalog() -> dict:
    return load_data(ROOT / "docs" / "contracts" / "COMMAND_EVENT_CATALOG.yaml")


def _machines() -> dict[str, dict]:
    root = ROOT / "docs" / "contracts" / "state-machines"
    return {
        "incident": load_data(root / "incident.yaml"),
        "runtime_task": load_data(root / "runtime_task.yaml"),
        "agent_graph": load_data(root / "agent_graph.yaml"),
        "action_transaction": load_data(root / "action_transaction.yaml"),
    }


def test_repository_contracts_are_conformant() -> None:
    loaded = validate_repository_schemas(ROOT)
    assert "docs/contracts/openapi.yaml" in loaded
    assert "docs/contracts/state-machines/action_transaction.yaml" in loaded


def test_unreachable_state_is_rejected() -> None:
    machine = _machines()["incident"]
    mutated = copy.deepcopy(machine)
    mutated["states"].append("ISOLATED")
    with pytest.raises(GovernanceError, match="unreachable states"):
        _validate_state_machine(mutated, _architecture(), _catalog())


def test_terminal_outgoing_transition_is_rejected() -> None:
    machine = _machines()["agent_graph"]
    mutated = copy.deepcopy(machine)
    transition = copy.deepcopy(mutated["transitions"][0])
    transition.update(
        {
            "id": "TR-GRAPH-ILLEGAL-TERMINAL",
            "from": "FINALIZE",
            "to": "ESCALATE",
        }
    )
    mutated["transitions"].append(transition)
    with pytest.raises(GovernanceError, match="terminal outgoing transition"):
        _validate_state_machine(mutated, _architecture(), _catalog())


def test_transition_missing_guard_is_rejected_by_schema() -> None:
    machine = _machines()["incident"]
    mutated = copy.deepcopy(machine)
    mutated["transitions"][0].pop("guard")
    schema = load_data(ROOT / "schemas" / "contracts" / "state-machine.schema.json")
    with pytest.raises(GovernanceError, match="required property"):
        validate_document(mutated, schema, "incident_without_guard")


def test_r2_approval_bypass_is_rejected() -> None:
    machines = _machines()
    approval = next(
        transition
        for transition in machines["action_transaction"]["transitions"]
        if transition["id"] == "TR-ACTION-DISPATCH"
    )
    approval["preconditions"].remove("valid_approval_digest")
    with pytest.raises(GovernanceError, match="Action dispatch.*safety preconditions"):
        _validate_safety_paths(machines)


def test_uncertain_cannot_automatically_retry() -> None:
    machines = _machines()
    reconciliation = next(
        transition
        for transition in machines["action_transaction"]["transitions"]
        if transition["id"] == "TR-ACTION-RECONCILE"
    )
    reconciliation["automatic"] = True
    with pytest.raises(GovernanceError, match="UNCERTAIN.*blind-retry"):
        _validate_safety_paths(machines)


def test_runtime_success_requires_current_fencing_token() -> None:
    machines = _machines()
    completion = next(
        transition
        for transition in machines["runtime_task"]["transitions"]
        if transition["id"] == "TR-TASK-SUCCEED"
    )
    completion["preconditions"].remove("valid_fencing_token")
    with pytest.raises(GovernanceError, match="Runtime success commit.*safety preconditions"):
        _validate_safety_paths(machines)


def test_openapi_request_cannot_accept_tenant_identity() -> None:
    document = load_data(ROOT / "docs" / "contracts" / "openapi.yaml")
    mutated = copy.deepcopy(document)
    mutated["components"]["schemas"]["IncidentCreate"]["properties"]["tenant_id"] = {
        "type": "string"
    }
    with pytest.raises(GovernanceError, match="caller supplied identity"):
        _validate_openapi(mutated)


def test_openapi_state_change_requires_expected_version() -> None:
    document = load_data(ROOT / "docs" / "contracts" / "openapi.yaml")
    mutated = copy.deepcopy(document)
    required = mutated["components"]["schemas"]["ApprovalRequest"]["required"]
    required.remove("expected_state_version")
    with pytest.raises(GovernanceError, match="lacks expected_state_version"):
        _validate_openapi(mutated)


def test_asyncapi_event_envelope_cannot_drop_event_id() -> None:
    document = load_data(ROOT / "docs" / "contracts" / "asyncapi.yaml")
    mutated = copy.deepcopy(document)
    required = mutated["components"]["schemas"]["DomainEventEnvelope"]["required"]
    required.remove("event_id")
    with pytest.raises(GovernanceError, match="DomainEventEnvelope drifted"):
        _validate_asyncapi(mutated)


def test_lost_action_response_cannot_use_bounded_retry() -> None:
    document = load_data(ROOT / "docs" / "contracts" / "FAILURE_SEMANTICS.yaml")
    mutated = copy.deepcopy(document)
    failure = next(
        record
        for record in mutated["failures"]
        if record["id"] == "FAIL-ACTION-RESPONSE-LOST"
    )
    failure["retry_policy"] = "bounded"
    with pytest.raises(GovernanceError, match="must reconcile without retry"):
        _validate_failure_semantics(mutated)


def test_command_cannot_reference_unknown_error_code() -> None:
    catalog = _catalog()
    failures = load_data(ROOT / "docs" / "contracts" / "FAILURE_SEMANTICS.yaml")
    mutated = copy.deepcopy(catalog)
    mutated["commands"][0]["errors"].append("ERR-NOT-REGISTERED")
    with pytest.raises(GovernanceError, match="unknown error codes"):
        _validate_error_references(mutated, failures)


def test_walkthrough_cannot_reference_unknown_transition() -> None:
    document = load_data(ROOT / "docs" / "contracts" / "WALKTHROUGH_BINDINGS.yaml")
    mutated = copy.deepcopy(document)
    mutated["bindings"][0]["transition_ids"].append("TR-NOT-REGISTERED")
    failures = load_data(ROOT / "docs" / "contracts" / "FAILURE_SEMANTICS.yaml")
    openapi = load_data(ROOT / "docs" / "contracts" / "openapi.yaml")
    with pytest.raises(GovernanceError, match="unknown contract references"):
        _validate_walkthrough_bindings(
            mutated, _machines(), _catalog(), failures, openapi
        )
