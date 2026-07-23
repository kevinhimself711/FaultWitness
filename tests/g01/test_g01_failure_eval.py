from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_failure_eval import (
    _control_api_load_manifest,
    _transition_sql,
    run_control_api_load_matrix,
    run_postgres_failure_matrix,
    run_redis_recovery_matrix,
)

ROOT = Path(__file__).resolve().parents[2]


def test_transition_matrix_contains_all_frozen_transitions() -> None:
    sql, count = _transition_sql(ROOT)
    assert count == 82
    assert sql.count("INSERT INTO") == 82 * 3
    assert "incident_owner.aggregate_state" in sql
    assert "action_owner.outbox" in sql


def test_postgres_failure_matrix_accepts_exact_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_failure_eval.run_remote_script",
        lambda *args, **kwargs: "82\n82\n82\n5000\n0\n0\n1\n",
    )
    result = run_postgres_failure_matrix(ROOT, "a" * 40)
    assert result["status"] == "pass"
    assert result["partial_commit_count"] == 0
    assert result["persistent_rows_after_rollback"] == 0


@pytest.mark.parametrize(
    "output",
    ["", "82\n82\n82\n4999\n0\n0\n1\n", "82\n82\n82\n5000\n1\n0\n1\n"],
)
def test_postgres_failure_matrix_rejects_counter_drift(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_failure_eval.run_remote_script",
        lambda *args, **kwargs: output,
    )
    with pytest.raises(GovernanceError, match="counter"):
        run_postgres_failure_matrix(ROOT, "a" * 40)


def test_redis_recovery_matrix_accepts_crash_reclaim_and_zero_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_failure_eval.run_remote_script",
        lambda *args, **kwargs: "100\n100\n0\n",
    )
    result = run_redis_recovery_matrix("a" * 40)
    assert result["status"] == "pass"
    assert result["pending_after_recovery"] == 0


@pytest.mark.parametrize("output", ["", "99\n100\n0\n", "100\n100\n1\n"])
def test_redis_recovery_matrix_rejects_counter_drift(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        "faultwitness_dev.g01_failure_eval.run_remote_script",
        lambda *args, **kwargs: output,
    )
    with pytest.raises(GovernanceError, match="Redis recovery matrix"):
        run_redis_recovery_matrix("a" * 40)


def test_control_api_load_manifest_is_private_and_candidate_bound() -> None:
    manifest = _control_api_load_manifest("a" * 40)
    assert "event_count" in manifest
    assert "range(9_999)" in manifest
    assert "g01-api-load-egress" in manifest
    assert "imagePullPolicy: Never" in manifest
    assert "docker.io/faultwitness/control-api:" + "a" * 40 in manifest


def test_control_api_load_matrix_accepts_all_frozen_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = {
        "candidate_sha": "a" * 40,
        "event_count": 10_000,
        "ordered": True,
        "reconnects": 100,
        "final_cursor": 10_000,
        "retention_gap": True,
        "slow_consumer_closed": True,
        "remaining_rows": 0,
    }
    monkeypatch.setattr(
        "faultwitness_dev.g01_failure_eval.run_remote_script",
        lambda *args, **kwargs: json.dumps(result),
    )
    assert run_control_api_load_matrix("a" * 40)["status"] == "pass"
