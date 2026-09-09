from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import faultwitness_dev.g02_baselines as g02_baselines
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.experiment import TrialJournal
from faultwitness_dev.g02_baselines import (
    QUALITY_FLOOR_EVIDENCE_V2,
    QUALITY_FLOORS,
    LiveInfrastructureError,
    aggregate_gate_baselines,
    build_baseline_prompt,
    build_observation_packet,
    canonical_observation_packet,
    deterministic_baseline,
    load_baseline_config,
    normalize_observation_packet_v2,
    percentile_cluster_bootstrap,
    resolve_quality_floor,
    resumable_trial_ids,
    run_gate_deterministic_matrix,
    run_gate_live_matrix,
    run_live_trials,
    score_result,
    token_cost,
    validate_quality_floor_coverage,
    validate_threshold_registry,
)
from faultwitness_dev.g02_lab import (
    MemoryFlagClient,
    base_flag_document,
    run_gate_scenario_matrix,
    scripted_sequence_observer,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "g02"
ROOT = Path(__file__).parents[2]
FROZEN_SCENARIOS = (
    ROOT
    / "docs"
    / "evals"
    / "EVAL-G02-046"
    / "artifacts"
    / "phases"
    / "scenario-matrix"
    / "summary.json"
)


def test_every_g02_versioned_entrypoint_rejects_unknown_before_io(
    tmp_path: Path,
) -> None:
    """Unknown versions may never fall through into v1 semantics or side effects."""
    calls = (
        lambda: g02_baselines.validate_threshold_registry({}, metric_version=99),
        lambda: g02_baselines.build_baseline_prompt("", {}, metric_version=99),
        lambda: g02_baselines.make_bailian_adapter(
            tmp_path,
            "no_rag",
            metric_version=99,
        ),
        lambda: g02_baselines.deterministic_baseline({}, metric_version=99),
        lambda: g02_baselines.validate_result({}, metric_version=99),
        lambda: g02_baselines.score_result({}, {}, metric_version=99),
        lambda: g02_baselines.run_live_trials(
            tmp_path,
            [],
            producer_sha="0" * 40,
            metric_version=99,
        ),
        lambda: g02_baselines._scenario_cases({}, metric_version=99),
        lambda: g02_baselines.run_gate_deterministic_matrix(
            "0" * 40,
            {},
            metric_version=99,
        ),
        lambda: g02_baselines._gate_trial_specs("", {}, metric_version=99),
        lambda: g02_baselines.run_gate_live_matrix(
            tmp_path,
            "0" * 40,
            "",
            {},
            tmp_path / "journal",
            metric_version=99,
        ),
        lambda: g02_baselines.aggregate_gate_baselines(
            {},
            {},
            {},
            "",
            metric_version=99,
        ),
        lambda: g02_baselines.aggregate_live_metrics([], "", metric_version=99),
    )
    for call in calls:
        with pytest.raises(GovernanceError, match="metric version"):
            call()
    assert list(tmp_path.iterdir()) == []


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
    ("observations", "expected"),
    [
        ([{"journey_failed": True, "correlated_error": True}], "productCatalogFailure"),
        (
            [{"cpu_rate": 2.0, "baseline_cpu_max": 1.0, "correlated_span": True}],
            "adHighCpu",
        ),
        (
            [
                {"working_set": 2.0, "email_stimulus_count": 1},
                {"working_set": 3.0, "email_stimulus_count": 2},
            ],
            "emailMemoryLeak",
        ),
        ([{"checkout_failed": True, "payment_error": True}], "paymentFailure"),
        ([{"checkout_failed": True, "connection_error": True}], "paymentUnreachable"),
        (
            [{"consumer_lag": 2.0, "baseline_lag": 1.0, "kafka_error": True}],
            "kafkaQueueProblems",
        ),
    ],
)
def test_deterministic_baseline_maps_all_six_fault_signatures(
    observations: list[dict], expected: str
) -> None:
    value = packet()
    value["observations"] = [
        {"id": f"signal-{index}", **observation}
        for index, observation in enumerate(observations, 1)
    ]
    assert deterministic_baseline(value)["root_cause"] == expected


