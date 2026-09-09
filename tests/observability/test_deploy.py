import inspect
from pathlib import Path

from faultwitness_dev.observability_deploy import deploy_trace_service, inspect_trace_service


def test_trace_deploy_uses_observed_provenance_without_binding() -> None:
    source = inspect.getsource(deploy_trace_service) + inspect.getsource(inspect_trace_service)
    assert "producer_provenance" in source
    assert "fw-trace-candidate" not in source


def test_trace_container_and_manifest_are_private_and_non_root() -> None:
    dockerfile = Path("deploy/observability/Dockerfile").read_text(encoding="utf-8")
    assert "@sha256:" in dockerfile.splitlines()[0]
    assert "USER 10001:10001" in dockerfile
    assert "--no-access-log" in dockerfile


def test_trace_deploy_rollout_has_no_preset_wall_clock_kill() -> None:
    source = inspect.getsource(deploy_trace_service)
    assert "rollout status deployment/trace-service --timeout" not in source
