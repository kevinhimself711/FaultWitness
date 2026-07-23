from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import (
    _listener_scope,
    compare_docker_baselines,
    render_core_installer,
    validate_preinstall_baseline,
)


def test_privileged_runner_separates_password_from_script(monkeypatch) -> None:
    import faultwitness_dev.infra as infra

    class Bundle:
        @property
        def server_password(self) -> str:
            return "secret-value"

    captured = {}

    monkeypatch.setattr(infra, "_remote_arguments", lambda _paths: (Bundle(), ["ssh"]))
    monkeypatch.setattr(infra.BootstrapPaths, "defaults", lambda: object())

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["input"] = kwargs["input"]
        return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(infra.subprocess, "run", fake_run)
    assert infra.run_remote_script("true\n", privileged=True) == "ok"
    assert captured["arguments"][-1].startswith("sudo -k -S -p '' /bin/sh -c ")
    assert "dHJ1ZQo=" in captured["arguments"][-1]
    assert captured["input"] == "secret-value\n"


def baseline() -> dict:
    return {
        "architecture": "x86_64",
        "kernel_release": "5.15.0-139-generic",
        "cgroup_version": 1,
        "k3s_installed": False,
        "reserved_cidr_overlap": False,
        "docker": {"containers": [{"running": True, "health": "healthy"}]},
    }


def test_preinstall_baseline_accepts_frozen_host_profile() -> None:
    validate_preinstall_baseline(baseline())


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("cgroup_version", 2, "cgroup_v1"),
        ("k3s_installed", True, "k3s_absent"),
        ("reserved_cidr_overlap", True, "reserved_cidrs_free"),
    ],
)
def test_preinstall_baseline_fails_closed(field: str, value: object, failure: str) -> None:
    document = baseline()
    document[field] = value
    with pytest.raises(GovernanceError, match=failure):
        validate_preinstall_baseline(document)


def test_preinstall_baseline_rejects_unhealthy_docker() -> None:
    document = baseline()
    document["docker"]["containers"][0]["health"] = "unhealthy"
    with pytest.raises(GovernanceError, match="docker_healthy"):
        validate_preinstall_baseline(document)


def test_core_installer_resolves_only_locked_artifacts() -> None:
    script = render_core_installer(Path(__file__).parents[2])
    assert "@K3S_" not in script
    assert "v1.34.9+k3s1" in script
    assert "v4.2.3" in script
    assert "curl | sh" not in script
    assert "bind-address: 127.0.0.1" not in script
    assert "bind-address: $node_ip" in script
    assert "FW_INSTALL_FAILED step=private-node-ip" in script


def test_docker_baseline_comparison_detects_restart_drift() -> None:
    before = {
        "docker": {
            "containers": [{"name": "existing", "restart_count": 0}],
            "networks": [{"name": "bridge", "id": "one"}],
        }
    }
    after = json.loads(json.dumps(before))
    after["docker"]["containers"][0]["restart_count"] = 1
    with pytest.raises(GovernanceError, match="baseline changed"):
        compare_docker_baselines(before, after)


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("127.0.0.1:6443", ("loopback", 6443)),
        ("[::1]:6443", ("loopback", 6443)),
        ("0.0.0.0:10250", ("wildcard", 10250)),
        ("*:8472", ("wildcard", 8472)),
        ("10.0.0.10:2379", ("private", 2379)),
        ("192.0.2.10:10250", ("private", 10250)),
        ("8.8.8.8:10250", ("public", 10250)),
    ],
)
def test_listener_scope(endpoint: str, expected: tuple[str, int]) -> None:
    assert _listener_scope(endpoint) == expected
