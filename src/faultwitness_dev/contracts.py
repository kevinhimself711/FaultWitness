from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError

MACHINE_FILES = {
    "incident": "docs/contracts/state-machines/incident.yaml",
    "runtime_task": "docs/contracts/state-machines/runtime_task.yaml",
    "agent_graph": "docs/contracts/state-machines/agent_graph.yaml",
    "action_transaction": "docs/contracts/state-machines/action_transaction.yaml",
}


def validate_contracts(root: Path, loaded: dict[str, Any]) -> None:
    architecture = loaded["docs/architecture/ARCHITECTURE.yaml"]
    catalog = loaded["docs/contracts/COMMAND_EVENT_CATALOG.yaml"]
    type_catalog = loaded["docs/contracts/TYPE_CATALOG.yaml"]
    failures = loaded["docs/contracts/FAILURE_SEMANTICS.yaml"]
    walkthroughs = loaded["docs/contracts/WALKTHROUGH_BINDINGS.yaml"]
    openapi = loaded["docs/contracts/openapi.yaml"]
    asyncapi = loaded["docs/contracts/asyncapi.yaml"]
    machines = {name: loaded[path] for name, path in MACHINE_FILES.items()}

    _validate_catalog(catalog, architecture)
    for name, machine in machines.items():
        if machine["id"] != name:
            raise GovernanceError(f"state machine file/id mismatch: {name}")
        _validate_state_machine(machine, architecture, catalog)
    expected_diagrams = render_state_machine_document(machines)
    diagram_path = root / "docs" / "contracts" / "STATE_MACHINE_DIAGRAMS.md"
    if not diagram_path.is_file() or diagram_path.read_text(encoding="utf-8") != expected_diagrams:
        raise GovernanceError("state machine Mermaid document drifted from YAML source")
    _validate_safety_paths(machines)
    _validate_type_catalog(type_catalog, architecture)
    _validate_failure_semantics(failures)
    _validate_error_references(catalog, failures)
    _validate_openapi(openapi)
    _validate_asyncapi(asyncapi)
    _validate_walkthrough_bindings(walkthroughs, machines, catalog, failures, openapi)


def render_state_machine_document(machines: dict[str, dict[str, Any]]) -> str:
    titles = {
        "incident": "Incident Lifecycle",
        "runtime_task": "Runtime Task",
        "agent_graph": "Agent Graph",
        "action_transaction": "ActionTransaction",
    }
    lines = [
        "# Generated State Machine Diagrams",
        "",
        "<!-- GENERATED from docs/contracts/state-machines/*.yaml; do not edit by hand. -->",
        "",
        "The YAML transition tables are the single source of truth. "
        "`faultwitness_dev validate` compares this document byte-for-byte with the renderer.",
        "",
    ]
    for machine_id in MACHINE_FILES:
        machine = machines[machine_id]
        lines.extend(
            [
                f"## {titles[machine_id]}",
                "",
                f"Owner: `{machine['owner_component']}`; store: "
                f"`{machine['authoritative_store']}`.",
                "",
                "```mermaid",
                "stateDiagram-v2",
                f"    [*] --> {machine['initial_state']}",
            ]
        )
        for transition in machine["transitions"]:
            lines.append(
                f"    {transition['from']} --> {transition['to']}: {transition['id']}"
            )
        for terminal in machine["terminal_states"]:
            lines.append(f"    {terminal} --> [*]")
        lines.extend(["```", "", "Invariants:", ""])
        lines.extend(f"- {invariant}" for invariant in machine["invariants"])
        lines.append("")
    return "\n".join(lines)


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _validate_catalog(catalog: dict[str, Any], architecture: dict[str, Any]) -> None:
    component_ids = {component["id"] for component in architecture["components"]}
    command_ids = [command["id"] for command in catalog["commands"]]
    event_ids = [event["id"] for event in catalog["events"]]
    if duplicates := _duplicates(command_ids):
        raise GovernanceError(f"duplicate command IDs: {duplicates}")
    if duplicates := _duplicates(event_ids):
        raise GovernanceError(f"duplicate event IDs: {duplicates}")
    for command in catalog["commands"]:
        if command["owner"] not in component_ids:
            raise GovernanceError(f"command {command['id']} has unknown owner")
        if command["idempotency"] == "not_applicable":
            raise GovernanceError(f"state command lacks idempotency semantics: {command['id']}")
        if command["version_check"] == "not_applicable":
            raise GovernanceError(f"state command lacks version semantics: {command['id']}")
    for event in catalog["events"]:
        if event["producer"] not in component_ids:
            raise GovernanceError(f"event {event['id']} has unknown producer")


