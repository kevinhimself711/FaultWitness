from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeWindow(APIModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def valid_window(self) -> TimeWindow:
        if self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start:
            raise ValueError("time window must be timezone-aware and increasing")
        return self


class AgentBudget(APIModel):
    deadline: datetime
    max_steps: int = Field(ge=1)
    max_model_calls: int = Field(ge=0)
    max_tokens: int = Field(ge=0)
    max_cost_usd: float = Field(ge=0)


class IncidentCreate(APIModel):
    source: str = Field(min_length=1, max_length=100)
    environment_id: str = Field(min_length=1, max_length=128)
    service_scope: list[str] = Field(min_length=1, max_length=50)
    time_window: TimeWindow
    symptom_summary: str = Field(min_length=1, max_length=4000)
    alert_refs: tuple[str, ...] = Field(default=(), max_length=100)
    change_events: tuple[dict[str, object], ...] = Field(default=(), max_length=100)
    mode: str = Field(pattern=r"^(diagnosis_only|allow_actions)$")
    budget: AgentBudget

    @model_validator(mode="after")
    def unique_service_scope(self) -> IncidentCreate:
        if len(self.service_scope) != len(set(self.service_scope)):
            raise ValueError("service_scope items must be unique")
        return self


class IncidentSnapshot(APIModel):
    incident_id: str
    state: str
    state_version: int = Field(ge=0)
    event_cursor: str
    final_report_ref: str | None = None


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalRequest(APIModel):
    action_id: str = Field(min_length=1)
    action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: ApprovalDecision
    expected_state_version: int = Field(ge=0)
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalResult(APIModel):
    action_id: str
    decision: ApprovalDecision
    action_digest: str
    state_version: int


class CancelRequest(APIModel):
    expected_state_version: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=2000)


class FeedbackRequest(APIModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=4000)
    expected_state_version: int = Field(ge=0)


class FeedbackResult(APIModel):
    feedback_id: str
    accepted_at: datetime


class ErrorEnvelope(APIModel):
    code: str
    message: str
    retryable: bool
    correlation_id: str
    details: dict[str, object]
