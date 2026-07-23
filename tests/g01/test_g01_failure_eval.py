from __future__ import annotations

from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_failure_eval import _transition_sql, run_postgres_failure_matrix

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