def _validate_state_machine(
    machine: dict[str, Any],
    architecture: dict[str, Any],
    catalog: dict[str, Any],
) -> None:
    component_ids = {component["id"] for component in architecture["components"]}
    store_ids = {store["id"] for store in architecture["stores"]}
    command_ids = {command["id"] for command in catalog["commands"]}
    event_ids = {event["id"] for event in catalog["events"]}
    state_names = machine["states"]
    state_set = set(state_names)
    terminal_set = set(machine["terminal_states"])
    if duplicates := _duplicates(state_names):
        raise GovernanceError(f"state machine {machine['id']} has duplicate states: {duplicates}")
    if machine["initial_state"] not in state_set:
        raise GovernanceError(f"state machine {machine['id']} has unknown initial state")
    if machine["initial_state"] in terminal_set:
        raise GovernanceError(f"state machine {machine['id']} starts terminal")
    if not terminal_set.issubset(state_set):
        raise GovernanceError(f"state machine {machine['id']} has unknown terminal states")
    if machine["owner_component"] not in component_ids:
        raise GovernanceError(f"state machine {machine['id']} has unknown owner")
    if machine["authoritative_store"] not in store_ids:
        raise GovernanceError(f"state machine {machine['id']} has unknown store")

    transition_ids = [transition["id"] for transition in machine["transitions"]]
    if duplicates := _duplicates(transition_ids):
        raise GovernanceError(
            f"state machine {machine['id']} has duplicate transitions: {duplicates}"
        )
    graph: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for transition in machine["transitions"]:
        source = transition["from"]
        target = transition["to"]
        if source not in state_set or target not in state_set:
            raise GovernanceError(
                f"state machine {machine['id']} transition {transition['id']} "
                "references an unknown state"
            )
        if source in terminal_set:
            raise GovernanceError(
                f"state machine {machine['id']} has terminal outgoing transition"
            )
        if transition["actor"] not in component_ids:
            raise GovernanceError(f"transition {transition['id']} has unknown actor")
        if transition["command"] not in command_ids:
            raise GovernanceError(f"transition {transition['id']} has unknown command")
        if transition["event"] not in event_ids:
            raise GovernanceError(f"transition {transition['id']} has unknown event")
        graph[source].add(target)
        reverse[target].add(source)

    reachable = _walk({machine["initial_state"]}, graph)
    unreachable = sorted(state_set - reachable)
    if unreachable:
        raise GovernanceError(
            f"state machine {machine['id']} has unreachable states: {unreachable}"
        )
    can_terminate = _walk(terminal_set, reverse)
    trapped = sorted(state_set - terminal_set - can_terminate)
    if trapped:
        raise GovernanceError(
            f"state machine {machine['id']} has states without terminal path: {trapped}"
        )


def _walk(starts: set[str], graph: dict[str, set[str]]) -> set[str]:
    visited = set(starts)
    queue = deque(starts)
    while queue:
        current = queue.popleft()
        for target in graph[current]:
            if target not in visited:
                visited.add(target)
                queue.append(target)
    return visited


