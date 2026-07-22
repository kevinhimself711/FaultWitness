"""Allowlist-only trace sanitization before any persistence or egress."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from faultwitness.contracts.models import TraceEnvelope, TraceStage

_STAGE_PREFIX = {
    TraceStage.API: "api.",
    TraceStage.STATE_TRANSITION: "state.",
    TraceStage.CHECKPOINT: "checkpoint.",
    TraceStage.MODEL: "model.",
    TraceStage.TOOL: "tool.",
    TraceStage.POLICY: "policy.",
    TraceStage.ACTION: "action.",
    TraceStage.EXPORT: "export.",
}
_SAFE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+){1,7}$")
_ALLOWED_ATTRIBUTES = frozenset(
    {
        "db.operation",
        "error.type",
        "event.type",
        "http.request.method",
        "http.response.status_code",
        "http.route",
        "messaging.destination.template",
        "messaging.operation",
        "model.family",
        "model.route",
        "model.snapshot",
        "outcome",
        "retry.attempt",
        "sequence",
        "state.from",
        "state.to",
    }
)
_DENIED_KEY_PARTS = (
    "authorization",
    "chain_of_thought",
    "cookie",
    "credential",
    "email",
    "hidden_reasoning",
    "host",
    "internal_monologue",
    "ip",
    "password",
    "private_reasoning",
    "prompt",
    "reasoning_content",
    "secret",
    "server",
    "token",
    "user",
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:sk|lsv2|api)[_-][a-z0-9_-]{12,}"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"(?<![a-z0-9])(?:\d{1,3}\.){3}\d{1,3}(?![a-z0-9])", re.I),
    re.compile(r"FW_(?:SECRET|PII|PRIVATE_REASONING)_CANARY", re.I),
)
_SCALAR_TYPES = (str, int, float, bool)


class SanitizationRejected(ValueError):
    """The entire trace is rejected; no rejected material may be persisted."""


@dataclass(frozen=True, slots=True)
class SanitizedSpan:
    span_ref: str
    remote_id: str
    otlp_span_id: str
    parent_span_ref: str | None
    name: str
    stage: str
    started_at: str
    ended_at: str
    status: str
    attributes: dict[str, str | int | float | bool]


@dataclass(frozen=True, slots=True)
class SanitizedTrace:
    schema_version: str
    trace_ref: str
    remote_trace_id: str
    otlp_trace_id: str
    tenant_ref: str
    correlation_ref: str
    causation_ref: str | None
    incident_ref: str | None
    task_ref: str | None
    action_ref: str | None
    contracts_version: str
    candidate_sha: str
    emitted_at: str
    spans: tuple[SanitizedSpan, ...]
    payload_digest: str

    def document(self, *, include_digest: bool = True) -> dict[str, Any]:
        document = asdict(self)
        if not include_digest:
            document.pop("payload_digest", None)
        return document

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.document(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()

    def content_bytes(self) -> bytes:
        return json.dumps(
            self.document(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> SanitizedTrace:
        spans = tuple(SanitizedSpan(**span) for span in document["spans"])
        return cls(**{**document, "spans": spans})


@dataclass(frozen=True, slots=True)
class LatencyReconciliation:
    wall_duration_ms: float
    trace_union_ms: float
    difference_ms: float
    tolerance_ms: float
    passed: bool


class TraceSanitizer:
    """Converts a strict TraceEnvelope to an irreversible, allowlisted export form."""

    def __init__(self, reference_key: bytes) -> None:
        if len(reference_key) < 32:
            raise ValueError("trace reference key must contain at least 32 bytes")
        self._key = reference_key

    def sanitize(self, envelope: TraceEnvelope) -> SanitizedTrace:
        self._validate_graph(envelope)
        trace_ref = self._ref("trace", envelope.trace_id, 24)
        root = next(span for span in envelope.spans if span.parent_span_id is None)
        remote_trace_id = self._uuid("langsmith-trace", root.span_id)
        span_refs = {span.span_id: self._ref("span", span.span_id, 24) for span in envelope.spans}
        sanitized_spans = tuple(
            SanitizedSpan(
                span_ref=span_refs[span.span_id],
                remote_id=self._uuid("langsmith-span", span.span_id),
                otlp_span_id=self._ref("otlp-span", span.span_id, 16),
                parent_span_ref=span_refs.get(span.parent_span_id),
                name=self._sanitize_name(span.name, span.stage),
                stage=span.stage.value,
                started_at=span.started_at.isoformat(),
                ended_at=span.ended_at.isoformat(),  # graph validation requires it
                status=span.status.value,
                attributes=self._sanitize_attributes(span.attributes),
            )
            for span in sorted(envelope.spans, key=lambda item: (item.started_at, item.span_id))
        )
        values: dict[str, Any] = {
            "schema_version": "1.0.0",
            "trace_ref": trace_ref,
            "remote_trace_id": remote_trace_id,
            "otlp_trace_id": self._ref("otlp-trace", envelope.trace_id, 32),
            "tenant_ref": self._ref("tenant", envelope.tenant_id, 24),
            "correlation_ref": self._ref("correlation", envelope.correlation_id, 24),
            "causation_ref": self._optional_ref("causation", envelope.causation_id),
            "incident_ref": self._optional_ref("incident", envelope.incident_id),
            "task_ref": self._optional_ref("task", envelope.task_id),
            "action_ref": self._optional_ref("action", envelope.action_id),
            "contracts_version": envelope.contracts_version,
            "candidate_sha": envelope.candidate_sha,
            "emitted_at": envelope.emitted_at.isoformat(),
            "spans": sanitized_spans,
        }
        canonical = json.dumps(
            {**values, "spans": [asdict(span) for span in sanitized_spans]},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        return SanitizedTrace(**values, payload_digest=hashlib.sha256(canonical).hexdigest())

    def _ref(self, kind: str, value: str, length: int) -> str:
        return hmac.new(self._key, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()[:length]

    def _optional_ref(self, kind: str, value: str | None) -> str | None:
        return None if value is None else self._ref(kind, value, 24)

    def _uuid(self, kind: str, value: str) -> str:
        digest = hmac.new(self._key, f"{kind}:{value}".encode(), hashlib.sha256).digest()
        raw = bytearray(digest[:16])
        raw[6] = (raw[6] & 0x0F) | 0x50
        raw[8] = (raw[8] & 0x3F) | 0x80
        return str(uuid.UUID(bytes=bytes(raw)))

    @staticmethod
    def _sanitize_name(name: str, stage: TraceStage) -> str:
        if not _SAFE_NAME.fullmatch(name) or not name.startswith(_STAGE_PREFIX[stage]):
            raise SanitizationRejected("span name is outside the fixed stage taxonomy")
        TraceSanitizer._scan_value(name)
        return name

    @staticmethod
    def _sanitize_attributes(
        attributes: dict[str, Any],
    ) -> dict[str, str | int | float | bool]:
        sanitized: dict[str, str | int | float | bool] = {}
        for key, value in attributes.items():
            normalized = key.casefold().replace("-", "_")
            if key not in _ALLOWED_ATTRIBUTES or any(
                part in normalized for part in _DENIED_KEY_PARTS
            ):
                raise SanitizationRejected("trace attribute is outside the allowlist")
            if not isinstance(value, _SCALAR_TYPES) or isinstance(value, str) and len(value) > 256:
                raise SanitizationRejected("trace attribute value is not a bounded scalar")
            TraceSanitizer._scan_value(str(value))
            sanitized[key] = value
        return dict(sorted(sanitized.items()))

    @staticmethod
    def _scan_value(value: str) -> None:
        if any(pattern.search(value) for pattern in _SENSITIVE_VALUE_PATTERNS):
            raise SanitizationRejected("trace value matches a sensitive-data pattern")

    @staticmethod
    def _validate_graph(envelope: TraceEnvelope) -> None:
        by_id = {span.span_id: span for span in envelope.spans}
        if len(by_id) != len(envelope.spans):
            raise SanitizationRejected("duplicate span identifier")
        roots = [span for span in envelope.spans if span.parent_span_id is None]
        if len(roots) != 1:
            raise SanitizationRejected("a trace must contain exactly one root span")
        for span in envelope.spans:
            if span.ended_at is None:
                raise SanitizationRejected("only completed spans can be exported")
            if span.parent_span_id is not None and span.parent_span_id not in by_id:
                raise SanitizationRejected("span parent is outside the trace")
            visited = {span.span_id}
            parent = span.parent_span_id
            while parent is not None:
                if parent in visited:
                    raise SanitizationRejected("span graph contains a cycle")
                visited.add(parent)
                parent = by_id[parent].parent_span_id


def reconcile_wall_time(
    trace: SanitizedTrace, *, wall_started_at: datetime, wall_ended_at: datetime
) -> LatencyReconciliation:
    if wall_started_at.tzinfo is None or wall_ended_at.tzinfo is None:
        raise ValueError("wall-clock timestamps must be timezone aware")
    if wall_ended_at < wall_started_at:
        raise ValueError("wall-clock end precedes start")
    intervals = sorted(
        (
            datetime.fromisoformat(span.started_at).astimezone(UTC),
            datetime.fromisoformat(span.ended_at).astimezone(UTC),
        )
        for span in trace.spans
    )
    merged: list[tuple[datetime, datetime]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    trace_ms = sum((end - start).total_seconds() * 1000 for start, end in merged)
    wall_ms = (wall_ended_at - wall_started_at).total_seconds() * 1000
    difference = abs(wall_ms - trace_ms)
    tolerance = max(50.0, wall_ms * 0.05)
    return LatencyReconciliation(wall_ms, trace_ms, difference, tolerance, difference <= tolerance)
