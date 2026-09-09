"""AMD-0007 appendix 3: a failed readiness case must explain itself.

These are negative tests for the runner-control defects that made a single
failure cost a whole round: observations were discarded on the failure path, the
first failure aborted the remaining 31 cases, a cleanup failure masked the
primary cause, and an absent Prometheus series was scored as an observed zero.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from test_g03_readiness import _scenario_document, _window

import faultwitness_dev.g03_readiness as readiness
from faultwitness_dev.errors import GovernanceError, InfrastructureFailure
from faultwitness_dev.g03_readiness import (
    replay_all_scenarios_v3,
    run_retest_baselines_v3,
)

ROOT = Path(__file__).resolve().parents[2]


class _MemoryFlagClientV3:
    """Minimal flag client whose write/read round-trips exactly."""

    def __init__(self) -> None:
        self.document: dict[str, object] = {
            "flags": {
                "kafkaQueueProblems": {
                    "defaultVariant": "off",
                    "variants": {"off": False, "on": True},
                }
            }
        }

    def read(self) -> dict[str, object]:
        return copy.deepcopy(self.document)

    def write(self, value: Mapping[str, object]) -> None:
        self.document = copy.deepcopy(dict(value))


def _kafka_scenario() -> dict[str, object]:
    return {
        "scenario_id": "SEED-G02-0001",
        "family": "runtime_data",
        "problem_brief": "A brief.",
        "fault_action": {"class": "kafkaQueueProblems"},
    }


def _kafka_window(*, lag: float, kafka_error: bool) -> dict[str, object]:
    return {
        "recorded_at": "2026-07-29T00:00:00+00:00",
        "ready": True,
        "journey_status": 200,
        "consumer_lag": lag,
        "baseline_lag": 0.0,
        "kafka_error": kafka_error,
        "kafka_log_error": kafka_error,
        "kafka_fault_log": kafka_error,
        "error_spans": 1 if kafka_error else 0,
    }


def test_failed_scenario_retains_observations_and_predicate_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure must explain itself without needing a second live run.

    The old failure path recorded only {scenario_id, fault_class, reason}, so
    every failure required a separate diagnostic run -- and that re-run is a
    different sample, so the original failure was never actually explained.
    """

    class Observer:
        fault_poll_stimuli = 3
        recovery_poll_stimuli = 2

        def __call__(self, phase: str, _fault_class: str) -> Mapping[str, object]:
            if phase == "control":
                return {"state": readiness.OracleState.HEALTHY}
            if phase == "fault":
                # Lag never exceeds baseline: the fault oracle cannot activate.
                return _kafka_window(lag=0.0, kafka_error=False)
            return {
                **_kafka_window(lag=0.0, kafka_error=False),
                "journey_healthy": True,
                "signal_not_worsening": True,
            }

        def collect_healthy_window(self) -> Mapping[str, object]:
            return _kafka_window(lag=0.0, kafka_error=False)

    with pytest.raises(GovernanceError) as caught:
        readiness.run_readiness_scenario_v3(
            _kafka_scenario(), _MemoryFlagClientV3(), Observer()
        )

    diagnostics = getattr(caught.value, "scenario_diagnostics", None)
    assert diagnostics is not None
    assert diagnostics["fault_class"] == "kafkaQueueProblems"
    assert diagnostics["healthy_window_count"] == readiness.HEALTHY_WINDOW_COUNT
    assert diagnostics["fault_observation_count"] == 2
    assert len(diagnostics["healthy_windows"]) == readiness.HEALTHY_WINDOW_COUNT
    assert len(diagnostics["fault_observations"]) == 2
    # Every predicate term is recorded per observation, so the reason a window
    # failed is visible without re-running the case.
    terms = diagnostics["fault_predicate_terms"]
    assert len(terms) == 2
    assert terms[0]["terms"]["consumer_lag"] == 0.0
    assert terms[0]["terms"]["baseline_lag"] == 0.0
    assert terms[0]["terms"]["kafka_error"] is False


def test_cleanup_failure_does_not_mask_the_primary_fault_failure() -> None:
    """When both the fault oracle and cleanup fail, report the primary cause."""

    class Observer:
        def __call__(self, phase: str, _fault_class: str) -> Mapping[str, object]:
            if phase == "control":
                return {"state": readiness.OracleState.HEALTHY}
            if phase == "fault":
                return _kafka_window(lag=0.0, kafka_error=False)
            # Recovery never reaches HEALTHY either.
            return {
                **_kafka_window(lag=99.0, kafka_error=True),
                "journey_healthy": False,
                "signal_not_worsening": False,
            }

        def collect_healthy_window(self) -> Mapping[str, object]:
            return _kafka_window(lag=0.0, kafka_error=False)

    with pytest.raises(GovernanceError) as caught:
        readiness.run_readiness_scenario_v3(
            _kafka_scenario(), _MemoryFlagClientV3(), Observer()
        )

    message = str(caught.value)
    # Both causes are present and the fault oracle failure comes first.
    assert "fault oracle did not reach FAULT_ACTIVE" in message
    assert "recovery oracle did not reach HEALTHY" in message
    assert message.index("fault oracle") < message.index("recovery oracle")
    diagnostics = getattr(caught.value, "scenario_diagnostics", None)
    assert diagnostics is not None
    assert "fault oracle" in str(diagnostics["primary_error"])
    assert "recovery oracle" in str(diagnostics["cleanup_error"])


