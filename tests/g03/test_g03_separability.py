"""Tests for the diagnostic-only metric-v3 root-signal separability probe.

These cover the probe's own honesty properties, not the dataset's numbers: that the
leave-one-case-out threshold never reads the held-out case's healthy samples, that a sealed key
reaching a classifier fails closed, that the single-signal ablation really consults one signal,
and that the probe reports a lookup table when the signals are orthogonal and does not when they
overlap.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g03_leakage_probe import ABSTAIN, LABELS
from faultwitness_dev.g03_readiness import (
    ROOT_SIGNAL_FEATURES,
    TARGET_SERVICES,
    V3_TRACE_QUERY_SERVICES,
    build_observation_packet_v3,
)
from faultwitness_dev.g03_separability import (
    SeparabilityProbeError,
    _frozen_thresholds_loo,
    ablation,
    classify_from_offsets,
    false_qualification_table,
    offset_table,
    orthogonality,
    run_separability_probe,
    run_separability_probe_from_path,
)

DATASET_LABELS: tuple[str, ...] = (
    ("productCatalogFailure",) * 8
    + ("kafkaQueueProblems",) * 8
    + ("paymentFailure",) * 4
    + ("paymentUnreachable",) * 4
    + ("adHighCpu",) * 4
    + ("emailMemoryLeak",) * 4
)

# Baselines chosen so every signal has headroom above zero and the memory relative floor is
# meaningful (5% of ~50MB).
BASE_CPU = 0.01
BASE_MEMORY = 50_000_000.0
BASE_LAG = 0.01

# Ambient drift. The healthy windows climb by one STEP each, so the pooled p99 lands near STEP,
# while a fault window on a family whose signal did *not* move sits one BUMP above the healthy
# median. BUMP < STEP is the whole point: such a cell clears a bare quantum of 1e-6 or 0.001 and
# does not clear the p99 threshold. That is the real dataset's condition, where adHighCpu's 1e-6
# quantum sat below ambient CPU movement and false-qualified on 21 of 28 foreign cases. Without
# drift a fixture cannot exhibit the defect this probe exists to measure.
CPU_STEP, CPU_BUMP = 0.001, 0.0005
LAG_STEP, LAG_BUMP = 0.005, 0.002
MEMORY_STEP, MEMORY_BUMP = 100_000.0, 50_000.0


def _window(
    label: str,
    phase: str,
    index: int,
    *,
    cross_talk: bool = False,
) -> dict[str, Any]:
    """One observation window.

    With `cross_talk` off, a fault moves exactly the one signal its family declares, which is the
    orthogonal case. With it on, the fault also moves a second family's signal, so more than one
    signal reads as offset and the probe should stop calling it a lookup table.
    """
    activity = {service: 10 for service in V3_TRACE_QUERY_SERVICES}
    errors = {
        service: {"error_count": 0, "connection_error_count": 0, "descriptions": []}
        for service in V3_TRACE_QUERY_SERVICES
    }
    if phase == "healthy":
        cpu = BASE_CPU + index * CPU_STEP
        memory = BASE_MEMORY + index * MEMORY_STEP
        lag = BASE_LAG + index * LAG_STEP
    else:
        # The median of the five healthy values, plus a bump smaller than one drift step.
        cpu = BASE_CPU + 2 * CPU_STEP + CPU_BUMP
        memory = BASE_MEMORY + 2 * MEMORY_STEP + MEMORY_BUMP
        lag = BASE_LAG + 2 * LAG_STEP + LAG_BUMP
    if phase == "fault":
        target = TARGET_SERVICES[label]
        activity[target] += 5
        # These two families share `error_count` and are told apart only by target service, which
        # mirrors the real registry.
        if label in ("productCatalogFailure", "paymentFailure"):
            errors[target]["error_count"] = 6
        elif label == "paymentUnreachable":
            errors[target]["connection_error_count"] = 6
            errors[target]["error_count"] = 6
        elif label == "adHighCpu":
            cpu += 0.5
        elif label == "emailMemoryLeak":
            # Well past the 5% relative floor, which is the binding threshold for this signal.
            memory += BASE_MEMORY * 0.4
        elif label == "kafkaQueueProblems":
            lag += 5.0
        if cross_talk:
            # Every fault also drives the queue signal well past its threshold, so the queue
            # channel co-occurs with each family's own signal.
            lag += 5.0
    return {
        "recorded_at": f"2026-09-11T00:00:{index:02d}+00:00",
        "ready": True,
        "journey_status": 200,
        "cpu_rate": cpu,
        "working_set": memory,
        "consumer_lag": lag,
        "consumer_record_lag": lag,
        "consumer_poll_lag_seconds": lag,
        "trace_activity": activity,
        "trace_errors": errors,
    }


def _dataset(*, cross_talk: bool = False) -> dict[str, Any]:
    trials = []
    for index, label in enumerate(DATASET_LABELS, 1):
        scenario = {
            "scenario_id": f"SEED-G02-{index:04d}",
            "family": f"family-{label}",
            "problem_brief": "Diagnose the incident from the public packet.",
        }
        packet = build_observation_packet_v3(
            scenario,
            [_window(label, "healthy", item, cross_talk=cross_talk) for item in range(5)],
            [_window(label, "fault", item, cross_talk=cross_talk) for item in range(2)],
        )
        trials.append(
            {
                "status": "pass",
                "payload": {
                    "scenario_id": scenario["scenario_id"],
                    "fault_class": label,
                    "family": scenario["family"],
                    "observation_packet": packet,
                },
            }
        )
    return {"status": "pass", "metric_version": 3, "scenario_count": 32, "trials": trials}


def _cases_and_truth(document: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    from faultwitness_dev.g03_readiness import scenario_cases_v3

    cases = scenario_cases_v3(document)
    truth = {
        case_id: str(case["ground_truth"]["root_cause"]) for case_id, case in cases.items()
    }
    return cases, truth


def test_leave_one_case_out_threshold_never_reads_the_held_out_healthy_samples() -> None:
    """The p99 pool is built from exactly the other 31 cases.

    Mutating one case's healthy windows must move every *other* case's threshold and must not move
    its own. That is the observable consequence of a genuine leave-one-out split, and it is
    stronger than asserting the training list excludes the case.
    """
    cases, _ = _cases_and_truth(_dataset())
    before = _frozen_thresholds_loo(cases)
    target = "SEED-G02-0001"
    for entry in before[target].values():
        assert target not in entry["training_case_ids"]
        assert len(entry["training_case_ids"]) == 31
        assert entry["healthy_drift_count"] == 31 * 4

    # Inflate the held-out case's own healthy CPU drift dramatically.
    mutated = json.loads(json.dumps({k: v for k, v in cases.items()}))
    packet = mutated[target]["packet"]
    for group in packet["observations"]:
        if group["kind"] == "cpu_window":
            for position, sample in enumerate(group["samples"]):
                sample["cpu_cores"] = BASE_CPU + position * 5.0
            # Only the healthy windows matter for the pooled drift; fault windows are untouched
            # by the threshold builder, so leaving them is fine.
    packet.pop("packet_digest")
    from faultwitness_dev.g03_readiness import _digest_json

    packet["packet_digest"] = _digest_json(packet)
    after = _frozen_thresholds_loo(mutated)

    # Its own adHighCpu threshold is unchanged: its samples are excluded from its own pool. The
    # relative-floor families are exempt from this claim by construction, and adHighCpu has no
    # relative floor.
    assert after[target]["adHighCpu"]["healthy_p99"] == before[target]["adHighCpu"]["healthy_p99"]
    # Every other case's threshold does move, proving the mutated samples were in *their* pools.
    others = [case_id for case_id in before if case_id != target]
    assert all(
        after[case_id]["adHighCpu"]["healthy_p99"] > before[case_id]["adHighCpu"]["healthy_p99"]
        for case_id in others
    )


def test_threshold_builder_rejects_a_short_fold() -> None:
    cases, _ = _cases_and_truth(_dataset())
    del cases[sorted(cases)[0]]
    with pytest.raises(SeparabilityProbeError):
        _frozen_thresholds_loo(cases)


def test_forbidden_field_assertion_is_wired_into_the_offset_table() -> None:
    """A sealed key in a classifier's input is a hard stop on the real extraction path."""
    document = _dataset()
    cases, truth = _cases_and_truth(document)
    thresholds = _frozen_thresholds_loo(cases)
    target = sorted(cases)[0]
    for group in cases[target]["packet"]["observations"]:
        if group["kind"] == "cpu_window":
            group["samples"][0]["fault_class"] = "adHighCpu"
    # The packet validator rejects it first, which is the stronger guarantee; either way the
    # sealed key never reaches a classifier.
    with pytest.raises(GovernanceError):
        offset_table(cases, thresholds, truth)


