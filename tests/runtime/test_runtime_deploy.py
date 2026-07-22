from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.runtime_deploy import deploy_runtime_schema, inspect_runtime_schema


@pytest.mark.parametrize("candidate", ["", "abc", "A" * 40, "0" * 39])
def test_runtime_deploy_rejects_invalid_candidate(candidate: str) -> None:
    with pytest.raises(GovernanceError, match="candidate SHA"):
        deploy_runtime_schema(Path.cwd(), candidate)
    with pytest.raises(GovernanceError, match="candidate SHA"):
        inspect_runtime_schema(candidate)