def test_diagnostic_scan_reports_every_case_and_is_never_promotable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """continue-on-case-failure produces the full failure spectrum in one pass."""
    journal = readiness.TrialJournal(tmp_path / "diagnostic-journal")
    failing = {"SEED-G02-0001", "SEED-G02-0008", "SEED-G02-0015"}

    def fake_run(
        scenario: Mapping[str, object],
        _client: object,
        _observer: object,
        *,
        metric_version: int,
    ) -> dict[str, object]:
        case_id = str(scenario["scenario_id"])
        if case_id in failing:
            error = GovernanceError("metric v3 fault oracle did not reach FAULT_ACTIVE")
            error.scenario_diagnostics = {  # type: ignore[attr-defined]
                "fault_class": scenario["fault_action"]["class"]
            }
            raise error
        fixture_case = next(
            case
            for case in _scenario_document()["trials"]
            if case["payload"]["scenario_id"] == case_id
        )
        return {
            "scenario_id": case_id,
            "family": scenario["family"],
            "fault_class": fixture_case["payload"]["fault_class"],
            "observation_packet": fixture_case["payload"]["observation_packet"],
        }

    monkeypatch.setattr(readiness, "run_readiness_scenario_v3", fake_run)
    result = replay_all_scenarios_v3(
        ROOT,
        "1" * 40,
        journal,
        sut_producer_sha="2" * 40,
        client_factory=lambda _sha: object(),
        observer_factory=lambda _sha, _fault_class: object(),
        continue_on_case_failure=True,
    )

    # All 32 cases were attempted rather than aborting on the first failure.
    assert result["execution_status"] == "diagnostic_scan"
    assert result["attempted_case_count"] == 32
    assert len(result["case_outcomes"]) == 32
    assert result["failed_case_count"] == 3
    assert result["diagnostic_only"] is True
    assert result["promotable_to_gate_evidence"] is False
    failed = {
        item["scenario_id"]
        for item in result["case_outcomes"]
        if item["status"] != "pass"
    }
    assert failed == failing
    # Each failure carries its own attribution.
    assert all(
        item["has_diagnostics"] is True
        for item in result["case_outcomes"]
        if item["status"] != "pass"
    )


def test_default_replay_still_aborts_on_the_first_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness evidence semantics are unchanged when the flag is absent."""
    journal = readiness.TrialJournal(tmp_path / "abort-journal")
    attempted: list[str] = []

    def fake_run(
        scenario: Mapping[str, object],
        _client: object,
        _observer: object,
        *,
        metric_version: int,
    ) -> dict[str, object]:
        attempted.append(str(scenario["scenario_id"]))
        raise GovernanceError("metric v3 fault oracle did not reach FAULT_ACTIVE")

    monkeypatch.setattr(readiness, "run_readiness_scenario_v3", fake_run)
    result = replay_all_scenarios_v3(
        ROOT,
        "1" * 40,
        journal,
        sut_producer_sha="2" * 40,
        client_factory=lambda _sha: object(),
        observer_factory=lambda _sha, _fault_class: object(),
    )

    assert len(attempted) == 1
    assert result["status"] == "metric_fail"
    assert result["execution_status"] == "incomplete"
    assert "diagnostic_only" not in result


def test_diagnostic_scan_cannot_be_used_as_a_resume_source(tmp_path: Path) -> None:
    output_dir = tmp_path / "diagnostic-run"
    output_dir.mkdir()
    (output_dir / "run-manifest.json").write_text("{}", encoding="utf-8")
    (output_dir / "preflight-summary.json").write_text(
        json.dumps(
            {
                "execution_status": "diagnostic_scan",
                "preflight_status": "blocked",
                "diagnostic_only": True,
                "promotable_to_gate_evidence": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GovernanceError, match="diagnostic"):
        readiness._assert_resume_identity_v3(ROOT, output_dir)


def test_diagnostic_scan_requires_skip_live(tmp_path: Path) -> None:
    with pytest.raises(GovernanceError, match="diagnostic scan requires"):
        run_retest_baselines_v3(
            ROOT,
            tmp_path / "unused",
            skip_live=False,
            resume=True,
            continue_on_case_failure=True,
        )


def test_public_window_rejects_absent_series_as_infrastructure() -> None:
    """A null measurement is a missing instrument, never an observed zero.

    All six evidence groups must be present for every label, so a null cannot be
    projected into a packet: emitting one group as null only for the labels whose
    series happened to be absent would itself leak the label.
    """
    window = _window("kafkaQueueProblems", "healthy", 0)
    window["consumer_poll_lag_seconds"] = None
    with pytest.raises(InfrastructureFailure, match="absent"):
        readiness._public_window(window, "healthy")

    healthy = _window("kafkaQueueProblems", "healthy", 0)
    assert readiness._public_window(healthy, "healthy")["phase"] == "healthy"
