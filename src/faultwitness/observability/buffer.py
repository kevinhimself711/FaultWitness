"""Encrypted bounded trace buffer with per-sink leases and deterministic replay."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import asyncpg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from faultwitness.observability.sanitizer import SanitizedTrace


class BufferFull(RuntimeError):
    pass


class PayloadConflict(RuntimeError):
    pass


class DeliverySink(StrEnum):
    LANGSMITH = "langsmith"
    OTLP = "otlp"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    key_id: str
    nonce: bytes
    ciphertext: bytes
    payload_digest: str
    format_version: int = 1


@dataclass(frozen=True, slots=True)
class Delivery:
    trace: SanitizedTrace
    sink: DeliverySink
    attempt_count: int


class PayloadCipher:
    def __init__(self, key_id: str, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("trace payload key must contain exactly 32 bytes")
        if not key_id or len(key_id) > 64:
            raise ValueError("trace payload key id is invalid")
        self.key_id = key_id
        self._cipher = AESGCM(key)

    def seal(self, trace: SanitizedTrace) -> EncryptedPayload:
        body = trace.canonical_bytes()
        digest = hashlib.sha256(trace.content_bytes()).hexdigest()
        if digest != trace.payload_digest:
            raise ValueError("sanitized trace digest drifted")
        nonce = os.urandom(12)
        aad = f"faultwitness-trace:v1:{trace.trace_ref}:{digest}".encode()
        return EncryptedPayload(self.key_id, nonce, self._cipher.encrypt(nonce, body, aad), digest)

    def open(self, trace_ref: str, payload: EncryptedPayload) -> SanitizedTrace:
        if payload.format_version != 1 or payload.key_id != self.key_id:
            raise ValueError("unknown encrypted trace format or key")
        aad = f"faultwitness-trace:v1:{trace_ref}:{payload.payload_digest}".encode()
        body = self._cipher.decrypt(payload.nonce, payload.ciphertext, aad)
        document = json.loads(body)
        trace = SanitizedTrace.from_document(document)
        if (
            trace.trace_ref != trace_ref
            or trace.payload_digest != payload.payload_digest
            or hashlib.sha256(trace.content_bytes()).hexdigest() != payload.payload_digest
        ):
            raise ValueError("encrypted trace identity mismatch")
        return trace


@dataclass(slots=True)
class _MemoryDelivery:
    state: str = "PENDING"
    attempt_count: int = 0
    lease_until: datetime | None = None
    last_error_code: str | None = None


@dataclass(slots=True)
class _MemoryRecord:
    payload: EncryptedPayload
    deliveries: dict[DeliverySink, _MemoryDelivery]


class InMemoryTraceBuffer:
    """Concurrency-safe semantic reference implementation used by locked tests."""

    def __init__(self, cipher: PayloadCipher, *, capacity: int = 1000) -> None:
        if capacity < 1:
            raise ValueError("trace buffer capacity must be positive")
        self.cipher = cipher
        self.capacity = capacity
        self._records: dict[str, _MemoryRecord] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, trace: SanitizedTrace) -> bool:
        encrypted = self.cipher.seal(trace)
        async with self._lock:
            prior = self._records.get(trace.trace_ref)
            if prior is not None:
                if prior.payload.payload_digest != trace.payload_digest:
                    raise PayloadConflict("trace reference reused with different payload")
                return False
            pending = sum(
                any(delivery.state != "ACKED" for delivery in record.deliveries.values())
                for record in self._records.values()
            )
            if pending >= self.capacity:
                raise BufferFull("trace buffer capacity is exhausted")
            self._records[trace.trace_ref] = _MemoryRecord(
                encrypted,
                {sink: _MemoryDelivery() for sink in DeliverySink},
            )
            return True

    async def claim(
        self, sink: DeliverySink, *, limit: int = 10, lease_seconds: int = 30
    ) -> list[Delivery]:
        now = datetime.now(UTC)
        claimed: list[Delivery] = []
        async with self._lock:
            for trace_ref, record in sorted(self._records.items()):
                delivery = record.deliveries[sink]
                if delivery.state == "ACKED" or (
                    delivery.state == "LEASED"
                    and delivery.lease_until is not None
                    and delivery.lease_until > now
                ):
                    continue
                delivery.state = "LEASED"
                delivery.lease_until = now + timedelta(seconds=lease_seconds)
                claimed.append(
                    Delivery(
                        self.cipher.open(trace_ref, record.payload),
                        sink,
                        delivery.attempt_count,
                    )
                )
                if len(claimed) >= limit:
                    break
        return claimed

    async def acknowledge(self, trace_ref: str, sink: DeliverySink) -> None:
        async with self._lock:
            delivery = self._records[trace_ref].deliveries[sink]
            delivery.state = "ACKED"
            delivery.lease_until = None
            delivery.last_error_code = None

    async def retry(self, trace_ref: str, sink: DeliverySink, error_code: str) -> None:
        if not error_code or len(error_code) > 64:
            raise ValueError("retry error code must be bounded and non-empty")
        async with self._lock:
            delivery = self._records[trace_ref].deliveries[sink]
            delivery.state = "PENDING"
            delivery.attempt_count += 1
            delivery.lease_until = None
            delivery.last_error_code = error_code

    async def status(self) -> dict[str, int]:
        async with self._lock:
            counts = {sink.value: 0 for sink in DeliverySink}
            for record in self._records.values():
                for sink, delivery in record.deliveries.items():
                    if delivery.state != "ACKED":
                        counts[sink.value] += 1
            counts["traces"] = sum(
                any(delivery.state != "ACKED" for delivery in record.deliveries.values())
                for record in self._records.values()
            )
            return counts


class PostgresTraceBuffer:
    """Durable encrypted buffer; PostgreSQL never receives an unsanitized payload."""

    def __init__(
        self,
        dsn: str,
        cipher: PayloadCipher,
        *,
        capacity: int = 10_000,
    ) -> None:
        if capacity < 1:
            raise ValueError("trace buffer capacity must be positive")
        self.dsn = dsn
        self.cipher = cipher
        self.capacity = capacity
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5, command_timeout=10)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("trace buffer is not connected")
        return self.pool

    async def enqueue(self, trace: SanitizedTrace) -> bool:
        payload = self.cipher.seal(trace)
        async with self._pool().acquire() as connection, connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(706190013)")
            prior = await connection.fetchrow(
                """SELECT payload_digest FROM trace_buffer_owner.trace_payload
                   WHERE trace_ref=$1 FOR UPDATE""",
                trace.trace_ref,
            )
            if prior:
                if prior["payload_digest"] != trace.payload_digest:
                    raise PayloadConflict("trace reference reused with different payload")
                return False
            pending = await connection.fetchval(
                """SELECT count(*) FROM trace_buffer_owner.trace_payload p
                   WHERE EXISTS (SELECT 1 FROM trace_buffer_owner.delivery d
                     WHERE d.trace_ref=p.trace_ref AND d.state <> 'ACKED')"""
            )
            if int(pending) >= self.capacity:
                raise BufferFull("trace buffer capacity is exhausted")
            await connection.execute(
                """INSERT INTO trace_buffer_owner.trace_payload
                   (trace_ref,payload_digest,key_id,nonce,ciphertext,format_version,candidate_sha)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                trace.trace_ref,
                payload.payload_digest,
                payload.key_id,
                payload.nonce,
                payload.ciphertext,
                payload.format_version,
                trace.candidate_sha,
            )
            await connection.executemany(
                """INSERT INTO trace_buffer_owner.delivery(trace_ref,sink,state)
                   VALUES ($1,$2,'PENDING')""",
                [(trace.trace_ref, sink.value) for sink in DeliverySink],
            )
        return True

    async def claim(
        self, sink: DeliverySink, *, limit: int = 10, lease_seconds: int = 30
    ) -> list[Delivery]:
        async with self._pool().acquire() as connection, connection.transaction():
            rows = await connection.fetch(
                """WITH selected AS (
                     SELECT trace_ref,sink FROM trace_buffer_owner.delivery
                     WHERE sink=$1 AND (state='PENDING' OR (state='LEASED' AND leased_until<now()))
                       AND next_attempt_at<=now()
                     ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT $2
                   ), claimed AS (
                     UPDATE trace_buffer_owner.delivery d SET state='LEASED',
                       leased_until=now()+make_interval(secs=>$3)
                     FROM selected s WHERE d.trace_ref=s.trace_ref AND d.sink=s.sink
                     RETURNING d.trace_ref,d.attempt_count
                   )
                   SELECT c.trace_ref,c.attempt_count,p.payload_digest,p.key_id,p.nonce,
                     p.ciphertext,p.format_version
                   FROM claimed c JOIN trace_buffer_owner.trace_payload p USING(trace_ref)
                   ORDER BY c.trace_ref""",
                sink.value,
                limit,
                lease_seconds,
            )
        deliveries: list[Delivery] = []
        for row in rows:
            payload = EncryptedPayload(
                row["key_id"],
                bytes(row["nonce"]),
                bytes(row["ciphertext"]),
                row["payload_digest"],
                row["format_version"],
            )
            deliveries.append(
                Delivery(
                    self.cipher.open(row["trace_ref"], payload),
                    sink,
                    row["attempt_count"],
                )
            )
        return deliveries

    async def acknowledge(self, trace_ref: str, sink: DeliverySink) -> None:
        result = await self._pool().execute(
            """UPDATE trace_buffer_owner.delivery SET state='ACKED',acked_at=now(),
               leased_until=NULL,last_error_code=NULL WHERE trace_ref=$1 AND sink=$2""",
            trace_ref,
            sink.value,
        )
        if result != "UPDATE 1":
            raise KeyError("trace delivery does not exist")

    async def retry(self, trace_ref: str, sink: DeliverySink, error_code: str) -> None:
        if not error_code or len(error_code) > 64:
            raise ValueError("retry error code must be bounded and non-empty")
        await self._pool().execute(
            """UPDATE trace_buffer_owner.delivery SET state='PENDING',attempt_count=attempt_count+1,
               leased_until=NULL,last_error_code=$3,
               next_attempt_at=now()+make_interval(secs=>LEAST(60,1<<LEAST(attempt_count,5)))
               WHERE trace_ref=$1 AND sink=$2""",
            trace_ref,
            sink.value,
            error_code,
        )

    async def status(self) -> dict[str, int]:
        rows = await self._pool().fetch(
            """SELECT sink,count(*) FILTER (WHERE state<>'ACKED') AS pending
               FROM trace_buffer_owner.delivery GROUP BY sink"""
        )
        counts = {sink.value: 0 for sink in DeliverySink}
        counts.update({row["sink"]: int(row["pending"]) for row in rows})
        counts["traces"] = int(
            await self._pool().fetchval(
                """SELECT count(*) FROM trace_buffer_owner.trace_payload p WHERE EXISTS
                   (SELECT 1 FROM trace_buffer_owner.delivery d
                    WHERE d.trace_ref=p.trace_ref AND d.state<>'ACKED')"""
            )
        )
        return counts
