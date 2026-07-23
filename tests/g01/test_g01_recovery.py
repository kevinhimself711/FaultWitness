from __future__ import annotations

from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_recovery import (
    _verify_fresh_ssh_session,
    run_k3s_restore_rehearsal,
    run_k3s_snapshot_rehearsal,
    run_platform_rollback_rehearsal,
    run_postgres_restore_rehearsal,
)


def test_postgres_restore_rehearsal_accepts_two_sanitized_digests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script",
        lambda *args, **kwargs: f"{'a' * 64}\n{'b' * 64}\n",
    )
    result = run_postgres_restore_rehearsal("c" * 40)
    assert result["status"] == "pass"
    assert result["temporary_target_removed"] is True


@pytest.mark.parametrize("output", ["", "not-a-digest\n", f"{'a' * 64}\nBAD\n"])
def test_postgres_restore_rehearsal_rejects_incomplete_output(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script", lambda *args, **kwargs: output
    )
    with pytest.raises(GovernanceError, match="invalid sanitized digests"):
        run_postgres_restore_rehearsal("c" * 40)


def test_k3s_snapshot_rehearsal_accepts_digest_and_positive_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script",
        lambda *args, **kwargs: f"{'d' * 64}\n4096\n",
    )
    result = run_k3s_snapshot_rehearsal("c" * 40)
    assert result["status"] == "pass"
    assert result["snapshot_size_bytes"] == 4096
    assert result["restore_executed"] is False


@pytest.mark.parametrize("output", ["", f"{'d' * 64}\n0\n", "bad\n4096\n"])
def test_k3s_snapshot_rehearsal_rejects_invalid_evidence(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script", lambda *args, **kwargs: output
    )
    with pytest.raises(GovernanceError, match="snapshot"):
        run_k3s_snapshot_rehearsal("c" * 40)


def test_k3s_restore_rehearsal_accepts_exact_snapshot_and_ready_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script",
        lambda *args, **kwargs: f"{'e' * 64}\n1\n",
    )
    result = run_k3s_restore_rehearsal("c" * 40)
    assert result["status"] == "pass"
    assert result["restore_executed"] is True
    assert result["ready_node_count"] == 1
    assert result["fresh_session_attempts"] == 1


def test_fresh_ssh_session_retries_only_connection_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = iter(
        [
            GovernanceError("remote infrastructure command failed (connection_timeout; exit=255)"),
            "fresh-session\n",
        ]
    )

    observed: list[dict[str, object]] = []

    def remote(*args: object, **kwargs: object) -> str:
        observed.append(kwargs)
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("faultwitness_dev.g01_recovery.run_remote_script", remote)
    monkeypatch.setattr("faultwitness_dev.g01_recovery.time.sleep", lambda seconds: None)
    assert _verify_fresh_ssh_session() == 2
    assert all(call["privileged"] is True for call in observed)


def test_fresh_ssh_session_rejects_non_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def remote(*args: object, **kwargs: object) -> str:
        raise GovernanceError("host identity mismatch")

    monkeypatch.setattr("faultwitness_dev.g01_recovery.run_remote_script", remote)
    with pytest.raises(GovernanceError, match="identity mismatch"):
        _verify_fresh_ssh_session()


@pytest.mark.parametrize("output", ["", f"{'e' * 64}\n0\n", "bad\n1\n"])
def test_k3s_restore_rehearsal_rejects_invalid_evidence(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script", lambda *args, **kwargs: output
    )
    with pytest.raises(GovernanceError, match="restore"):
        run_k3s_restore_rehearsal("c" * 40)


def test_platform_rollback_reinstalls_candidate_and_checks_coexistence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script", lambda *args, **kwargs: "7\n6\n"
    )
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.deploy_platform",
        lambda *args, **kwargs: {"deployment_bundle_sha256": "a" * 64},
    )
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.inspect_platform_readiness",
        lambda *args, **kwargs: {"workload_count": 11},
    )
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.audit_runtime_coexistence",
        lambda *args, **kwargs: {"docker_regression_count": 0},
    )
    result = run_platform_rollback_rehearsal(tmp_path, "c" * 40)
    assert result["status"] == "pass"
    assert result["rolled_back_to_revision"] == 6
    assert result["docker_regression_count"] == 0


@pytest.mark.parametrize("output", ["", "7\n", "6\n7\n", "bad\n6\n"])
def test_platform_rollback_rejects_invalid_revision_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, output: str
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script", lambda *args, **kwargs: output
    )
    with pytest.raises(GovernanceError, match="rollback"):
        run_platform_rollback_rehearsal(tmp_path, "c" * 40)
