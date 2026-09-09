from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

PROBE = runpy.run_path(
    str(Path(__file__).parents[2] / "deploy" / "bootstrap" / "probe_host.py")
)
docker_networks_conflict = PROBE["docker_networks_conflict"]
docker_state = PROBE["docker_state"]
docker_cidr_conflict = PROBE["docker_cidr_conflict"]
seccomp_supported = PROBE["seccomp_supported"]


def test_docker_networks_allow_null_ipam_config_without_crashing() -> None:
    assert docker_networks_conflict([{"IPAM": {"Config": None}}]) is False
    assert docker_networks_conflict([{"IPAM": None}]) is False


def test_docker_networks_fail_closed_on_invalid_or_reserved_subnets() -> None:
    assert docker_networks_conflict({"unexpected": "shape"}) is True
    assert docker_networks_conflict([{"IPAM": {"Config": "invalid"}}]) is True
    assert (
        docker_networks_conflict([{"IPAM": {"Config": [{"Subnet": "10.42.8.0/24"}]}}])
        is True
    )


def test_docker_networks_accept_non_conflicting_subnets() -> None:
    assert (
        docker_networks_conflict([{"IPAM": {"Config": [{"Subnet": "172.18.0.0/16"}]}}])
        is False
    )


def _result(returncode: int, stdout: str = "") -> object:
    return type("Result", (), {"returncode": returncode, "stdout": stdout, "stderr": ""})()


def test_docker_state_fails_closed_when_the_daemon_is_unreachable(monkeypatch) -> None:
    """An unreadable docker.sock previously reported 0 running / 0 unhealthy, which
    passes docker_unhealthy_count while having measured nothing."""
    namespace = docker_state.__globals__
    monkeypatch.setitem(namespace, "shutil", SimpleNamespace(which=lambda _name: "/usr/bin/docker"))
    monkeypatch.setitem(
        namespace, "subprocess", SimpleNamespace(run=lambda *_args, **_kwargs: _result(1))
    )
    with pytest.raises(RuntimeError, match="API is unreachable"):
        docker_state()


def test_docker_state_counts_running_and_unhealthy_containers(monkeypatch) -> None:
    namespace = docker_state.__globals__
    monkeypatch.setitem(namespace, "shutil", SimpleNamespace(which=lambda _name: "/usr/bin/docker"))
    listing = "Up 3 hours (healthy)\nUp 2 minutes (unhealthy)\n"
    monkeypatch.setitem(
        namespace, "subprocess", SimpleNamespace(run=lambda *_args, **_kwargs: _result(0, listing))
    )
    assert docker_state() == (2, 1)


def test_docker_cidr_conflict_fails_closed_when_no_network_is_listed(monkeypatch) -> None:
    """Docker always owns bridge/host/none; an empty list means the query failed."""
    namespace = docker_cidr_conflict.__globals__
    monkeypatch.setitem(namespace, "shutil", SimpleNamespace(which=lambda _name: "/usr/bin/docker"))
    monkeypatch.setitem(namespace, "command_output", lambda _arguments: "")
    assert docker_cidr_conflict() is True


def test_seccomp_capability_does_not_require_current_process_filter(tmp_path: Path) -> None:
    actions = tmp_path / "actions_avail"
    status = tmp_path / "status"
    config = tmp_path / "config"
    actions.write_text("kill_process kill_thread errno allow\n", encoding="utf-8")
    status.write_text("Seccomp:\t0\n", encoding="utf-8")
    assert seccomp_supported(actions, status, config) is True


def test_seccomp_capability_falls_back_to_kernel_status_field(tmp_path: Path) -> None:
    actions = tmp_path / "missing-actions"
    status = tmp_path / "status"
    config = tmp_path / "missing-config"
    status.write_text("Name:\tpython3\nSeccomp:\t0\n", encoding="utf-8")
    assert seccomp_supported(actions, status, config) is True
