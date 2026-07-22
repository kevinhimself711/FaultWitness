from pathlib import Path

import pytest

from faultwitness_dev.control_api_deploy import deploy_control_api, inspect_control_api
from faultwitness_dev.errors import GovernanceError


@pytest.mark.parametrize("candidate", ["", "abc", "A" * 40, "0" * 39])
def test_control_api_deploy_rejects_invalid_candidate(candidate: str) -> None:
    with pytest.raises(GovernanceError, match="candidate SHA"):
        deploy_control_api(Path.cwd(), candidate)
    with pytest.raises(GovernanceError, match="candidate SHA"):
        inspect_control_api(candidate)


def test_control_api_container_is_pinned_and_non_root() -> None:
    dockerfile = Path("deploy/control-api/Dockerfile").read_text(encoding="utf-8")
    assert "@sha256:" in dockerfile.splitlines()[0]
    assert "USER 10001:10001" in dockerfile
    assert "--no-access-log" in dockerfile
