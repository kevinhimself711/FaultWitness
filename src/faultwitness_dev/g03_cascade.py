"""Diagnostic-only cascade-existence probe for the widened metric-v3 trace scope.

This answers one question, registered as criterion E in
`docs/engineering/diagnostics/g03-observation-scope-widening/PRE_REGISTRATION.md`:

    When a fault is injected into one service, do the *uninjected* services that call it show
    trace errors of their own?

It exists because the separability probe's all-zero off-diagonal co-occurrence matrix admits two
incompatible readings. Either faults genuinely do not propagate across services in this SUT, or
nothing downstream of an injected service was ever queried -- the observation scope was 1:1 with
the label set, so propagation was unobservable by construction. Those readings point opposite ways
on whether widening the scope can make the task harder, and no existing artifact separates them.
Criterion E is independent of the D1 lookup-table gate and is reported separately from it: a D1
drop with no cascade is a *worse* outcome than no drop at all, because it means the widening added
noise and would be mistaken for added difficulty.

The probe reports per case and does not aggregate. A single family-level rate would hide exactly
the thing worth seeing: whether propagation, when it happens, always lands on the same neighbours
(a bigger lookup table) or varies across cases (real discrimination work). Counts are reported
beside the per-case rows, never in place of them.

`diagnostic_only: true`. Products here are never promotable to readiness evidence, register no work
item, and change no threshold. Zero model calls: this reads a dataset that already exists.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_lab import V3_TRACE_QUERY_SERVICES
from faultwitness_dev.g03_readiness import (
    METRIC_VERSION,
    TARGET_SERVICES,
    dataset_digest_v3,
    scenario_cases_v3,
    write_json_artifact_v3,
)

#: Which uninjected services are plausible carriers of propagation from which injected service.
#: These are call-graph relations in the OpenTelemetry demo, not measurements: frontend and
#: recommendation call product-catalog; frontend and cart sit either side of checkout and payment.
#: Declaring the relation up front is what makes a non-zero reading interpretable -- an error on a
#: service with no call path to the injected one would be ambient noise, not propagation.
UPSTREAM_OF: Mapping[str, tuple[str, ...]] = {
    "product-catalog": ("frontend", "recommendation"),
    "payment": ("frontend", "cart"),
    "checkout": ("frontend", "cart"),
}

#: The registered form of criterion E, carried into the artifact so a reader of the JSON alone can
#: see which branch the measurement lands on. The last row is the reason this table exists: a
#: failed gate exits by switching mechanism, not by stopping. A gate with a stop and no switch
#: reads to the next session as the end of the project.
INTERPRETATION: Mapping[str, str] = {
    "cascade_present_d1_drops": (
        "widening worked; propagation is a real source of difficulty; continue to 3b"
    ),
    "cascade_present_d1_high": (
        "propagation exists but its pattern is unique per family, so the task is still a lookup "
        "table with larger cells; the next mechanism is multi-fault injection, not a dead end"
    ),
    "cascade_absent_d1_drops": (
        "alarm: the D1 drop comes from noise rather than difficulty. This is a false positive and "
        "is more dangerous than D1 staying high, because it looks like success"
    ),
    "cascade_absent_d1_high": (
        "the flagd injection surface does not produce cross-service propagation. That is a "
        "property of the SUT, and a wider observation scope cannot fix it; the exit is to change "
        "the injection surface (kubectl, NetworkPolicy, multiple simultaneous flags). "
        "This is NOT the end of the project"
    ),
}


class CascadeProbeError(GovernanceError):
    """The probe cannot run honestly, as opposed to running and reporting a negative."""


def uninjected_services() -> tuple[str, ...]:
    """Queried services that are never fault-injection targets, in the queried order."""
    injected = set(TARGET_SERVICES.values())
    return tuple(service for service in V3_TRACE_QUERY_SERVICES if service not in injected)


def cascade_candidate_families() -> tuple[str, ...]:
    """Families whose injected service has at least one queried upstream caller.

    Derived rather than listed, so it cannot drift from the trace scope. The other families'
    targets have no caller in the queried scope, which means a zero reading there is not evidence
    either way -- those cases are reported but excluded from the criterion.
    """
    queried = set(V3_TRACE_QUERY_SERVICES)
    return tuple(
        label
        for label, target in sorted(TARGET_SERVICES.items())
        if queried.intersection(UPSTREAM_OF.get(target, ()))
    )


def _phase_samples(packet: Mapping[str, Any], kind: str, phase: str) -> list[Mapping[str, Any]]:
    """The samples of one evidence group belonging to one phase.

    Phase comes from the packet's own window list rather than from the sample, because public
    samples carry no phase field -- `_public_window` strips it when projecting.
    """
    phases = [str(window["phase"]) for window in packet["windows"]]
    group = next(
        (item for item in packet["observations"] if str(item.get("kind")) == kind),
        None,
    )
    if group is None:
        raise CascadeProbeError(f"packet lacks evidence kind: {kind}")
    samples = group.get("samples")
    if not isinstance(samples, list) or len(samples) != len(phases):
        raise CascadeProbeError(f"evidence kind {kind} does not align with the window list")
    return [
        sample
        for sample, sample_phase in zip(samples, phases, strict=True)
        if sample_phase == phase
    ]


def case_row(case_id: str, case: Mapping[str, Any]) -> dict[str, Any]:
    """One case's per-service error readings, injected and uninjected side by side.

    A non-zero count on an uninjected service is the observable form of propagation. The healthy
    maximum is carried for every service so a reader can tell propagation from a service that is
    simply noisy: errors under fault on a service that also shows errors while healthy prove
    nothing. `excess_over_healthy` is the reading criterion E turns on.
    """
    packet = case["packet"]
    label = str(case["ground_truth"]["root_cause"])
    try:
        target = TARGET_SERVICES[label]
    except KeyError as error:
        raise CascadeProbeError(f"{case_id} carries an unknown sealed label: {label}") from error
    fault = _phase_samples(packet, "trace_errors", "fault")
    healthy = _phase_samples(packet, "trace_errors", "healthy")
    if not fault or not healthy:
        raise CascadeProbeError(f"{case_id} lacks both phases of trace_errors samples")
    activity = _phase_samples(packet, "trace_activity", "fault")

    services: dict[str, Any] = {}
    for service in V3_TRACE_QUERY_SERVICES:
        for kind, samples in (("trace_errors", (*fault, *healthy)), ("trace_activity", activity)):
            if any(service not in sample.get("services", {}) for sample in samples):
                # A queried service absent from the packet means the widening did not reach the
                # collector. Reporting zero here would read as "no propagation observed", which is
                # the exact confusion this probe exists to remove.
                raise CascadeProbeError(
                    f"{case_id} {kind} does not cover the queried service {service}"
                )
        fault_error = max(int(sample["services"][service]["error_count"]) for sample in fault)
        fault_conn = max(
            int(sample["services"][service]["connection_error_count"]) for sample in fault
        )
        healthy_error = max(int(sample["services"][service]["error_count"]) for sample in healthy)
        healthy_conn = max(
            int(sample["services"][service]["connection_error_count"]) for sample in healthy
        )
        total_fault = fault_error + fault_conn
        total_healthy = healthy_error + healthy_conn
        # Jaeger returns no traces for a service it has never seen, and the collector records that
        # as zero rather than as absent (unlike Prometheus, where a missing series becomes null and
        # is classified as infrastructure). So a service with no fault-phase traces has an error
        # count of zero for a reason that has nothing to do with propagation, and criterion E must
        # be able to tell the two apart. Carried per service rather than raised: for a service that
        # genuinely receives no traffic in a window this is a fact about the SUT, not a defect.
        fault_traces = max(
            int(sample["services"][service]["trace_count"]) for sample in activity
        ) if activity else 0
        services[service] = {
            "is_injected_target": service == target,
            "is_upstream_of_target": service in UPSTREAM_OF.get(target, ()),
            "fault_trace_count_max": fault_traces,
            "observed_under_fault": fault_traces > 0,
            "fault_error_max": fault_error,
            "fault_connection_error_max": fault_conn,
            "healthy_error_max": healthy_error,
            "healthy_connection_error_max": healthy_conn,
            "nonzero_in_fault": total_fault > 0,
            "nonzero_in_healthy": total_healthy > 0,
            "excess_over_healthy": max(0, total_fault - total_healthy),
        }

    upstream = tuple(UPSTREAM_OF.get(target, ()))
    uninjected = uninjected_services()
    propagating = sorted(
        service for service in uninjected if services[service]["excess_over_healthy"] > 0
    )
    # An uninjected service Jaeger never saw under fault cannot demonstrate propagation and cannot
    # refute it either. Naming those cases is what keeps a zero row honest.
    unobserved = sorted(
        service for service in uninjected if not services[service]["observed_under_fault"]
    )
    return {
        "case_id": case_id,
        "root_cause": label,
        "injected_service": target,
        "upstream_services_queried": [s for s in upstream if s in V3_TRACE_QUERY_SERVICES],
        "unobserved_uninjected_services": unobserved,
        "cascade_unobservable_on_all_upstream": all(
            not services[s]["observed_under_fault"] for s in upstream if s in services
        )
        and bool(upstream),
        "cascade_candidate": label in cascade_candidate_families(),
        "injected_service_excess": services[target]["excess_over_healthy"],
        "injected_service_nonzero": services[target]["excess_over_healthy"] > 0,
        "propagating_uninjected_services": propagating,
        "propagating_upstream_services": [s for s in propagating if s in upstream],
        "cascade_observed": bool(propagating),
        "services": services,
    }


def _family_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts per family, reported *beside* the per-case rows and never instead of them."""
    families: dict[str, Any] = {}
    for row in rows:
        entry = families.setdefault(
            str(row["root_cause"]),
            {
                "n": 0,
                "cascade_observed_count": 0,
                "cascade_candidate": bool(row["cascade_candidate"]),
                "injected_service": str(row["injected_service"]),
                "propagation_patterns": {},
            },
        )
        entry["n"] += 1
        if row["cascade_observed"]:
            entry["cascade_observed_count"] += 1
        pattern = ",".join(row["propagating_uninjected_services"]) or "(none)"
        entry["propagation_patterns"][pattern] = entry["propagation_patterns"].get(pattern, 0) + 1
    for entry in families.values():
        entry["cascade_observed_rate"] = entry["cascade_observed_count"] / entry["n"]
        # One pattern across every case of a family means propagation is deterministic: the lookup
        # table grew but is still a lookup table. That distinction is the cascade_present_d1_high
        # branch of the registered interpretation table, and it is the reason this probe reports
        # patterns rather than only a rate.
        observed = {
            pattern: count
            for pattern, count in entry["propagation_patterns"].items()
            if pattern != "(none)"
        }
        entry["distinct_propagation_patterns"] = len(observed)
        entry["propagation_pattern_is_unique"] = len(observed) == 1
    return families


