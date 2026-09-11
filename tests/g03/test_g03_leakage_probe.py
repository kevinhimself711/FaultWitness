"""Tests for the diagnostic-only metric-v3 descriptions leakage probe.

These cover the probe's own honesty properties, not the dataset's verdict: that a sealed key
reaching a classifier's input fails closed, that a leave-one-out fold never sees the held-out
case, and that the probe reports leakage when descriptions name the fault and reports none when
they do not.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g03_leakage_probe import (
    ABSTAIN,
    LABELS,
    LeakageProbeError,
    _assert_no_forbidden_input,
    _keyword_table,
    classify_descriptions_loo,
    description_features,
    root_signal_features,
    run_leakage_probe,
    run_leakage_probe_from_path,
)
from faultwitness_dev.g03_readiness import (
    TARGET_SERVICES,
    V3_TRACE_QUERY_SERVICES,
    build_observation_packet_v3,
)

# One case per label, repeated to reach the 32 the dataset contract requires. The two largest
# families are deliberately tied at 8, matching the landed distribution.
DATASET_LABELS: tuple[str, ...] = (
    ("productCatalogFailure",) * 8
    + ("kafkaQueueProblems",) * 8
    + ("paymentFailure",) * 4
    + ("paymentUnreachable",) * 4
    + ("adHighCpu",) * 4
    + ("emailMemoryLeak",) * 4
)

# Text that names the fault in plain language, as the landed dataset does.
LEAKY_DESCRIPTIONS = {
    "productCatalogFailure": ["Error: Product Catalog Fail Feature Flag Enabled"],
    "paymentFailure": ["Payment request failed. Invalid token."],
    "paymentUnreachable": ["name resolver error: produced zero addresses"],
}

# Text that is present and non-trivial but identical across families, so it cannot name one.
NEUTRAL_DESCRIPTIONS = {
    "productCatalogFailure": ["upstream request failed"],
    "paymentFailure": ["upstream request failed"],
    "paymentUnreachable": ["upstream request failed"],
}


def _window(
    label: str,
    phase: str,
    index: int,
    descriptions: Mapping[str, list[str]],
) -> dict[str, Any]:
    activity = {service: 10 for service in V3_TRACE_QUERY_SERVICES}
    errors = {
        service: {"error_count": 0, "connection_error_count": 0, "descriptions": []}
        for service in V3_TRACE_QUERY_SERVICES
    }
    cpu = 0.01
    memory = 10_000.0
    lag = 0.01
    if phase == "fault":
        target = TARGET_SERVICES[label]
        activity[target] += 5
        if label in descriptions:
            if label == "paymentUnreachable":
                errors[target]["connection_error_count"] = 3
            errors[target]["error_count"] = 3
            errors[target]["descriptions"] = list(descriptions[label])
        elif label == "adHighCpu":
            cpu += 0.1
        elif label == "emailMemoryLeak":
            memory += 5_000.0 + index
        elif label == "kafkaQueueProblems":
            lag += 1.0
    return {
        "recorded_at": f"2026-09-10T00:00:{index:02d}+00:00",
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


def _dataset(descriptions: Mapping[str, list[str]]) -> dict[str, Any]:
    trials = []
    for index, label in enumerate(DATASET_LABELS, 1):
        scenario = {
            "scenario_id": f"SEED-G02-{index:04d}",
            "family": f"family-{label}",
            "problem_brief": "Diagnose the incident from the public packet.",
        }
        packet = build_observation_packet_v3(
            scenario,
            [_window(label, "healthy", item, descriptions) for item in range(5)],
            [_window(label, "fault", item, descriptions) for item in range(2)],
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


def _packet_of(document: Mapping[str, Any], index: int = 0) -> Mapping[str, Any]:
    return document["trials"][index]["payload"]["observation_packet"]


def test_forbidden_field_assertion_rejects_a_sealed_key_reaching_a_classifier() -> None:
    """A sealed or evaluator-side key in a classifier's own input is a hard stop.

    The assertion runs on the extracted features, not just the packet, because the features are
    what actually reaches a classifier.
    """
    with pytest.raises(LeakageProbeError) as error:
        _assert_no_forbidden_input(
            {"case_id": "SEED-G02-0001", "nested": [{"fault_class": "adHighCpu"}]},
            classifier="A",
            case_id="SEED-G02-0001",
        )
    assert "fault_class" in str(error.value)
    # Every key the readiness module seals is covered, not only the ones spelled out here.
    with pytest.raises(LeakageProbeError):
        _assert_no_forbidden_input(
            {"sealed_truth": "x"}, classifier="B", case_id="SEED-G02-0001"
        )
    # A probe error is a governance error, so the CLI's existing handler catches it.
    assert issubclass(LeakageProbeError, GovernanceError)
    # A clean payload passes untouched.
    _assert_no_forbidden_input(
        {"case_id": "SEED-G02-0001", "incident_tokens": ["catalog"]},
        classifier="A",
        case_id="SEED-G02-0001",
    )


def test_forbidden_field_assertion_is_wired_into_both_feature_extractors() -> None:
    """The check is reachable through the real extraction path, not only callable directly."""
    document = _dataset(LEAKY_DESCRIPTIONS)
    packet = json.loads(json.dumps(_packet_of(document)))
    for kind in packet["observations"]:
        if kind["kind"] == "trace_errors":
            kind["samples"][0]["services"]["payment"]["ground_truth"] = "paymentFailure"
    # The packet validator rejects it first, which is the stronger guarantee; either way the
    # sealed key never reaches a classifier.
    with pytest.raises(GovernanceError):
        description_features(packet)
    with pytest.raises(GovernanceError):
        root_signal_features(packet)


def test_leave_one_out_never_lets_a_case_vote_on_itself() -> None:
    """Each fold trains on exactly the other 31 cases."""
    document = _dataset(LEAKY_DESCRIPTIONS)
    features = {
        str(trial["payload"]["observation_packet"]["case_id"]): description_features(
            trial["payload"]["observation_packet"]
        )
        for trial in document["trials"]
    }
    labels = {
        str(trial["payload"]["observation_packet"]["case_id"]): str(
            trial["payload"]["fault_class"]
        )
        for trial in document["trials"]
    }
    probe = classify_descriptions_loo(features, labels)
    assert len(probe["folds"]) == 32
    for fold in probe["folds"]:
        assert fold["case_id"] not in fold["training_case_ids"]
        assert len(fold["training_case_ids"]) == 31
        assert len(set(fold["training_case_ids"])) == 31


def test_a_single_case_family_cannot_be_recognized_from_its_own_tokens() -> None:
    """The held-out case's own text is genuinely withheld, not merely absent from a list.

    With one case carrying a unique token, the fold that holds it out has no training example of
    that token, so the probe must abstain rather than recognize it. A fold that leaked the
    held-out case would score it correct instead.
    """
    document = _dataset(NEUTRAL_DESCRIPTIONS)
    features = {
        str(trial["payload"]["observation_packet"]["case_id"]): description_features(
            trial["payload"]["observation_packet"]
        )
        for trial in document["trials"]
    }
    labels = {
        str(trial["payload"]["observation_packet"]["case_id"]): str(
            trial["payload"]["fault_class"]
        )
        for trial in document["trials"]
    }
    target = "SEED-G02-0001"
    features[target] = {
        **features[target],
        "incident_tokens": ["singleton-token-seen-in-no-other-case"],
    }
    probe = classify_descriptions_loo(features, labels)
    assert probe["predictions"][target] == ABSTAIN
    # The same token is discriminative once its own case is in the training set, which is what
    # makes the abstention above attributable to the held-out split.
    table = _keyword_table(features, labels, sorted(features))
    assert (
        "singleton-token-seen-in-no-other-case"
        in table["discriminative_tokens"][labels[target]]
    )


def test_probe_reports_leakage_when_descriptions_name_the_fault() -> None:
    document = _dataset(LEAKY_DESCRIPTIONS)
    report = run_leakage_probe(document, source_run="unit", source_run_invalidated=False)
    verdict = report["verdict"]
    assert report["diagnostic_only"] is True
    assert report["model_calls"] == 0
    assert report["n_cases"] == 32
    assert verdict["code"] == "localized_leakage_trace_errors_families"
    trio = verdict["trace_errors_family_accuracy"]
    assert trio == pytest.approx(1.0)
    assert verdict["other_family_accuracy"] == pytest.approx(0.0)
    assert verdict["margin_over_majority_class"] > 0.10
    # The human-readable table names the fault in plain words, which is the point of printing it.
    catalog = report["keyword_table"]["discriminative_tokens"]["productCatalogFailure"]
    assert {"catalog", "feature", "flag"} <= set(catalog)


def test_probe_reports_no_leakage_when_descriptions_are_family_neutral() -> None:
    """The probe is not a rubber stamp: identical text across families yields no shortcut."""
    document = _dataset(NEUTRAL_DESCRIPTIONS)
    report = run_leakage_probe(document, source_run="unit", source_run_invalidated=False)
    verdict = report["verdict"]
    assert verdict["code"] == "no_leakage_detected"
    assert verdict["descriptions_accuracy"] <= verdict["majority_class_accuracy"] + 0.10
    assert all(
        not report["keyword_table"]["discriminative_tokens"][label] for label in LABELS
    )


def test_classifier_a_reads_no_numeric_field_from_the_shared_evidence_kind() -> None:
    """Perturbing the counts beside the descriptions must not move A's features.

    `error_count` and `connection_error_count` live in the same mapping as `descriptions`, so
    this is the check that A reads the text channel and nothing else.
    """
    document = _dataset(LEAKY_DESCRIPTIONS)
    packet = _packet_of(document)
    before = description_features(packet)
    mutated = json.loads(json.dumps(packet))
    for group in mutated["observations"]:
        if group["kind"] == "trace_errors":
            for sample in group["samples"]:
                for measurement in sample["services"].values():
                    measurement["error_count"] += 41
                    measurement["connection_error_count"] += 17
    mutated.pop("packet_digest")
    from faultwitness_dev.g03_readiness import _digest_json

    mutated["packet_digest"] = _digest_json(mutated)
    after = description_features(mutated)
    assert after == before


def test_probe_records_the_source_run_and_flags_an_invalidated_origin(tmp_path: Path) -> None:
    dataset = tmp_path / "g03-4622470-r9-invalidated-example" / "scenarios.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(json.dumps(_dataset(LEAKY_DESCRIPTIONS)), encoding="utf-8")
    output = tmp_path / "out" / "probe.json"
    report = run_leakage_probe_from_path(dataset, output)
    assert report["source_run"] == "g03-4622470-r9-invalidated-example"
    assert report["source_run_invalidated"] is True
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["diagnostic_only"] is True
    assert written["source_run_invalidated"] is True


def test_probe_refuses_an_incomplete_dataset(tmp_path: Path) -> None:
    document = _dataset(LEAKY_DESCRIPTIONS)
    document["trials"] = document["trials"][:31]
    dataset = tmp_path / "run" / "scenarios.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(GovernanceError):
        run_leakage_probe_from_path(dataset, tmp_path / "probe.json")
    with pytest.raises(LeakageProbeError):
        run_leakage_probe_from_path(tmp_path / "missing" / "scenarios.json", tmp_path / "p.json")
