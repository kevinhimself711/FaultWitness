import inspect
import json
from pathlib import Path

from faultwitness_dev.control_api_deploy import (
    deploy_control_api,
    inspect_control_api,
    inspect_keycloak_realm,
    provision_keycloak_realm,
    run_control_api_smoke,
    run_keycloak_outage_smoke,
)


def test_control_api_deploy_has_no_head_binding_or_orchestration_timeout() -> None:
    sources = "\n".join(
        inspect.getsource(function)
        for function in (
            deploy_control_api,
            inspect_control_api,
            provision_keycloak_realm,
            inspect_keycloak_realm,
            run_control_api_smoke,
            run_keycloak_outage_smoke,
        )
    )
    assert "producer_provenance" in sources
    assert "candidate-binding" not in sources
    assert "--timeout" not in sources
    assert "run_remote_script(script, privileged=True, timeout=" not in sources


def test_keycloak_outage_smoke_is_secret_safe_and_fail_closed() -> None:
    source = inspect.getsource(run_keycloak_outage_smoke)
    assert "cold_jwks_status" in source
    assert "unset token" in source
    assert 'state_write_attempted": False' in source
    assert 'echo "$token"' not in source
    assert 'printf "$token"' not in source


def test_control_api_container_is_pinned_and_non_root() -> None:
    dockerfile = Path("deploy/control-api/Dockerfile").read_text(encoding="utf-8")
    assert "@sha256:" in dockerfile.splitlines()[0]
    assert "USER 10001:10001" in dockerfile
    assert "--no-access-log" in dockerfile


def test_keycloak_realm_has_two_tenant_roles_without_credentials() -> None:
    realm = json.loads(Path("deploy/keycloak/faultwitness-realm.json").read_text(encoding="utf-8"))
    assert realm["realm"] == "faultwitness"
    serialized = json.dumps(realm)
    for role in ("viewer", "operator", "approver", "admin"):
        assert f'"name": "{role}"' in serialized
    assert "users" not in realm
    assert all(
        "secret" not in client and "credentials" not in client for client in realm["clients"]
    )


def test_synthetic_oidc_tenants_use_frozen_typed_ids() -> None:
    source = Path("src/faultwitness_dev/control_api_deploy.py").read_text(encoding="utf-8")
    assert "tenant-a) tenant_ref=ten_01ARZ3NDEKTSV4RRFFQ69G5FAV" in source
    assert "tenant-b) tenant_ref=ten_01ARZ3NDEKTSV4RRFFQ69G5FAW" in source
    assert 'sh "$user" "$role" "$tenant_ref"' in source
