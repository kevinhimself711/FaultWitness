from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from faultwitness.contracts.models import ModelUsage
from faultwitness.identity.oidc import AuthenticatedPrincipal
from faultwitness.models.catalog import CapabilityCatalog
from faultwitness.models.channel import ChannelResult
from faultwitness.models.server import create_app
from faultwitness.models.types import ChannelName

ROOT = Path(__file__).resolve().parents[2]
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class Auth:
    async def authenticate(self, authorization):
        if authorization != "Bearer valid":
            from faultwitness.identity.oidc import AuthenticationError

            raise AuthenticationError("invalid")
        return AuthenticatedPrincipal(
            tenant_id="ten_" + ULID,
            user_id="usr_" + ULID,
            roles=frozenset({"operator"}),
            token_id="tok_" + ULID,
            expires_at=int(datetime.now(UTC).timestamp()) + 60,
        )


class Channel:
    async def complete(self, request, profile, route):
        assert request.tenant_id == "ten_" + ULID
        return ChannelResult(
            response_id="response-1",
            resolved_model=profile.model_id,
            content="OK",
            tool_calls=(),
            finish_reason="stop",
            usage=ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2),
        )


def app():
    return create_app(
        catalog=CapabilityCatalog.load(ROOT / "config/models/catalog.yaml"),
        channels={ChannelName.BAILIAN: Channel()},
        authenticator=Auth(),
    )


def test_model_service_derives_tenant_from_authenticated_context() -> None:
    response = TestClient(app()).post(
        "/internal/v1/models/complete",
        headers={"Authorization": "Bearer valid"},
        json={
            "correlation_id": "corr_" + ULID,
            "model_family": "qwen",
            "messages": [{"role": "user", "content": "reply OK"}],
            "target_json_schema": None,
            "tool_schemas": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["route"]["resolved_model"] == "qwen3.7-plus-2026-05-26"


def test_model_service_rejects_identity_injection() -> None:
    response = TestClient(app()).post(
        "/internal/v1/models/complete",
        headers={"Authorization": "Bearer valid", "X-Tenant-ID": "forged"},
        json={
            "correlation_id": "corr_" + ULID,
            "model_family": "qwen",
            "messages": [{"role": "user", "content": "reply OK"}],
        },
    )
    assert response.status_code == 403
