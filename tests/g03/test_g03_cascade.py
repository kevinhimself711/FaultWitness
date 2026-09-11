"""Tests for the diagnostic-only metric-v3 cascade-existence probe (criterion E).

These cover the probe's honesty properties rather than the dataset's numbers. The property that
matters most is the one the probe exists for: a zero reading must mean "propagation did not happen"
and never "nothing downstream was queried". So the probe has to refuse to run on a 1:1 scope, refuse
when a queried service is missing from the packet, subtract each service's own healthy errors before
calling anything propagation, and report per case rather than collapsing to a rate that would hide
whether propagation lands on the same neighbours every time.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from faultwitness_dev.g02_lab import V3_TRACE_QUERY_SERVICES
from faultwitness_dev.g03_cascade import (
    INTERPRETATION,
    UPSTREAM_OF,
    CascadeProbeError,
    cascade_candidate_families,
    case_row,
    run_cascade_probe,
    run_cascade_probe_from_path,
    uninjected_services,
)
from faultwitness_dev.g03_readiness import (
    TARGET_SERVICES,
    DatasetIncompleteError,
    _digest_json,
    build_observation_packet_v3,
    scenario_cases_v3,
)

DATASET_LABELS: tuple[str, ...] = (
    ("productCatalogFailure",) * 8
    + ("kafkaQueueProblems",) * 8
    + ("paymentFailure",) * 4
    + ("paymentUnreachable",) * 4
    + ("adHighCpu",) * 4
    + ("emailMemoryLeak",) * 4
)

BASE_CPU = 0.01
BASE_MEMORY = 50_000_000.0
BASE_LAG = 0.01

#: Propagation carriers per case index, keyed by scenario number. A test installs exactly the
#: pattern it wants to read back, so nothing about the assertion depends on ambient fixture values.
PropagationPlan = Mapping[int, Sequence[str]]


def _window(
    label: str,
    phase: str,
    index: int,
    *,
    propagate_to: Sequence[str] = (),
    noisy_services: Sequence[str] = (),
) -> dict[str, Any]:
    """One observation window.

    `propagate_to` puts fault-phase errors on the named uninjected services, which is the
    observable form of a cascade. `noisy_services` puts the *same* error count on both phases, so
    the service is non-zero under fault yet demonstrates nothing -- the case the healthy-baseline
    subtraction has to catch.
    """
    activity = {service: 10 for service in V3_TRACE_QUERY_SERVICES}
    errors = {
        service: {"error_count": 0, "connection_error_count": 0, "descriptions": []}
        for service in V3_TRACE_QUERY_SERVICES
    }
    for service in noisy_services:
        errors[service]["error_count"] = 4
    if phase == "fault":
        target = TARGET_SERVICES[label]
        activity[target] += 5
        if label in ("productCatalogFailure", "paymentFailure"):
            errors[target]["error_count"] = 6
        elif label == "paymentUnreachable":
            errors[target]["connection_error_count"] = 6
            errors[target]["error_count"] = 6
        for service in propagate_to:
            errors[service]["error_count"] = errors[service]["error_count"] + 3
    return {
        "recorded_at": f"2026-09-11T00:00:{index:02d}+00:00",
        "ready": True,
        "journey_status": 200,
        "cpu_rate": BASE_CPU + index * 0.001,
        "working_set": BASE_MEMORY + index * 100_000.0,
        "consumer_lag": BASE_LAG + index * 0.005,
        "consumer_record_lag": BASE_LAG + index * 0.005,
        "consumer_poll_lag_seconds": BASE_LAG + index * 0.005,
        "trace_activity": activity,
        "trace_errors": errors,
    }


def _dataset(
    *,
    propagation: PropagationPlan | None = None,
    noisy: PropagationPlan | None = None,
) -> dict[str, Any]:
    propagation = propagation or {}
    noisy = noisy or {}
    trials = []
    for index, label in enumerate(DATASET_LABELS, 1):
        scenario = {
            "scenario_id": f"SEED-G02-{index:04d}",
            "family": f"family-{label}",
            "problem_brief": "Diagnose the incident from the public packet.",
        }
        carriers = propagation.get(index, ())
        noise = noisy.get(index, ())
        packet = build_observation_packet_v3(
            scenario,
            [
                _window(label, "healthy", item, noisy_services=noise)
                for item in range(5)
            ],
            [
                _window(label, "fault", item, propagate_to=carriers, noisy_services=noise)
                for item in range(2)
            ],
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


def _probe(document: Mapping[str, Any]) -> dict[str, Any]:
    return run_cascade_probe(document, source_run="g03-test", source_run_invalidated=False)


def _row(report: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    return next(row for row in report["cases"] if row["case_id"] == case_id)


def test_criterion_e_is_unanswerable_on_a_one_to_one_scope() -> None:
    """The probe refuses rather than reporting a negative when nothing downstream was queried.

    This is the whole reason the module exists. On the pre-widening scope the observation set was
    exactly the injection targets, so no cascade *could* appear and a zero reading carried no
    information. Returning `cascade_exists: false` there would manufacture the false conclusion
    the probe was written to remove, so refusing is the correct behaviour.
    """
    injected = tuple(sorted(set(TARGET_SERVICES.values())))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("faultwitness_dev.g03_cascade.V3_TRACE_QUERY_SERVICES", injected)
        with pytest.raises(CascadeProbeError, match="strictly wider"):
            _probe(_dataset())


def test_a_service_that_also_errors_while_healthy_is_not_reported_as_propagation() -> None:
    """Non-zero under fault is not enough; the excess over the service's own healthy level is.

    `frontend` here carries the same four errors in both phases. A probe keyed on `nonzero_in_fault`
    would call that a cascade on every case of the family and would report propagation that the
    fault did not cause.
    """
    report = _probe(_dataset(noisy={1: ("frontend",)}))
    row = _row(report, "SEED-G02-0001")
    services = row["services"]
    assert services["frontend"]["nonzero_in_fault"] is True
    assert services["frontend"]["nonzero_in_healthy"] is True
    assert services["frontend"]["excess_over_healthy"] == 0
    assert row["propagating_uninjected_services"] == []
    assert row["cascade_observed"] is False
    assert report["assessment"]["cascade_exists"] is False


def test_propagation_on_an_uninjected_upstream_service_is_reported_per_case() -> None:
    """One case's cascade is visible as itself, not only as a family rate."""
    report = _probe(_dataset(propagation={1: ("frontend", "recommendation")}))
    row = _row(report, "SEED-G02-0001")
    assert row["root_cause"] == "productCatalogFailure"
    assert row["injected_service"] == "product-catalog"
    assert row["cascade_candidate"] is True
    assert row["propagating_uninjected_services"] == ["frontend", "recommendation"]
    assert row["propagating_upstream_services"] == ["frontend", "recommendation"]
    assert row["cascade_observed"] is True
    assert row["services"]["frontend"]["excess_over_healthy"] == 3

    # Every other case of the same family stays false, so the row is the reading and the family
    # count is derived from rows rather than replacing them.
    others = [
        r for r in report["cases"] if r["root_cause"] == "productCatalogFailure"
        and r["case_id"] != "SEED-G02-0001"
    ]
    assert others
    assert all(r["cascade_observed"] is False for r in others)
    family = report["families"]["productCatalogFailure"]
    assert family["cascade_observed_count"] == 1
    assert family["n"] == 8
    assert report["assessment"]["cascade_exists"] is True
    assert report["assessment"]["candidate_cases_with_cascade"] == 1


