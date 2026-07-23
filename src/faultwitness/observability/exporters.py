"""Deterministic LangSmith, OTLP/HTTP and private evidence exporters."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import httpx

from faultwitness.observability.sanitizer import SanitizedSpan, SanitizedTrace


class ExportFailure(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class TraceExporter(Protocol):
    async def export(self, trace: SanitizedTrace) -> dict[str, Any]: ...


def _langsmith_order(trace: SanitizedTrace) -> dict[str, str]:
    by_ref = {span.span_ref: span for span in trace.spans}
    orders: dict[str, str] = {}

    def visit(span: SanitizedSpan) -> str:
        if span.span_ref in orders:
            return orders[span.span_ref]
        timestamp = datetime.fromisoformat(span.started_at).strftime("%Y%m%dT%H%M%S%fZ")
        own = timestamp + span.remote_id
        orders[span.span_ref] = (
            own if span.parent_span_ref is None else visit(by_ref[span.parent_span_ref]) + "." + own
        )
        return orders[span.span_ref]

    for item in trace.spans:
        visit(item)
    return orders


class LangSmithExporter:
    """Uses complete deterministic runs so uncertain acknowledgements are reconcilable."""

    def __init__(
        self,
        api_key: str,
        *,
        project: str,
        endpoint: str = "https://api.smith.langchain.com",
        workspace_id: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key or not project:
            raise ValueError("LangSmith API key and project are required")
        self.project = project
        self.endpoint = endpoint.rstrip("/")
        self._headers = {"x-api-key": api_key}
        if workspace_id:
            self._headers["x-tenant-id"] = workspace_id
        self._client = client

    async def export(self, trace: SanitizedTrace) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=10)
        owned = self._client is None
        orders = _langsmith_order(trace)
        root = next(span for span in trace.spans if span.parent_span_ref is None)
        try:
            for span in trace.spans:
                body = {
                    "id": span.remote_id,
                    "trace_id": root.remote_id,
                    "parent_run_id": self._parent_remote_id(trace, span),
                    "dotted_order": orders[span.span_ref],
                    "name": span.name,
                    "run_type": self._run_type(span.stage),
                    "session_name": self.project,
                    "start_time": span.started_at,
                    "end_time": span.ended_at,
                    "inputs": {"trace_ref": trace.trace_ref, "stage": span.stage},
                    "outputs": {"status": span.status},
                    "extra": {
                        "metadata": {
                            "candidate_sha": trace.candidate_sha,
                            "contracts_version": trace.contracts_version,
                            "correlation_ref": trace.correlation_ref,
                            "payload_digest": trace.payload_digest,
                            **span.attributes,
                        }
                    },
                    "tags": ["faultwitness", "g01", span.stage],
                }
                if body["parent_run_id"] is None:
                    body.pop("parent_run_id")
                response = await client.post(
                    self.endpoint + "/runs", headers=self._headers, json=body
                )
                if response.status_code in {200, 201, 202, 409}:
                    if response.status_code == 409:
                        await self._verify_existing(client, trace, span)
                    continue
                raise self._http_failure("langsmith", response.status_code)
        except httpx.TimeoutException as error:
            raise ExportFailure("langsmith_timeout", retryable=True) from error
        except httpx.TransportError as error:
            raise ExportFailure("langsmith_transport", retryable=True) from error
        finally:
            if owned:
                await client.aclose()
        return {
            "sink": "langsmith",
            "trace_ref": trace.trace_ref,
            "remote_trace_id": root.remote_id,
            "span_count": len(trace.spans),
        }

    async def _verify_existing(
        self, client: httpx.AsyncClient, trace: SanitizedTrace, span: SanitizedSpan
    ) -> None:
        response = await client.get(
            self.endpoint + "/runs/" + span.remote_id, headers=self._headers
        )
        if response.status_code != 200:
            raise self._http_failure("langsmith_reconcile", response.status_code)
        try:
            metadata = response.json().get("extra", {}).get("metadata", {})
        except (ValueError, AttributeError) as error:
            raise ExportFailure("langsmith_reconcile_invalid", retryable=False) from error
        if metadata.get("payload_digest") != trace.payload_digest:
            raise ExportFailure("langsmith_identity_conflict", retryable=False)

    @staticmethod
    def _parent_remote_id(trace: SanitizedTrace, span: SanitizedSpan) -> str | None:
        if span.parent_span_ref is None:
            return None
        return next(item.remote_id for item in trace.spans if item.span_ref == span.parent_span_ref)

    @staticmethod
    def _run_type(stage: str) -> str:
        return {"model": "llm", "tool": "tool"}.get(stage, "chain")

    @staticmethod
    def _http_failure(prefix: str, status: int) -> ExportFailure:
        return ExportFailure(
            f"{prefix}_http_{status}", retryable=status in {408, 409, 425, 429, 500, 502, 503, 504}
        )


def _any_value(value: str | int | float | bool) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": value}


class OTLPHTTPExporter:
    def __init__(self, endpoint: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        for suffix in ("/v1/traces", "/v1/metrics", "/v1/logs"):
            if self.endpoint.endswith(suffix):
                self.endpoint = self.endpoint[: -len(suffix)]
                break
        self._client = client

    async def export(self, trace: SanitizedTrace) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=10)
        owned = self._client is None
        try:
            await self._send(client, "traces", self.payload(trace), "rejectedSpans")
            await self._send(client, "metrics", self.metric_payload(trace), "rejectedDataPoints")
            await self._send(client, "logs", self.log_payload(trace), "rejectedLogRecords")
        except httpx.TimeoutException as error:
            raise ExportFailure("otlp_timeout", retryable=True) from error
        except httpx.TransportError as error:
            raise ExportFailure("otlp_transport", retryable=True) from error
        finally:
            if owned:
                await client.aclose()
        return {
            "sink": "otlp",
            "trace_ref": trace.trace_ref,
            "otlp_trace_id": trace.otlp_trace_id,
            "span_count": len(trace.spans),
        }

    async def _send(
        self,
        client: httpx.AsyncClient,
        signal: str,
        body: dict[str, Any],
        rejection_field: str,
    ) -> None:
        response = await client.post(
            f"{self.endpoint}/v1/{signal}",
            headers={"content-type": "application/json"},
            json=body,
        )
        if response.status_code != 200:
            raise ExportFailure(
                f"otlp_{signal}_http_{response.status_code}",
                retryable=response.status_code in {408, 425, 429, 502, 503, 504},
            )
        if response.content:
            reply = response.json()
            partial = reply.get("partialSuccess") or {}
            if int(partial.get(rejection_field, 0)) != 0:
                raise ExportFailure(f"otlp_{signal}_partial_rejection", retryable=False)

    @staticmethod
    def payload(trace: SanitizedTrace) -> dict[str, Any]:
        spans = []
        by_ref = {span.span_ref: span for span in trace.spans}
        for span in trace.spans:
            attributes = {
                "faultwitness.trace_ref": trace.trace_ref,
                "faultwitness.correlation_ref": trace.correlation_ref,
                "faultwitness.candidate_sha": trace.candidate_sha,
                "faultwitness.contracts_version": trace.contracts_version,
                "faultwitness.stage": span.stage,
                **span.attributes,
            }
            document: dict[str, Any] = {
                "traceId": trace.otlp_trace_id,
                "spanId": span.otlp_span_id,
                "name": span.name,
                "kind": 1,
                "startTimeUnixNano": str(
                    int(datetime.fromisoformat(span.started_at).timestamp() * 1_000_000_000)
                ),
                "endTimeUnixNano": str(
                    int(datetime.fromisoformat(span.ended_at).timestamp() * 1_000_000_000)
                ),
                "attributes": [
                    {"key": key, "value": _any_value(value)}
                    for key, value in sorted(attributes.items())
                ],
                "status": {"code": {"unset": 0, "ok": 1, "error": 2}[span.status]},
            }
            if span.parent_span_ref is not None:
                document["parentSpanId"] = by_ref[span.parent_span_ref].otlp_span_id
            spans.append(document)
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "faultwitness"}},
                            {
                                "key": "service.version",
                                "value": {"stringValue": trace.candidate_sha},
                            },
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "faultwitness.observability", "version": "1.0.0"},
                            "spans": spans,
                        }
                    ],
                }
            ]
        }

    @staticmethod
    def metric_payload(trace: SanitizedTrace) -> dict[str, Any]:
        timestamp = str(int(datetime.fromisoformat(trace.emitted_at).timestamp() * 1_000_000_000))
        attributes = [
            {"key": "faultwitness.trace_ref", "value": {"stringValue": trace.trace_ref}},
            {
                "key": "faultwitness.correlation_ref",
                "value": {"stringValue": trace.correlation_ref},
            },
            {
                "key": "faultwitness.candidate_sha",
                "value": {"stringValue": trace.candidate_sha},
            },
        ]
        return {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "faultwitness"}}
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "scope": {"name": "faultwitness.observability", "version": "1.0.0"},
                            "metrics": [
                                {
                                    "name": "faultwitness.trace.exported",
                                    "unit": "{trace}",
                                    "sum": {
                                        "aggregationTemporality": 2,
                                        "isMonotonic": True,
                                        "dataPoints": [
                                            {
                                                "attributes": attributes,
                                                "startTimeUnixNano": timestamp,
                                                "timeUnixNano": timestamp,
                                                "asInt": "1",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }

    @staticmethod
    def log_payload(trace: SanitizedTrace) -> dict[str, Any]:
        timestamp = str(int(datetime.fromisoformat(trace.emitted_at).timestamp() * 1_000_000_000))
        return {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "faultwitness"}}
                        ]
                    },
                    "scopeLogs": [
                        {
                            "scope": {"name": "faultwitness.observability", "version": "1.0.0"},
                            "logRecords": [
                                {
                                    "timeUnixNano": timestamp,
                                    "severityNumber": 9,
                                    "severityText": "INFO",
                                    "body": {"stringValue": "trace_exported"},
                                    "attributes": [
                                        {
                                            "key": "faultwitness.trace_ref",
                                            "value": {"stringValue": trace.trace_ref},
                                        },
                                        {
                                            "key": "faultwitness.correlation_ref",
                                            "value": {"stringValue": trace.correlation_ref},
                                        },
                                        {
                                            "key": "faultwitness.candidate_sha",
                                            "value": {"stringValue": trace.candidate_sha},
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }


@dataclass(frozen=True, slots=True)
class S3Credentials:
    access_key: str
    secret_key: str
    region: str = "us-east-1"


class EvidenceArchiveExporter:
    """Writes a sanitized content-addressed manifest and DVC pointer to private MinIO."""

    def __init__(
        self,
        endpoint: str,
        credentials: S3Credentials,
        *,
        bucket: str = "faultwitness-evidence",
        prefix: str = "g01/traces",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.credentials = credentials
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = client

    async def export(self, trace: SanitizedTrace) -> dict[str, Any]:
        manifest = {
            "schema_version": "1.0.0",
            "candidate_sha": trace.candidate_sha,
            "trace_ref": trace.trace_ref,
            "correlation_ref": trace.correlation_ref,
            "payload_digest": trace.payload_digest,
            "span_count": len(trace.spans),
            "stage_counts": {
                stage: sum(span.stage == stage for span in trace.spans)
                for stage in sorted({span.stage for span in trace.spans})
            },
            "langsmith_trace_id": next(
                span.remote_id for span in trace.spans if span.parent_span_ref is None
            ),
            "otlp_trace_id": trace.otlp_trace_id,
        }
        content = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(content).hexdigest()
        object_key = f"{self.prefix}/{trace.candidate_sha}/{digest}.json"
        dvc = (
            "outs:\n"
            f"- hash: sha256\n  sha256: {digest}\n  size: {len(content)}\n"
            f"  path: {object_key}\n"
        ).encode()
        client = self._client or httpx.AsyncClient(timeout=10)
        owned = self._client is None
        try:
            await self._put(client, self.bucket, "", b"")
            await self._put(client, self.bucket, object_key, content)
            await self._put(client, self.bucket, object_key + ".dvc", dvc)
        finally:
            if owned:
                await client.aclose()
        return {
            "sink": "archive",
            "trace_ref": trace.trace_ref,
            "artifact_sha256": digest,
            "private_uri": f"s3://{self.bucket}/{object_key}",
        }

    async def _put(self, client: httpx.AsyncClient, bucket: str, key: str, content: bytes) -> None:
        path = "/" + quote(bucket, safe="")
        if key:
            path += "/" + quote(key, safe="/")
        url = self.endpoint + path
        headers = self._signed_headers("PUT", url, content)
        try:
            response = await client.put(url, headers=headers, content=content)
        except httpx.TimeoutException as error:
            raise ExportFailure("archive_timeout", retryable=True) from error
        except httpx.TransportError as error:
            raise ExportFailure("archive_transport", retryable=True) from error
        accepted = {200, 201, 204}
        if not key:
            accepted.add(409)
        if response.status_code not in accepted:
            raise ExportFailure(
                f"archive_http_{response.status_code}",
                retryable=response.status_code in {408, 425, 429, 500, 502, 503, 504},
            )

    def _signed_headers(self, method: str, url: str, content: bytes) -> dict[str, str]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date = now.strftime("%Y%m%d")
        parsed = urlparse(url)
        payload_hash = hashlib.sha256(content).hexdigest()
        canonical_headers = (
            f"host:{parsed.netloc}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join(
            [
                method,
                parsed.path or "/",
                parsed.query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{date}/{self.credentials.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )

        def sign(key: bytes, value: str) -> bytes:
            return hmac.new(key, value.encode(), hashlib.sha256).digest()

        signing_key = sign(
            sign(
                sign(
                    sign(("AWS4" + self.credentials.secret_key).encode(), date),
                    self.credentials.region,
                ),
                "s3",
            ),
            "aws4_request",
        )
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.credentials.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "authorization": authorization,
            "host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
