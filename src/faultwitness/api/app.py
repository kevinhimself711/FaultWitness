# ruff: noqa: B008 -- FastAPI declares dependency injection in callable defaults.

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from faultwitness.api.schemas import (
    ApprovalRequest,
    ApprovalResult,
    CancelRequest,
    ErrorEnvelope,
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
)
from faultwitness.identity.oidc import (
    AuthenticatedPrincipal,
    AuthenticationError,
    OIDCAuthenticator,
    OIDCSettings,
)


class Authenticator(Protocol):
    async def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal: ...


class APIError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


ROLE_SCOPES = {
    "viewer": frozenset({"read"}),
    "operator": frozenset({"read", "write"}),
    "approver": frozenset({"read", "approve"}),
    "admin": frozenset({"read", "write", "approve"}),
}


def create_app(
    *,
    store: Any | None = None,
    authenticator: Authenticator | None = None,
    lifespan: Any | None = None,
) -> FastAPI:
    incident_store = store or MemoryIncidentStore()
    auth = authenticator or _authenticator_from_environment()
    app = FastAPI(title="FaultWitness Control API", version="1.0.0", lifespan=lifespan)
    app.state.store = incident_store

    @app.exception_handler(APIError)
    async def api_error(request: Request, error: APIError) -> JSONResponse:
        return _error_response(request, error.status, error.code, error.message, error.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return _error_response(
            request,
            400,
            "ERR-INVALID-REQUEST",
            "request does not conform to the public contract",
            details={"error_count": len(error.errors())},
        )

    async def principal(
        request: Request, authorization: str | None = Header(default=None)
    ) -> AuthenticatedPrincipal:
        if any(
            name in request.headers
            for name in ("x-tenant-id", "x-user-id", "x-roles", "x-faultwitness-tenant")
        ):
            raise APIError(403, "ERR-FORBIDDEN", "identity injection headers are forbidden")
        try:
            return await auth.authenticate(authorization)
        except AuthenticationError as error:
            raise APIError(401, "ERR-UNAUTHENTICATED", str(error)) from error

    def require(scope: str):
        async def dependency(
            identity: AuthenticatedPrincipal = Depends(principal),
        ) -> AuthenticatedPrincipal:
            granted = set().union(*(ROLE_SCOPES.get(role, frozenset()) for role in identity.roles))
            if scope not in granted:
                raise APIError(403, "ERR-FORBIDDEN", f"{scope} role scope is required")
            return identity

        return dependency

    async def idempotency(
        value: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> str:
        if value is None or not 16 <= len(value) <= 128:
            raise APIError(400, "ERR-INVALID-REQUEST", "valid Idempotency-Key is required")
        return value

    @app.post(
        "/v1/incidents",
        operation_id="createIncident",
        response_model=IncidentSnapshot,
        responses={200: {"model": IncidentSnapshot}},
        status_code=201,
    )
    async def create_incident(
        body: IncidentCreate,
        request: Request,
        identity: AuthenticatedPrincipal = Depends(require("write")),
        key: str = Depends(idempotency),
    ) -> JSONResponse:
        try:
            snapshot, created = await incident_store.create(identity.tenant_id, key, body)
        except IdempotencyConflict as error:
            raise APIError(409, "ERR-CONFLICT", str(error)) from error
        return JSONResponse(
            snapshot.model_dump(mode="json"),
            status_code=201 if created else 200,
            headers={"X-Correlation-ID": _correlation_id(request)},
        )

    @app.get(
        "/v1/incidents/{incident_id}",
        response_model=IncidentSnapshot,
        operation_id="getIncident",
    )
    async def get_incident(
        incident_id: str,
        identity: AuthenticatedPrincipal = Depends(require("read")),
    ) -> IncidentSnapshot:
        _incident_id(incident_id)
        try:
            return await incident_store.get(identity.tenant_id, incident_id)
        except IncidentNotFound as error:
            raise APIError(404, "ERR-NOT-FOUND", str(error)) from error

    @app.post(
        "/v1/incidents/{incident_id}/cancel",
        response_model=IncidentSnapshot,
        status_code=202,
        operation_id="cancelIncident",
    )
    async def cancel_incident(
        incident_id: str,
        body: CancelRequest,
        identity: AuthenticatedPrincipal = Depends(require("write")),
        key: str = Depends(idempotency),
    ) -> IncidentSnapshot:
        _incident_id(incident_id)
        try:
            return await incident_store.cancel(
                identity.tenant_id, incident_id, key, body.expected_state_version
            )
        except IncidentNotFound as error:
            raise APIError(404, "ERR-NOT-FOUND", str(error)) from error
        except (IdempotencyConflict, StateConflict) as error:
            raise APIError(409, "ERR-CONFLICT", str(error)) from error

    @app.post(
        "/v1/incidents/{incident_id}/feedback",
        response_model=FeedbackResult,
        status_code=202,
        operation_id="recordIncidentFeedback",
    )
    async def record_feedback(
        incident_id: str,
        body: FeedbackRequest,
        identity: AuthenticatedPrincipal = Depends(require("write")),
        key: str = Depends(idempotency),
    ) -> FeedbackResult:
        _incident_id(incident_id)
        try:
            return await incident_store.feedback(
                identity.tenant_id, identity.user_id, incident_id, key, body
            )
        except IncidentNotFound as error:
            raise APIError(404, "ERR-NOT-FOUND", str(error)) from error
        except (IdempotencyConflict, StateConflict) as error:
            raise APIError(409, "ERR-CONFLICT", str(error)) from error

    @app.post(
        "/v1/incidents/{incident_id}/approvals",
        response_model=ApprovalResult,
        operation_id="decideApproval",
    )
    async def decide_approval(
        incident_id: str,
        body: ApprovalRequest,
        identity: AuthenticatedPrincipal = Depends(require("approve")),
        key: str = Depends(idempotency),
    ) -> ApprovalResult:
        _incident_id(incident_id)
        try:
            return await incident_store.approval(identity.tenant_id, incident_id, key, body)
        except IncidentNotFound as error:
            raise APIError(404, "ERR-NOT-FOUND", str(error)) from error
        except (IdempotencyConflict, StateConflict, ApprovalConflict) as error:
            raise APIError(409, "ERR-CONFLICT", str(error)) from error

    @app.get("/v1/tools", response_model=list[dict[str, object]], operation_id="listTools")
    async def list_tools(
        _identity: AuthenticatedPrincipal = Depends(require("read")),
    ) -> list[dict[str, object]]:
        return []

    @app.get("/v1/skills", response_model=list[dict[str, object]], operation_id="listSkills")
    async def list_skills(
        _identity: AuthenticatedPrincipal = Depends(require("read")),
    ) -> list[dict[str, object]]:
        return []

    @app.get("/v1/incidents/{incident_id}/events", operation_id="streamIncidentEvents")
    async def stream_incident_events(
        request: Request,
        incident_id: str,
        identity: AuthenticatedPrincipal = Depends(require("read")),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        _incident_id(incident_id)
        subscriber = None
        try:
            subscriber = await incident_store.subscribe(identity.tenant_id, incident_id)
            replay = await incident_store.replay(identity.tenant_id, incident_id, last_event_id)
        except IncidentNotFound as error:
            raise APIError(404, "ERR-NOT-FOUND", str(error)) from error
        except RetentionGap as gap:
            if subscriber is not None:
                await incident_store.unsubscribe(identity.tenant_id, incident_id, subscriber)
            earliest_cursor = gap.earliest_cursor

            async def gap_stream() -> AsyncIterator[str]:
                yield _sse_control(
                    "retention_gap",
                    last_event_id or "0",
                    {"earliest_cursor": earliest_cursor, "recoverable": True},
                )

            return StreamingResponse(gap_stream(), media_type="text/event-stream")
        except CursorError as error:
            if subscriber is not None:
                await incident_store.unsubscribe(identity.tenant_id, incident_id, subscriber)
            raise APIError(400, "ERR-INVALID-REQUEST", str(error)) from error

        async def event_stream() -> AsyncIterator[str]:
            delivered = int(last_event_id or 0)
            try:
                for event in replay:
                    delivered = event.sequence
                    yield _sse_event(event)
                while time.time() < identity.expires_at and not await request.is_disconnected():
                    if subscriber.closed:
                        yield _sse_control(
                            "slow_consumer",
                            str(delivered),
                            {"recoverable": True, "resume_from": str(delivered)},
                        )
                        break
                    try:
                        event = await asyncio.wait_for(subscriber.queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if event.sequence <= delivered:
                        continue
                    delivered = event.sequence
                    yield _sse_event(event)
            finally:
                await incident_store.unsubscribe(identity.tenant_id, incident_id, subscriber)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _authenticator_from_environment() -> OIDCAuthenticator:
    required = {
        name: os.environ.get(name)
        for name in ("FW_OIDC_ISSUER", "FW_OIDC_AUDIENCE", "FW_OIDC_JWKS_URL")
    }
    if any(not value for value in required.values()):
        raise RuntimeError("OIDC issuer, audience, and JWKS URL must be configured")
    return OIDCAuthenticator(
        OIDCSettings(
            issuer=required["FW_OIDC_ISSUER"] or "",
            audience=required["FW_OIDC_AUDIENCE"] or "",
            jwks_url=required["FW_OIDC_JWKS_URL"] or "",
        )
    )


def _incident_id(value: str) -> None:
    if not value.startswith("inc_") or len(value) < 5:
        raise APIError(400, "ERR-INVALID-REQUEST", "incident_id is malformed")


def _correlation_id(request: Request) -> str:
    supplied = request.headers.get("x-correlation-id")
    return supplied if supplied and len(supplied) <= 128 else "corr_" + uuid.uuid4().hex


def _error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        code=code,
        message=message,
        retryable=retryable,
        correlation_id=_correlation_id(request),
        details=details or {},
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


def _sse_event(event: IncidentEvent) -> str:
    data = {
        "event_id": event.event_id,
        "incident_id": event.incident_id,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": event.payload,
    }
    serialized = json.dumps(data, separators=(",", ":"))
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {serialized}\n\n"


def _sse_control(kind: str, cursor: str, details: dict[str, object]) -> str:
    body = {"kind": kind, "cursor": cursor, "details": details}
    return f"event: control.{kind}\ndata: {json.dumps(body, separators=(',', ':'))}\n\n"
