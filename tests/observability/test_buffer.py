import asyncio

import pytest

from faultwitness.observability.buffer import (
    BufferFull,
    DeliverySink,
    InMemoryTraceBuffer,
    PayloadCipher,
    PayloadConflict,
)
from faultwitness.observability.exporters import ExportFailure
from faultwitness.observability.sanitizer import TraceSanitizer
from faultwitness.observability.service import TraceExportService
from tests.observability.test_sanitizer import envelope


def run(coroutine):
    return asyncio.run(coroutine)


def test_encrypted_buffer_is_idempotent_bounded_and_replayable() -> None:
    cipher = PayloadCipher("test-key", b"p" * 32)
    store = InMemoryTraceBuffer(cipher, capacity=1)
    sanitizer = TraceSanitizer(b"r" * 32)
    first = sanitizer.sanitize(envelope())
    assert run(store.enqueue(first)) is True
    assert run(store.enqueue(first)) is False
    record = store._records[first.trace_ref]
    assert first.trace_ref.encode() not in record.payload.ciphertext
    assert first.correlation_ref.encode() not in record.payload.ciphertext

    with pytest.raises(BufferFull):
        run(store.enqueue(sanitizer.sanitize(envelope(marker="2"))))

    delivery = run(store.claim(DeliverySink.LANGSMITH))[0]
    assert delivery.trace == first
    run(store.retry(first.trace_ref, DeliverySink.LANGSMITH, "planned_outage"))
    replay = run(store.claim(DeliverySink.LANGSMITH))[0]
    assert replay.trace.remote_trace_id == delivery.trace.remote_trace_id
    assert replay.attempt_count == 1


def test_buffer_rejects_same_reference_with_different_digest() -> None:
    store = InMemoryTraceBuffer(PayloadCipher("test-key", b"p" * 32))
    sanitizer = TraceSanitizer(b"r" * 32)
    run(store.enqueue(sanitizer.sanitize(envelope(attributes={"outcome": "first"}))))
    with pytest.raises(PayloadConflict):
        run(store.enqueue(sanitizer.sanitize(envelope(attributes={"outcome": "second"}))))


class FakeExporter:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.fail_once = fail_once
        self.ids: list[str] = []

    async def export(self, trace):
        self.ids.append(trace.remote_trace_id)
        if self.fail_once:
            self.fail_once = False
            raise ExportFailure("planned_outage", retryable=True)
        return {"trace_ref": trace.trace_ref}


def test_service_replays_only_failed_sink_and_drains_without_duplicates() -> None:
    store = InMemoryTraceBuffer(PayloadCipher("test-key", b"p" * 32))
    exporters = {
        DeliverySink.LANGSMITH: FakeExporter(fail_once=True),
        DeliverySink.OTLP: FakeExporter(),
        DeliverySink.ARCHIVE: FakeExporter(),
    }
    service = TraceExportService(store, TraceSanitizer(b"r" * 32), exporters)
    run(service.ingest(envelope()))
    first = run(service.drain_once())
    assert first == {"acked": 2, "retried": 1}
    second = run(service.drain_once())
    assert second == {"acked": 1, "retried": 0}
    assert run(store.status()) == {"langsmith": 0, "otlp": 0, "archive": 0, "traces": 0}
    assert len(exporters[DeliverySink.LANGSMITH].ids) == 2
    assert len(exporters[DeliverySink.OTLP].ids) == 1
    assert len(exporters[DeliverySink.ARCHIVE].ids) == 1


def test_operator_relay_mode_leaves_only_langsmith_for_explicit_claim() -> None:
    store = InMemoryTraceBuffer(PayloadCipher("test-key", b"p" * 32))
    exporters = {
        DeliverySink.LANGSMITH: FakeExporter(),
        DeliverySink.OTLP: FakeExporter(),
        DeliverySink.ARCHIVE: FakeExporter(),
    }
    service = TraceExportService(
        store,
        TraceSanitizer(b"r" * 32),
        exporters,
        automatic_sinks=(DeliverySink.OTLP, DeliverySink.ARCHIVE),
    )
    trace, _ = run(service.ingest(envelope()))
    assert run(service.drain_once()) == {"acked": 2, "retried": 0}
    assert run(store.status()) == {"langsmith": 1, "otlp": 0, "archive": 0, "traces": 1}
    claim = run(store.claim(DeliverySink.LANGSMITH))[0]
    assert claim.trace == trace
    run(store.acknowledge(trace.trace_ref, DeliverySink.LANGSMITH))
    assert run(store.status())["traces"] == 0
