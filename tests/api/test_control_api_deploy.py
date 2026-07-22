import json
from pathlib import Path

import pytest

from faultwitness_dev.control_api_deploy import (
    deploy_control_api,
    inspect_control_api,
    inspect_keycloak_realm,
    provision_keycloak_realm,
    run_control_api_smoke,
)
from faultwitness_dev.errors import GovernanceError


@pytest.mark.parametrize("candidate", ["", "abc", "A" * 40, "0" * 39])
def test_control_api_deploy_rejects_invalid_candidate(candidate: str) -> None:
    with pytest.raises(GovernanceError, match="candidate SHA"):
        deploy_control_api(Path.cwd(), candidate)
    with pytest.raises(GovernanceError, match="candidate SHA"):
        inspect_control_api(candidate)
    with pytest.raises(GovernanceError, match="candidate SHA"):
        provision_keycloak_realm(Path.cwd(), candidate)
    with pytest.raises(GovernanceError, match="candidate SHA"):
        inspect_keycloak_realm(candidate)
    with pytest.raises(GovernanceError, match="candidate SHA"):
        run_control_api_smoke(candidate)


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
