from __future__ import annotations

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_recovery import run_postgres_restore_rehearsal


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
