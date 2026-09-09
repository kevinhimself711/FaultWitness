from __future__ import annotations

import hashlib
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faultwitness.api.app import create_app
from faultwitness.identity.oidc import AuthenticatedPrincipal, AuthenticationError
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.experiment import ExperimentRunner, ExperimentUnit, TrialJournal

ROOT = Path(__file__).resolve().parents[2]


class FakeAuthenticator:
    async def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError("invalid token")
        tenant, role = authorization.removeprefix("Bearer ").split(":")
        return AuthenticatedPrincipal(
            tenant_id=tenant,
            user_id=f"user-{tenant}",
            roles=frozenset({role}),
            token_id=f"token-{tenant}",
            expires_at=int(time.time()),
        )


def _incident_body() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "source": "governance-v2-proof",
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


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer tenant-a:operator",
        "Idempotency-Key": "governance-v2-idempotency",
    }


def _tracked_tree_fingerprint() -> str:
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "."],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(diff).hexdigest()


def test_application_tenant_identity_override_fails_closed() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    body = _incident_body() | {"tenant_id": "tenant-b"}
    assert client.post("/v1/incidents", headers=_headers(), json=body).status_code == 400
    headers = _headers() | {"X-Tenant-ID": "tenant-b"}
    assert client.post("/v1/incidents", headers=headers, json=_incident_body()).status_code == 403


def test_application_idempotency_digest_conflict_fails_closed() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    first = client.post("/v1/incidents", headers=_headers(), json=_incident_body())
    assert first.status_code == 201
    changed = _incident_body()
    changed["symptom_summary"] = "different semantic request"
    conflict = client.post("/v1/incidents", headers=_headers(), json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "ERR-CONFLICT"


def test_application_direct_debug_campaign_uses_one_journal_unit(tmp_path: Path) -> None:
    before = _tracked_tree_fingerprint()
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    unit = ExperimentUnit(
        "application-request",
        ("request_builder",),
        (),
        "tenant-create-contract",
    )
    journal = TrialJournal(tmp_path)

    def broken(_execution):  # type: ignore[no-untyped-def]
        response = client.post(
            "/v1/incidents",
            headers=_headers() | {"X-Tenant-ID": "tenant-b"},
            json=_incident_body(),
        )
        assert response.status_code == 403
        return {
            "status": "metric_fail",
            "payload": {"root_cause": "cross-tenant header", "observed": 403},
        }

    failed = ExperimentRunner(
        (unit,), journal, {"request_builder": "mutant-header"}, producer_sha="1" * 40
    ).run({unit.unit_id: broken})
    assert failed.records[0]["status"] == "metric_fail"
    with pytest.raises(GovernanceError, match="cannot retry unchanged"):
        ExperimentRunner(
            (unit,),
            journal,
            {"request_builder": "mutant-header"},
            producer_sha="2" * 40,
        ).run({unit.unit_id: broken})

    def fixed(_execution):  # type: ignore[no-untyped-def]
        headers = _headers() | {"Idempotency-Key": "governance-v2-fixed"}
        created = client.post("/v1/incidents", headers=headers, json=_incident_body())
        body_override = client.post(
            "/v1/incidents",
            headers=_headers() | {"Idempotency-Key": "governance-v2-body-override"},
            json=_incident_body() | {"tenant_id": "tenant-b"},
        )
        changed = _incident_body()
        changed["symptom_summary"] = "different semantic request"
        conflict = client.post("/v1/incidents", headers=headers, json=changed)
        observed = {
            "created": created.status_code,
            "body_override": body_override.status_code,
            "idempotency_conflict": conflict.status_code,
        }
        assert observed == {
            "created": 201,
            "body_override": 400,
            "idempotency_conflict": 409,
        }
        return {"status": "pass", "payload": observed}

    repaired = ExperimentRunner(
        (unit,), journal, {"request_builder": "fixed"}, producer_sha="3" * 40
    ).run({unit.unit_id: fixed})
    assert repaired.executed_units == (unit.unit_id,)
    assert journal.read(unit.unit_id)["execution_attempt"] == 2  # type: ignore[index]
    assert _tracked_tree_fingerprint() == before
