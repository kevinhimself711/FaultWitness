from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.observability_deploy import deploy_trace_service, inspect_trace_service


@pytest.mark.parametrize("candidate", ["", "abc", "A" * 40, "0" * 39])
def test_trace_deploy_rejects_invalid_candidate(candidate: str) -> None:
    with pytest.raises(GovernanceError, match="candidate SHA"):
        deploy_trace_service(Path.cwd(), candidate)
    with pytest.raises(GovernanceError, match="candidate SHA"):
        inspect_trace_service(candidate)


def test_trace_container_and_manifest_are_private_and_non_root() -> None:
    dockerfile = Path("deploy/observability/Dockerfile").read_text(encoding="utf-8")
    assert "@sha256:" in dockerfile.splitlines()[0]
    assert "USER 10001:10001" in dockerfile
    assert "--no-access-log" in dockerfile
