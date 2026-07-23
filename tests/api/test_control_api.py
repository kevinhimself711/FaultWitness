from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from faultwitness.api.app import create_app
from faultwitness.identity.oidc import AuthenticatedPrincipal, AuthenticationError


class FakeAuthenticator:
    async def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError("invalid token")
        token = authorization.removeprefix("Bearer ")
        tenant, role = token.split(":")
        return AuthenticatedPrincipal(
            tenant_id=tenant,
            user_id=f"user-{tenant}",
            roles=frozenset({role}),
            token_id=f"token-{tenant}",
            expires_at=int(time.time()),
        )


def incident_body() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "source": "synthetic-alert",
        "environment_id": "env_test",
        "service_scope": ["svc_api"],
        "time_window": {
            "start": (now - timedelta(minutes=5)).isoformat(),
            "end": now.isoformat(),
        },
        "symptom_summary": "synthetic latency increase",
        "mode": "diagnosis_only",
        "budget": {
            "deadline": (now + timedelta(minutes=10)).isoformat(),
            "max_steps": 10,
            "max_model_calls": 3,
            "max_tokens": 2000,
            "max_cost_usd": 1.0,
        },
    }


def headers(tenant: str = "tenant-a", role: str = "operator") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant}:{role}",
        "Idempotency-Key": "idempotency-key-0001",
    }


def test_eight_frozen_paths_are_exposed() -> None:
    app = create_app(authenticator=FakeAuthenticator())
    document = app.openapi()
    assert set(document["paths"]) == {
        "/v1/incidents",
        "/v1/incidents/{incident_id}",
        "/v1/incidents/{incident_id}/events",
        "/v1/incidents/{incident_id}/approvals",
        "/v1/incidents/{incident_id}/cancel",
        "/v1/incidents/{incident_id}/feedback",
        "/v1/tools",
        "/v1/skills",
    }
    assert {
        operation["operationId"]
        for path in document["paths"].values()
        for operation in path.values()
    } == {
        "createIncident",
        "getIncident",
        "streamIncidentEvents",
        "decideApproval",
        "cancelIncident",
        "recordIncidentFeedback",
        "listTools",
        "listSkills",
    }


def test_create_is_tenant_scoped_and_idempotent() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    body = incident_body()
    created = client.post("/v1/incidents", headers=headers(), json=body)
    assert created.status_code == 201
    incident_id = created.json()["incident_id"]

    repeated = client.post("/v1/incidents", headers=headers(), json=body)
    assert repeated.status_code == 200
    assert repeated.json()["incident_id"] == incident_id
    assert (
        client.get(
            f"/v1/incidents/{incident_id}", headers={"Authorization": "Bearer tenant-b:viewer"}
        ).status_code
        == 404
    )

    changed = incident_body()
    changed["symptom_summary"] = "different"
    conflict = client.post("/v1/incidents", headers=headers(), json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "ERR-CONFLICT"


def test_identity_injection_and_role_bypass_fail_closed() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    injected = incident_body() | {"tenant_id": "tenant-b"}
    assert client.post("/v1/incidents", headers=headers(), json=injected).status_code == 400
    injection_headers = headers() | {"X-Tenant-ID": "tenant-b"}
    assert (
        client.post("/v1/incidents", headers=injection_headers, json=incident_body()).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/incidents", headers=headers(role="viewer"), json=incident_body()
        ).status_code
        == 403
    )
    assert client.get("/v1/tools").status_code == 401


def test_cancel_feedback_empty_capabilities_and_false_approval() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    created = client.post("/v1/incidents", headers=headers(), json=incident_body()).json()
    incident_id = created["incident_id"]
    assert client.get("/v1/tools", headers={"Authorization": "Bearer tenant-a:viewer"}).json() == []
    assert (
        client.get("/v1/skills", headers={"Authorization": "Bearer tenant-a:viewer"}).json() == []
    )

    feedback = client.post(
        f"/v1/incidents/{incident_id}/feedback",
        headers=headers() | {"Idempotency-Key": "idempotency-feedback"},
        json={"rating": 4, "expected_state_version": 0},
    )
    assert feedback.status_code == 202
    approval = client.post(
        f"/v1/incidents/{incident_id}/approvals",
        headers=headers(role="approver") | {"Idempotency-Key": "idempotency-approval"},
        json={
            "action_id": "act_missing",
            "action_digest": "a" * 64,
            "decision": "approve",
            "expected_state_version": 0,
        },
    )
    assert approval.status_code == 409

    cancelled = client.post(
        f"/v1/incidents/{incident_id}/cancel",
        headers=headers() | {"Idempotency-Key": "idempotency-cancel-1"},
        json={"expected_state_version": 0},
    )
    assert cancelled.status_code == 202
    assert cancelled.json()["state"] == "CANCELLED"


def test_sse_replays_monotonic_events_and_rejects_future_cursor() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    incident_id = client.post("/v1/incidents", headers=headers(), json=incident_body()).json()[
        "incident_id"
    ]
    auth = {"Authorization": "Bearer tenant-a:viewer"}
    with client.stream("GET", f"/v1/incidents/{incident_id}/events", headers=auth) as response:
        assert response.status_code == 200
        first = next(response.iter_text())
        assert "id: 1" in first
        assert "EVT-INCIDENT-CREATED" in first
    invalid = client.get(
        f"/v1/incidents/{incident_id}/events", headers=auth | {"Last-Event-ID": "999"}
    )
    assert invalid.status_code == 400
