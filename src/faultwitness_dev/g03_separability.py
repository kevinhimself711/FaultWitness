"""Diagnostic-only probe: how much discrimination survives once `descriptions` is redacted?

The descriptions leakage probe answered a narrower question and answered it yes: on 16 of 32 cases
the free text names the fault family outright, so that text has to be redacted. This module answers
the question that decides what happens *after* the redaction. If the six declared numeric channels
alone still identify the family, redaction buys nothing and the task representation itself has to
change; if they do not, redaction may be sufficient and baselines can be resampled.

That question cannot be answered from the earlier probe's classifier B. B reached 32/32 on its own
threshold test, but against the **bare per-family quantum** rather than the frozen
leave-one-case-out healthy p99 the metric actually uses. `adHighCpu`'s quantum is `1e-6`, below
ambient CPU drift, so it qualified on 25 of 32 cases -- 21 of them wrongly. A perfect score built
partly on mutually cancelling false qualifications and a perfect score built on genuinely orthogonal
signals are indistinguishable from that number alone, and they point opposite ways. This module
replaces the threshold with the real one and reports the difference.

Four zero-model classifiers, all reading **only** the six `ROOT_SIGNAL_FEATURES` channels and no
text:

* ``D1`` uses the leave-one-case-out healthy p99 threshold, as `build_deterministic_thresholds_v3`
  freezes it. This is the honest discrimination of the numeric channels.
* ``D2`` reproduces the earlier probe's bare-quantum rule, reported side by side to quantify what
  changing the threshold changed.
* ``D3`` constantly predicts the most frequent family, as a floor.
* ``D4`` ablates to one single signal at a time, six runs, to test whether each channel alone
  identifies its own family -- the direct evidence for a six-way lookup table.

Beyond accuracy the module reports the diagnostics that let a human judge the instrument rather
than trust a scalar: the full 32x6 offset table, per-signal false-qualification counts, a
co-occurrence matrix for signal orthogonality, per-family accuracy to expose difficulty fractures,
and the D1-minus-D2 delta.

Products are ``diagnostic_only`` and can never be promoted to readiness evidence. Nothing here
mutates the dataset, the descriptions, any threshold, or any function in `g03_readiness`.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from faultwitness_dev.g03_leakage_probe import (
    ABSTAIN,
    LABELS,
    LeakageProbeError,
    _assert_no_forbidden_input,
    _confusion,
    _prior_majority,
    _scores,
    root_signal_features,
    root_signal_qualification_detail,
)
from faultwitness_dev.g03_readiness import (
    DETERMINISTIC_PERCENTILE,
    METRIC_VERSION,
    RELATIVE_ROOT_SIGNAL_FLOORS,
    ROOT_SIGNAL_FEATURES,
    TARGET_SERVICES,
    _feature_values,
    _nearest_rank,
    _positive_consecutive_drifts,
    dataset_digest_v3,
    ground_truth_v3,
    scenario_cases_v3,
    validate_observation_packet_v3,
)

# A signal counts as "near-perfect for its own family" in the ablation when it identifies that
# family this often. Set below 1.0 so a single stray case does not hide a lookup table.
ABLATION_SELF_FLOOR = 0.75

# D1 at or above this, with the ablation and co-occurrence evidence agreeing, reads as a lookup
# table rather than an investigation. Deliberately below 1.0 for the same reason.
LOOKUP_TABLE_FLOOR = 0.90

# Fraction of cases with exactly one offset signal above which the dataset offers no main-versus-
# secondary discrimination to make.
SINGLE_SIGNAL_LOOKUP_FRACTION = 0.75

# A per-family accuracy spread this wide is reported as a difficulty fracture in its own right.
FRACTURE_FLOOR = 0.75


class SeparabilityProbeError(LeakageProbeError):
    """Raised when the separability probe cannot make an honest measurement."""


def _frozen_thresholds_loo(
    cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Per-case root-signal thresholds from the healthy windows of the *other* 31 cases.

    This mirrors the `root_signal` half of `build_deterministic_thresholds_v3`: pool the healthy
    consecutive positive drifts of every other case, take the nearest-rank p99, and add the
    family's measurement quantum. `RELATIVE_ROOT_SIGNAL_FLOORS` is preserved and, as in the real
    registry, its relative floor is derived from the held-out case's own healthy *median* -- a
    scale reference, not a discrimination signal, and the one place the real registry reads the
    held-out case at all. That asymmetry is inherited deliberately rather than silently: changing
    it would mean measuring a threshold rule the metric does not use.

    The held-out case contributes nothing to the pooled drift distribution, which is asserted per
    case rather than assumed.
    """
    case_ids = sorted(cases)
    if len(case_ids) != 32:
        raise SeparabilityProbeError("separability probe requires exactly 32 cases")
    registry: dict[str, dict[str, dict[str, Any]]] = {}
    for case_id in case_ids:
        training = [other for other in case_ids if other != case_id]
        if case_id in training or len(training) != 31:
            raise SeparabilityProbeError("leave-one-case-out fold retained the held-out case")
        per_label: dict[str, dict[str, Any]] = {}
        for label in LABELS:
            kind, field, quantum = ROOT_SIGNAL_FEATURES[label]
            drifts = [
                drift
                for other in training
                for drift in _positive_consecutive_drifts(
                    _feature_values(cases[other]["packet"], label, "root_signal", "healthy")
                )
            ]
            # 31 training cases x 4 consecutive differences per healthy window.
            if len(drifts) != 31 * 4:
                raise SeparabilityProbeError(
                    "leave-one-case-out drift pool has the wrong size: "
                    f"{case_id}/{label} got {len(drifts)}"
                )
            p99 = _nearest_rank(drifts, DETERMINISTIC_PERCENTILE)
            threshold = p99 + float(quantum)
            entry: dict[str, Any] = {
                "kind": kind,
                "field": field,
                "service": TARGET_SERVICES[label],
                "quantum": float(quantum),
                "healthy_drift_count": len(drifts),
                "healthy_p99": p99,
                "absolute_threshold": threshold,
                "relative_floor_fraction": None,
                "relative_floor": None,
                "training_case_ids": training,
            }
            fraction = RELATIVE_ROOT_SIGNAL_FLOORS.get(label)
            if fraction is not None:
                healthy_level = float(
                    median(
                        _feature_values(cases[case_id]["packet"], label, "root_signal", "healthy")
                    )
                )
                floor = healthy_level * fraction
                entry["relative_floor_fraction"] = fraction
                entry["relative_floor_healthy_median"] = healthy_level
                entry["relative_floor"] = floor
                threshold = max(threshold, floor)
            entry["threshold"] = threshold
            per_label[label] = entry
        registry[case_id] = per_label
    return registry