def test_one_pattern_per_family_reads_as_deterministic_and_two_do_not() -> None:
    """The lookup-table-versus-discrimination distinction the per-case reporting exists to make.

    A family that always propagates to the same neighbours has grown its cell in the lookup table.
    A family whose carriers vary between cases requires the reader to discriminate. Collapsing to a
    rate would make these two identical, and they point opposite ways on whether widening helped.
    """
    same = _probe(
        _dataset(propagation={1: ("frontend", "recommendation"), 2: ("frontend", "recommendation")})
    )
    entry = same["families"]["productCatalogFailure"]
    assert entry["distinct_propagation_patterns"] == 1
    assert entry["propagation_pattern_is_unique"] is True
    assert same["assessment"]["propagation_is_deterministic"] is True
    assert same["assessment"]["reading"] == "cascade_present_single_pattern_per_family"

    varied = _probe(_dataset(propagation={1: ("frontend", "recommendation"), 2: ("frontend",)}))
    entry = varied["families"]["productCatalogFailure"]
    assert entry["distinct_propagation_patterns"] == 2
    assert entry["propagation_pattern_is_unique"] is False
    assert varied["assessment"]["propagation_is_deterministic"] is False
    assert varied["assessment"]["reading"] == "cascade_present_varying_pattern"


def test_candidate_families_are_derived_from_the_trace_scope_not_listed() -> None:
    """Only families whose target has a queried caller can answer E.

    `adHighCpu`, `emailMemoryLeak` and `kafkaQueueProblems` have no upstream in the queried scope,
    so a zero reading on them is not evidence either way. Deriving the candidate set from the scope
    means widening or narrowing the scope cannot leave a stale hand-written list behind.
    """
    assert cascade_candidate_families() == (
        "paymentFailure",
        "paymentUnreachable",
        "productCatalogFailure",
    )
    report = _probe(_dataset())
    assert report["candidate_families"] == list(cascade_candidate_families())
    for row in report["cases"]:
        upstream = set(UPSTREAM_OF.get(row["injected_service"], ()))
        expected = bool(upstream & set(report["trace_scope"]))
        assert row["cascade_candidate"] is expected
    for label in ("adHighCpu", "emailMemoryLeak", "kafkaQueueProblems"):
        assert report["families"][label]["cascade_candidate"] is False


