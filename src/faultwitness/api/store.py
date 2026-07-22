from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from faultwitness.api.schemas import (
    ApprovalRequest,
    ApprovalResult,
    FeedbackRequest,
    FeedbackResult,
    IncidentCreate,
    IncidentSnapshot,
)


class IncidentNotFound(RuntimeError):
    pass


class StateConflict(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


class ApprovalConflict(RuntimeError):
    pass


class CursorError(RuntimeError):
    pass


class RetentionGap(CursorError):
    def __init__(self, earliest_cursor: str) -> None:
        self.earliest_cursor = earliest_cursor
        super().__init__("cursor precedes retained projection")


@dataclass(frozen=True, slots=True)
class IncidentEvent:
    event_id: str
    event_type: str
    incident_id: str
    sequence: int
    occurred_at: datetime
    payload: dict[str, Any]


@dataclass(slots=True, eq=False)
class Subscriber:
    queue: asyncio.Queue[IncidentEvent]
    closed: bool = False


@dataclass(slots=True)
class _Incident:
    tenant_id: str
    snapshot: IncidentSnapshot
    spec: IncidentCreate
    pending_action: tuple[str, str] | None = None


class MemoryIncidentStore:
    """Contract reference store used by tests; production adapters preserve the same semantics."""

    def __init__(self, retention_count: int = 100_000, retention_days: int = 7) -> None:
        self.retention_count = retention_count
        self.retention_age = timedelta(days=retention_days)
        self._incidents: dict[str, _Incident] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, Any]] = {}
        self._events: dict[tuple[str, str], list[IncidentEvent]] = {}
        self._subscribers: dict[tuple[str, str], set[Subscriber]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def request_digest(value: Any) -> str:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(body.encode()).hexdigest()

    async def create(
        self, tenant_id: str, idempotency_key: str, request: IncidentCreate
    ) -> tuple[IncidentSnapshot, bool]:
        digest = self.request_digest(request)
        slot = (tenant_id, "create", idempotency_key)
        async with self._lock:
            if prior := self._idempotency.get(slot):
                if prior[0] != digest:
                    raise IdempotencyConflict("idempotency key has a different request digest")
                return prior[1], False
            incident_id = "inc_" + uuid.uuid4().hex
            snapshot = IncidentSnapshot(
                incident_id=incident_id,
                state="NEW",
                state_version=0,
                event_cursor="0",
                final_report_ref=None,
            )
            self._incidents[incident_id] = _Incident(tenant_id, snapshot, request)
            event = self._append_locked(
                tenant_id, incident_id, "EVT-INCIDENT-CREATED", {"state": "NEW"}
            )
            snapshot = snapshot.model_copy(update={"event_cursor": str(event.sequence)})
            self._incidents[incident_id].snapshot = snapshot
            self._idempotency[slot] = (digest, snapshot)
            return snapshot, True

    async def get(self, tenant_id: str, incident_id: str) -> IncidentSnapshot:
        async with self._lock:
            return self._owned(tenant_id, incident_id).snapshot

    async def cancel(
        self, tenant_id: str, incident_id: str, idempotency_key: str, expected_version: int
    ) -> IncidentSnapshot:
        digest = self.request_digest({"incident_id": incident_id, "version": expected_version})
        slot = (tenant_id, "cancel", idempotency_key)
        async with self._lock:
            if prior := self._idempotency.get(slot):
                if prior[0] != digest:
                    raise IdempotencyConflict("idempotency key has a different request digest")
                return prior[1]
            incident = self._owned(tenant_id, incident_id)
            if incident.snapshot.state_version != expected_version:
                raise StateConflict("expected state version is stale")
            if incident.snapshot.state in {"RESOLVED", "ESCALATED", "CANCELLED"}:
                raise StateConflict("terminal incident cannot be cancelled")
            event = self._append_locked(tenant_id, incident_id, "EVT-INCIDENT-CANCEL-REQUESTED", {})
            snapshot = incident.snapshot.model_copy(
                update={
                    "state": "CANCELLED",
                    "state_version": expected_version + 1,
                    "event_cursor": str(event.sequence),
                }
            )
            incident.snapshot = snapshot
            self._idempotency[slot] = (digest, snapshot)
            return snapshot

    async def feedback(
        self,
        tenant_id: str,
        user_id: str,
        incident_id: str,
        idempotency_key: str,
        request: FeedbackRequest,
    ) -> FeedbackResult:
        digest = self.request_digest(request)
        slot = (tenant_id, "feedback", idempotency_key)
        async with self._lock:
            if prior := self._idempotency.get(slot):
                if prior[0] != digest:
                    raise IdempotencyConflict("idempotency key has a different request digest")
                return prior[1]
            incident = self._owned(tenant_id, incident_id)
            if incident.snapshot.state_version != request.expected_state_version:
                raise StateConflict("expected state version is stale")
            result = FeedbackResult(
                feedback_id="feedback_" + uuid.uuid4().hex,
                accepted_at=datetime.now(UTC),
            )
            self._append_locked(
                tenant_id,
                incident_id,
                "EVT-INCIDENT-FEEDBACK-RECORDED",
                {"feedback_id": result.feedback_id, "rating": request.rating, "user": user_id},
            )
            self._idempotency[slot] = (digest, result)
            return result

    async def approval(
        self,
        tenant_id: str,
        incident_id: str,
        idempotency_key: str,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        digest = self.request_digest(request)
        slot = (tenant_id, "approval", idempotency_key)
        async with self._lock:
            if prior := self._idempotency.get(slot):
                if prior[0] != digest:
                    raise IdempotencyConflict("idempotency key has a different request digest")
                return prior[1]
            incident = self._owned(tenant_id, incident_id)
            if incident.snapshot.state_version != request.expected_state_version:
                raise StateConflict("expected state version is stale")
            if incident.pending_action != (request.action_id, request.action_digest):
                raise ApprovalConflict("no matching pending action digest")
            result = ApprovalResult(
                action_id=request.action_id,
                decision=request.decision,
                action_digest=request.action_digest,
                state_version=request.expected_state_version,
            )
            self._append_locked(
                tenant_id,
                incident_id,
                "EVT-ACTION-APPROVAL-DECIDED",
                {"action_id": request.action_id, "decision": request.decision.value},
            )
            incident.pending_action = None
            self._idempotency[slot] = (digest, result)
            return result

    async def replay(
        self, tenant_id: str, incident_id: str, last_event_id: str | None
    ) -> list[IncidentEvent]:
        async with self._lock:
            self._owned(tenant_id, incident_id)
            events = list(self._events.get((tenant_id, incident_id), []))
            if last_event_id is None:
                return events
            try:
                cursor = int(last_event_id)
            except ValueError as error:
                raise CursorError("cursor must be an integer sequence") from error
            if cursor < 0 or (events and cursor > events[-1].sequence):
                raise CursorError("cursor is outside the projection")
            if events and cursor < events[0].sequence - 1:
                raise RetentionGap(str(events[0].sequence))
            return [event for event in events if event.sequence > cursor]

    async def subscribe(
        self, tenant_id: str, incident_id: str, buffer_size: int = 100
    ) -> Subscriber:
        async with self._lock:
            self._owned(tenant_id, incident_id)
            subscriber = Subscriber(asyncio.Queue(maxsize=buffer_size))
            self._subscribers.setdefault((tenant_id, incident_id), set()).add(subscriber)
            return subscriber

    async def unsubscribe(self, tenant_id: str, incident_id: str, subscriber: Subscriber) -> None:
        async with self._lock:
            self._subscribers.get((tenant_id, incident_id), set()).discard(subscriber)

    def _owned(self, tenant_id: str, incident_id: str) -> _Incident:
        incident = self._incidents.get(incident_id)
        if incident is None or incident.tenant_id != tenant_id:
            raise IncidentNotFound("tenant-scoped incident not found")
        return incident

    def _append_locked(
        self, tenant_id: str, incident_id: str, event_type: str, payload: dict[str, Any]
    ) -> IncidentEvent:
        key = (tenant_id, incident_id)
        events = self._events.setdefault(key, [])
        sequence = events[-1].sequence + 1 if events else 1
        event = IncidentEvent(
            event_id=f"evt_{incident_id[4:]}_{sequence}",
            event_type=event_type,
            incident_id=incident_id,
            sequence=sequence,
            occurred_at=datetime.now(UTC),
            payload=payload,
        )
        events.append(event)
        cutoff = datetime.now(UTC) - self.retention_age
        while len(events) > self.retention_count or events[0].occurred_at < cutoff:
            events.pop(0)
        for subscriber in tuple(self._subscribers.get(key, set())):
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                subscriber.closed = True
        return event
