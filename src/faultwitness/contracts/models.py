"""Strict executable boundary models for the FaultWitness contract catalog.

The models in this module deliberately contain no transport or persistence logic.  They
are immutable value objects used at trust and ownership boundaries.  In particular,
unstructured dictionaries are checked recursively so that private model reasoning cannot
be smuggled into a command, event, checkpoint, model, or trace payload.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

CONTRACTS_VERSION = "1.1.0"
_SEMVER_RE = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
_SHA256_RE = r"^[0-9a-f]{64}$"
_GIT_SHA_RE = r"^[0-9a-f]{40}$"
_ULID_RE = r"[0-9A-HJKMNP-TV-Z]{26}"
_PRIVATE_REASONING_KEYS = frozenset(
    {
        "chain_of_thought",
        "chainofthought",
        "cot",
        "private_reasoning",
        "reasoning_content",
        "hidden_reasoning",
        "internal_monologue",
    }
)


def _prefixed_ulid(prefix: str) -> type[str]:
    return Annotated[str, StringConstraints(pattern=rf"^{re.escape(prefix)}{_ULID_RE}$")]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC offset +00:00")
    return value


def _reject_private_reasoning(value: Any, path: str = "payload") -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in _PRIVATE_REASONING_KEYS:
                raise ValueError(f"private reasoning field is prohibited at {path}.{key}")
            _reject_private_reasoning(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_private_reasoning(nested, f"{path}[{index}]")
    return value


type UtcDateTime = Annotated[datetime, AfterValidator(_utc)]
type SemVer = Annotated[str, StringConstraints(pattern=_SEMVER_RE)]
type Sha256 = Annotated[str, StringConstraints(pattern=_SHA256_RE)]
type GitSha = Annotated[str, StringConstraints(pattern=_GIT_SHA_RE)]
type BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
type NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
type IdempotencyKey = Annotated[str, StringConstraints(min_length=16, max_length=128)]

TenantId = _prefixed_ulid("ten_")
UserId = _prefixed_ulid("usr_")
TokenId = _prefixed_ulid("tok_")
EnvironmentId = _prefixed_ulid("env_")
ServiceId = _prefixed_ulid("svc_")
IncidentId = _prefixed_ulid("inc_")
TaskId = _prefixed_ulid("task_")
AttemptId = _prefixed_ulid("att_")
WorkerId = _prefixed_ulid("wrk_")
ChangeId = _prefixed_ulid("chg_")
EvidenceRefId = _prefixed_ulid("evi_")
HypothesisId = _prefixed_ulid("hyp_")
ProbeId = _prefixed_ulid("prb_")
ToolId = _prefixed_ulid("tool_")
ToolCallId = _prefixed_ulid("call_")
SkillId = _prefixed_ulid("skill_")
ActionId = _prefixed_ulid("act_")
TrajectoryId = _prefixed_ulid("traj_")
EvalId = _prefixed_ulid("eval_")
EventId = _prefixed_ulid("evt_")
CommandId = _prefixed_ulid("cmd_")
CorrelationId = _prefixed_ulid("corr_")
FeedbackId = _prefixed_ulid("feedback_")
OutboxId = _prefixed_ulid("out_")
InboxId = _prefixed_ulid("inbox_")
CheckpointId = _prefixed_ulid("ckpt_")
ModelRequestId = _prefixed_ulid("mreq_")
ModelResponseId = _prefixed_ulid("mres_")
ModelChunkId = _prefixed_ulid("mchunk_")
TraceId = _prefixed_ulid("trace_")
SpanId = _prefixed_ulid("span_")


class ContractModel(BaseModel):
    """Base policy shared by every executable contract."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


class IncidentMode(StrEnum):
    DIAGNOSIS_ONLY = "diagnosis_only"
    ALLOW_ACTIONS = "allow_actions"


class RiskLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class IncidentStateName(StrEnum):
    NEW = "NEW"
    QUEUED = "QUEUED"
    INVESTIGATING = "INVESTIGATING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    ROLLING_BACK = "ROLLING_BACK"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class RunStateName(StrEnum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RETRY_WAIT = "RETRY_WAIT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


class AgentGraphStateName(StrEnum):
    INTAKE = "INTAKE"
    SCOPE_AND_RISK = "SCOPE_AND_RISK"
    BUILD_INITIAL_PLAN = "BUILD_INITIAL_PLAN"
    RETRIEVE_CONTEXT = "RETRIEVE_CONTEXT"
    COLLECT_EVIDENCE = "COLLECT_EVIDENCE"
    NORMALIZE_EVIDENCE = "NORMALIZE_EVIDENCE"
    GENERATE_HYPOTHESES = "GENERATE_HYPOTHESES"
    VERIFY_HYPOTHESES = "VERIFY_HYPOTHESES"
    PLAN_PROBES = "PLAN_PROBES"
    COMPOSE_REPORT = "COMPOSE_REPORT"
    PROPOSE_ACTION = "PROPOSE_ACTION"
    POLICY_CHECK = "POLICY_CHECK"
    AWAIT_APPROVAL = "AWAIT_APPROVAL"
    DISPATCH_ACTION = "DISPATCH_ACTION"
    AWAIT_ACTION_RESULT = "AWAIT_ACTION_RESULT"
    VERIFY_OUTCOME = "VERIFY_OUTCOME"
    REQUEST_COMPENSATION = "REQUEST_COMPENSATION"
    FINALIZE = "FINALIZE"
    ESCALATE = "ESCALATE"


class ActionStateName(StrEnum):
    PREPARED = "PREPARED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPENSATING = "COMPENSATING"
    UNCERTAIN = "UNCERTAIN"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ROLLED_BACK = "ROLLED_BACK"
    MANUAL = "MANUAL"
    CANCELLED = "CANCELLED"


class TimeRange(ContractModel):
    start: UtcDateTime
    end: UtcDateTime

    @model_validator(mode="after")
    def end_after_start(self) -> TimeRange:
        if self.end <= self.start:
            raise ValueError("time range end must be after start")
        return self


class AgentBudget(ContractModel):
    deadline: UtcDateTime
    max_steps: int = Field(ge=1)
    max_model_calls: int = Field(ge=0)
    max_tokens: int = Field(ge=0)
    max_cost_usd: float = Field(ge=0)


class BudgetCounters(ContractModel):
    steps: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)


class ProgressDigest(ContractModel):
    evidence_count: int = Field(ge=0)
    supported_claim_count: int = Field(ge=0)
    digest: Sha256


class SourceVersionRef(ContractModel):
    source_id: NonEmptyText
    source_version: NonEmptyText


class VersionBundle(ContractModel):
    contracts_version: SemVer
    architecture_version: SemVer
    candidate_sha: GitSha


class ResourceRef(ContractModel):
    resource_type: NonEmptyText
    resource_id: NonEmptyText
    resource_version: NonEmptyText


class ToolCall(ContractModel):
    call_id: ToolCallId
    tool_id: ToolId
    arguments: dict[str, Any]
    tenant_id: TenantId

    _safe_arguments = field_validator("arguments")(_reject_private_reasoning)


class TenantContext(ContractModel):
    tenant_id: TenantId
    user_id: UserId
    roles: frozenset[Role] = Field(min_length=1)
    token_id: TokenId
    expires_at: UtcDateTime


class IncidentSpec(ContractModel):
    environment_id: EnvironmentId
    service_scope: frozenset[ServiceId] = Field(min_length=1, max_length=50)
    time_window: TimeRange
    symptom_summary: BoundedText
    mode: IncidentMode
    budget: AgentBudget


class IncidentState(ContractModel):
    incident_id: IncidentId
    state: IncidentStateName
    state_version: int = Field(ge=0)
    final_report_ref: str | None = None