def test_a_cascade_outside_the_candidate_set_is_surfaced_rather_than_dropped() -> None:
    """A propagation the declared call graph does not predict means the graph is wrong.

    `adHighCpu`'s target has no queried caller, so the case is outside criterion E. Silently
    dropping errors seen there would hide a defect in `UPSTREAM_OF` itself.
    """
    ad_case = 1 + DATASET_LABELS.index("adHighCpu")
    report = _probe(_dataset(propagation={ad_case: ("cart",)}))
    case_id = f"SEED-G02-{ad_case:04d}"
    row = _row(report, case_id)
    assert row["root_cause"] == "adHighCpu"
    assert row["cascade_candidate"] is False
    assert row["cascade_observed"] is True
    assessment = report["assessment"]
    assert assessment["non_candidate_cases_with_cascade"] == [case_id]
    # It is reported, and it does not answer E, which is only about candidate cases.
    assert assessment["cascade_exists"] is False
    assert assessment["candidate_cases_with_cascade"] == 0


def test_a_queried_service_missing_from_the_packet_fails_closed() -> None:
    """A collector that did not follow the widening must not read as "no propagation".

    This is the same confusion as the 1:1 scope, one layer down: absent instrumentation and an
    observed zero are different facts, and the artifact must not merge them. Two layers refuse it.
    `validate_observation_packet_v3` rejects the dataset first, which is the path a real run takes;
    the probe's own guard covers `case_row` being called on an already-loaded case, so neither layer
    depends on the other still being there.
    """
    document = _dataset()
    packet = document["trials"][0]["payload"]["observation_packet"]
    for group in packet["observations"]:
        if group["kind"] == "trace_errors":
            for sample in group["samples"]:
                sample["services"].pop("frontend")
    with pytest.raises(DatasetIncompleteError, match="trace_errors sample service set drifted"):
        _probe(document)

    case = scenario_cases_v3(_dataset())["SEED-G02-0001"]
    for group in case["packet"]["observations"]:
        if group["kind"] == "trace_errors":
            for sample in group["samples"]:
                sample["services"].pop("frontend")
    with pytest.raises(CascadeProbeError, match="does not cover the queried service frontend"):
        case_row("SEED-G02-0001", case)


def test_a_service_jaeger_never_saw_is_not_read_as_absence_of_propagation() -> None:
    """Zero traces and zero errors are different facts, and Jaeger returns the same number for both.

    Prometheus reports a missing series as null, which the collector classifies as infrastructure.
    Jaeger has no such signal: a service it has never seen simply returns no traces, and the
    collector records `trace_count: 0` and `error_count: 0`. That zero is the 1:1-scope problem
    surviving the widening -- nothing downstream was observed -- so a verdict built only on such
    cases must not read as `cascade_absent`.
    """
    document = _dataset()
    for trial in document["trials"]:
        packet = trial["payload"]["observation_packet"]
        for group in packet["observations"]:
            if group["kind"] != "trace_activity":
                continue
            for sample in group["samples"]:
                for service in uninjected_services():
                    sample["services"][service]["trace_count"] = 0
        packet.pop("packet_digest")
        packet["packet_digest"] = _digest_json(packet)

    report = _probe(document)
    assessment = report["assessment"]
    assert assessment["e_verdict"] == "cascade_unobservable"
    assert assessment["reading"] == (
        "cascade_unobservable_no_upstream_traces_in_any_candidate_case"
    )
    assert assessment["candidate_cases_answerable"] == 0
    assert len(assessment["candidate_cases_with_no_upstream_traces"]) == (
        assessment["candidate_case_count"]
    )
    row = _row(report, "SEED-G02-0001")
    assert row["unobserved_uninjected_services"] == list(uninjected_services())
    assert row["cascade_unobservable_on_all_upstream"] is True
    assert row["services"]["frontend"]["observed_under_fault"] is False

    # With traces present and still no errors, the same zero *is* a measurement, and the verdict
    # separates the two cases rather than collapsing them.
    clean = _probe(_dataset())
    assert clean["assessment"]["e_verdict"] == "cascade_absent"
    assert clean["assessment"]["candidate_cases_answerable"] == (
        clean["assessment"]["candidate_case_count"]
    )
    assert _row(clean, "SEED-G02-0001")["services"]["frontend"]["observed_under_fault"] is True


