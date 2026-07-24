from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_baselines import (
    QUALITY_FLOORS,
    LiveInfrastructureError,
    build_observation_packet,
    canonical_observation_packet,
    deterministic_baseline,
    load_baseline_config,
    percentile_cluster_bootstrap,
    resumable_trial_ids,
    run_live_trials,
    score_result,
    token_cost,
    validate_threshold_registry,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "g02"


def packet(case_id: str = "synthetic-a") -> dict:
    return {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "problem_brief": "Investigate a product catalog failure.",
        "observations": [{"id": "catalog-error", "journey_failed": True, "correlated_error": True}],
    }


def test_packet_rejects_ground_truth() -> None:
    leaked = {**packet(), "ground_truth_ref": "s3://sealed/answer.json"}
    with pytest.raises(GovernanceError, match="sealed fields"):
        canonical_observation_packet(leaked)


def test_packet_builder_exposes_only_public_fields() -> None:
    built = build_observation_packet(
        {
            "scenario_id": "SEED-G02-0001",
            "problem_brief": "Investigate the visible symptom.",
            "fault_action": {"class": "productCatalogFailure"},
            "ground_truth_ref": "s3://sealed/answer.json",
        },
        [{"journey_failed": True, "correlated_error": True}],
    )
    assert set(built) == {
        "schema_version",
        "case_id",
        "problem_brief",
        "observations",
        "packet_digest",
    }
    assert built["observations"][0]["id"] == "SEED-G02-0001-OBS-01"


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        ({"journey_failed": True, "correlated_error": True}, "productCatalogFailure"),
        (
            {"cpu_rate": 2.0, "baseline_cpu_max": 1.0, "correlated_span": True},
            "adHighCpu",
        ),
        ({"working_set": 2.0}, "emailMemoryLeak"),
        ({"checkout_failed": True, "payment_error": True}, "paymentFailure"),
        ({"checkout_failed": True, "connection_error": True}, "paymentUnreachable"),
        (
            {"consumer_lag": 2.0, "baseline_lag": 1.0, "kafka_error": True},
            "kafkaQueueProblems",
        ),
    ],
)
def test_deterministic_baseline_maps_all_six_fault_signatures(
    observation: dict, expected: str
) -> None:
    value = packet()
    value["observations"] = [{"id": "signal", **observation}]
    assert deterministic_baseline(value)["root_cause"] == expected


def test_deterministic_baseline_and_scorer_are_exact() -> None:
    result = deterministic_baseline(packet())
    score = score_result(
        result, {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]}
    )
    assert result["root_cause"] == "productCatalogFailure"
    assert score["core_e2e"] == 1.0
    malformed = dict(result)
    malformed.pop("root_cause")
    assert (
        score_result(malformed, {"root_cause": "productCatalogFailure"})["failure_class"]
        == "malformed"
    )


def test_quality_registry_is_the_exact_seven_value_floor() -> None:
    assert QUALITY_FLOORS == {
        "core_e2e": {"operator": ">=", "value": "max(0.70,best_baseline+0.10)"},
        "root_cause_top3": {"operator": ">=", "value": 0.85},
        "evidence_precision": {"operator": ">=", "value": 0.90},
        "unsupported_critical_claim": {"operator": "<=", "value": 0.02},
        "tool_schema_validity": {"operator": ">=", "value": 0.99},
        "dead_no_progress_loop": {"operator": "<", "value": 0.01},
        "fault_family_success": {"operator": ">=", "value": 0.55},
    }
    config = load_baseline_config(Path(__file__).parents[2])
    assert config["model"]["orchestration_timeout_seconds"] is None
    assert config["model"]["fallback_profiles"] == []


def test_registered_threshold_negative_fixture_is_rejected() -> None:
    fixture = yaml.safe_load((FIXTURES / "threshold_decrease.yaml").read_text())
    with pytest.raises(GovernanceError, match="quality floor"):
        validate_threshold_registry(fixture["thresholds"])


def test_registered_scorer_negative_fixtures_are_scored_failures() -> None:
    unsupported = json.loads((FIXTURES / "score_unsupported_claim.json").read_text())
    score = score_result(
        unsupported,
        {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]},
    )
    assert score["unsupported_critical_claim"] == 1.0
    wrong = json.loads((FIXTURES / "deterministic_wrong_root.json").read_text())
    score = score_result(
        wrong, {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]}
    )
    assert score["failure_class"] == "wrong_root_cause"


def test_registered_partial_journal_resumes_only_infra_failure() -> None:
    fixture = json.loads((FIXTURES / "journal_partial_transport.json").read_text())
    assert resumable_trial_ids(fixture) == ["interrupted"]


def test_cluster_bootstrap_is_reproducible_and_retains_repetitions() -> None:
    rows = [
        {"case_id": "a", "core_e2e": 1.0},
        {"case_id": "a", "core_e2e": 0.0},
        {"case_id": "b", "core_e2e": 1.0},
        {"case_id": "b", "core_e2e": 1.0},
    ]
    first = percentile_cluster_bootstrap(rows, "core_e2e", seed="dataset-digest")
    second = percentile_cluster_bootstrap(rows, "core_e2e", seed="dataset-digest")
    assert first == second
    assert first["estimate"] == 0.75
    assert first["B"] == 2000


def test_trial_journal_resumes_only_incomplete_trial(tmp_path: Path) -> None:
    trials = [
        {"trial_id": "trial-a", "baseline": "naive_react", "packet": packet("a")},
        {"trial_id": "trial-b", "baseline": "no_rag", "packet": packet("b")},
    ]
    first = run_live_trials(tmp_path, trials)
    assert [item["status"] for item in first] == ["pass", "pass"]
    second = run_live_trials(tmp_path, trials)
    assert second == first
    stored = json.loads((tmp_path / "trials" / "trial-a.json").read_text())
    assert stored["attempt"] == 2


def test_trial_journal_resumes_only_infrastructure_failure(tmp_path: Path) -> None:
    calls = 0

    def flaky(item: dict) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LiveInfrastructureError("transport")
        return deterministic_baseline(item)

    trial = [{"trial_id": "trial-flaky", "baseline": "no_rag", "packet": packet()}]
    assert run_live_trials(tmp_path, trial, flaky)[0]["status"] == "infra_failed"
    assert run_live_trials(tmp_path, trial, flaky)[0]["status"] == "pass"


def test_token_cost_uses_frozen_cny_rates() -> None:
    assert token_cost(1_000_000, 1_000_000) == 10.0