def offset_table(
    cases: Mapping[str, Mapping[str, Any]],
    thresholds: Mapping[str, Mapping[str, Mapping[str, Any]]],
    truth: Mapping[str, str],
) -> dict[str, Any]:
    """The 32x6 per-case per-signal offset table, the probe's core human-readable product.

    Every cell carries the frozen p99 threshold, the observed fault-window value, the healthy
    baseline it is measured against, the offset and its multiple of the threshold, and whether the
    cell qualifies -- under both the p99 rule and the bare-quantum rule, so the two are comparable
    cell by cell.
    """
    rows: dict[str, Any] = {}
    for case_id in sorted(cases):
        packet = cases[case_id]["packet"]
        validate_observation_packet_v3(packet)
        cells: dict[str, Any] = {}
        for label in LABELS:
            frozen = thresholds[case_id][label]
            healthy = _feature_values(packet, label, "root_signal", "healthy")
            fault = _feature_values(packet, label, "root_signal", "fault")
            healthy_median = float(median(healthy))
            fault_max = max(fault)
            excess = fault_max - healthy_median
            p99_cutoff = float(frozen["threshold"])
            quantum = float(frozen["quantum"])
            quantum_cutoff = quantum
            quantum_floor = frozen.get("relative_floor")
            if quantum_floor is not None:
                # The bare-quantum rule as classifier B applied it, relative floor included.
                quantum_cutoff = max(quantum, float(quantum_floor))
            cells[label] = {
                "kind": frozen["kind"],
                "field": frozen["field"],
                "service": frozen["service"],
                "is_true_family": label == truth[case_id],
                "healthy_median": healthy_median,
                "fault_max": fault_max,
                "incident_excess": excess,
                "healthy_p99": float(frozen["healthy_p99"]),
                "quantum": quantum,
                "p99_threshold": p99_cutoff,
                "quantum_threshold": quantum_cutoff,
                "excess_over_p99_threshold_multiple": (
                    excess / p99_cutoff if p99_cutoff > 0 else None
                ),
                "excess_over_quantum_threshold_multiple": (
                    excess / quantum_cutoff if quantum_cutoff > 0 else None
                ),
                "qualifies_p99": excess >= p99_cutoff,
                "qualifies_quantum": excess >= quantum_cutoff,
                "standardized_excess_p99": (excess - p99_cutoff) / max(p99_cutoff, quantum),
                "standardized_excess_quantum": (
                    (excess - quantum_cutoff) / max(quantum_cutoff, quantum)
                ),
            }
        _assert_no_forbidden_input(cells, classifier="D1", case_id=case_id)
        rows[case_id] = {"root_cause": truth[case_id], "signals": cells}
    return rows