def test_single_signal_ablation_consults_exactly_one_signal() -> None:
    """D4 restricted to one label can only name that label or abstain.

    The check is behavioural: the six ablation runs are recomputed from an offset table whose
    *other* five signals have been forced to qualify with enormous excesses. If a run consulted
    any signal but its own, those forced cells would capture the prediction.
    """
    document = _dataset()
    cases, truth = _cases_and_truth(document)
    thresholds = _frozen_thresholds_loo(cases)
    table = offset_table(cases, thresholds, truth)
    honest = ablation(table, truth)

    for label in LABELS:
        for row in table.values():
            for other, cell in row["signals"].items():
                if other == label:
                    continue
                cell["qualifies_p99"] = True
                cell["standardized_excess_p99"] = 10_000.0
        for case_id, row in table.items():
            prediction = classify_from_offsets(row, rule="p99", restrict_to=label)
            assert prediction in (label, ABSTAIN)
            assert prediction == honest["runs"][label]["predictions"][case_id]
        # Restore before the next label so each iteration starts from the same table.
        table = offset_table(cases, thresholds, truth)

    # Unrestricted, the same forced table is dominated by the forced signals, which confirms the
    # forcing was actually effective and the assertion above was not vacuous.
    for row in table.values():
        for other, cell in row["signals"].items():
            if other == "adHighCpu":
                continue
            cell["qualifies_p99"] = True
            cell["standardized_excess_p99"] = 10_000.0
    unrestricted = {
        case_id: classify_from_offsets(row, rule="p99") for case_id, row in table.items()
    }
    assert set(unrestricted.values()) != {"adHighCpu"}


