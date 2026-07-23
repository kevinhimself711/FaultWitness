from __future__ import annotations

from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_eval import (
    _head,
    _platform_stability,
    _require_candidate,
    evaluate_g01_close,
)

ROOT = Path(__file__).resolve().parents[2]


def test_candidate_must_be_full_lowercase_head_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("faultwitness_dev.g01_eval._head", lambda root: "a" * 40)
    with pytest.raises(GovernanceError, match="full lowercase 40-character SHA"):
        _require_candidate(ROOT, "A" * 40)


def test_candidate_must_equal_checked_out_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("faultwitness_dev.g01_eval._head", lambda root: "b" * 40)
    with pytest.raises(GovernanceError, match="equal checked-out HEAD"):
        _require_candidate(ROOT, "a" * 40)


def test_close_readiness_rejects_current_incomplete_gate() -> None:
    candidate = _head(ROOT)
    with pytest.raises(GovernanceError, match="incomplete evidence"):
        evaluate_g01_close(ROOT, candidate)


def test_platform_stability_accepts_only_generic_error_after_full_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> dict:
        raise GovernanceError(
            "remote infrastructure command failed (remote_command_or_transport_failed; exit=1)"
        )

    monkeypatch.setattr("faultwitness_dev.g01_eval.inspect_platform_readiness", fail)
    ticks = iter([0.0, 901.0])
    monkeypatch.setattr("faultwitness_dev.g01_eval.time.monotonic", lambda: next(ticks))
    result = _platform_stability(ROOT, "a" * 40)
    assert result["status"] == "operator_adjudicated_pass"


def test_platform_stability_rejects_generic_error_inside_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> dict:
        raise GovernanceError(
            "remote infrastructure command failed (remote_command_or_transport_failed; exit=1)"
        )

    monkeypatch.setattr("faultwitness_dev.g01_eval.inspect_platform_readiness", fail)
    ticks = iter([0.0, 899.9])
    monkeypatch.setattr("faultwitness_dev.g01_eval.time.monotonic", lambda: next(ticks))
    with pytest.raises(GovernanceError, match="remote_command_or_transport_failed"):
        _platform_stability(ROOT, "a" * 40)


def test_platform_stability_rejects_specific_error_after_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> dict:
        raise GovernanceError("platform workloads are not Ready")

    monkeypatch.setattr("faultwitness_dev.g01_eval.inspect_platform_readiness", fail)
    ticks = iter([0.0, 901.0])
    monkeypatch.setattr("faultwitness_dev.g01_eval.time.monotonic", lambda: next(ticks))
    with pytest.raises(GovernanceError, match="not Ready"):
        _platform_stability(ROOT, "a" * 40)