def test_deterministic_baseline_reads_values_not_ambient_key_presence() -> None:
    value = packet()
    value["observations"] = [
        {
            "id": "payment-signal",
            "working_set": 42_000_000,
            "checkout_failed": True,
            "payment_error": True,
        }
    ]
    assert deterministic_baseline(value)["root_cause"] == "paymentFailure"


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


def test_model_evidence_alias_is_a_scored_schema_failure() -> None:
    result = deterministic_baseline(packet())
    result["evidence_ids"] = result.pop("evidence")
    score = score_result(result, {"root_cause": "productCatalogFailure"})
    assert score["status"] == "scored_failure"
    assert score["failure_class"] == "malformed"


def _metric_v2_case() -> tuple[dict, dict]:
    raw = {
        "schema_version": "1.0.0",
        "case_id": "SEED-G02-0001",
        "problem_brief": "Investigate the service incident.",
        "observations": [
            {
                "id": "raw-1",
                "recorded_at": "2026-07-28T00:00:00+00:00",
                "working_set": 42_000_000,
                "cpu_rate": 0.01,
                "consumer_lag": 0,
                "baseline_lag": 0,
                "checkout_error_spans": 1,
                "payment_connection_errors": 0,
                "descriptions": ["Payment request failed. Invalid token."],
                "payment_error": True,
                "kafka_error": False,
            },
            {
                "id": "raw-2",
                "recorded_at": "2026-07-28T00:00:30+00:00",
                "working_set": 42_000_000,
                "cpu_rate": 0.01,
                "consumer_lag": 0,
                "baseline_lag": 0,
                "checkout_error_spans": 1,
                "payment_connection_errors": 0,
                "descriptions": ["Payment request failed. Invalid token."],
                "payment_error": True,
                "kafka_error": False,
            },
        ],
    }
    normalized = normalize_observation_packet_v2(raw)
    required = "SEED-G02-0001-EVID-04"
    truth = {
        "root_cause": "paymentFailure",
        "required_evidence": [required],
        "distractor_evidence": [
            str(item["id"])
            for item in normalized["observations"]
            if item["id"] != required
        ],
    }
    return normalized, truth


def _metric_v2_result(
    evidence_id: str,
    *,
    case_id: str = "SEED-G02-0001",
    root_cause: str = "paymentFailure",
) -> dict:
    return {
        "schema_version": "2.0.0",
        "case_id": case_id,
        "status": "ok",
        "root_cause": root_cause,
        "root_cause_candidates": [root_cause],
        "evidence": [evidence_id],
        "claims": [
            {
                "claim_type": "root_cause",
                "value": root_cause,
                "evidence_refs": [evidence_id],
            }
        ],
    }


def test_metric_v2_discloses_labels_and_removes_oracle_shortcuts() -> None:
    normalized, _truth = _metric_v2_case()
    prompt = build_baseline_prompt("no_rag", normalized, metric_version=2)
    assert all(label in prompt[0]["content"] for label in g02_baselines.ROOT_CAUSE_LABELS)
    rendered = json.dumps(normalized)
    assert "payment_error" not in rendered
    assert "kafka_error" not in rendered
    assert "correlated_error" not in rendered
    assert {item["id"] for item in normalized["observations"]} == {
        f"SEED-G02-0001-EVID-{index:02d}" for index in range(1, 7)
    }


def test_metric_v2_scores_typed_claim_and_distractor_negatives() -> None:
    _normalized, truth = _metric_v2_case()
    required = truth["required_evidence"][0]
    correct = score_result(_metric_v2_result(required), truth, metric_version=2)
    assert correct["core_e2e"] == 1.0
    assert correct["unsupported_critical_claim"] == 0.0
    assert correct["tool_schema_validity"] is None

    malformed = _metric_v2_result(required)
    malformed["claims"] = [{"claim": "payment failed", "supported": True}]
    assert score_result(malformed, truth, metric_version=2)["failure_class"] == "malformed"

    unnormalized = _metric_v2_result(required)
    unnormalized["root_cause"] = "payment failure"
    unnormalized["root_cause_candidates"] = ["payment failure"]
    unnormalized["claims"][0]["value"] = "payment failure"
    assert score_result(unnormalized, truth, metric_version=2)["failure_class"] == "invalid_label"

    distractor = _metric_v2_result("SEED-G02-0001-EVID-03")
    scored = score_result(distractor, truth, metric_version=2)
    assert scored["failure_class"] == "distractor_evidence"
    assert scored["evidence_precision"] == 0.0
    assert scored["unsupported_critical_claim"] == 1.0