class RunTask(ContractModel):
    task_id: TaskId
    incident_id: IncidentId
    tenant_id: TenantId
    deadline: UtcDateTime


class RunState(ContractModel):
    state: RunStateName
    state_version: int = Field(ge=0)
    attempt_id: AttemptId
    terminal_reason: str | None = None

    @model_validator(mode="after")
    def terminal_failure_has_reason(self) -> RunState:
        terminal_failure = self.state in {RunStateName.FAILED, RunStateName.DEAD_LETTER}
        if terminal_failure and not self.terminal_reason:
            raise ValueError("failed terminal run state requires terminal_reason")
        return self


class Lease(ContractModel):
    attempt_id: AttemptId
    worker_id: WorkerId
    fencing_token: int = Field(ge=0)
    expires_at: UtcDateTime


class ChangeEvent(ContractModel):
    change_id: ChangeId
    resource_ref: ResourceRef
    observed_at: UtcDateTime
    evidence_refs: tuple[EvidenceRefId, ...]


class AgentState(ContractModel):
    graph_state: AgentGraphStateName
    state_version: int = Field(ge=0)
    budgets_used: BudgetCounters
    evidence_progress: ProgressDigest


class EvidenceRef(ContractModel):
    evidence_id: EvidenceRefId
    source_ref: SourceVersionRef
    observed_at: UtcDateTime
    artifact_digest: Sha256


class Hypothesis(ContractModel):
    hypothesis_id: HypothesisId
    statement: BoundedText
    supporting_evidence: tuple[EvidenceRefId, ...]
    contradicting_evidence: tuple[EvidenceRefId, ...]


class ProbePlan(ContractModel):
    probe_id: ProbeId
    hypothesis_id: HypothesisId
    tool_calls: tuple[ToolCall, ...] = Field(min_length=1)
    expected_information_gain: float = Field(ge=0, le=1)


class ToolDefinition(ContractModel):
    tool_id: ToolId
    input_schema_ref: NonEmptyText
    output_schema_ref: NonEmptyText
    risk: RiskLevel


class ToolResultStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolResult(ContractModel):
    call_id: ToolCallId
    status: ToolResultStatus
    result_ref: str | None = None
    error_code: Annotated[str, StringConstraints(pattern=r"^ERR-[A-Z0-9-]+$")] | None = None

    @model_validator(mode="after")
    def status_fields_are_consistent(self) -> ToolResult:
        if self.status is ToolResultStatus.SUCCESS and self.error_code is not None:
            raise ValueError("successful tool result cannot have error_code")
        if self.status is not ToolResultStatus.SUCCESS and self.error_code is None:
            raise ValueError("failed tool result requires error_code")
        return self


class SkillManifest(ContractModel):
    skill_id: SkillId
    triggers: tuple[NonEmptyText, ...]
    anti_triggers: tuple[NonEmptyText, ...]
    allowed_tools: frozenset[ToolId]


class ActionProposal(ContractModel):
    action_id: ActionId
    action_type: NonEmptyText
    canonical_parameters: dict[str, Any]
    resource_version: NonEmptyText
    action_digest: Sha256

    _safe_parameters = field_validator("canonical_parameters")(_reject_private_reasoning)


class ApprovalGrant(ContractModel):
    action_digest: Sha256
    approver_id: UserId
    approver_scope: NonEmptyText
    expires_at: UtcDateTime
    single_use_token: Annotated[
        str, StringConstraints(min_length=32, max_length=512)
    ] = Field(repr=False)


class ActionTransaction(ContractModel):
    action_id: ActionId
    state: ActionStateName
    state_version: int = Field(ge=0)
    idempotency_key: IdempotencyKey = Field(repr=False)
    receipt_ref: str | None = None


class TrajectorySplit(StrEnum):
    TRAIN = "train"
    DEV = "dev"
    VALIDATION = "validation"
    LOCKED = "locked"
    EXTERNAL = "external"


