from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from faultwitness.contracts.models import (
    CONTRACTS_VERSION,
    CORE_MODEL_TYPES,
    SUPPORT_MODEL_TYPES,
    ActionStateName,
    AgentBudget,
    AgentGraphStateName,
    CommandEnvelope,
    DomainEvent,
    IncidentMode,
    IncidentSpec,
    IncidentState,
    IncidentStateName,
    ModelChunk,
    ModelFamily,
    ModelMessage,
    ModelRequest,
    ModelUsage,
    Role,
    RunStateName,
    SpanRecord,
    SpanStatus,
    StreamControlEvent,
    StreamControlKind,
    TenantContext,
    TraceStage,
)

ROOT = Path(__file__).parents[2]
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def ident(prefix: str) -> str:
    return f"{prefix}{ULID}"


def test_executable_core_models_match_frozen_type_catalog() -> None:
    catalog = yaml.safe_load(
        (ROOT / "docs/contracts/TYPE_CATALOG.yaml").read_text(encoding="utf-8")
    )
    expected = {
        entry["name"]: {field["name"] for field in entry["fields"]}
        for entry in catalog["types"]
    }
    actual = {model.__name__: set(model.model_fields) for model in CORE_MODEL_TYPES}

    assert len(CORE_MODEL_TYPES) == 21
    assert actual == expected


def test_all_boundary_models_are_strict_frozen_and_forbid_extra() -> None:
    assert len(SUPPORT_MODEL_TYPES) == 12
    for model in CORE_MODEL_TYPES + SUPPORT_MODEL_TYPES:
        assert model.model_config["strict"] is True
        assert model.model_config["frozen"] is True
        assert model.model_config["extra"] == "forbid"


def test_tenant_context_accepts_only_typed_ids_and_utc() -> None:
    context = TenantContext(
        tenant_id=ident("ten_"),
        user_id=ident("usr_"),
        roles=frozenset({Role.OPERATOR}),
        token_id=ident("tok_"),
        expires_at=NOW,
    )
    assert context.tenant_id.startswith("ten_")

    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        TenantContext(
            tenant_id=ident("inc_"),
            user_id=ident("usr_"),
            roles=frozenset({Role.OPERATOR}),
            token_id=ident("tok_"),
            expires_at=NOW,
        )

    with pytest.raises(ValidationError, match="timestamp must use UTC"):
        TenantContext(
            tenant_id=ident("ten_"),
            user_id=ident("usr_"),
            roles=frozenset({Role.OPERATOR}),
            token_id=ident("tok_"),
            expires_at=NOW.astimezone(timezone(timedelta(hours=8))),
        )


def test_incident_spec_rejects_coercion_extra_and_invalid_range() -> None:
    budget = AgentBudget(
        deadline=NOW + timedelta(hours=1),
        max_steps=10,
        max_model_calls=3,
        max_tokens=1000,
        max_cost_usd=1.0,
    )
    valid = {
        "environment_id": ident("env_"),
        "service_scope": frozenset({ident("svc_")}),
        "time_window": {"start": NOW - timedelta(hours=1), "end": NOW},
        "symptom_summary": "elevated latency",
        "mode": IncidentMode.DIAGNOSIS_ONLY,
        "budget": budget,
    }
    assert IncidentSpec.model_validate(valid).mode is IncidentMode.DIAGNOSIS_ONLY

    with pytest.raises(ValidationError):
        IncidentSpec.model_validate(valid | {"unknown": True})
    with pytest.raises(ValidationError):
        IncidentSpec.model_validate(valid | {"mode": 1})
    with pytest.raises(ValidationError, match="end must be after start"):
        IncidentSpec.model_validate(valid | {"time_window": {"start": NOW, "end": NOW}})


def test_command_requires_version_idempotency_tenant_and_rejects_private_reasoning() -> None:
    command = {
        "command_id": ident("cmd_"),
        "command_type": "CMD-CREATE-INCIDENT",
        "schema_version": CONTRACTS_VERSION,
        "occurred_at": NOW,
        "tenant_id": ident("ten_"),
        "correlation_id": ident("corr_"),
        "causation_id": None,
        "idempotency_key": "idempotency-key-0001",
        "expected_state_version": 0,
        "payload": {"summary": {"text": "safe structured explanation"}},
    }
    assert CommandEnvelope.model_validate(command).schema_version == "1.1.0"

    for field in ("schema_version", "tenant_id", "idempotency_key", "expected_state_version"):
        invalid = command.copy()
        invalid.pop(field)
        with pytest.raises(ValidationError):
            CommandEnvelope.model_validate(invalid)

    with pytest.raises(ValidationError, match="private reasoning field is prohibited"):
        CommandEnvelope.model_validate(command | {"payload": {"nested": {"chain_of_thought": "x"}}})


def test_domain_event_is_tenant_scoped_versioned_sequenced_and_safe() -> None:
    event = DomainEvent(
        event_id=ident("evt_"),
        event_type="EVT-INCIDENT-CREATED",
        schema_version="1.0.0",
        tenant_id=ident("ten_"),
        correlation_id=ident("corr_"),
        sequence=1,
        payload={"incident_id": ident("inc_")},
    )
    assert event.causation_id is None

    with pytest.raises(ValidationError):
        DomainEvent.model_validate(event.model_dump() | {"sequence": -1})


def test_state_enums_are_exact_frozen_machine_states() -> None:
    assert len(IncidentStateName) == 10
    assert len(RunStateName) == 10
    assert len(AgentGraphStateName) == 19
    assert len(ActionStateName) == 13

    state = IncidentState(
        incident_id=ident("inc_"), state=IncidentStateName.NEW, state_version=0
    )
    with pytest.raises(ValidationError, match="frozen_instance"):
        state.state_version = 1


def test_model_support_types_bind_identity_budget_usage_and_stream_order() -> None:
    budget = AgentBudget(
        deadline=NOW + timedelta(minutes=5),
        max_steps=1,
        max_model_calls=1,
        max_tokens=100,
        max_cost_usd=0.1,
    )
    request = ModelRequest(
        request_id=ident("mreq_"),
        tenant_id=ident("ten_"),
        correlation_id=ident("corr_"),
        model_family=ModelFamily.QWEN,
        model_id="qwen-plus-pinned",
        messages=(ModelMessage(role="user", content="summarize evidence"),),
        stream=True,
        budget=budget,
    )
    usage = ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    chunk = ModelChunk(
        chunk_id=ident("mchunk_"),
        request_id=request.request_id,
        tenant_id=request.tenant_id,
        correlation_id=request.correlation_id,
        sequence=0,
        delta="bounded summary",
        usage=usage,
        occurred_at=NOW,
    )
    assert chunk.sequence == 0

    with pytest.raises(ValidationError, match="total_tokens"):
        ModelUsage(input_tokens=10, output_tokens=5, total_tokens=14)


def test_trace_and_stream_models_reject_private_reasoning_at_any_depth() -> None:
    with pytest.raises(ValidationError, match="private reasoning field is prohibited"):
        SpanRecord(
            span_id=ident("span_"),
            name="model.invoke",
            stage=TraceStage.MODEL,
            started_at=NOW,
            status=SpanStatus.OK,
            attributes={"result": {"reasoning_content": "secret"}},
        )

    with pytest.raises(ValidationError, match="private reasoning field is prohibited"):
        StreamControlEvent(
            event_id=ident("evt_"),
            tenant_id=ident("ten_"),
            incident_id=ident("inc_"),
            kind=StreamControlKind.RETENTION_GAP,
            cursor="cursor-1",
            occurred_at=NOW,
            recoverable=True,
            details={"cot": "secret"},
        )