def _validate_safety_paths(machines: dict[str, dict[str, Any]]) -> None:
    incident = machines["incident"]
    incident_r2 = next(
        transition
        for transition in incident["transitions"]
        if transition["from"] == "WAITING_APPROVAL" and transition["to"] == "EXECUTING"
    )
    _require_preconditions(
        incident_r2,
        {"valid_approval_digest", "valid_resource_version", "approval_not_expired"},
        "Incident R2 execution",
    )

    graph = machines["agent_graph"]
    graph_r2 = next(
        transition
        for transition in graph["transitions"]
        if transition["from"] == "AWAIT_APPROVAL" and transition["to"] == "DISPATCH_ACTION"
    )
    _require_preconditions(
        graph_r2,
        {"valid_approval_digest", "valid_resource_version", "matching_tenant"},
        "Agent R2 dispatch",
    )

    action = machines["action_transaction"]
    dispatches = [
        transition for transition in action["transitions"] if transition["to"] == "EXECUTING"
    ]
    if len(dispatches) != 1 or dispatches[0]["from"] != "APPROVED":
        raise GovernanceError("Action execution bypasses APPROVED")
    _require_preconditions(
        dispatches[0],
        {
            "matching_tenant",
            "valid_authorization",
            "valid_approval_if_R2",
            "valid_approval_digest",
            "valid_resource_version",
            "current_policy_allow",
            "idempotency_reserved",
        },
        "Action dispatch",
    )
    uncertain_outgoing = [
        transition for transition in action["transitions"] if transition["from"] == "UNCERTAIN"
    ]
    if not uncertain_outgoing or any(
        transition["automatic"]
        or transition["command"] != "CMD-RECONCILE-ACTION"
        or transition["to"] not in {"VERIFYING", "MANUAL"}
        for transition in uncertain_outgoing
    ):
        raise GovernanceError("UNCERTAIN has an automatic or blind-retry path")

    runtime = machines["runtime_task"]
    completion = [
        transition for transition in runtime["transitions"] if transition["to"] == "SUCCEEDED"
    ]
    if len(completion) != 1:
        raise GovernanceError("Runtime Task must have one success commit path")
    _require_preconditions(
        completion[0],
        {"valid_fencing_token", "matching_attempt_id", "checkpoint_committed"},
        "Runtime success commit",
    )
    if any(
        transition["to"] == "SUCCEEDED" and transition["from"] != "RUNNING"
        for transition in runtime["transitions"]
    ):
        raise GovernanceError("Runtime Task can commit after lease loss")


def _require_preconditions(
    transition: dict[str, Any], expected: set[str], label: str
) -> None:
    missing = sorted(expected - set(transition["preconditions"]))
    if missing:
        raise GovernanceError(f"{label} is missing safety preconditions: {missing}")


def _validate_type_catalog(
    catalog: dict[str, Any], architecture: dict[str, Any]
) -> None:
    expected_types = {
        "TenantContext",
        "IncidentSpec",
        "IncidentState",
        "RunTask",
        "RunState",
        "Lease",
        "ChangeEvent",
        "AgentState",
        "EvidenceRef",
        "Hypothesis",
        "ProbePlan",
        "ToolDefinition",
        "ToolCall",
        "ToolResult",
        "SkillManifest",
        "ActionProposal",
        "ApprovalGrant",
        "ActionTransaction",
        "TrajectoryIR",
        "EvalResult",
        "DomainEvent",
    }
    records = {record["name"]: record for record in catalog["types"]}
    if len(records) != len(catalog["types"]) or set(records) != expected_types:
        raise GovernanceError("core type catalog is incomplete or has duplicate names")
    components = {component["id"] for component in architecture["components"]}
    stores = {store["id"] for store in architecture["stores"]}
    for record in records.values():
        if record["owner_component"] not in components:
            raise GovernanceError(f"type {record['name']} has unknown owner")
        store = record["authoritative_store"]
        if store is not None and store not in stores:
            raise GovernanceError(f"type {record['name']} has unknown store")
        field_names = [field["name"] for field in record["fields"]]
        if _duplicates(field_names):
            raise GovernanceError(f"type {record['name']} has duplicate fields")
    tenant_fields = {field["name"]: field for field in records["TenantContext"]["fields"]}
    for field_name in ("tenant_id", "user_id", "roles"):
        if tenant_fields[field_name]["source"] != "oidc_claim":
            raise GovernanceError(f"TenantContext {field_name} is not sourced from OIDC")
    forbidden = {"chain_of_thought", "ground_truth", "locked_answer"}
    for record in records.values():
        if forbidden.intersection(field["name"] for field in record["fields"]):
            raise GovernanceError(f"type {record['name']} exposes forbidden private data")