def test_ablation_rejects_a_run_that_predicts_another_family() -> None:
    document = _dataset()
    cases, truth = _cases_and_truth(document)
    table = offset_table(cases, _frozen_thresholds_loo(cases), truth)

    def _sabotage(row: Mapping[str, Any], *, rule: str, restrict_to: str | None = None) -> str:
        return "kafkaQueueProblems" if restrict_to == "adHighCpu" else ABSTAIN

    import faultwitness_dev.g03_separability as module

    original = module.classify_from_offsets
    module.classify_from_offsets = _sabotage  # type: ignore[assignment]
    try:
        with pytest.raises(SeparabilityProbeError):
            ablation(table, truth)
    finally:
        module.classify_from_offsets = original  # type: ignore[assignment]


def test_orthogonal_signals_are_reported_as_a_lookup_table() -> None:
    """Each fault moves exactly one signal: the probe must say so rather than call it healthy."""
    report = run_separability_probe(
        _dataset(), source_run="unit", source_run_invalidated=False
    )
    assert report["diagnostic_only"] is True
    assert report["model_calls"] == 0
    assert report["n_cases"] == 32
    d1 = report["classifiers"]["D1_root_signal_p99"]["scores"]
    assert d1["accuracy"] == pytest.approx(1.0)
    ablation_result = report["d4_single_signal_ablation"]
    assert ablation_result["every_signal_identifies_its_own_family"] is True
    assert report["orthogonality"]["p99"]["single_offset_fraction"] == pytest.approx(1.0)
    readings = report["assessment"]["readings"]
    assert readings["six_way_lookup_table"]["holds"] is True
    assert readings["room_for_investigation"]["holds"] is False
    # No family is unreachable, so nothing should be flagged as a fracture here.
    assert readings["difficulty_fracture"]["holds"] is False