def test_metric_v2_negative_classes_are_enforced_for_all_32_cases() -> None:
    scenarios = json.loads(FROZEN_SCENARIOS.read_text(encoding="utf-8"))
    cases = g02_baselines._scenario_cases(scenarios, metric_version=2)
    assert len(cases) == 32

    observed: dict[str, set[str]] = {
        "malformed": set(),
        "invalid_label": set(),
        "distractor_evidence": set(),
    }
    for case_id, case in cases.items():
        truth = case["ground_truth"]
        expected = str(truth["root_cause"])
        required = str(truth["required_evidence"][0])
        distractor = str(truth["distractor_evidence"][0])

        malformed = _metric_v2_result(
            required,
            case_id=case_id,
            root_cause=expected,
        )
        malformed.pop("claims")
        assert (
            score_result(malformed, truth, metric_version=2)["failure_class"]
            == "malformed"
        )
        observed["malformed"].add(case_id)

        unnormalized = _metric_v2_result(
            required,
            case_id=case_id,
            root_cause=expected,
        )
        unnormalized["root_cause"] = "semantic but noncanonical label"
        unnormalized["root_cause_candidates"] = ["semantic but noncanonical label"]
        unnormalized["claims"][0]["value"] = "semantic but noncanonical label"
        assert (
            score_result(unnormalized, truth, metric_version=2)["failure_class"]
            == "invalid_label"
        )
        observed["invalid_label"].add(case_id)

        distracted = _metric_v2_result(
            distractor,
            case_id=case_id,
            root_cause=expected,
        )
        assert (
            score_result(distracted, truth, metric_version=2)["failure_class"]
            == "distractor_evidence"
        )
        observed["distractor_evidence"].add(case_id)

    assert all(len(case_ids) == 32 for case_ids in observed.values())


def test_fixed_legacy_signature_has_no_email_false_positives() -> None:
    scenarios = json.loads(FROZEN_SCENARIOS.read_text(encoding="utf-8"))
    matrix = run_gate_deterministic_matrix("1" * 40, scenarios)
    truth = {
        str(trial["payload"]["scenario_id"]): str(trial["payload"]["fault_class"])
        for trial in scenarios["trials"]
    }
    false_email = [
        row["case_id"]
        for row in matrix["rows"]
        if row["result"]["root_cause"] == "emailMemoryLeak"
        and truth[str(row["case_id"])] != "emailMemoryLeak"
    ]
    assert false_email == []


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
    validate_threshold_registry(
        QUALITY_FLOORS,
        metric_version=2,
        evidence=QUALITY_FLOOR_EVIDENCE_V2,
    )
    assert resolve_quality_floor("core_e2e", best_baseline=0.5) == 0.7


def test_quality_floor_coverage_rejects_an_uncomputed_floor() -> None:
    with pytest.raises(GovernanceError, match="no computed metric evidence: evidence_precision"):
        validate_quality_floor_coverage(
            {
                "core_e2e",
                "root_cause_top3",
                "unsupported_critical_claim",
                "fault_family_success",
            }
        )


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
    first = run_live_trials(tmp_path, trials, producer_sha="1" * 40)
    assert [item["status"] for item in first] == ["pass", "pass"]
    second = run_live_trials(tmp_path, trials, producer_sha="1" * 40)
    assert second == first
    stored = json.loads((tmp_path / "trials" / "trial-a.json").read_text())
    assert stored["execution_attempt"] == 1
    assert stored["record_version"] == 2


def test_trial_journal_resumes_only_infrastructure_failure(tmp_path: Path) -> None:
    calls = 0

    def flaky(item: dict) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LiveInfrastructureError("transport")
        return deterministic_baseline(item)

    trial = [{"trial_id": "trial-flaky", "baseline": "no_rag", "packet": packet()}]
    assert (
        run_live_trials(tmp_path, trial, flaky, producer_sha="1" * 40)[0]["status"]
        == "infra_failed"
    )
    assert run_live_trials(tmp_path, trial, flaky, producer_sha="1" * 40)[0]["status"] == "pass"


