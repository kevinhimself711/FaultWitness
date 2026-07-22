from datetime import UTC, datetime, timedelta

import pytest

from faultwitness.contracts.models import (
    SpanRecord,
    SpanStatus,
    TraceEnvelope,
    TraceStage,
)
from faultwitness.observability.sanitizer import (
    SanitizationRejected,
    TraceSanitizer,
    reconcile_wall_time,
)

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def ident(prefix: str, marker: str = "0") -> str:
    return prefix + marker * 26


def envelope(*, marker: str = "0", attributes: dict | None = None) -> TraceEnvelope:
    root = SpanRecord(
        span_id=ident("span_", marker),
        name="api.incident.create",
        stage=TraceStage.API,
        started_at=NOW,
        ended_at=NOW + timedelta(milliseconds=100),
        status=SpanStatus.OK,
        attributes=attributes or {"http.request.method": "POST", "http.route": "/v1/incidents"},
    )
    child_marker = "1" if marker != "1" else "2"
    child = SpanRecord(
        span_id=ident("span_", child_marker),
        parent_span_id=root.span_id,
        name="state.incident.create",
        stage=TraceStage.STATE_TRANSITION,
        started_at=NOW + timedelta(milliseconds=25),
        ended_at=NOW + timedelta(milliseconds=75),
        status=SpanStatus.OK,
        attributes={"state.from": "NEW", "state.to": "QUEUED"},
    )
    return TraceEnvelope(
        trace_id=ident("trace_", marker),
        tenant_id=ident("ten_", marker),
        correlation_id=ident("corr_", marker),
        incident_id=ident("inc_", marker),
        candidate_sha="a" * 40,
        spans=(root, child),
        emitted_at=NOW + timedelta(milliseconds=100),
    )


def test_sanitizer_is_deterministic_irreversible_and_allowlist_only() -> None:
    raw = envelope()
    sanitizer = TraceSanitizer(b"r" * 32)
    first = sanitizer.sanitize(raw)
    second = sanitizer.sanitize(raw)
    assert first == second
    assert first.payload_digest == second.payload_digest
    encoded = first.canonical_bytes().decode()
    for private in (raw.tenant_id, raw.correlation_id, raw.incident_id, raw.trace_id):
        assert private not in encoded
    assert first.trace_ref != raw.trace_id
    assert len(first.otlp_trace_id) == 32
    assert all(len(span.otlp_span_id) == 16 for span in first.spans)


@pytest.mark.parametrize(
    ("attributes", "match"),
    [
        ({"password": "not-exportable"}, "outside the allowlist"),
        ({"outcome": "operator@example.test"}, "sensitive-data pattern"),
        ({"outcome": "FW_SECRET_CANARY-123"}, "sensitive-data pattern"),
        ({"http.route": "x" * 257}, "bounded scalar"),
    ],
)
def test_sanitizer_rejects_entire_trace_before_persistence(attributes: dict, match: str) -> None:
    with pytest.raises(SanitizationRejected, match=match):
        TraceSanitizer(b"r" * 32).sanitize(envelope(attributes=attributes))


def test_sanitizer_rejects_stage_name_mismatch_and_disconnected_parent() -> None:
    raw = envelope()
    wrong_name = raw.spans[0].model_copy(update={"name": "model.invoke"})
    with pytest.raises(SanitizationRejected, match="taxonomy"):
        TraceSanitizer(b"r" * 32).sanitize(
            raw.model_copy(update={"spans": (wrong_name, raw.spans[1])})
        )

    orphan = raw.spans[1].model_copy(update={"parent_span_id": ident("span_", "9")})
    with pytest.raises(SanitizationRejected, match="outside the trace"):
        TraceSanitizer(b"r" * 32).sanitize(raw.model_copy(update={"spans": (raw.spans[0], orphan)}))


def test_latency_uses_interval_union_instead_of_naive_child_sum() -> None:
    trace = TraceSanitizer(b"r" * 32).sanitize(envelope())
    result = reconcile_wall_time(
        trace, wall_started_at=NOW, wall_ended_at=NOW + timedelta(milliseconds=100)
    )
    assert result.trace_union_ms == pytest.approx(100)
    assert result.wall_duration_ms == pytest.approx(100)
    assert result.difference_ms == pytest.approx(0)
    assert result.passed is True
