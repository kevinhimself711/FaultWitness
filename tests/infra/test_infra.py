from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import (
    _listener_scope,
    _remote_process,
    compare_docker_baselines,
    render_core_installer,
    validate_preinstall_baseline,
)


def test_remote_process_preserves_lf_bytes_with_real_child() -> None:
    payload = "set -eu\nprintf ok\n"
    result = _remote_process(
        subprocess.run,
        [sys.executable, "-c"],
        "import sys; print(sys.stdin.buffer.read().hex())",
        payload,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == payload.encode("utf-8").hex()
    assert "0d0a" not in result.stdout


def test_privileged_runner_uses_bounded_arguments_and_separate_channels(monkeypatch) -> None:
    import faultwitness_dev.infra as infra

    class Bundle:
        @property
        def server_password(self) -> str:
            return "secret-value"

    captured = []

    monkeypatch.setattr(infra, "_remote_arguments", lambda _paths: (Bundle(), ["ssh"]))
    monkeypatch.setattr(infra.BootstrapPaths, "defaults", lambda: object())

    responses = iter(
        [
            (0, "/tmp/faultwitness-remote.A1b2C3\n", ""),
            (0, "ok", ""),
            (0, "", ""),
        ]
    )

    def fake_run(arguments, **kwargs):
        captured.append((arguments, kwargs))
        returncode, stdout, stderr = next(responses)
        return type(
            "Result",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    monkeypatch.setattr(infra.subprocess, "run", fake_run)
    script = "printf transport-marker\\n\n" + "x" * 100_000
    assert infra.run_remote_script(script, privileged=True, timeout=1) == "ok"
    assert len(captured) == 3
    commands = [call[0][-1] for call in captured]
    assert all(sum(len(argument) for argument in call[0]) < 32_767 for call in captured)
    assert all("transport-marker" not in command for command in commands)
    assert all("secret-value" not in command for command in commands)
    assert "mktemp /tmp/faultwitness-remote.XXXXXX" in commands[0]
    assert commands[1] == "sudo -k -S -p '' /bin/sh /tmp/faultwitness-remote.A1b2C3"
    assert commands[2] == "rm -f -- /tmp/faultwitness-remote.A1b2C3"
    assert [call[1]["input"] for call in captured] == [
        script.encode("utf-8"),
        b"secret-value\n",
        b"",
    ]
    assert all(call[1]["text"] is False for call in captured)
    assert all("encoding" not in call[1] for call in captured)
    assert all("timeout" not in call[1] for call in captured)


def test_privileged_runner_cleans_up_after_execute_failure(monkeypatch) -> None:
    import faultwitness_dev.infra as infra

    responses = iter(
        [
            (0, "/tmp/faultwitness-remote.Fail01\n", ""),
            (7, "", "FW_PROBE_FAILED step=execute"),
            (0, "", ""),
        ]
    )
    commands = []

    def fake_run(arguments, **_kwargs):
        commands.append(arguments[-1])
        returncode, stdout, stderr = next(responses)
        return type(
            "Result",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    with pytest.raises(GovernanceError, match="FW_PROBE_FAILED step=execute"):
        infra._run_remote_script_transport(
            "exit 7\n",
            privileged=True,
            sudo_stdin="credential",
            arguments=["ssh"],
            runner=fake_run,
        )
    assert commands[-1] == "rm -f -- /tmp/faultwitness-remote.Fail01"


def test_privileged_runner_fails_closed_on_cleanup_failure() -> None:
    import faultwitness_dev.infra as infra

    responses = iter(
        [
            (0, "/tmp/faultwitness-remote.Clean01\n", ""),
            (0, "ok", ""),
            (9, "", "FW_CLEANUP_FAILED step=remove"),
        ]
    )

    def fake_run(_arguments, **_kwargs):
        returncode, stdout, stderr = next(responses)
        return type(
            "Result",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    with pytest.raises(GovernanceError, match="remote script cleanup failed"):
        infra._run_remote_script_transport(
            "true\n",
            privileged=True,
            sudo_stdin="credential",
            arguments=["ssh"],
            runner=fake_run,
        )


def test_privileged_runner_rejects_invalid_remote_path_without_execution() -> None:
    import faultwitness_dev.infra as infra

    calls = 0

    def fake_run(_arguments, **_kwargs):
        nonlocal calls
        calls += 1
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": "/tmp/not-bound\n", "stderr": ""},
        )()

    with pytest.raises(GovernanceError, match="invalid temporary path"):
        infra._run_remote_script_transport(
            "true\n",
            privileged=True,
            sudo_stdin="credential",
            arguments=["ssh"],
            runner=fake_run,
        )
    assert calls == 1


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
