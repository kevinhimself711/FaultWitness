from __future__ import annotations

from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_eval import _head, _require_candidate, evaluate_g01_close

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