class TrajectoryIR(ContractModel):
    trajectory_id: TrajectoryId
    event_refs: tuple[EventId, ...]
    version_bundle: VersionBundle
    split: TrajectorySplit


class EvalResult(ContractModel):
    eval_id: EvalId
    candidate_sha: GitSha
    metrics: dict[str, float]
    artifact_digest: Sha256


class DomainEvent(ContractModel):
    event_id: EventId
    event_type: Annotated[str, StringConstraints(pattern=r"^EVT-[A-Z0-9-]+$")]
    schema_version: SemVer
    tenant_id: TenantId
    correlation_id: CorrelationId
    causation_id: EventId | None = None
    sequence: int = Field(ge=0)
    payload: dict[str, Any]

    _safe_payload = field_validator("payload")(_reject_private_reasoning)


class CommandEnvelope(ContractModel):
    command_id: CommandId
    command_type: Annotated[str, StringConstraints(pattern=r"^CMD-[A-Z0-9-]+$")]
    schema_version: SemVer
    occurred_at: UtcDateTime
    tenant_id: TenantId
    correlation_id: CorrelationId
    causation_id: EventId | None
    idempotency_key: IdempotencyKey = Field(repr=False)
    expected_state_version: int = Field(ge=0)
    payload: dict[str, Any]
    incident_id: IncidentId | None = None
    run_id: TaskId | None = None
    action_id: ActionId | None = None
    fencing_token: int | None = Field(default=None, ge=0)

    _safe_payload = field_validator("payload")(_reject_private_reasoning)


