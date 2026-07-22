import asyncio
import json

import httpx

from faultwitness.observability.exporters import (
    EvidenceArchiveExporter,
    LangSmithExporter,
    OTLPHTTPExporter,
    S3Credentials,
)
from faultwitness.observability.sanitizer import TraceSanitizer
from tests.observability.test_sanitizer import envelope


def run(coroutine):
    return asyncio.run(coroutine)


def test_otlp_json_uses_deterministic_ids_and_contains_no_raw_identity() -> None:
    raw = envelope()
    trace = TraceSanitizer(b"r" * 32).sanitize(raw)
    payload = OTLPHTTPExporter.payload(trace)
    encoded = json.dumps(payload)
    assert trace.otlp_trace_id in encoded
    assert all(span.otlp_span_id in encoded for span in trace.spans)
    assert raw.tenant_id not in encoded
    assert raw.correlation_id not in encoded
    assert '"traceId": "' in encoded


def test_otlp_export_correlates_trace_metric_and_log_signals() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    trace = TraceSanitizer(b"r" * 32).sanitize(envelope())
    exporter = OTLPHTTPExporter("https://collector.test", client=client)
    result = run(exporter.export(trace))
    run(client.aclose())
    assert result["span_count"] == 2
    assert paths == ["/v1/traces", "/v1/metrics", "/v1/logs"]


def test_langsmith_export_contains_only_sanitized_complete_runs() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    raw = envelope()
    trace = TraceSanitizer(b"r" * 32).sanitize(raw)
    exporter = LangSmithExporter(
        "private-key", project="test-project", endpoint="https://langsmith.test", client=client
    )
    result = run(exporter.export(trace))
    run(client.aclose())
    assert result["span_count"] == 2
    assert len(requests) == 2
    bodies = [json.loads(request.content) for request in requests]
    assert all(body["end_time"] and body["session_name"] == "test-project" for body in bodies)
    encoded = json.dumps(bodies)
    assert raw.tenant_id not in encoded
    assert raw.incident_id not in encoded
    assert "private-key" not in encoded
    assert bodies[1]["parent_run_id"] == bodies[0]["id"]


def test_archive_writes_content_addressed_manifest_and_dvc_pointer() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    raw = envelope()
    trace = TraceSanitizer(b"r" * 32).sanitize(raw)
    exporter = EvidenceArchiveExporter(
        "https://minio.test",
        S3Credentials("access", "private-secret"),
        client=client,
    )
    result = run(exporter.export(trace))
    run(client.aclose())
    assert result["artifact_sha256"] in result["private_uri"]
    assert len(requests) == 3
    assert requests[1].url.path.endswith(".json")
    assert requests[2].url.path.endswith(".json.dvc")
    bodies = b"".join(request.content for request in requests)
    assert raw.tenant_id.encode() not in bodies
    assert b"private-secret" not in bodies