def classify_from_offsets(
    row: Mapping[str, Any],
    *,
    rule: str,
    restrict_to: str | None = None,
) -> str:
    """Predict the family with the largest standardized excess among qualifying signals.

    `rule` selects the p99 or bare-quantum threshold. `restrict_to` limits the classifier to a
    single signal, which is what makes D4 an ablation: with one label available the classifier can
    only ever name that label or abstain.
    """
    if rule not in ("p99", "quantum"):
        raise SeparabilityProbeError(f"unknown separability threshold rule: {rule}")
    qualifies_key = f"qualifies_{rule}"
    score_key = f"standardized_excess_{rule}"
    candidates = []
    for label, cell in row["signals"].items():
        if restrict_to is not None and label != restrict_to:
            continue
        if cell[qualifies_key]:
            candidates.append((float(cell[score_key]), label))
    if not candidates:
        return ABSTAIN
    return min(candidates, key=lambda item: (-item[0], item[1]))[1]


def false_qualification_table(
    table: Mapping[str, Any],
    truth: Mapping[str, str],
) -> dict[str, Any]:
    """How often each signal reads as offset on cases that are not its own family.

    This is the diagnostic that exposed the earlier probe's dirty threshold: `adHighCpu` false-
    qualified on 21 of the 28 cases that were not its own. Both rules are reported so the change
    is legible per signal.
    """
    support = Counter(truth.values())
    per_signal: dict[str, Any] = {}
    for label in LABELS:
        own = {"p99": 0, "quantum": 0}
        foreign = {"p99": 0, "quantum": 0}
        foreign_cases: dict[str, list[str]] = {"p99": [], "quantum": []}
        for case_id, row in table.items():
            cell = row["signals"][label]
            for rule in ("p99", "quantum"):
                if not cell[f"qualifies_{rule}"]:
                    continue
                if truth[case_id] == label:
                    own[rule] += 1
                else:
                    foreign[rule] += 1
                    foreign_cases[rule].append(case_id)
        foreign_total = len(truth) - support[label]
        per_signal[label] = {
            "kind": ROOT_SIGNAL_FEATURES[label][0],
            "field": ROOT_SIGNAL_FEATURES[label][1],
            "support": support[label],
            "foreign_case_count": foreign_total,
            "p99": {
                "true_qualifications": own["p99"],
                "true_qualification_rate": own["p99"] / support[label] if support[label] else 0.0,
                "false_qualifications": foreign["p99"],
                "false_qualification_rate": (
                    foreign["p99"] / foreign_total if foreign_total else 0.0
                ),
                "false_qualified_case_ids": sorted(foreign_cases["p99"]),
            },
            "quantum": {
                "true_qualifications": own["quantum"],
                "true_qualification_rate": (
                    own["quantum"] / support[label] if support[label] else 0.0
                ),
                "false_qualifications": foreign["quantum"],
                "false_qualification_rate": (
                    foreign["quantum"] / foreign_total if foreign_total else 0.0
                ),
                "false_qualified_case_ids": sorted(foreign_cases["quantum"]),
            },
            "false_qualifications_removed_by_p99": foreign["quantum"] - foreign["p99"],
        }
    return per_signal