class OutboxState(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    PUBLISHED = "PUBLISHED"


class OutboxRecord(ContractModel):
    outbox_id: OutboxId
    tenant_id: TenantId
    owner: NonEmptyText
    aggregate_id: NonEmptyText
    event: DomainEvent
    state: OutboxState = OutboxState.PENDING
    attempt_count: int = Field(default=0, ge=0)
    available_at: UtcDateTime
    claimed_until: UtcDateTime | None = None
    published_at: UtcDateTime | None = None


class InboxState(StrEnum):
    RECEIVED = "RECEIVED"
    APPLIED = "APPLIED"
    DUPLICATE_ACK = "DUPLICATE_ACK"
    DEAD_LETTER = "DEAD_LETTER"


class InboxRecord(ContractModel):
    inbox_id: InboxId
    tenant_id: TenantId
    consumer: NonEmptyText
    event_id: EventId
    state: InboxState
    received_at: UtcDateTime
    applied_at: UtcDateTime | None = None
    failure_code: str | None = None


class CheckpointWrite(ContractModel):
    checkpoint_id: CheckpointId
    tenant_id: TenantId
    task_id: TaskId
    attempt_id: AttemptId
    state_version: int = Field(ge=0)
    fencing_token: int = Field(ge=0)
    graph_state: AgentGraphStateName
    checkpoint: dict[str, Any]
    created_at: UtcDateTime

    _safe_checkpoint = field_validator("checkpoint")(_reject_private_reasoning)


class IncidentFeedback(ContractModel):
    feedback_id: FeedbackId
    incident_id: IncidentId
    tenant_id: TenantId
    user_id: UserId
    rating: int = Field(ge=1, le=5)
    comment: Annotated[str, StringConstraints(max_length=4000)] | None = None
    expected_state_version: int = Field(ge=0)
    submitted_at: UtcDateTime


class StreamControlKind(StrEnum):
    REPLAY_STARTED = "replay_started"
    LIVE_STARTED = "live_started"
    RETENTION_GAP = "retention_gap"
    SLOW_CONSUMER = "slow_consumer"
    CLOSED = "closed"


class StreamControlEvent(ContractModel):
    event_id: EventId
    tenant_id: TenantId
    incident_id: IncidentId
    kind: StreamControlKind
    cursor: NonEmptyText
    occurred_at: UtcDateTime
    recoverable: bool
    details: dict[str, Any] = Field(default_factory=dict)

    _safe_details = field_validator("details")(_reject_private_reasoning)


class ModelFamily(StrEnum):
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    GLM = "glm"


class ModelMessage(ContractModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class ModelUsage(ContractModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def total_is_consistent(self) -> ModelUsage:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        return self


class ModelRequest(ContractModel):
    request_id: ModelRequestId
    tenant_id: TenantId
    correlation_id: CorrelationId
    model_family: ModelFamily
    model_id: NonEmptyText
    messages: tuple[ModelMessage, ...] = Field(min_length=1)
    target_json_schema: dict[str, Any] | None = None
    tool_schemas: tuple[dict[str, Any], ...] = ()
    stream: bool = False
    budget: AgentBudget

    @field_validator("target_json_schema", "tool_schemas")
    @classmethod
    def no_private_reasoning(cls, value: Any) -> Any:
        return _reject_private_reasoning(value)


class ModelResponse(ContractModel):
    response_id: ModelResponseId
    request_id: ModelRequestId
    tenant_id: TenantId
    correlation_id: CorrelationId
    model_family: ModelFamily
    model_id: NonEmptyText
    content: str
    structured_output: dict[str, Any] | None = None
    finish_reason: NonEmptyText
    usage: ModelUsage
    completed_at: UtcDateTime

    _safe_output = field_validator("structured_output")(_reject_private_reasoning)


class ModelChunk(ContractModel):
    chunk_id: ModelChunkId
    request_id: ModelRequestId
    tenant_id: TenantId
    correlation_id: CorrelationId
    sequence: int = Field(ge=0)
    delta: str
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    occurred_at: UtcDateTime


class TraceStage(StrEnum):
    API = "api"
    STATE_TRANSITION = "state_transition"
    CHECKPOINT = "checkpoint"
    MODEL = "model"
    TOOL = "tool"
    POLICY = "policy"
    ACTION = "action"
    EXPORT = "export"


class SpanStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class SpanRecord(ContractModel):
    span_id: SpanId
    parent_span_id: SpanId | None = None
    name: NonEmptyText
    stage: TraceStage
    started_at: UtcDateTime
    ended_at: UtcDateTime | None = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: dict[str, Any] = Field(default_factory=dict)

    _safe_attributes = field_validator("attributes")(_reject_private_reasoning)

    @model_validator(mode="after")
    def end_not_before_start(self) -> SpanRecord:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("span ended_at cannot precede started_at")
        return self


class TraceEnvelope(ContractModel):
    trace_id: TraceId
    tenant_id: TenantId
    correlation_id: CorrelationId
    causation_id: EventId | None = None
    incident_id: IncidentId | None = None
    task_id: TaskId | None = None
    action_id: ActionId | None = None
    contracts_version: SemVer = CONTRACTS_VERSION
    candidate_sha: GitSha
    spans: tuple[SpanRecord, ...] = Field(min_length=1)
    emitted_at: UtcDateTime


CORE_MODEL_TYPES = (
    TenantContext,
    IncidentSpec,
    IncidentState,
    RunTask,
    RunState,
    Lease,
    ChangeEvent,
    AgentState,
    EvidenceRef,
    Hypothesis,
    ProbePlan,
    ToolDefinition,
    ToolCall,
    ToolResult,
    SkillManifest,
    ActionProposal,
    ApprovalGrant,
    ActionTransaction,
    TrajectoryIR,
    EvalResult,
    DomainEvent,
)

SUPPORT_MODEL_TYPES = (
    CommandEnvelope,
    OutboxRecord,
    InboxRecord,
    CheckpointWrite,
    IncidentFeedback,
    StreamControlEvent,
    ModelRequest,
    ModelResponse,
    ModelChunk,
    ModelUsage,
    TraceEnvelope,
    SpanRecord,
)

__all__ = [model.__name__ for model in CORE_MODEL_TYPES + SUPPORT_MODEL_TYPES]
