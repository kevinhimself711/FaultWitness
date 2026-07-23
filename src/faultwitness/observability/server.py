"""Private ClusterIP trace ingestion service."""

from __future__ import annotations

import asyncio
import base64
import hmac
import os
from contextlib import asynccontextmanager
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, ValidationError

from faultwitness.contracts.models import TraceEnvelope
from faultwitness.observability.buffer import (
    BufferFull,
    DeliverySink,
    PayloadCipher,
    PostgresTraceBuffer,
)
from faultwitness.observability.exporters import (
    EvidenceArchiveExporter,
    ExportFailure,
    LangSmithExporter,
    OTLPHTTPExporter,
    S3Credentials,
)
from faultwitness.observability.sanitizer import SanitizationRejected, TraceSanitizer
from faultwitness.observability.service import TraceExportService, run_drain_loop


class TraceAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    trace_ref: str
    langsmith_trace_id: str
    otlp_trace_id: str
    payload_digest: str
    duplicate: bool


class TraceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pending_traces: int
    pending_langsmith: int
    pending_otlp: int
    pending_archive: int


class DrainResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    acknowledged: int
    retried: int
    status: TraceStatus


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required configuration {name} is absent")
    return value


def _key(name: str) -> bytes:
    try:
        value = base64.b64decode(_required(name), validate=True)
    except ValueError as error:
        raise RuntimeError(f"required configuration {name} is invalid") from error
    if len(value) != 32:
        raise RuntimeError(f"required configuration {name} must decode to 32 bytes")
    return value


def _build_service() -> TraceExportService:
    cipher = PayloadCipher(_required("TRACE_KEY_ID"), _key("TRACE_PAYLOAD_KEY_B64"))
    store = PostgresTraceBuffer(
        _postgres_dsn(),
        cipher,
        capacity=int(os.environ.get("TRACE_BUFFER_CAPACITY", "10000")),
    )
    export_mode = os.environ.get("LANGSMITH_EXPORT_MODE", "direct")
    if export_mode not in {"direct", "operator_relay"}:
        raise RuntimeError("LANGSMITH_EXPORT_MODE is invalid")
    langsmith_exporter = (
        LangSmithExporter(
            _required("LANGSMITH_API_KEY"),
            project=_required("LANGSMITH_PROJECT"),
            endpoint=os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
            workspace_id=os.environ.get("LANGSMITH_WORKSPACE_ID"),
        )
        if export_mode == "direct"
        else RelayOnlyExporter()
    )
    exporters = {
        DeliverySink.LANGSMITH: langsmith_exporter,
        DeliverySink.OTLP: OTLPHTTPExporter(_required("OTLP_HTTP_ENDPOINT")),
        DeliverySink.ARCHIVE: EvidenceArchiveExporter(
            _required("MINIO_ENDPOINT"),
            S3Credentials(_required("MINIO_ACCESS_KEY"), _required("MINIO_SECRET_KEY")),
            bucket=os.environ.get("TRACE_EVIDENCE_BUCKET", "faultwitness-evidence"),
        ),
    }
    automatic_sinks = (
        tuple(DeliverySink)
        if export_mode == "direct"
        else (DeliverySink.OTLP, DeliverySink.ARCHIVE)
    )
    return TraceExportService(
        store,
        TraceSanitizer(_key("TRACE_REFERENCE_KEY_B64")),
        exporters,
        automatic_sinks=automatic_sinks,
    )


class RelayOnlyExporter:
    async def export(self, trace: Any) -> dict[str, Any]:
        raise ExportFailure("langsmith_operator_relay_required", retryable=True)


def _postgres_dsn() -> str:
    configured = os.environ.get("DATABASE_DSN")
    if configured:
        return configured
    user = quote(_required("POSTGRES_USER"), safe="")
    password = quote(_required("POSTGRES_PASSWORD"), safe="")
    database = quote(_required("POSTGRES_DB"), safe="")
    return f"postgresql://{user}:{password}@postgres.fw-data.svc.cluster.local:5432/{database}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = _build_service()
    await service.store.connect()
    stop = asyncio.Event()
    drain_task = asyncio.create_task(run_drain_loop(service, stop))
    app.state.trace_service = service
    app.state.drain_stop = stop
    try:
        yield
    finally:
        stop.set()
        await drain_task
        await service.store.close()