def orthogonality(table: Mapping[str, Any], truth: Mapping[str, str]) -> dict[str, Any]:
    """How many signals read as offset per case, and which pairs co-occur.

    A dataset that requires investigation should present cases where several signals move and the
    work is telling primary from secondary. If nearly every case has exactly one signal offset,
    there is nothing to disentangle.
    """
    result: dict[str, Any] = {}
    for rule in ("p99", "quantum"):
        counts: Counter[int] = Counter()
        per_case: dict[str, Any] = {}
        pair_matrix = {left: dict.fromkeys(LABELS, 0) for left in LABELS}
        single_only_true = 0
        for case_id, row in sorted(table.items()):
            offset = sorted(
                label for label in LABELS if row["signals"][label][f"qualifies_{rule}"]
            )
            counts[len(offset)] += 1
            per_case[case_id] = {
                "root_cause": truth[case_id],
                "offset_signals": offset,
                "offset_count": len(offset),
                "true_family_offset": truth[case_id] in offset,
            }
            if len(offset) == 1 and offset[0] == truth[case_id]:
                single_only_true += 1
            for left in offset:
                for right in offset:
                    pair_matrix[left][right] += 1
        total = len(table)
        single = counts.get(1, 0)
        mean_offset = (
            sum(size * quantity for size, quantity in counts.items()) / total if total else 0.0
        )
        result[rule] = {
            "offset_count_distribution": dict(sorted(counts.items())),
            "mean_offset_signals_per_case": mean_offset,
            "single_offset_cases": single,
            "single_offset_fraction": single / total if total else 0.0,
            "single_offset_and_it_is_the_true_family": single_only_true,
            "single_offset_and_it_is_the_true_family_fraction": (
                single_only_true / total if total else 0.0
            ),
            "co_occurrence_matrix": pair_matrix,
            "per_case": per_case,
        }
    return result


def ablation(table: Mapping[str, Any], truth: Mapping[str, str]) -> dict[str, Any]:
    """D4: six runs, each reading exactly one signal.

    For each signal this records whether it alone recovers its own family (recall on that family),
    how often it fires on other families, and the resulting overall accuracy. Every run asserts
    that only the intended signal was consulted.
    """
    runs: dict[str, Any] = {}
    for label in LABELS:
        predictions: dict[str, str] = {}
        for case_id, row in table.items():
            prediction = classify_from_offsets(row, rule="p99", restrict_to=label)
            if prediction not in (label, ABSTAIN):
                raise SeparabilityProbeError(
                    f"single-signal ablation for {label} predicted {prediction}"
                )
            predictions[case_id] = prediction
        scores = _scores(truth, predictions)
        own = scores["per_family"][label]
        own_cases = [case_id for case_id in truth if truth[case_id] == label]
        fired_foreign = sorted(
            case_id
            for case_id in truth
            if predictions[case_id] == label and truth[case_id] != label
        )
        runs[label] = {
            "signal": {
                "kind": ROOT_SIGNAL_FEATURES[label][0],
                "field": ROOT_SIGNAL_FEATURES[label][1],
                "service": TARGET_SERVICES[label],
                "quantum": float(ROOT_SIGNAL_FEATURES[label][2]),
            },
            "reads_only": f"{ROOT_SIGNAL_FEATURES[label][0]}.{ROOT_SIGNAL_FEATURES[label][1]}",
            "overall_accuracy": scores["accuracy"],
            "abstentions": scores["abstentions"],
            "own_family": {
                "support": own["support"],
                "recovered": own["correct"],
                "recall": own["accuracy"],
                "precision": own["precision"],
                "case_ids": sorted(own_cases),
            },
            "fired_on_foreign_cases": fired_foreign,
            "identifies_own_family_alone": own["accuracy"] >= ABLATION_SELF_FLOOR,
            "predictions": predictions,
        }
    self_identifying = sorted(
        label for label in LABELS if runs[label]["identifies_own_family_alone"]
    )
    return {
        "runs": runs,
        "floor": ABLATION_SELF_FLOOR,
        "self_identifying_signals": self_identifying,
        "self_identifying_count": len(self_identifying),
        "every_signal_identifies_its_own_family": len(self_identifying) == len(LABELS),
    }


