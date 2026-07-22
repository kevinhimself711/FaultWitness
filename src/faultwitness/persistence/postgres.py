"""PostgreSQL transactions for state, idempotency, outbox, inbox, and checkpoints."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from faultwitness.state.kernel import TransitionDecision


class VersionConflict(RuntimeError):
    pass


class DuplicateCommand(RuntimeError):
    pass


class StaleFence(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AppliedTransition:
    decision: TransitionDecision
    event_id: str
    outbox_id: str
    duplicate: bool = False


class PostgresStateStore:
    """Owner-scoped repository; callers provide a pool-issued connection."""

    def __init__(self, connection: Any, owner_schema: str) -> None:
        if owner_schema not in {"incident_owner", "task_owner", "graph_owner", "action_owner"}:
            raise ValueError("unknown owner schema")
        self.connection = connection
        self.schema = owner_schema

    def apply_transition(
        self,
        decision: TransitionDecision,
        *,
        tenant_id: str,
        event_id: str,
        outbox_id: str,
    ) -> AppliedTransition:
        """Atomically persist state, idempotent result and one pending outbox event."""
        key = decision.idempotency_key
        if key is None:
            raise ValueError("durable commands require an idempotency key")
        with self.connection.transaction(), self.connection.cursor() as cur:
            cur.execute(
                f"SELECT request_digest, response FROM {self.schema}.idempotency "
                "WHERE tenant_id=%s AND idempotency_key=%s FOR UPDATE",
                (tenant_id, key),
            )
            prior = cur.fetchone()
            if prior:
                request_digest, response = prior
                if request_digest != decision.request_digest:
                    raise DuplicateCommand("idempotency key reused with a different request")
                return AppliedTransition(
                    decision, response["event_id"], response["outbox_id"], True
                )

            cur.execute(
                f"""INSERT INTO {self.schema}.aggregate_state
                    (tenant_id, aggregate_id, machine_id, state, state_version, updated_at)
                    VALUES (%s,%s,%s,%s,%s,now())
                    ON CONFLICT (tenant_id, aggregate_id) DO UPDATE SET
                      state=EXCLUDED.state, state_version=EXCLUDED.state_version, updated_at=now()
                    WHERE {self.schema}.aggregate_state.state_version=%s""",
                (
                    tenant_id,
                    decision.aggregate_id,
                    decision.machine_id,
                    decision.next_state,
                    decision.next_state_version,
                    decision.previous_state_version,
                ),
            )
            if cur.rowcount != 1:
                raise VersionConflict("optimistic state version rejected")
            payload = json.dumps(asdict(decision), sort_keys=True, separators=(",", ":"))
            cur.execute(
                f"""INSERT INTO {self.schema}.outbox
                    (outbox_id, tenant_id, aggregate_id, event_id, event_type, payload)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                (outbox_id, tenant_id, decision.aggregate_id, event_id, decision.event, payload),
            )
            response = {"event_id": event_id, "outbox_id": outbox_id}
            cur.execute(
                f"""INSERT INTO {self.schema}.idempotency
                    (tenant_id,idempotency_key,request_digest,response)
                    VALUES (%s,%s,%s,%s::jsonb)""",
                (tenant_id, key, decision.request_digest, json.dumps(response)),
            )
        return AppliedTransition(decision, event_id, outbox_id)

    def record_inbox(self, *, tenant_id: str, consumer: str, event_id: str) -> bool:
        """Return true only for the first delivery; duplicate deliveries are acknowledged."""
        with self.connection.transaction(), self.connection.cursor() as cur:
            cur.execute(
                """INSERT INTO runtime_shared.inbox(tenant_id,consumer,event_id,state)
                   VALUES (%s,%s,%s,'RECEIVED') ON CONFLICT DO NOTHING""",
                (tenant_id, consumer, event_id),
            )
            return cur.rowcount == 1

    def write_checkpoint(
        self,
        *,
        tenant_id: str,
        task_id: str,
        attempt_id: str,
        fencing_token: int,
        state_version: int,
        ciphertext: bytes,
        key_id: str,
        event_id: str,
        outbox_id: str,
    ) -> None:
        """Fence validation, checkpoint, and graph event share one transaction."""
        with self.connection.transaction(), self.connection.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM task_owner.lease WHERE tenant_id=%s AND task_id=%s
                   AND attempt_id=%s AND fencing_token=%s AND expires_at>now() FOR UPDATE""",
                (tenant_id, task_id, attempt_id, fencing_token),
            )
            if cur.fetchone() is None:
                raise StaleFence("checkpoint rejected for stale or expired lease")
            cur.execute(
                """INSERT INTO graph_owner.checkpoint
                   (tenant_id,task_id,attempt_id,fencing_token,state_version,ciphertext,key_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (tenant_id,task_id) DO UPDATE SET
                     attempt_id=EXCLUDED.attempt_id,fencing_token=EXCLUDED.fencing_token,
                     state_version=EXCLUDED.state_version,ciphertext=EXCLUDED.ciphertext,
                     key_id=EXCLUDED.key_id,created_at=now()
                   WHERE graph_owner.checkpoint.state_version < EXCLUDED.state_version""",
                (tenant_id, task_id, attempt_id, fencing_token, state_version, ciphertext, key_id),
            )
            if cur.rowcount != 1:
                raise VersionConflict("checkpoint version did not advance")
            payload = json.dumps({"task_id": task_id, "state_version": state_version})
            cur.execute(
                """INSERT INTO graph_owner.outbox
                   (outbox_id,tenant_id,aggregate_id,event_id,event_type,payload)
                   VALUES (%s,%s,%s,%s,'EVT-GRAPH-CHECKPOINTED',%s::jsonb)""",
                (outbox_id, tenant_id, task_id, event_id, payload),
            )

    def mark_dead_letter(
        self, *, tenant_id: str, consumer: str, event_id: str, reason: str, payload: bytes
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cur:
            cur.execute(
                """INSERT INTO runtime_shared.dead_letter
                   (tenant_id,consumer,event_id,reason,payload) VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (tenant_id,consumer,event_id) DO NOTHING""",
                (tenant_id, consumer, event_id, reason, payload),
            )


def utcnow() -> datetime:
    return datetime.now(UTC)