def _validate_failure_semantics(document: dict[str, Any]) -> None:
    expected = {
        "FAIL-OIDC-TENANT-INVALID",
        "FAIL-DUPLICATE-CREATE",
        "FAIL-DATABASE-TRANSACTION",
        "FAIL-OUTBOX-PUBLISH",
        "FAIL-WORKER-LEASE-LOSS",
        "FAIL-MODEL-TOOL-TRANSIENT",
        "FAIL-STRUCTURED-OUTPUT",
        "FAIL-QDRANT-UNAVAILABLE",
        "FAIL-MINIO-UNAVAILABLE",
        "FAIL-LANGSMITH-UNAVAILABLE",
        "FAIL-OPA-UNAVAILABLE",
        "FAIL-KEYCLOAK-UNAVAILABLE",
        "FAIL-ACTION-RESPONSE-LOST",
        "FAIL-POSTCONDITION",
        "FAIL-COMPENSATION-UNKNOWN",
        "FAIL-CANCEL",
        "FAIL-GROUND-TRUTH-ACCESS",
    }
    records = {record["id"]: record for record in document["failures"]}
    if len(records) != len(document["failures"]) or set(records) != expected:
        raise GovernanceError("fixed failure semantics catalog is incomplete")
    if records["FAIL-ACTION-RESPONSE-LOST"]["retry_policy"] != "reconcile_only":
        raise GovernanceError("lost action response must reconcile without retry")
    if records["FAIL-COMPENSATION-UNKNOWN"]["retry_policy"] != "manual_only":
        raise GovernanceError("unknown compensation must require manual handling")


def _validate_error_references(
    catalog: dict[str, Any], failure_document: dict[str, Any]
) -> None:
    errors = failure_document["errors"]
    error_ids = [error["id"] for error in errors]
    if duplicates := _duplicates(error_ids):
        raise GovernanceError(f"duplicate error codes: {duplicates}")
    known = set(error_ids)
    referenced = {
        error
        for command in catalog["commands"]
        for error in command["errors"]
    } | {failure["client_error"] for failure in failure_document["failures"]}
    unknown = sorted(referenced - known)
    if unknown:
        raise GovernanceError(f"contracts reference unknown error codes: {unknown}")
    uncertain = next(error for error in errors if error["id"] == "ERR-UNCERTAIN")
    stale_lease = next(error for error in errors if error["id"] == "ERR-STALE-LEASE")
    if uncertain["retryable"] or stale_lease["retryable"]:
        raise GovernanceError("uncertain effects and stale leases cannot be client retried")


def _validate_openapi(document: dict[str, Any]) -> None:
    required_paths = {
        "/v1/incidents",
        "/v1/incidents/{incident_id}",
        "/v1/incidents/{incident_id}/events",
        "/v1/incidents/{incident_id}/approvals",
        "/v1/incidents/{incident_id}/cancel",
        "/v1/incidents/{incident_id}/feedback",
        "/v1/tools",
        "/v1/skills",
    }
    if set(document["paths"]) != required_paths:
        raise GovernanceError("OpenAPI path baseline drifted")
    operation_ids: list[str] = []
    for path_item in document["paths"].values():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if operation:
                operation_ids.append(operation["operationId"])
    if _duplicates(operation_ids):
        raise GovernanceError("OpenAPI has duplicate operationId values")

    for path in (
        "/v1/incidents",
        "/v1/incidents/{incident_id}/approvals",
        "/v1/incidents/{incident_id}/cancel",
        "/v1/incidents/{incident_id}/feedback",
    ):
        parameters = document["paths"][path]["post"].get("parameters", [])
        if not any(
            parameter.get("$ref") == "#/components/parameters/IdempotencyKey"
            for parameter in parameters
        ):
            raise GovernanceError(f"state modifying OpenAPI operation lacks idempotency: {path}")
    schemas = document["components"]["schemas"]
    for schema_name in ("ApprovalRequest", "CancelRequest", "FeedbackRequest"):
        if "expected_state_version" not in schemas[schema_name].get("required", []):
            raise GovernanceError(f"OpenAPI {schema_name} lacks expected_state_version")
    request_schema_names = {
        "IncidentCreate",
        "ApprovalRequest",
        "CancelRequest",
        "FeedbackRequest",
    }
    forbidden_identity = {"tenant_id", "user_id", "roles"}
    for schema_name in request_schema_names:
        fields = set(schemas[schema_name].get("properties", {}))
        if fields.intersection(forbidden_identity):
            raise GovernanceError(f"OpenAPI {schema_name} accepts caller supplied identity")
    error_required = set(schemas["ErrorEnvelope"]["required"])
    if error_required != {"code", "message", "retryable", "correlation_id", "details"}:
        raise GovernanceError("OpenAPI ErrorEnvelope drifted")
    event_parameters = document["paths"]["/v1/incidents/{incident_id}/events"]["get"][
        "parameters"
    ]
    if not any(parameter.get("name") == "Last-Event-ID" for parameter in event_parameters):
        raise GovernanceError("SSE contract lacks Last-Event-ID resume")