def _family_delta(d1: Mapping[str, Any], d2: Mapping[str, Any]) -> dict[str, Any]:
    return {
        label: {
            "support": d1["per_family"][label]["support"],
            "d1_p99_accuracy": d1["per_family"][label]["accuracy"],
            "d2_quantum_accuracy": d2["per_family"][label]["accuracy"],
            "delta": d1["per_family"][label]["accuracy"] - d2["per_family"][label]["accuracy"],
            "d1_correct": d1["per_family"][label]["correct"],
            "d2_correct": d2["per_family"][label]["correct"],
        }
        for label in LABELS
    }


def _fracture(scores: Mapping[str, Any]) -> dict[str, Any]:
    accuracies = {label: scores["per_family"][label]["accuracy"] for label in LABELS}
    best = max(accuracies.values())
    worst = min(accuracies.values())
    perfect = sorted(label for label, value in accuracies.items() if value >= 1.0)
    zero = sorted(label for label, value in accuracies.items() if value <= 0.0)
    return {
        "per_family_accuracy": accuracies,
        "spread": best - worst,
        "best": best,
        "worst": worst,
        "perfect_families": perfect,
        "zero_families": zero,
        "fractured": (best - worst) >= FRACTURE_FLOOR,
        "floor": FRACTURE_FLOOR,
        "note": (
            "A wide spread means difficulty is not distributed across families. Families at 1.0 "
            "are free marks and families at 0.0 are unreachable through the declared channel; "
            "both are dataset properties, not model properties, and a fracture is harder to "
            "repair than uniform easiness because raising the floor and lowering the ceiling are "
            "different pieces of work."
        ),
    }


def _assessment(
    d1: Mapping[str, Any],
    d2: Mapping[str, Any],
    d3: Mapping[str, Any],
    ablation_result: Mapping[str, Any],
    orthogonality_result: Mapping[str, Any],
    fracture: Mapping[str, Any],
) -> dict[str, Any]:
    """The four registered readings. Deliberately not a pass/fail verdict.

    Several can hold at once and the routing decision is a human's. Each entry states whether it
    holds, on what measured quantities, and what it implies.
    """
    d1_accuracy = float(d1["accuracy"])
    d2_accuracy = float(d2["accuracy"])
    single_fraction = float(orthogonality_result["p99"]["single_offset_fraction"])
    every_signal = bool(ablation_result["every_signal_identifies_its_own_family"])

    lookup_table = (
        d1_accuracy >= LOOKUP_TABLE_FLOOR
        and every_signal
        and single_fraction >= SINGLE_SIGNAL_LOOKUP_FRACTION
    )
    threshold_contaminated = d1_accuracy < d2_accuracy
    room_to_investigate = (
        not lookup_table and single_fraction < SINGLE_SIGNAL_LOOKUP_FRACTION
    )
    readings = {
        "six_way_lookup_table": {
            "holds": lookup_table,
            "criterion": (
                f"D1 >= {LOOKUP_TABLE_FLOOR} and every signal identifies its own family alone "
                f"(>= {ABLATION_SELF_FLOOR}) and single-offset cases >= "
                f"{SINGLE_SIGNAL_LOOKUP_FRACTION}"
            ),
            "measured": {
                "d1_accuracy": d1_accuracy,
                "every_signal_identifies_its_own_family": every_signal,
                "self_identifying_signals": ablation_result["self_identifying_signals"],
                "single_offset_fraction": single_fraction,
            },
            "implication": (
                "Redacting `descriptions` is not sufficient. The declared numeric channels alone "
                "resolve the family without cross-signal reasoning, so the task is a six-way "
                "lookup and the task representation needs rebuilding before baselines are worth "
                "resampling."
            ),
        },
        "prior_32_of_32_was_threshold_contamination": {
            "holds": threshold_contaminated,
            "criterion": "D1 < D2",
            "measured": {
                "d1_p99_accuracy": d1_accuracy,
                "d2_quantum_accuracy": d2_accuracy,
                "delta": d1_accuracy - d2_accuracy,
            },
            "implication": (
                "The earlier probe's bare-quantum score was inflated by false qualifications. "
                "D1 is the honest discrimination of the numeric channels."
            ),
        },
        "room_for_investigation": {
            "holds": room_to_investigate,
            "criterion": (
                f"not a lookup table and single-offset cases < {SINGLE_SIGNAL_LOOKUP_FRACTION}"
            ),
            "measured": {
                "d1_accuracy": d1_accuracy,
                "single_offset_fraction": single_fraction,
                "mean_offset_signals_per_case": orthogonality_result["p99"][
                    "mean_offset_signals_per_case"
                ],
            },
            "implication": (
                "Multiple signals move on the same case often enough that telling primary from "
                "secondary is real work. Redacting `descriptions` may be sufficient."
            ),
        },
        "difficulty_fracture": {
            "holds": bool(fracture["fractured"]),
            "criterion": f"per-family accuracy spread >= {FRACTURE_FLOOR}",
            "measured": {
                "spread": fracture["spread"],
                "perfect_families": fracture["perfect_families"],
                "zero_families": fracture["zero_families"],
            },
            "implication": (
                "Difficulty is unevenly distributed across families. Flag separately: this is "
                "harder to repair than uniform easiness and must be addressed explicitly during "
                "any rebuild."
            ),
        },
    }
    return {
        "readings": readings,
        "holding": sorted(name for name, entry in readings.items() if entry["holds"]),
        "output_is_not_binary": (
            "This probe reports measurements, not a gate result. More than one reading can hold "
            "at once and the routing decision belongs to a human."
        ),
        "bias_note": (
            "Boundaries are set to report `too easy` on doubt: a false negative puts months of "
            "work on sand, a false positive costs one task-rebuild assessment."
        ),
        "floors": {
            "lookup_table_accuracy": LOOKUP_TABLE_FLOOR,
            "ablation_self_identification": ABLATION_SELF_FLOOR,
            "single_signal_lookup_fraction": SINGLE_SIGNAL_LOOKUP_FRACTION,
            "fracture_spread": FRACTURE_FLOOR,
        },
    }


