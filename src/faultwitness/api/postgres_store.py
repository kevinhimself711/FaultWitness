from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from faultwitness.api.schemas import (
    ApprovalRequest,
    ApprovalResult,
    FeedbackRequest,
    FeedbackResult,
    IncidentCreate,
    IncidentSnapshot,
)
from faultwitness.api.store import (
    ApprovalConflict,
    CursorError,
    IdempotencyConflict,
    IncidentEvent,
    IncidentNotFound,
    MemoryIncidentStore,
    RetentionGap,
    StateConflict,
    Subscriber,
)


class PostgresIncidentStore:
    """Durable single-writer Incident store with tenant-qualified access on every query."""

    def __init__(self, dsn: str, *, retention_count: int = 100_000) -> None:
        self.dsn = dsn
        self.retention_count = retention_count
        self.pool: asyncpg.Pool | None = None
        self._subscribers: dict[tuple[str, str], set[Subscriber]] = {}
        self._subscriber_lock = asyncio.Lock()

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10, command_timeout=5)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("PostgreSQL store is not connected")
        return self.pool

    async def create(
        self, tenant_id: str, idempotency_key: str, request: IncidentCreate
    ) -> tuple[IncidentSnapshot, bool]:
        digest = MemoryIncidentStore.request_digest(request)
        async with self._pool().acquire() as connection, connection.transaction():
            prior = await connection.fetchrow(
                """SELECT request_digest,response,http_status
                   FROM incident_owner.api_idempotency
                   WHERE tenant_id=$1 AND operation='create' AND idempotency_key=$2
                   FOR UPDATE""",
                tenant_id,
                idempotency_key,
            )
            if prior:
                if prior["request_digest"] != digest:
                    raise IdempotencyConflict("idempotency key has a different request digest")
                return IncidentSnapshot.model_validate(json.loads(prior["response"])), False
            incident_id = "inc_" + uuid.uuid4().hex
            await connection.execute(
                """INSERT INTO incident_owner.incident
                   (tenant_id,incident_id,state,state_version,event_cursor,spec)
                   VALUES ($1,$2,'NEW',0,1,$3::jsonb)""",
                tenant_id,
                incident_id,
                request.model_dump_json(),
            )
            event = self._event(incident_id, 1, "EVT-INCIDENT-CREATED", {"state": "NEW"})
            await self._insert_event(connection, tenant_id, event)
            snapshot = IncidentSnapshot(
                incident_id=incident_id,
                state="NEW",
                state_version=0,
                event_cursor="1",
                final_report_ref=None,
            )
            await self._save_idempotency(
                connection, tenant_id, "create", idempotency_key, digest, snapshot, 201
            )
        await self._publish(tenant_id, event)
        return snapshot, True

    async def get(self, tenant_id: str, incident_id: str) -> IncidentSnapshot:
        async with self._pool().acquire() as connection:
            row = await connection.fetchrow(
                """SELECT incident_id,state,state_version,event_cursor,final_report_ref
                   FROM incident_owner.incident WHERE tenant_id=$1 AND incident_id=$2""",
                tenant_id,
                incident_id,
            )
        if row is None:
            raise IncidentNotFound("tenant-scoped incident not found")
        return self._snapshot(row)

    async def cancel(
        self, tenant_id: str, incident_id: str, idempotency_key: str, expected_version: int
    ) -> IncidentSnapshot:
        digest = MemoryIncidentStore.request_digest(
            {"incident_id": incident_id, "version": expected_version}
        )
        async with self._pool().acquire() as connection, connection.transaction():
            prior = await self._idempotent(
                connection, tenant_id, "cancel", idempotency_key, digest, IncidentSnapshot
            )
            if prior is not None:
                return prior
            row = await self._lock_incident(connection, tenant_id, incident_id)
            if row["state_version"] != expected_version or row["state"] in {
                "RESOLVED",
                "ESCALATED",
                "CANCELLED",
            }:
                raise StateConflict("expected state version is stale or terminal")
            sequence = row["event_cursor"] + 1
            event = self._event(incident_id, sequence, "EVT-INCIDENT-CANCEL-REQUESTED", {})
            await connection.execute(
                """UPDATE incident_owner.incident SET state='CANCELLED',state_version=$3,
                   event_cursor=$4,updated_at=now() WHERE tenant_id=$1 AND incident_id=$2""",
                tenant_id,
                incident_id,
                expected_version + 1,
                sequence,
            )
            await self._insert_event(connection, tenant_id, event)
            snapshot = IncidentSnapshot(
                incident_id=incident_id,
                state="CANCELLED",
                state_version=expected_version + 1,
                event_cursor=str(sequence),
                final_report_ref=row["final_report_ref"],
            )
            await self._save_idempotency(
                connection, tenant_id, "cancel", idempotency_key, digest, snapshot, 202
            )
        await self._publish(tenant_id, event)
        return snapshot

    async def feedback(
        self,
        tenant_id: str,
        user_id: str,
        incident_id: str,
        idempotency_key: str,
        request: FeedbackRequest,
    ) -> FeedbackResult:
        digest = MemoryIncidentStore.request_digest(request)
        async with self._pool().acquire() as connection, connection.transaction():
            prior = await self._idempotent(
                connection, tenant_id, "feedback", idempotency_key, digest, FeedbackResult
            )
            if prior is not None:
                return prior
            row = await self._lock_incident(connection, tenant_id, incident_id)
            if row["state_version"] != request.expected_state_version:
                raise StateConflict("expected state version is stale")
            sequence = row["event_cursor"] + 1
            result = FeedbackResult(
                feedback_id="feedback_" + uuid.uuid4().hex, accepted_at=datetime.now(UTC)
            )
            await connection.execute(
                """INSERT INTO incident_owner.feedback
                   (feedback_id,tenant_id,incident_id,user_id,rating,comment,accepted_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                result.feedback_id,
                tenant_id,
                incident_id,
                user_id,
                request.rating,
                request.comment,
                result.accepted_at,
            )
            event = self._event(
                incident_id,
                sequence,
                "EVT-INCIDENT-FEEDBACK-RECORDED",
                {"feedback_id": result.feedback_id, "rating": request.rating},
            )
            await self._insert_event(connection, tenant_id, event)
            await connection.execute(
                """UPDATE incident_owner.incident SET event_cursor=$3,updated_at=now()
                   WHERE tenant_id=$1 AND incident_id=$2""",
                tenant_id,
                incident_id,
                sequence,
            )
            await self._save_idempotency(
                connection, tenant_id, "feedback", idempotency_key, digest, result, 202
            )
        await self._publish(tenant_id, event)
        return result

    async def approval(
        self,
        tenant_id: str,
        incident_id: str,
        idempotency_key: str,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        digest = MemoryIncidentStore.request_digest(request)
        async with self._pool().acquire() as connection, connection.transaction():
            prior = await self._idempotent(
                connection, tenant_id, "approval", idempotency_key, digest, ApprovalResult
            )
            if prior is not None:
                return prior
            row = await self._lock_incident(connection, tenant_id, incident_id)
            if row["state_version"] != request.expected_state_version:
                raise StateConflict("expected state version is stale")
            pending = await connection.fetchrow(
                """SELECT action_digest FROM incident_owner.pending_approval
                   WHERE tenant_id=$1 AND incident_id=$2 AND action_id=$3 FOR UPDATE""",
                tenant_id,
                incident_id,
                request.action_id,
            )
            if pending is None or pending["action_digest"] != request.action_digest:
                raise ApprovalConflict("no matching pending action digest")
            sequence = row["event_cursor"] + 1
            result = ApprovalResult(
                action_id=request.action_id,
                decision=request.decision,
                action_digest=request.action_digest,
                state_version=request.expected_state_version,
            )
            event = self._event(
                incident_id,
                sequence,
                "EVT-ACTION-APPROVAL-DECIDED",
                {"action_id": request.action_id, "decision": request.decision.value},
            )
            await self._insert_event(connection, tenant_id, event)
            await connection.execute(
                """DELETE FROM incident_owner.pending_approval
                   WHERE tenant_id=$1 AND incident_id=$2 AND action_id=$3""",
                tenant_id,
                incident_id,
                request.action_id,
            )
            await connection.execute(
                """UPDATE incident_owner.incident SET event_cursor=$3,updated_at=now()
                   WHERE tenant_id=$1 AND incident_id=$2""",
                tenant_id,
                incident_id,
                sequence,
            )
            await self._save_idempotency(
                connection, tenant_id, "approval", idempotency_key, digest, result, 200
            )
        await self._publish(tenant_id, event)
        return result

    async def replay(
        self, tenant_id: str, incident_id: str, last_event_id: str | None
    ) -> list[IncidentEvent]:
        try:
            cursor = int(last_event_id or 0)
        except ValueError as error:
            raise CursorError("cursor must be an integer sequence") from error
        if cursor < 0:
            raise CursorError("cursor is outside the projection")
        async with self._pool().acquire() as connection:
            row = await connection.fetchrow(
                """SELECT event_cursor FROM incident_owner.incident
                   WHERE tenant_id=$1 AND incident_id=$2""",
                tenant_id,
                incident_id,
            )
            if row is None:
                raise IncidentNotFound("tenant-scoped incident not found")
            if cursor > row["event_cursor"]:
                raise CursorError("cursor is outside the projection")
            earliest = await connection.fetchval(
                """SELECT min(sequence) FROM incident_owner.event_projection
                   WHERE tenant_id=$1 AND incident_id=$2""",
                tenant_id,
                incident_id,
            )
            if earliest is not None and cursor < earliest - 1:
                raise RetentionGap(str(earliest))
            rows = await connection.fetch(
                """SELECT event_id,event_type,incident_id,sequence,occurred_at,payload
                   FROM incident_owner.event_projection
                   WHERE tenant_id=$1 AND incident_id=$2 AND sequence>$3 ORDER BY sequence""",
                tenant_id,
                incident_id,
                cursor,
            )
        return [self._event_from_row(item) for item in rows]

    async def subscribe(
        self, tenant_id: str, incident_id: str, buffer_size: int = 100
    ) -> Subscriber:
        await self.get(tenant_id, incident_id)
        subscriber = Subscriber(asyncio.Queue(maxsize=buffer_size))
        async with self._subscriber_lock:
            self._subscribers.setdefault((tenant_id, incident_id), set()).add(subscriber)
        return subscriber

    async def unsubscribe(self, tenant_id: str, incident_id: str, subscriber: Subscriber) -> None:
        async with self._subscriber_lock:
            self._subscribers.get((tenant_id, incident_id), set()).discard(subscriber)

    async def _lock_incident(
        self, connection: asyncpg.Connection, tenant_id: str, incident_id: str
    ) -> asyncpg.Record:
        row = await connection.fetchrow(
            """SELECT state,state_version,event_cursor,final_report_ref
               FROM incident_owner.incident WHERE tenant_id=$1 AND incident_id=$2 FOR UPDATE""",
            tenant_id,
            incident_id,
        )
        if row is None:
            raise IncidentNotFound("tenant-scoped incident not found")
        return row

    async def _idempotent(
        self,
        connection: asyncpg.Connection,
        tenant_id: str,
        operation: str,
        key: str,
        digest: str,
        model: Any,
    ) -> Any | None:
        row = await connection.fetchrow(
            """SELECT request_digest,response FROM incident_owner.api_idempotency
               WHERE tenant_id=$1 AND operation=$2 AND idempotency_key=$3 FOR UPDATE""",
            tenant_id,
            operation,
            key,
        )
        if row is None:
            return None
        if row["request_digest"] != digest:
            raise IdempotencyConflict("idempotency key has a different request digest")
        return model.model_validate(json.loads(row["response"]))

    @staticmethod
    async def _save_idempotency(
        connection: asyncpg.Connection,
        tenant_id: str,
        operation: str,
        key: str,
        digest: str,
        response: Any,
        status: int,
    ) -> None:
        await connection.execute(
            """INSERT INTO incident_owner.api_idempotency
               (tenant_id,operation,idempotency_key,request_digest,response,http_status)
               VALUES ($1,$2,$3,$4,$5::jsonb,$6)""",
            tenant_id,
            operation,
            key,
            digest,
            response.model_dump_json(),
            status,
        )

    @staticmethod
    async def _insert_event(
        connection: asyncpg.Connection, tenant_id: str, event: IncidentEvent
    ) -> None:
        await connection.execute(
            """INSERT INTO incident_owner.event_projection
               (tenant_id,incident_id,sequence,event_id,event_type,occurred_at,payload)
               VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)""",
            tenant_id,
            event.incident_id,
            event.sequence,
            event.event_id,
            event.event_type,
            event.occurred_at,
            json.dumps(event.payload),
        )

    async def _publish(self, tenant_id: str, event: IncidentEvent) -> None:
        async with self._subscriber_lock:
            subscribers = tuple(self._subscribers.get((tenant_id, event.incident_id), set()))
        for subscriber in subscribers:
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                subscriber.closed = True

    @staticmethod
    def _event(
        incident_id: str, sequence: int, event_type: str, payload: dict[str, Any]
    ) -> IncidentEvent:
        return IncidentEvent(
            event_id=f"evt_{incident_id[4:]}_{sequence}",
            event_type=event_type,
            incident_id=incident_id,
            sequence=sequence,
            occurred_at=datetime.now(UTC),
            payload=payload,
        )

    @staticmethod
    def _event_from_row(row: asyncpg.Record) -> IncidentEvent:
        return IncidentEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            incident_id=row["incident_id"],
            sequence=row["sequence"],
            occurred_at=row["occurred_at"],
            payload=json.loads(row["payload"]),
        )

    @staticmethod
    def _snapshot(row: asyncpg.Record) -> IncidentSnapshot:
        return IncidentSnapshot(
            incident_id=row["incident_id"],
            state=row["state"],
            state_version=row["state_version"],
            event_cursor=str(row["event_cursor"]),
            final_report_ref=row["final_report_ref"],
        )