app = FastAPI(
    title="FaultWitness Trace Service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def _authorize(x_faultwitness_ingest_token: Annotated[str | None, Header()] = None) -> None:
    expected = _required("TRACE_INGEST_TOKEN")
    if x_faultwitness_ingest_token is None or not hmac.compare_digest(
        x_faultwitness_ingest_token, expected
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credential")


def _service(request: Request) -> TraceExportService:
    return request.app.state.trace_service


def _status(values: dict[str, int]) -> TraceStatus:
    return TraceStatus(
        pending_traces=values["traces"],
        pending_langsmith=values["langsmith"],
        pending_otlp=values["otlp"],
        pending_archive=values["archive"],
    )


def parse_trace_envelope(raw: bytes) -> TraceEnvelope:
    if not raw or len(raw) > 1_048_576:
        raise ValueError("trace request body is empty or too large")
    try:
        return TraceEnvelope.model_validate_json(raw)
    except ValidationError as error:
        raise ValueError("trace request does not match the strict contract") from error


@app.get("/health/ready")
async def ready(request: Request) -> dict[str, str]:
    await _service(request).store.status()
    return {"status": "ready"}


@app.post(
    "/internal/v1/traces",
    response_model=TraceAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_authorize)],
)
async def ingest_trace(request: Request) -> TraceAccepted:
    try:
        envelope = parse_trace_envelope(await request.body())
        trace, created = await _service(request).ingest(envelope)
    except (SanitizationRejected, ValueError) as error:
        raise HTTPException(status_code=422, detail="trace rejected by sanitizer") from error
    except BufferFull as error:
        raise HTTPException(status_code=503, detail="trace buffer is full") from error
    return TraceAccepted(
        trace_ref=trace.trace_ref,
        langsmith_trace_id=next(
            span.remote_id for span in trace.spans if span.parent_span_ref is None
        ),
        otlp_trace_id=trace.otlp_trace_id,
        payload_digest=trace.payload_digest,
        duplicate=not created,
    )


@app.get(
    "/internal/v1/status",
    response_model=TraceStatus,
    dependencies=[Depends(_authorize)],
)
async def trace_status(request: Request) -> TraceStatus:
    return _status(await _service(request).store.status())


@app.post(
    "/internal/v1/drain",
    response_model=DrainResult,
    dependencies=[Depends(_authorize)],
)
async def drain(request: Request) -> DrainResult:
    service = _service(request)
    result = await service.drain_until_idle()
    return DrainResult(
        acknowledged=result["acked"],
        retried=result["retried"],
        status=_status(await service.store.status()),
    )


@app.post(
    "/internal/v1/relay/langsmith/claim",
    response_model=None,
    dependencies=[Depends(_authorize)],
)
async def relay_claim(request: Request) -> Response | dict[str, Any]:
    service = _service(request)
    if DeliverySink.LANGSMITH in service.automatic_sinks:
        raise HTTPException(status_code=409, detail="operator relay is not enabled")
    deliveries = await service.store.claim(DeliverySink.LANGSMITH, limit=1, lease_seconds=120)
    if not deliveries:
        return Response(status_code=204)
    return deliveries[0].trace.document()


@app.post(
    "/internal/v1/relay/langsmith/{trace_ref}/ack",
    status_code=204,
    dependencies=[Depends(_authorize)],
)
async def relay_ack(trace_ref: str, request: Request) -> Response:
    if len(trace_ref) != 24 or any(character not in "0123456789abcdef" for character in trace_ref):
        raise HTTPException(status_code=422, detail="invalid trace reference")
    await _service(request).store.acknowledge(trace_ref, DeliverySink.LANGSMITH)
    return Response(status_code=204)


@app.post(
    "/internal/v1/relay/langsmith/{trace_ref}/retry",
    status_code=204,
    dependencies=[Depends(_authorize)],
)
async def relay_retry(trace_ref: str, request: Request) -> Response:
    if len(trace_ref) != 24 or any(character not in "0123456789abcdef" for character in trace_ref):
        raise HTTPException(status_code=422, detail="invalid trace reference")
    await _service(request).store.retry(trace_ref, DeliverySink.LANGSMITH, "operator_relay_failure")
    return Response(status_code=204)