def run_separability_probe(
    document: Mapping[str, Any],
    *,
    source_run: str,
    source_run_invalidated: bool,
) -> dict[str, Any]:
    """Run D1-D4 over a landed metric-v3 scenario document. Zero model calls."""
    cases = scenario_cases_v3(document)
    if len(cases) != 32:
        raise SeparabilityProbeError("metric v3 separability probe requires exactly 32 cases")
    truth: dict[str, str] = {}
    for case_id, case in cases.items():
        root_cause = str(case["ground_truth"]["root_cause"])
        if root_cause not in LABELS:
            raise SeparabilityProbeError(f"unknown sealed label in dataset: {root_cause}")
        if case["ground_truth"] != ground_truth_v3(case_id, root_cause):
            raise SeparabilityProbeError(f"ground truth for {case_id} is not kind-derived")
        truth[case_id] = root_cause

    thresholds = _frozen_thresholds_loo(cases)
    table = offset_table(cases, thresholds, truth)

    predictions_d1 = {
        case_id: classify_from_offsets(row, rule="p99") for case_id, row in table.items()
    }
    predictions_d2 = {
        case_id: classify_from_offsets(row, rule="quantum") for case_id, row in table.items()
    }
    majority = _prior_majority(truth, sorted(truth))
    predictions_d3 = dict.fromkeys(truth, majority)

    scores_d1 = _scores(truth, predictions_d1)
    scores_d2 = _scores(truth, predictions_d2)
    scores_d3 = _scores(truth, predictions_d3)

    # Cross-check: D2 here must reproduce the earlier probe's classifier B, which reached its
    # verdict through a separate code path. A mismatch means one of the two is wrong.
    legacy_signal = {
        case_id: root_signal_features(case["packet"]) for case_id, case in sorted(cases.items())
    }
    legacy_detail = root_signal_qualification_detail(legacy_signal, truth)

    ablation_result = ablation(table, truth)
    orthogonality_result = orthogonality(table, truth)
    fracture = _fracture(scores_d1)

    return {
        "diagnostic_only": True,
        "source_run": source_run,
        "source_run_invalidated": source_run_invalidated,
        "dataset_digest": dataset_digest_v3(document),
        "metric_version": METRIC_VERSION,
        "n_cases": len(cases),
        "model_calls": 0,
        "generated_at": datetime.now(UTC).isoformat(),
        "probe": "metric-v3 root-signal separability",
        "question": (
            "If `trace_errors.descriptions` is redacted, do the six declared numeric root signals "
            "alone still identify the fault family?"
        ),
        "promotion": (
            "diagnostic_only: never promotable to readiness evidence, per AMD-0005 and ADR-0014 "
            "as limited by commit 1c46820."
        ),
        "threshold_method": {
            "d1": (
                "leave-one-case-out healthy consecutive-positive-drift nearest-rank p99 plus the "
                "family measurement quantum, mirroring build_deterministic_thresholds_v3"
            ),
            "d2": "bare per-family measurement quantum, reproducing the earlier probe's B",
            "percentile": DETERMINISTIC_PERCENTILE,
            "relative_floors": dict(sorted(RELATIVE_ROOT_SIGNAL_FLOORS.items())),
            "relative_floor_note": (
                "Preserved from the real registry, including its one asymmetry: the "
                "emailMemoryLeak relative floor is a fraction of the held-out case's own healthy "
                "median. That is a scale reference rather than a discrimination signal, and it is "
                "how build_deterministic_thresholds_v3 computes it; the pooled drift "
                "distribution that sets the p99 excludes the held-out case entirely."
            ),
        },
        "label_distribution": dict(sorted(Counter(truth.values()).items())),
        "majority_class": majority,
        "classifiers": {
            "D1_root_signal_p99": {
                "reads": "the six ROOT_SIGNAL_FEATURES numeric channels, no text",
                "method": (
                    "max(fault) - median(healthy) against the leave-one-case-out healthy p99 "
                    "threshold; highest standardized excess among qualifying families wins"
                ),
                "scores": scores_d1,
                "predictions": predictions_d1,
            },
            "D2_root_signal_bare_quantum": {
                "reads": "the six ROOT_SIGNAL_FEATURES numeric channels, no text",
                "method": "the same rule against the bare per-family quantum (the earlier B)",
                "scores": scores_d2,
                "predictions": predictions_d2,
                "legacy_qualification_detail": legacy_detail,
                "note": (
                    "Reported for comparison only. Its threshold sits below ambient drift for at "
                    "least one family, which is why this probe exists."
                ),
            },
            "D3_majority_class": {
                "reads": "nothing",
                "method": f"constant prediction of {majority}",
                "scores": scores_d3,
            },
        },
        "d1_minus_d2": {
            "accuracy": float(scores_d1["accuracy"]) - float(scores_d2["accuracy"]),
            "macro_f1": float(scores_d1["macro_f1"]) - float(scores_d2["macro_f1"]),
            "per_family": _family_delta(scores_d1, scores_d2),
        },
        "d4_single_signal_ablation": ablation_result,
        "false_qualifications": false_qualification_table(table, truth),
        "orthogonality": orthogonality_result,
        "per_family_fracture": fracture,
        "offset_table": table,
        "frozen_thresholds": thresholds,
        "confusion_matrices": {
            "D1_root_signal_p99": _confusion(truth, predictions_d1),
            "D2_root_signal_bare_quantum": _confusion(truth, predictions_d2),
            "D3_majority_class": _confusion(truth, predictions_d3),
        },
        "statistics_note": (
            "n = 32. Point estimates and complete tables only: no confidence intervals and no "
            "significance tests are reported."
        ),
        "assessment": _assessment(
            scores_d1, scores_d2, scores_d3, ablation_result, orthogonality_result, fracture
        ),
    }


def run_separability_probe_from_path(dataset: Path, output: Path) -> dict[str, Any]:
    """Load a scenarios.json, run the probe, and write the diagnostic artifact."""
    try:
        document = json.loads(dataset.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SeparabilityProbeError(
            f"separability probe dataset is unreadable: {dataset}"
        ) from error
    if not isinstance(document, dict):
        raise SeparabilityProbeError(f"separability probe dataset root is not an object: {dataset}")
    run_name = dataset.parent.name
    report = run_separability_probe(
        document,
        source_run=run_name,
        source_run_invalidated="-invalidated-" in run_name,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def _signals_only(sequence: Sequence[str]) -> tuple[str, ...]:
    """Helper for tests: the ordered signal labels, so a fixture cannot silently reorder them."""
    return tuple(label for label in LABELS if label in set(sequence))