def test_co_occurring_signals_are_not_reported_as_a_lookup_table() -> None:
    """The probe is not a rubber stamp: overlapping signals leave discrimination work to do."""
    report = run_separability_probe(
        _dataset(cross_talk=True), source_run="unit", source_run_invalidated=False
    )
    orthogonality_result = report["orthogonality"]["p99"]
    assert orthogonality_result["mean_offset_signals_per_case"] > 1.0
    assert orthogonality_result["single_offset_fraction"] < 1.0
    assert report["assessment"]["readings"]["six_way_lookup_table"]["holds"] is False


def test_false_qualification_table_counts_foreign_cases_per_signal() -> None:
    """A signal that fires everywhere is reported as such, per rule.

    `adHighCpu`'s quantum is 1e-6, far below the ambient CPU drift these fixtures carry, so the
    bare-quantum rule must show many false qualifications and the p99 rule must show fewer. That
    contrast is the whole reason this probe replaced the threshold.
    """
    document = _dataset()
    cases, truth = _cases_and_truth(document)
    table = offset_table(cases, _frozen_thresholds_loo(cases), truth)
    counts = false_qualification_table(table, truth)
    cpu = counts["adHighCpu"]
    assert cpu["support"] == 4
    assert cpu["foreign_case_count"] == 28
    assert cpu["quantum"]["false_qualifications"] > cpu["p99"]["false_qualifications"]
    assert cpu["false_qualifications_removed_by_p99"] > 0
    for label in LABELS:
        entry = counts[label]
        assert entry["kind"] == ROOT_SIGNAL_FEATURES[label][0]
        assert entry["p99"]["false_qualifications"] <= entry["foreign_case_count"]


def test_offset_table_is_complete_and_carries_both_rules() -> None:
    document = _dataset()
    cases, truth = _cases_and_truth(document)
    table = offset_table(cases, _frozen_thresholds_loo(cases), truth)
    assert len(table) == 32
    for case_id, row in table.items():
        assert set(row["signals"]) == set(LABELS)
        assert row["root_cause"] == truth[case_id]
        for label, cell in row["signals"].items():
            assert cell["is_true_family"] == (label == truth[case_id])
            # Every cell must let a reader recompute the verdict by hand.
            for key in (
                "healthy_median",
                "fault_max",
                "incident_excess",
                "healthy_p99",
                "p99_threshold",
                "quantum_threshold",
                "qualifies_p99",
                "qualifies_quantum",
            ):
                assert key in cell


def test_orthogonality_matrix_is_symmetric_and_diagonal_dominant() -> None:
    document = _dataset(cross_talk=True)
    cases, truth = _cases_and_truth(document)
    table = offset_table(cases, _frozen_thresholds_loo(cases), truth)
    matrix = orthogonality(table, truth)["p99"]["co_occurrence_matrix"]
    for left in LABELS:
        for right in LABELS:
            assert matrix[left][right] == matrix[right][left]
            assert matrix[left][right] <= matrix[left][left]


def test_probe_records_the_source_run_and_flags_an_invalidated_origin(tmp_path: Path) -> None:
    dataset = tmp_path / "g03-4622470-r9-invalidated-example" / "scenarios.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(json.dumps(_dataset()), encoding="utf-8")
    output = tmp_path / "out" / "separability.json"
    report = run_separability_probe_from_path(dataset, output)
    assert report["source_run"] == "g03-4622470-r9-invalidated-example"
    assert report["source_run_invalidated"] is True
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["diagnostic_only"] is True
    assert written["model_calls"] == 0
    assert written["dataset_digest"] == report["dataset_digest"]


def test_probe_refuses_an_incomplete_dataset(tmp_path: Path) -> None:
    document = _dataset()
    document["trials"] = document["trials"][:31]
    dataset = tmp_path / "run" / "scenarios.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(GovernanceError):
        run_separability_probe_from_path(dataset, tmp_path / "probe.json")
    with pytest.raises(SeparabilityProbeError):
        run_separability_probe_from_path(
            tmp_path / "missing" / "scenarios.json", tmp_path / "p.json"
        )
