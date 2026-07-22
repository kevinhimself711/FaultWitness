from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from faultwitness.contracts.compiler import compile_repository
from faultwitness.state.kernel import (
    ActorMismatchError,
    CommandMismatchError,
    ContractRegistryError,
    GuardRejectedError,
    IdempotencyError,
    IllegalTransitionError,
    OwnerMismatchError,
    PredicateRegistry,
    SchemaVersionError,
    TransitionKernel,
    TransitionRequest,
    UnknownTransitionError,
    VersionConflictError,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def resource() -> dict[str, object]:
    return json.loads(compile_repository(ROOT))


@pytest.fixture(scope="module")
def kernel(resource: dict[str, object]) -> TransitionKernel:
    names = TransitionKernel.required_predicates(resource)
    return TransitionKernel(resource, PredicateRegistry.fact_registry(names))


def request(**overrides: object) -> TransitionRequest:
    values: dict[str, object] = {
        "machine_id": "incident",
        "transition_id": "TR-INCIDENT-CREATE",
        "owner_component": "CMP-CONTROL-API",
        "actor": "CMP-CONTROL-API",
        "aggregate_id": "incident-1",
        "state": "NEW",
        "state_version": 0,
        "expected_state_version": 0,
        "command": "CMD-CREATE-INCIDENT",
        "idempotency_key": "create-1",
        "facts": {
            "guard:TR-INCIDENT-CREATE": True,
            "tenant_from_oidc": True,
            "idempotency_reserved": True,
            "expected_state_version": True,
        },
    }
    values.update(overrides)
    return TransitionRequest(**values)  # type: ignore[arg-type]


def test_all_four_owners_and_all_82_transitions_are_loaded(
    resource: dict[str, object], kernel: TransitionKernel
) -> None:
    documents = resource["documents"]
    assert isinstance(documents, dict)
    count = sum(
        len(documents[f"state_machine.{machine}"]["transitions"])
        for machine in ("incident", "runtime_task", "agent_graph", "action_transaction")
    )
    assert count == 82
    assert kernel.service("incident").owner_component == "CMP-CONTROL-API"
    assert kernel.service("runtime_task").owner_component == "CMP-SCHEDULER"
    assert kernel.service("agent_graph").owner_component == "CMP-AGENT-WORKER"
    assert kernel.service("action_transaction").owner_component == "CMP-ACTION-EXECUTOR"


def test_all_82_frozen_legal_transitions_execute(resource: dict[str, object]) -> None:
    documents = resource["documents"]
    assert isinstance(documents, dict)
    commands = {item["id"]: item for item in documents["commands_events"]["commands"]}
    names = TransitionKernel.required_predicates(resource)
    kernel = TransitionKernel(resource, PredicateRegistry.fact_registry(names))
    decisions = []

    for machine_id in ("incident", "runtime_task", "agent_graph", "action_transaction"):
        machine = documents[f"state_machine.{machine_id}"]
        for transition in machine["transitions"]:
            command = commands[transition["command"]]
            required_idempotency = command["idempotency"] == "required"
            transition_request = TransitionRequest(
                machine_id=machine_id,
                transition_id=transition["id"],
                owner_component=machine["owner_component"],
                actor=transition["actor"],
                aggregate_id=f"aggregate-{machine_id}",
                state=transition["from"],
                state_version=7,
                command=transition["command"],
                expected_state_version=7,
                idempotency_key=f"idem-{transition['id']}" if required_idempotency else None,
                current_fencing_token="fence-current",
                fencing_token="fence-current",
                current_action_digest="digest-current",
                action_digest="digest-current",
                facts={
                    f"guard:{transition['id']}": True,
                    **{name: True for name in transition["preconditions"]},
                },
            )
            decision = kernel.service(machine_id).decide(transition_request)
            assert decision.next_state == transition["to"]
            assert decision.event == transition["event"]
            assert decision.next_state_version == 8
            decisions.append(decision)

    assert len(decisions) == 82
    assert len({decision.transition_id for decision in decisions}) == 82


def test_legal_transition_is_deterministic_and_increments_version(
    kernel: TransitionKernel,
) -> None:
    first = kernel.decide(request())
    second = kernel.decide(request())
    assert first == second
    assert first.previous_state == "NEW"
    assert first.next_state == "QUEUED"
    assert first.previous_state_version == 0
    assert first.next_state_version == 1
    assert first.event == "EVT-INCIDENT-CREATED"
    assert len(first.decision_digest) == 64


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"owner_component": "CMP-SCHEDULER"}, OwnerMismatchError),
        ({"actor": "CMP-AGENT-WORKER"}, ActorMismatchError),
        ({"state": "INVESTIGATING"}, IllegalTransitionError),
        ({"command": "CMD-CANCEL-INCIDENT"}, CommandMismatchError),
        ({"transition_id": "TR-NOT-REGISTERED"}, UnknownTransitionError),
    ],
)
def test_owner_actor_state_command_and_transition_are_fail_closed(
    kernel: TransitionKernel,
    overrides: dict[str, object],
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        kernel.decide(request(**overrides))


def test_terminal_state_cannot_transition_even_when_transition_identifier_is_known(
    kernel: TransitionKernel,
) -> None:
    with pytest.raises(IllegalTransitionError, match="terminal state"):
        kernel.decide(request(state="CANCELLED"))


def test_guard_evaluates_every_precondition_and_reports_all_failures(
    kernel: TransitionKernel,
) -> None:
    with pytest.raises(GuardRejectedError) as raised:
        kernel.decide(
            request(
                facts={
                    "guard:TR-INCIDENT-CREATE": True,
                    "tenant_from_oidc": False,
                    "idempotency_reserved": True,
                    "expected_state_version": False,
                }
            )
        )
    assert raised.value.failed_predicates == (
        "tenant_from_oidc",
        "expected_state_version",
    )

    with pytest.raises(GuardRejectedError) as guard_rejected:
        kernel.decide(
            request(
                facts={
                    "guard:TR-INCIDENT-CREATE": False,
                    "tenant_from_oidc": True,
                    "idempotency_reserved": True,
                    "expected_state_version": True,
                }
            )
        )
    assert guard_rejected.value.failed_predicates == ("guard:TR-INCIDENT-CREATE",)


def test_predicate_registry_rejects_missing_unknown_and_non_boolean(
    resource: dict[str, object],
) -> None:
    names = TransitionKernel.required_predicates(resource)
    missing = PredicateRegistry.fact_registry(set(names) - {"matching_tenant"})
    with pytest.raises(ContractRegistryError, match="missing predicates"):
        TransitionKernel(resource, missing)

    unknown = PredicateRegistry.fact_registry(set(names) | {"not_in_contract"})
    with pytest.raises(ContractRegistryError, match="unknown predicates"):
        TransitionKernel(resource, unknown)

    predicates = {name: (lambda _request: True) for name in names}
    predicates["tenant_from_oidc"] = lambda _request: "yes"  # type: ignore[assignment]
    bad_kernel = TransitionKernel(resource, PredicateRegistry(predicates))
    with pytest.raises(ContractRegistryError, match="did not return bool"):
        bad_kernel.decide(request())


def test_unknown_command_and_event_in_contract_are_rejected(
    resource: dict[str, object],
) -> None:
    names = TransitionKernel.required_predicates(resource)
    for field, value in (("command", "CMD-UNKNOWN"), ("event", "EVT-UNKNOWN")):
        changed = deepcopy(resource)
        changed["documents"]["state_machine.incident"]["transitions"][0][field] = value
        with pytest.raises(ContractRegistryError, match=f"unknown {field}"):
            TransitionKernel(changed, PredicateRegistry.fact_registry(names))

    changed = deepcopy(resource)
    changed["documents"]["state_machine.incident"]["transitions"][0]["actor"] = "CMP-UNKNOWN"
    with pytest.raises(ContractRegistryError, match="unknown actor"):
        TransitionKernel(changed, PredicateRegistry.fact_registry(names))

    changed = deepcopy(resource)
    changed["documents"]["commands_events"]["commands"].append(
        {
            "id": "CMD-UNBOUND",
            "owner": "CMP-CONTROL-API",
            "idempotency": "required",
            "version_check": "state_version",
        }
    )
    with pytest.raises(ContractRegistryError, match="unbound command"):
        TransitionKernel(changed, PredicateRegistry.fact_registry(names))

    changed = deepcopy(resource)
    changed["contracts_version"] = "9.9.9"
    with pytest.raises(ContractRegistryError, match="unsupported contracts version"):
        TransitionKernel(changed, PredicateRegistry.fact_registry(names))


def test_state_version_fencing_and_digest_policies_are_enforced(
    kernel: TransitionKernel,
) -> None:
    with pytest.raises(VersionConflictError, match="state version"):
        kernel.decide(request(expected_state_version=1))

    graph_facts = {
        "guard:TR-GRAPH-INTAKE": True,
        "valid_fencing_token": True,
        "bounded_budget": True,
        "checkpoint_committed": True,
    }
    graph_request = request(
        machine_id="agent_graph",
        transition_id="TR-GRAPH-INTAKE",
        owner_component="CMP-AGENT-WORKER",
        actor="CMP-AGENT-WORKER",
        aggregate_id="graph-1",
        state="INTAKE",
        command="CMD-ADVANCE-AGENT-GRAPH",
        expected_state_version=None,
        idempotency_key=None,
        current_fencing_token="fence-2",
        fencing_token="fence-1",
        facts=graph_facts,
    )
    with pytest.raises(VersionConflictError, match="fencing"):
        kernel.decide(graph_request)

    action_facts = {
        "guard:TR-ACTION-R1-AUTHORIZE": True,
        "matching_tenant": True,
        "valid_policy_decision": True,
        "immutable_action_digest": True,
        "valid_resource_version": True,
        "idempotency_reserved": True,
    }
    action_request = request(
        machine_id="action_transaction",
        transition_id="TR-ACTION-R1-AUTHORIZE",
        owner_component="CMP-ACTION-EXECUTOR",
        actor="CMP-POLICY-ENGINE",
        aggregate_id="action-1",
        state="PREPARED",
        command="CMD-AUTHORIZE-ACTION",
        idempotency_key=None,
        current_action_digest="digest-current",
        action_digest="digest-stale",
        facts=action_facts,
    )
    with pytest.raises(VersionConflictError, match="action digest"):
        kernel.decide(action_request)


def test_required_and_derived_idempotency_are_distinct(kernel: TransitionKernel) -> None:
    with pytest.raises(IdempotencyError, match="required"):
        kernel.decide(request(idempotency_key=None))

    facts = {
        "guard:TR-INCIDENT-START": True,
        "matching_tenant": True,
        "expected_state_version": True,
    }
    derived_request = request(
        transition_id="TR-INCIDENT-START",
        actor="CMP-SCHEDULER",
        state="QUEUED",
        command="CMD-START-INVESTIGATION",
        idempotency_key=None,
        facts=facts,
    )
    decision = kernel.decide(derived_request)
    assert decision.idempotency_key is not None
    assert decision.idempotency_key.startswith("derived:")
    assert decision == kernel.decide(derived_request)

    with pytest.raises(IdempotencyError, match="forbidden"):
        kernel.decide(
            request(
                transition_id="TR-INCIDENT-START",
                actor="CMP-SCHEDULER",
                state="QUEUED",
                command="CMD-START-INVESTIGATION",
                idempotency_key="caller-value",
                facts=facts,
            )
        )


def test_owner_service_cannot_cross_machine_boundary(kernel: TransitionKernel) -> None:
    incident_service = kernel.service("incident")
    assert incident_service.decide(request()).next_state == "QUEUED"
    with pytest.raises(OwnerMismatchError):
        incident_service.decide(request(machine_id="runtime_task", owner_component="CMP-SCHEDULER"))


def test_unknown_schema_and_same_key_different_digest_are_rejected(
    kernel: TransitionKernel,
) -> None:
    with pytest.raises(SchemaVersionError):
        kernel.decide(request(schema_version="9.9.9"))

    accepted = kernel.decide(request())
    assert len(accepted.request_digest) == 64
    assert kernel.decide(request(reserved_request_digest=accepted.request_digest)) == accepted
    with pytest.raises(IdempotencyError, match="different canonical digest"):
        kernel.decide(
            request(
                aggregate_id="incident-2",
                reserved_request_digest=accepted.request_digest,
            )
        )