def _validate_asyncapi(document: dict[str, Any]) -> None:
    required_channels = {
        "incidentCommands",
        "incidentEvents",
        "runtimeCommands",
        "runtimeEvents",
        "agentEvents",
        "actionCommands",
        "actionEvents",
        "traceEvents",
    }
    if set(document["channels"]) != required_channels:
        raise GovernanceError("AsyncAPI channel baseline drifted")
    for operation in document["operations"].values():
        channel_ref = operation["channel"]["$ref"]
        if not channel_ref.startswith("#/channels/"):
            raise GovernanceError("AsyncAPI operation has an invalid channel reference")
        channel_name = channel_ref.removeprefix("#/channels/")
        if channel_name not in document["channels"]:
            raise GovernanceError("AsyncAPI operation references an unknown channel")
    schemas = document["components"]["schemas"]
    command_required = set(schemas["CommandEnvelope"]["required"])
    expected_command_fields = {
        "command_id",
        "command_type",
        "schema_version",
        "occurred_at",
        "tenant_id",
        "correlation_id",
        "causation_id",
        "idempotency_key",
        "expected_state_version",
        "payload",
    }
    if not expected_command_fields.issubset(command_required):
        raise GovernanceError("AsyncAPI CommandEnvelope lacks idempotency or version fields")
    event_required = set(schemas["DomainEventEnvelope"]["required"])
    expected_event_fields = {
        "event_id",
        "event_type",
        "schema_version",
        "occurred_at",
        "tenant_id",
        "correlation_id",
        "causation_id",
        "sequence",
        "payload",
    }
    if event_required != expected_event_fields:
        raise GovernanceError("AsyncAPI DomainEventEnvelope drifted")


def _validate_walkthrough_bindings(
    document: dict[str, Any],
    machines: dict[str, dict[str, Any]],
    catalog: dict[str, Any],
    failures: dict[str, Any],
    openapi: dict[str, Any],
) -> None:
    expected_ids = {f"W-ARCH-{number:03d}" for number in range(1, 11)}
    records = {record["id"]: record for record in document["bindings"]}
    if len(records) != len(document["bindings"]) or set(records) != expected_ids:
        raise GovernanceError("contract walkthrough binding set is incomplete")
    transition_ids = {
        transition["id"]
        for machine in machines.values()
        for transition in machine["transitions"]
    }
    command_ids = {command["id"] for command in catalog["commands"]}
    failure_ids = {failure["id"] for failure in failures["failures"]}
    operation_ids = {
        operation["operationId"]
        for path_item in openapi["paths"].values()
        for method in ("get", "post", "put", "patch", "delete")
        if (operation := path_item.get(method))
    }
    for record in records.values():
        unknown_transitions = sorted(set(record["transition_ids"]) - transition_ids)
        unknown_commands = sorted(set(record["command_ids"]) - command_ids)
        unknown_failures = sorted(set(record["failure_ids"]) - failure_ids)
        unknown_operations = sorted(set(record["operations"]) - operation_ids)
        if unknown_transitions or unknown_commands or unknown_failures or unknown_operations:
            raise GovernanceError(
                f"walkthrough {record['id']} has unknown contract references: "
                f"transitions={unknown_transitions}, commands={unknown_commands}, "
                f"failures={unknown_failures}, operations={unknown_operations}"
            )
    required_failure_bindings = {
        "W-ARCH-004": {"FAIL-WORKER-LEASE-LOSS"},
        "W-ARCH-005": {"FAIL-ACTION-RESPONSE-LOST"},
        "W-ARCH-006": {"FAIL-POSTCONDITION"},
        "W-ARCH-007": {"FAIL-COMPENSATION-UNKNOWN"},
        "W-ARCH-008": {"FAIL-CANCEL"},
        "W-ARCH-009": {
            "FAIL-LANGSMITH-UNAVAILABLE",
            "FAIL-OPA-UNAVAILABLE",
            "FAIL-KEYCLOAK-UNAVAILABLE",
        },
        "W-ARCH-010": {"FAIL-OIDC-TENANT-INVALID", "FAIL-GROUND-TRUTH-ACCESS"},
    }
    for walkthrough_id, expected in required_failure_bindings.items():
        missing = sorted(expected - set(records[walkthrough_id]["failure_ids"]))
        if missing:
            raise GovernanceError(
                f"walkthrough {walkthrough_id} misses fixed failures: {missing}"
            )