def test_the_report_carries_the_switch_mechanism_for_a_negative_reading() -> None:
    """A gate with a stop and no switch reads to the next session as the end of the project.

    Criterion E's registered interpretation table says what to do in each of the four combinations,
    including that a flagd surface which does not propagate means changing the injection surface
    rather than abandoning the work. That sentence has to survive in the artifact, not only in the
    pre-registration, because the artifact is what a later reader opens.
    """
    report = _probe(_dataset())
    assert report["interpretation"] == dict(INTERPRETATION)
    absent = report["interpretation"]["cascade_absent_d1_high"]
    assert "injection surface" in absent
    assert "NOT the end of the project" in absent
    assert "independent of the D1" in report["assessment"]["d1_is_not_measured_here"]


def test_products_are_diagnostic_only_and_reproducible(tmp_path: Path) -> None:
    """Zero model calls, never promotable, and byte-identical on a re-run but for the timestamp."""
    document = _dataset(propagation={1: ("frontend",)})
    dataset_path = tmp_path / "g03-wide-r1" / "scenarios.json"
    dataset_path.parent.mkdir(parents=True)
    dataset_path.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "cascade.json"

    first = run_cascade_probe_from_path(dataset_path, output)
    assert first["diagnostic_only"] is True
    assert first["model_calls"] == 0
    assert "never promotable" in first["promotion"]
    assert first["source_run"] == "g03-wide-r1"
    assert first["source_run_invalidated"] is False
    assert first["n_cases"] == 32
    assert first["uninjected_services"] == list(uninjected_services())
    assert first["dataset_digest"]

    written = json.loads(output.read_text(encoding="utf-8"))
    second = run_cascade_probe_from_path(dataset_path, output)
    for report in (written, second):
        assert {k: v for k, v in report.items() if k != "generated_at"} == {
            k: v for k, v in first.items() if k != "generated_at"
        }


def test_an_invalidated_source_run_is_carried_into_the_artifact(tmp_path: Path) -> None:
    """Provenance travels with the reading; an invalidated run must not look clean downstream."""
    dataset_path = tmp_path / "g03-invalidated-20260911" / "scenarios.json"
    dataset_path.parent.mkdir(parents=True)
    dataset_path.write_text(json.dumps(_dataset()), encoding="utf-8")
    report = run_cascade_probe_from_path(dataset_path, tmp_path / "out.json")
    assert report["source_run_invalidated"] is True


def test_the_probe_reads_only_a_landed_dataset(tmp_path: Path) -> None:
    missing = tmp_path / "absent" / "scenarios.json"
    with pytest.raises(CascadeProbeError, match="unreadable"):
        run_cascade_probe_from_path(missing, tmp_path / "out.json")

    malformed = tmp_path / "run" / "scenarios.json"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(CascadeProbeError, match="root is not an object"):
        run_cascade_probe_from_path(malformed, tmp_path / "out.json")


def test_every_case_row_covers_the_full_queried_scope() -> None:
    """Injected and uninjected services sit side by side, so a reader can compare them directly."""
    report = _probe(_dataset())
    cases = scenario_cases_v3(_dataset())
    assert len(report["cases"]) == len(cases)
    for row in report["cases"]:
        assert set(row["services"]) == set(V3_TRACE_QUERY_SERVICES)
        target = row["injected_service"]
        assert row["services"][target]["is_injected_target"] is True
        assert sum(1 for cell in row["services"].values() if cell["is_injected_target"]) == 1