def test_token_cost_uses_frozen_cny_rates() -> None:
    assert token_cost(1_000_000, 1_000_000) == 10.0


def test_gate_baseline_runners_execute_exact_32_and_192_without_external_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = "1" * 40

    def client_factory(_producer_sha: str) -> MemoryFlagClient:
        return MemoryFlagClient(base_flag_document())

    def observer_factory(_producer_sha: str, _fault_class: str):
        return scripted_sequence_observer()

    scenarios = run_gate_scenario_matrix(
        Path(__file__).parents[2],
        producer,
        TrialJournal(tmp_path / "scenarios"),
        client_factory=client_factory,
        observer_factory=observer_factory,
    )
    deterministic = run_gate_deterministic_matrix(producer, scenarios)
    monkeypatch.setattr(
        g02_baselines,
        "make_bailian_adapter",
        lambda _root, _baseline, **_kwargs: deterministic_baseline,
    )
    live = run_gate_live_matrix(
        Path(__file__).parents[2],
        producer,
        "2" * 64,
        scenarios,
        tmp_path / "live",
    )
    repeated = run_gate_live_matrix(
        Path(__file__).parents[2],
        producer,
        "2" * 64,
        scenarios,
        tmp_path / "live",
    )
    aggregate = aggregate_gate_baselines(scenarios, deterministic, live, "2" * 64)
    assert deterministic["N"] == 32
    assert live["trial_count"] == 192
    assert live["status"] == "pass"
    assert [row["trial_id"] for row in repeated["trials"]] == [
        row["trial_id"] for row in live["trials"]
    ]
    journal_records = [
        json.loads(path.read_text()) for path in (tmp_path / "live" / "trials").glob("*.json")
    ]
    assert len(journal_records) == 192
    assert all(record["execution_attempt"] == 1 for record in journal_records)
    assert all(record["record_version"] == 2 for record in journal_records)
    assert aggregate["case_clusters"] == 32
    assert aggregate["resamples"] == 2000


def test_metric_v2_aggregate_computes_all_earned_floors_and_never_caps_target() -> None:
    scenarios = json.loads(FROZEN_SCENARIOS.read_text(encoding="utf-8"))
    dataset_digest = g02_baselines.metric_v2_dataset_digest(scenarios)
    cases = g02_baselines._scenario_cases(scenarios, metric_version=2)
    deterministic = run_gate_deterministic_matrix(
        "1" * 40,
        scenarios,
        metric_version=2,
    )
    trials = []
    for baseline in ("naive_react", "no_rag"):
        for case_id, case in sorted(cases.items()):
            truth = case["ground_truth"]
            required = str(truth["required_evidence"][0])
            for repetition in range(1, 4):
                trials.append(
                    {
                        "trial_id": f"{baseline}-{case_id}-{repetition}",
                        "baseline": baseline,
                        "case_id": case_id,
                        "repetition": repetition,
                        "status": "pass",
                        "fallback_count": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_cny": 0.0,
                        "result": _metric_v2_result(
                            required,
                            case_id=case_id,
                            root_cause=str(truth["root_cause"]),
                        ),
                    }
                )
    aggregate = aggregate_gate_baselines(
        scenarios,
        deterministic,
        {"trials": trials},
        dataset_digest,
        metric_version=2,
    )

    assert aggregate["metric_version"] == 2
    assert aggregate["best_baseline"]["core_e2e"] == 1.0
    assert aggregate["g03_comparison"] == {
        "operator": ">=",
        "margin": 0.05,
        "minimum_core_e2e": 1.05,
        "feasible_on_unit_interval": False,
    }
    assert aggregate["future_core_e2e_floor"] == 1.1
    for baseline in ("deterministic", "naive_react", "no_rag"):
        result = aggregate["baselines"][baseline]
        assert "core_e2e" in result["metrics"]
        assert set(result["fault_family_success"]) == {
            "change_config",
            "dependency_network",
            "resource_capacity",
            "runtime_data",
        }
        assert set(result["not_applicable"]) == {
            "tool_schema_validity",
            "dead_no_progress_loop",
        }