def _assessment(rows: Sequence[Mapping[str, Any]], families: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [row for row in rows if row["cascade_candidate"]]
    observed = [row for row in candidates if row["cascade_observed"]]
    non_candidates_with_cascade = sorted(
        str(row["case_id"])
        for row in rows
        if not row["cascade_candidate"] and row["cascade_observed"]
    )
    # Candidate cases where no upstream service was seen by Jaeger at all under fault. Their zero
    # is unobservability, not absence of propagation, so a negative E has to report how many of its
    # own cases could not have answered either way.
    unobservable = sorted(
        str(row["case_id"])
        for row in candidates
        if row["cascade_unobservable_on_all_upstream"]
    )
    candidate_families = {
        name: entry for name, entry in families.items() if entry["cascade_candidate"]
    }
    with_cascade = sorted(
        name for name, entry in candidate_families.items() if entry["cascade_observed_count"]
    )
    unique_pattern = sorted(
        name
        for name, entry in candidate_families.items()
        if entry["cascade_observed_count"] and entry["propagation_pattern_is_unique"]
    )
    deterministic = bool(with_cascade) and unique_pattern == with_cascade
    return {
        "criterion": "E_cascade_existence",
        "question": (
            "When a fault is injected into one service, do the uninjected services that call it "
            "show trace errors of their own?"
        ),
        "candidate_case_count": len(candidates),
        "candidate_cases_with_cascade": len(observed),
        "candidate_cases_with_no_upstream_traces": unobservable,
        "candidate_cases_answerable": len(candidates) - len(unobservable),
        "candidate_families": sorted(candidate_families),
        "families_with_cascade": with_cascade,
        "families_with_unique_propagation_pattern": unique_pattern,
        # E holds if propagation is observed on any candidate case. Deliberately not gated on a
        # rate: the pre-registration asks whether propagation exists, not how often, and one
        # reproducible cascade makes the phenomenon real. The rate is reported per family instead.
        "cascade_exists": bool(observed),
        "every_candidate_family_cascades": (
            bool(candidate_families) and len(with_cascade) == len(candidate_families)
        ),
        "propagation_is_deterministic": deterministic,
        # Cases outside the candidate set are not part of the criterion, but a cascade appearing
        # there would mean the declared call graph is wrong, so it is surfaced rather than dropped.
        "non_candidate_cases_with_cascade": non_candidates_with_cascade,
        "e_verdict": (
            "cascade_present"
            if observed
            # A negative built entirely on cases where no upstream service was traced is not a
            # negative. It is the 1:1-scope problem surviving the widening, and saying
            # "cascade_absent" there would be the same false conclusion in a new place.
            else "cascade_unobservable"
            if len(unobservable) == len(candidates)
            else "cascade_absent"
        ),
        "reading": (
            "cascade_unobservable_no_upstream_traces_in_any_candidate_case"
            if not observed and len(unobservable) == len(candidates)
            else "cascade_absent_injection_surface_does_not_propagate"
            if not observed
            else "cascade_present_single_pattern_per_family"
            if deterministic
            else "cascade_present_varying_pattern"
        ),
        "d1_is_not_measured_here": (
            "Criterion E is independent of the D1 lookup-table gate. Read this artifact together "
            "with the separability probe's D1 and pick the matching row of `interpretation`."
        ),
    }


def run_cascade_probe(
    document: Mapping[str, Any],
    *,
    source_run: str,
    source_run_invalidated: bool,
) -> dict[str, Any]:
    """Answer criterion E over a landed metric-v3 scenario document. Zero model calls."""
    injected = set(TARGET_SERVICES.values())
    observed_scope = set(V3_TRACE_QUERY_SERVICES)
    if not injected < observed_scope:
        raise CascadeProbeError(
            "cascade probe requires a trace scope strictly wider than the injection targets; "
            "with a 1:1 scope propagation is unobservable and a zero reading means nothing"
        )
    candidates = cascade_candidate_families()
    if not candidates:
        raise CascadeProbeError(
            "no injected service has a queried upstream caller, so criterion E is unanswerable "
            "on this trace scope"
        )
    cases = scenario_cases_v3(document)
    rows = [case_row(case_id, cases[case_id]) for case_id in sorted(cases)]
    families = _family_summary(rows)
    return {
        "probe": "metric-v3 cascade existence",
        "diagnostic_only": True,
        "promotion": (
            "diagnostic_only: never promotable to readiness evidence, registers no work item, and "
            "changes no threshold."
        ),
        "model_calls": 0,
        "metric_version": METRIC_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_run": source_run,
        "source_run_invalidated": source_run_invalidated,
        "dataset_digest": dataset_digest_v3(document),
        "n_cases": len(rows),
        "trace_scope": list(V3_TRACE_QUERY_SERVICES),
        "injected_services": sorted(injected),
        "uninjected_services": list(uninjected_services()),
        "upstream_map": {key: list(value) for key, value in sorted(UPSTREAM_OF.items())},
        "candidate_families": list(candidates),
        "method": (
            "For each case, the per-service maximum of error_count + connection_error_count over "
            "the two fault windows, minus the same maximum over the five healthy windows. A "
            "positive difference on a service that is never an injection target is propagation. "
            "Per case, not aggregated; counts are reported beside the rows, not instead of them."
        ),
        "interpretation": dict(INTERPRETATION),
        "statistics_note": (
            "n = 32. Point counts and complete per-case rows only: no confidence intervals and no "
            "significance tests are reported."
        ),
        "assessment": _assessment(rows, families),
        "families": families,
        "cases": rows,
    }


def run_cascade_probe_from_path(dataset: Path, output: Path) -> dict[str, Any]:
    """Load a scenarios.json, answer criterion E, and write the diagnostic artifact."""
    try:
        document = json.loads(dataset.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CascadeProbeError(f"cascade probe dataset is unreadable: {dataset}") from error
    if not isinstance(document, dict):
        raise CascadeProbeError(f"cascade probe dataset root is not an object: {dataset}")
    run_name = dataset.parent.name
    report = run_cascade_probe(
        document,
        source_run=run_name,
        source_run_invalidated="-invalidated-" in run_name,
    )
    write_json_artifact_v3(output, report)
    return report


__all__ = [
    "INTERPRETATION",
    "UPSTREAM_OF",
    "CascadeProbeError",
    "cascade_candidate_families",
    "case_row",
    "run_cascade_probe",
    "run_cascade_probe_from_path",
    "uninjected_services",
]
