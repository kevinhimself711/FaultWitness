# ruff: noqa: B008 -- FastAPI dependency injection uses callable defaults.

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, ValidationError

from faultwitness.contracts.models import (
    AgentBudget,
    CorrelationId,
    ModelFamily,
    ModelMessage,
    ModelRequest,
)
from faultwitness.identity.oidc import (
    AuthenticatedPrincipal,
    AuthenticationError,
    OIDCAuthenticator,
    OIDCSettings,
)
from faultwitness.models.catalog import CapabilityCatalog
from faultwitness.models.channel import ModelChannel, OpenAICompatibleChannel
from faultwitness.models.gateway import ModelGateway
from faultwitness.models.types import ChannelName, ModelCapability, ModelFailure
from faultwitness.models.types import StrictModel as ModelBoundary

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class Authenticator(Protocol):
    async def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal: ...


class ModelInvoke(ModelBoundary):
    correlation_id: CorrelationId
    model_family: ModelFamily
    messages: tuple[ModelMessage, ...] = Field(min_length=1, max_length=64)
    target_json_schema: dict[str, Any] | None = None
    tool_schemas: tuple[dict[str, Any], ...] = ()


def _id(prefix: str) -> str:
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(26))


def _authenticator() -> OIDCAuthenticator:
    required = {
        name: os.environ.get(name)
        for name in ("FW_OIDC_ISSUER", "FW_OIDC_AUDIENCE", "FW_OIDC_JWKS_URL")
    }
    if any(not value for value in required.values()):
        raise RuntimeError("OIDC environment is incomplete")
    return OIDCAuthenticator(
        OIDCSettings(
            issuer=required["FW_OIDC_ISSUER"] or "",
            audience=required["FW_OIDC_AUDIENCE"] or "",
            jwks_url=required["FW_OIDC_JWKS_URL"] or "",
        )
    )


def create_app(
    *,
    catalog: CapabilityCatalog,
    channels: dict[ChannelName, ModelChannel],
    authenticator: Authenticator,
) -> FastAPI:
    gateway = ModelGateway(catalog=catalog, channels=channels)
    app = FastAPI(title="FaultWitness Model Gateway", version="1.0.0")

    async def principal(
        request: Request, authorization: str | None = Header(default=None)
    ) -> AuthenticatedPrincipal:
        if any(
            name in request.headers
            for name in ("x-tenant-id", "x-user-id", "x-roles", "x-faultwitness-tenant")
        ):
            raise HTTPException(status_code=403, detail="identity injection headers are forbidden")
        try:
            identity = await authenticator.authenticate(authorization)
        except AuthenticationError:
            raise HTTPException(status_code=401, detail="OIDC token validation failed") from None
        if not identity.roles.intersection({"operator", "admin"}):
            raise HTTPException(status_code=403, detail="operator role is required")
        return identity

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready", "catalog_version": catalog.catalog_version}

    @app.post("/internal/v1/models/complete")
    async def complete(
        request: Request,
        identity: AuthenticatedPrincipal = Depends(principal),
    ) -> JSONResponse:
        try:
            body = ModelInvoke.model_validate_json(await request.body())
            primary = catalog.candidates(body.model_family, _capability(body))[0]
            model_request = ModelRequest(
                request_id=_id("mreq_"),
                tenant_id=identity.tenant_id,
                correlation_id=body.correlation_id,
                model_family=body.model_family,
                model_id=primary.model_id,
                messages=body.messages,
                target_json_schema=body.target_json_schema,
                tool_schemas=body.tool_schemas,
                stream=False,
                budget=AgentBudget(
                    deadline=datetime.now(UTC) + timedelta(minutes=3),
                    max_steps=1,
                    max_model_calls=3,
                    max_tokens=4096,
                    max_cost_usd=5,
                ),
            )
            response = await gateway.complete(model_request)
        except ModelFailure as error:
            status = 429 if error.retryable else 502
            return JSONResponse(
                {"error": {"code": error.code.value, "retryable": error.retryable}},
                status_code=status,
            )
        except ValidationError:
            return JSONResponse(
                {"error": {"code": "invalid_request", "retryable": False}},
                status_code=400,
            )
        return JSONResponse(response.model_dump(mode="json"))

    return app


def _capability(body: ModelInvoke) -> ModelCapability:
    if body.tool_schemas:
        return ModelCapability.FORCED_TOOL
    if body.target_json_schema is not None:
        return ModelCapability.STRUCTURED
    return ModelCapability.COMPLETE


def app_from_environment() -> FastAPI:
    catalog = CapabilityCatalog.load(
        Path(os.environ.get("MODEL_CATALOG_PATH", "/opt/faultwitness/config/models/catalog.yaml"))
    )
    credential = os.environ.get("BAILIAN_API_KEY")
    if not credential:
        raise RuntimeError("Bailian credential is absent")
    channel = OpenAICompatibleChannel(
        base_url=os.environ.get(
            "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        credential=credential,
        timeout_seconds=120,
    )
    return create_app(
        catalog=catalog,
        channels={ChannelName.BAILIAN: channel},
        authenticator=_authenticator(),
    )


if all(
    os.environ.get(name)
    for name in (
        "BAILIAN_API_KEY",
        "FW_OIDC_ISSUER",
        "FW_OIDC_AUDIENCE",
        "FW_OIDC_JWKS_URL",
    )
):
    app = app_from_environment()
else:
    app = FastAPI(title="Unconfigured FaultWitness Model Gateway")

    @app.get("/health/ready", status_code=503)
    async def unconfigured() -> dict[str, str]:
        return {"status": "unconfigured"}
