from __future__ import annotations

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_recovery import (
    run_k3s_restore_rehearsal,
    run_k3s_snapshot_rehearsal,
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


@pytest.mark.parametrize("output", ["", f"{'e' * 64}\n0\n", "bad\n1\n"])
def test_k3s_restore_rehearsal_rejects_invalid_evidence(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_recovery.run_remote_script", lambda *args, **kwargs: output
    )
    with pytest.raises(GovernanceError, match="restore"):
        run_k3s_restore_rehearsal("c" * 40)
