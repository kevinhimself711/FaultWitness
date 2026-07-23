"""Pure, deterministic execution kernel for the four frozen state owners.

The kernel interprets the compiled contract bundle.  It performs no persistence,
I/O, clock reads, identifier generation, or side effects; callers own those
concerns and may persist the returned decision atomically with their outbox.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Final

Predicate = Callable[["TransitionRequest"], bool]

MACHINE_OWNERS: Final[dict[str, str]] = {
    "incident": "CMP-CONTROL-API",
    "runtime_task": "CMP-SCHEDULER",
    "agent_graph": "CMP-AGENT-WORKER",
    "action_transaction": "CMP-ACTION-EXECUTOR",
}
GUARD_PREFIX: Final = "guard:"
SUPPORTED_CONTRACTS_VERSION: Final = "1.1.0"


class TransitionKernelError(ValueError):
    """Base class for deterministic contract rejections."""

    code = "transition_rejected"


class ContractRegistryError(TransitionKernelError):
    code = "contract_registry_invalid"


class UnknownMachineError(TransitionKernelError):
    code = "unknown_machine"


class UnknownTransitionError(TransitionKernelError):
    code = "unknown_transition"


class OwnerMismatchError(TransitionKernelError):
    code = "owner_mismatch"


class ActorMismatchError(TransitionKernelError):
    code = "actor_mismatch"


class IllegalTransitionError(TransitionKernelError):
    code = "illegal_transition"


class CommandMismatchError(TransitionKernelError):
    code = "command_mismatch"


class VersionConflictError(TransitionKernelError):
    code = "version_conflict"


class SchemaVersionError(TransitionKernelError):
    code = "schema_version_unknown"


class IdempotencyError(TransitionKernelError):
    code = "idempotency_invalid"


class GuardRejectedError(TransitionKernelError):
    code = "guard_rejected"

    def __init__(self, transition_id: str, failed_predicates: tuple[str, ...]) -> None:
        self.transition_id = transition_id
        self.failed_predicates = failed_predicates
        super().__init__(
            f"{transition_id}: guard predicates rejected: {', '.join(failed_predicates)}"
        )


@dataclass(frozen=True, slots=True)
class TransitionRequest:
    """All deterministic inputs needed to decide one state transition."""

    machine_id: str
    transition_id: str
    owner_component: str
    actor: str
    aggregate_id: str
    state: str
    state_version: int
    command: str
    schema_version: str = "1.1.0"
    expected_state_version: int | None = None
    idempotency_key: str | None = None
    reserved_request_digest: str | None = None
    current_fencing_token: str | None = None
    fencing_token: str | None = None
    current_action_digest: str | None = None
    action_digest: str | None = None
    facts: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        required_strings = {
            "machine_id": self.machine_id,
            "transition_id": self.transition_id,
            "owner_component": self.owner_component,
            "actor": self.actor,
            "aggregate_id": self.aggregate_id,
            "state": self.state,
            "command": self.command,
            "schema_version": self.schema_version,
        }
        for field, value in required_strings.items():
            if not isinstance(value, str) or not value:
                raise TypeError(f"{field} must be a non-empty string")
        if type(self.state_version) is not int or self.state_version < 0:
            raise TypeError("state_version must be a non-negative integer")
        if self.expected_state_version is not None and (
            type(self.expected_state_version) is not int or self.expected_state_version < 0
        ):
            raise TypeError("expected_state_version must be a non-negative integer or None")
        if self.facts is not None and not isinstance(self.facts, Mapping):
            raise TypeError("facts must be a mapping or None")


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    """A stable decision that an owner may persist; it is not a persistence claim."""

    machine_id: str
    owner_component: str
    transition_id: str
    actor: str
    aggregate_id: str
    previous_state: str
    next_state: str
    previous_state_version: int
    next_state_version: int
    command: str
    event: str
    schema_version: str
    automatic: bool
    idempotency_key: str | None
    request_digest: str
    evaluated_predicates: tuple[str, ...]
    decision_digest: str


class PredicateRegistry:
    """Closed registry of named, side-effect-free guard predicates."""

    def __init__(self, predicates: Mapping[str, Predicate]) -> None:
        if not isinstance(predicates, Mapping):
            raise TypeError("predicates must be a mapping")
        copied: dict[str, Predicate] = {}
        for name, predicate in predicates.items():
            if not isinstance(name, str) or not name:
                raise ContractRegistryError("predicate names must be non-empty strings")
            if not callable(predicate):
                raise ContractRegistryError(f"predicate {name!r} is not callable")
            copied[name] = predicate
        self._predicates = MappingProxyType(copied)

    @classmethod
    def fact_registry(cls, names: set[str] | frozenset[str]) -> PredicateRegistry:
        """Build strict predicates that accept only the literal fact value ``True``."""

        return cls(
            {
                name: lambda request, predicate=name: (request.facts or {}).get(predicate) is True
                for name in names
            }
        )

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._predicates)

    def evaluate(self, name: str, request: TransitionRequest) -> bool:
        try:
            predicate = self._predicates[name]
        except KeyError as exc:
            raise ContractRegistryError(f"unknown predicate {name!r}") from exc
        result = predicate(request)
        if type(result) is not bool:
            raise ContractRegistryError(f"predicate {name!r} did not return bool")
        return result


@dataclass(frozen=True, slots=True)
class _Machine:
    machine_id: str
    owner_component: str
    states: frozenset[str]
    terminal_states: frozenset[str]
    transitions: Mapping[str, Mapping[str, Any]]


class TransitionKernel:
    """Contract-driven kernel shared by four isolated owner services."""

    def __init__(self, resource: Mapping[str, Any], predicates: PredicateRegistry) -> None:
        self._contracts_version = _nonempty_string(
            resource.get("contracts_version"), "resource.contracts_version"
        )
        if self._contracts_version != SUPPORTED_CONTRACTS_VERSION:
            raise ContractRegistryError(
                f"unsupported contracts version {self._contracts_version!r}"
            )
        documents = _mapping(resource.get("documents"), "resource.documents")
        catalog = _mapping(documents.get("commands_events"), "commands_events")
        self._commands = _index_registry(catalog.get("commands"), "command")
        self._events = _index_registry(catalog.get("events"), "event")
        for command_id, command in self._commands.items():
            _nonempty_string(command.get("owner"), f"{command_id}.owner")
            if command.get("idempotency") not in {"required", "derived", "not_applicable"}:
                raise ContractRegistryError(f"{command_id}: unknown idempotency policy")
            if command.get("version_check") not in {
                "state_version",
                "fencing_token",
                "digest_and_state_version",
            }:
                raise ContractRegistryError(f"{command_id}: unknown version policy")
        for event_id, event in self._events.items():
            _nonempty_string(event.get("producer"), f"{event_id}.producer")
            if event.get("delivery") != "at_least_once" or event.get("dedupe_key") != "event_id":
                raise ContractRegistryError(f"{event_id}: unknown delivery contract")

        known_components = {
            *(command["owner"] for command in self._commands.values()),
            *(event["producer"] for event in self._events.values()),
            *MACHINE_OWNERS.values(),
        }

        machines: dict[str, _Machine] = {}
        used_predicates: set[str] = set()
        used_commands: set[str] = set()
        used_events: set[str] = set()
        for machine_id, expected_owner in MACHINE_OWNERS.items():
            raw = _mapping(
                documents.get(f"state_machine.{machine_id}"),
                f"state_machine.{machine_id}",
            )
            if raw.get("id") != machine_id:
                raise ContractRegistryError(f"state machine identity mismatch for {machine_id}")
            owner = raw.get("owner_component")
            if owner != expected_owner:
                raise ContractRegistryError(
                    f"{machine_id}: expected owner {expected_owner}, got {owner!r}"
                )
            states = _string_set(raw.get("states"), f"{machine_id}.states")
            terminal_states = _string_set(
                raw.get("terminal_states"), f"{machine_id}.terminal_states"
            )
            if not terminal_states <= states:
                raise ContractRegistryError(f"{machine_id}: terminal state is not declared")

            transitions: dict[str, Mapping[str, Any]] = {}
            raw_transitions = raw.get("transitions")
            if not isinstance(raw_transitions, list):
                raise ContractRegistryError(f"{machine_id}.transitions must be a list")
            for raw_transition in raw_transitions:
                transition = _mapping(raw_transition, f"{machine_id}.transition")
                transition_id = _nonempty_string(transition.get("id"), "transition.id")
                if transition_id in transitions:
                    raise ContractRegistryError(f"duplicate transition {transition_id}")
                actor = _nonempty_string(transition.get("actor"), f"{transition_id}.actor")
                if actor not in known_components:
                    raise ContractRegistryError(f"{transition_id}: unknown actor {actor}")
                _nonempty_string(transition.get("guard"), f"{transition_id}.guard")
                if type(transition.get("automatic")) is not bool:
                    raise ContractRegistryError(f"{transition_id}: automatic must be bool")
                source = _nonempty_string(transition.get("from"), f"{transition_id}.from")
                target = _nonempty_string(transition.get("to"), f"{transition_id}.to")
                if source not in states or target not in states:
                    raise ContractRegistryError(
                        f"{transition_id}: transition references unknown state"
                    )
                command = _nonempty_string(transition.get("command"), f"{transition_id}.command")
                event = _nonempty_string(transition.get("event"), f"{transition_id}.event")
                if command not in self._commands:
                    raise ContractRegistryError(f"{transition_id}: unknown command {command}")
                if event not in self._events:
                    raise ContractRegistryError(f"{transition_id}: unknown event {event}")
                used_commands.add(command)
                used_events.add(event)
                preconditions = transition.get("preconditions")
                if not isinstance(preconditions, list) or not preconditions:
                    raise ContractRegistryError(f"{transition_id}: preconditions must be non-empty")
                predicate_names = tuple(
                    _nonempty_string(value, f"{transition_id}.precondition")
                    for value in preconditions
                )
                if len(predicate_names) != len(set(predicate_names)):
                    raise ContractRegistryError(f"{transition_id}: duplicate precondition")
                guard_predicate = f"{GUARD_PREFIX}{transition_id}"
                used_predicates.add(guard_predicate)
                used_predicates.update(predicate_names)
                transitions[transition_id] = MappingProxyType(
                    {
                        **transition,
                        "guard_predicate": guard_predicate,
                        "preconditions": predicate_names,
                    }
                )
            machines[machine_id] = _Machine(
                machine_id=machine_id,
                owner_component=owner,
                states=states,
                terminal_states=terminal_states,
                transitions=MappingProxyType(transitions),
            )

        if unbound_commands := sorted(set(self._commands) - used_commands):
            raise ContractRegistryError(f"unbound command registry items {unbound_commands}")
        if unbound_events := sorted(set(self._events) - used_events):
            raise ContractRegistryError(f"unbound event registry items {unbound_events}")

        missing = sorted(used_predicates - predicates.names)
        unknown = sorted(predicates.names - used_predicates)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing predicates {missing}")
            if unknown:
                details.append(f"unknown predicates {unknown}")
            raise ContractRegistryError("predicate registry mismatch: " + "; ".join(details))
        self._machines = MappingProxyType(machines)
        self._predicates = predicates
        self.predicate_names = frozenset(used_predicates)

    @staticmethod
    def required_predicates(resource: Mapping[str, Any]) -> frozenset[str]:
        documents = _mapping(resource.get("documents"), "resource.documents")
        names: set[str] = set()
        for machine_id in MACHINE_OWNERS:
            machine = _mapping(
                documents.get(f"state_machine.{machine_id}"),
                f"state_machine.{machine_id}",
            )
            transitions = machine.get("transitions")
            if not isinstance(transitions, list):
                raise ContractRegistryError(f"{machine_id}.transitions must be a list")
            for transition in transitions:
                item = _mapping(transition, f"{machine_id}.transition")
                transition_id = _nonempty_string(item.get("id"), "transition.id")
                names.add(f"{GUARD_PREFIX}{transition_id}")
                preconditions = item.get("preconditions")
                if not isinstance(preconditions, list):
                    raise ContractRegistryError("transition preconditions must be a list")
                names.update(
                    _nonempty_string(value, "transition.precondition") for value in preconditions
                )
        return frozenset(names)

    def service(self, machine_id: str) -> OwnerTransitionService:
        try:
            machine = self._machines[machine_id]
        except KeyError as exc:
            raise UnknownMachineError(f"unknown state machine {machine_id!r}") from exc
        return OwnerTransitionService(self, machine.machine_id, machine.owner_component)

    def decide(self, request: TransitionRequest) -> TransitionDecision:
        if request.schema_version != self._contracts_version:
            raise SchemaVersionError(
                f"expected schema version {self._contracts_version!r}, "
                f"got {request.schema_version!r}"
            )
        try:
            machine = self._machines[request.machine_id]
        except KeyError as exc:
            raise UnknownMachineError(f"unknown state machine {request.machine_id!r}") from exc
        if request.owner_component != machine.owner_component:
            raise OwnerMismatchError(
                f"{request.machine_id}: {request.owner_component!r} cannot own "
                f"{machine.owner_component!r} state"
            )
        try:
            transition = machine.transitions[request.transition_id]
        except KeyError as exc:
            raise UnknownTransitionError(
                f"{request.machine_id}: unknown transition {request.transition_id!r}"
            ) from exc
        if request.state in machine.terminal_states:
            raise IllegalTransitionError(
                f"{request.machine_id}: terminal state {request.state!r} cannot transition"
            )
        if request.state != transition["from"]:
            raise IllegalTransitionError(
                f"{request.transition_id}: expected state {transition['from']!r}, "
                f"got {request.state!r}"
            )
        if request.actor != transition["actor"]:
            raise ActorMismatchError(
                f"{request.transition_id}: expected actor {transition['actor']!r}, "
                f"got {request.actor!r}"
            )
        if request.command != transition["command"]:
            raise CommandMismatchError(
                f"{request.transition_id}: expected command {transition['command']!r}, "
                f"got {request.command!r}"
            )

        command = self._commands[request.command]
        self._check_versions(request, transition, command)
        idempotency_key = self._idempotency_key(request, command)

        predicate_order = (transition["guard_predicate"], *transition["preconditions"])
        failed = tuple(
            name for name in predicate_order if not self._predicates.evaluate(name, request)
        )
        if failed:
            raise GuardRejectedError(request.transition_id, failed)

        request_digest = self._request_digest(request, idempotency_key, predicate_order)
        if (
            request.reserved_request_digest is not None
            and request.reserved_request_digest != request_digest
        ):
            raise IdempotencyError(
                f"{request.command}: same idempotency key has a different canonical digest"
            )

        fields: dict[str, Any] = {
            "actor": request.actor,
            "aggregate_id": request.aggregate_id,
            "automatic": transition["automatic"],
            "command": request.command,
            "evaluated_predicates": list(predicate_order),
            "event": transition["event"],
            "idempotency_key": idempotency_key,
            "machine_id": request.machine_id,
            "next_state": transition["to"],
            "next_state_version": request.state_version + 1,
            "owner_component": machine.owner_component,
            "previous_state": request.state,
            "previous_state_version": request.state_version,
            "request_digest": request_digest,
            "schema_version": self._contracts_version,
            "transition_id": request.transition_id,
        }
        digest = sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        fields["evaluated_predicates"] = tuple(fields["evaluated_predicates"])
        return TransitionDecision(**fields, decision_digest=digest)

    @staticmethod
    def _request_digest(
        request: TransitionRequest,
        idempotency_key: str | None,
        predicate_order: tuple[str, ...],
    ) -> str:
        material = {
            "action_digest": request.action_digest,
            "actor": request.actor,
            "aggregate_id": request.aggregate_id,
            "command": request.command,
            "expected_state_version": request.expected_state_version,
            "fencing_token": request.fencing_token,
            "idempotency_key": idempotency_key,
            "machine_id": request.machine_id,
            "owner_component": request.owner_component,
            "predicates": list(predicate_order),
            "schema_version": request.schema_version,
            "state": request.state,
            "state_version": request.state_version,
            "transition_id": request.transition_id,
        }
        return sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _check_versions(
        request: TransitionRequest,
        transition: Mapping[str, Any],
        command: Mapping[str, Any],
    ) -> None:
        version_check = command.get("version_check")
        requires_state = version_check in {"state_version", "digest_and_state_version"}
        requires_state = requires_state or "expected_state_version" in transition["preconditions"]
        if requires_state and request.expected_state_version != request.state_version:
            raise VersionConflictError(
                f"{request.transition_id}: expected state version "
                f"{request.expected_state_version!r}, current is {request.state_version}"
            )
        if version_check == "fencing_token":
            if (
                not request.current_fencing_token
                or request.fencing_token != request.current_fencing_token
            ):
                raise VersionConflictError(f"{request.transition_id}: stale fencing token")
        elif version_check == "digest_and_state_version":
            if (
                not request.current_action_digest
                or request.action_digest != request.current_action_digest
            ):
                raise VersionConflictError(f"{request.transition_id}: stale action digest")
        elif version_check != "state_version":
            raise ContractRegistryError(
                f"{request.command}: unknown version policy {version_check!r}"
            )

    @staticmethod
    def _idempotency_key(request: TransitionRequest, command: Mapping[str, Any]) -> str | None:
        policy = command.get("idempotency")
        supplied = request.idempotency_key
        if policy == "required":
            if not isinstance(supplied, str) or not supplied:
                raise IdempotencyError(f"{request.command}: idempotency key is required")
            return supplied
        if policy == "derived":
            if supplied is not None:
                raise IdempotencyError(
                    f"{request.command}: caller key is forbidden for derived idempotency"
                )
            material = {
                "aggregate_id": request.aggregate_id,
                "command": request.command,
                "machine_id": request.machine_id,
                "state_version": request.state_version,
                "transition_id": request.transition_id,
            }
            digest = sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            return f"derived:{digest}"
        if policy == "not_applicable":
            if supplied is not None:
                raise IdempotencyError(f"{request.command}: idempotency key is not applicable")
            return None
        raise ContractRegistryError(f"{request.command}: unknown idempotency policy {policy!r}")


@dataclass(frozen=True, slots=True)
class OwnerTransitionService:
    """A view that cannot be rebound from one state owner to another."""

    _kernel: TransitionKernel
    machine_id: str
    owner_component: str

    def decide(self, request: TransitionRequest) -> TransitionDecision:
        if request.machine_id != self.machine_id:
            raise OwnerMismatchError(
                f"{self.machine_id} service cannot decide {request.machine_id!r} state"
            )
        if request.owner_component != self.owner_component:
            raise OwnerMismatchError(f"{self.machine_id} service owner is {self.owner_component!r}")
        return self._kernel.decide(request)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractRegistryError(f"{field} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise ContractRegistryError(f"{field} keys must be strings")
    return value


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractRegistryError(f"{field} must be a non-empty string")
    return value


def _string_set(value: Any, field: str) -> frozenset[str]:
    if not isinstance(value, list) or not value:
        raise ContractRegistryError(f"{field} must be a non-empty list")
    strings = [_nonempty_string(item, field) for item in value]
    if len(strings) != len(set(strings)):
        raise ContractRegistryError(f"{field} contains duplicates")
    return frozenset(strings)


def _index_registry(value: Any, kind: str) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ContractRegistryError(f"{kind} registry must be a list")
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in value:
        entry = _mapping(item, f"{kind} registry item")
        identifier = _nonempty_string(entry.get("id"), f"{kind}.id")
        if identifier in indexed:
            raise ContractRegistryError(f"duplicate {kind} {identifier}")
        indexed[identifier] = MappingProxyType(dict(entry))
    return MappingProxyType(indexed)
