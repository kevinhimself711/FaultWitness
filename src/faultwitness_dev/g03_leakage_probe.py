"""Diagnostic-only probe: can `trace_errors.descriptions` alone name the metric-v3 fault class?

`_public_window` in `g03_readiness` projects each service's error `descriptions` through to the
public packet verbatim. The formal root signal for `productCatalogFailure`, `paymentFailure` and
`paymentUnreachable` is a *count* (`error_count` / `connection_error_count`), but the same evidence
kind also carries the free text those counts were derived from. If that text names the fault, then
those three families -- half the dataset -- are a reading-comprehension task rather than an
investigation task, and no harness can demonstrate value on them.

This module measures that, and only that. Three zero-model classifiers run over a landed metric-v3
scenario dataset:

* ``A`` reads **only** the description strings. No numeric field, no other evidence kind.
* ``B`` reads **only** the one numeric channel `ROOT_SIGNAL_FEATURES` declares per family.
* ``C`` constantly predicts the most frequent family, as a floor for A and B.

Products are ``diagnostic_only`` and can never be promoted to readiness evidence. Nothing here
mutates the dataset, the thresholds, or any function in `g03_readiness`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g03_readiness import (
    EVIDENCE_KINDS,
    FORBIDDEN_PUBLIC_KEYS,
    METRIC_VERSION,
    RELATIVE_ROOT_SIGNAL_FLOORS,
    REQUIRED_KINDS,
    ROOT_SIGNAL_FEATURES,
    TARGET_SERVICES,
    _feature_values,
    _group_by_kind,
    _walk_forbidden,
    ground_truth_v3,
    scenario_cases_v3,
    validate_observation_packet_v3,
)

LABELS: tuple[str, ...] = tuple(sorted(REQUIRED_KINDS))

# The evidence kind classifier A is allowed to touch, and the only one it does touch.
DESCRIPTION_KIND = "trace_errors"

# Families whose declared root signal lives in `trace_errors` -- the suspected leak region.
TRACE_ERROR_LABELS: tuple[str, ...] = tuple(
    label for label in LABELS if ROOT_SIGNAL_FEATURES[label][0] == DESCRIPTION_KIND
)
OTHER_LABELS: tuple[str, ...] = tuple(
    label for label in LABELS if label not in TRACE_ERROR_LABELS
)

ABSTAIN = "unknown"
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")

# Verdict boundaries. Both are deliberately biased toward *reporting* leakage: a false positive
# costs one redaction pass, a false negative puts every downstream decision on sand. A only has
# to beat the majority-class floor by one case in ten to be called leaky.
LEAK_MARGIN_OVER_MAJORITY = 0.10
# Localized rather than global requires the suspected trio to be both high on its own terms and
# clearly separated from the three families that do not share the evidence kind.
LOCALIZED_TRIO_FLOOR = 0.75
LOCALIZED_SEPARATION = 0.25


class LeakageProbeError(GovernanceError):
    """Raised when the probe cannot make an honest measurement."""


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT.split(text.casefold()) if token]


def _assert_no_forbidden_input(payload: Any, *, classifier: str, case_id: str) -> None:
    """Fail closed if a classifier's own input carries a sealed or evaluator-side key.

    `validate_observation_packet_v3` already rejects such a packet, so reaching this means
    something worse than a description leak: an answer field landed in public evidence. The check
    is repeated on the extracted features because that -- not the packet -- is what actually
    reaches a classifier.
    """
    found = sorted(_walk_forbidden(payload))
    if found:
        raise LeakageProbeError(
            f"classifier {classifier} input for {case_id} carries sealed keys: " + ", ".join(found)
        )


def description_features(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Project a packet down to description text only, split by window phase.

    Reads `trace_errors` sample descriptions and the packet's own window phase registry. Reads no
    numeric measurement, no `service_scope`, and no other evidence kind.
    """
    validate_observation_packet_v3(packet)
    group = _group_by_kind(packet)[DESCRIPTION_KIND]
    phases = {int(window["index"]): str(window["phase"]) for window in packet["windows"]}
    by_phase: dict[str, list[str]] = {"healthy": [], "fault": []}
    for sample in group["samples"]:
        phase = phases[int(sample["window_index"])]
        for service in sorted(sample["services"]):
            measurement = sample["services"][service]
            # Only the description list is read. `error_count` and `connection_error_count` sit
            # in this same mapping and are deliberately left untouched.
            by_phase[phase].extend(str(value) for value in measurement["descriptions"])
    healthy = {token for text in by_phase["healthy"] for token in _tokens(text)}
    fault = {token for text in by_phase["fault"] for token in _tokens(text)}
    features = {
        "case_id": str(packet["case_id"]),
        "healthy_texts": sorted(set(by_phase["healthy"])),
        "fault_texts": sorted(set(by_phase["fault"])),
        # The healthy/fault contrast the metric itself uses, applied to text instead of counts.
        "incident_tokens": sorted(fault - healthy),
        "fault_tokens": sorted(fault),
        "healthy_tokens": sorted(healthy),
    }
    _assert_no_forbidden_input(features, classifier="A", case_id=features["case_id"])
    return features


def _keyword_table(
    features_by_case: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, str],
    case_ids: Sequence[str],
) -> dict[str, Any]:
    """Tokens occurring in exactly one family across the given cases, with their case counts."""
    per_family: dict[str, Counter[str]] = {label: Counter() for label in LABELS}
    for case_id in case_ids:
        label = labels[case_id]
        for token in features_by_case[case_id]["incident_tokens"]:
            per_family[label][token] += 1
    families_per_token: Counter[str] = Counter()
    for label in LABELS:
        for token in per_family[label]:
            families_per_token[token] += 1
    discriminative = {
        label: {
            token: count
            for token, count in sorted(per_family[label].items())
            if families_per_token[token] == 1
        }
        for label in LABELS
    }
    shared = sorted(token for token, count in families_per_token.items() if count > 1)
    return {
        "training_case_count": len(case_ids),
        "discriminative_tokens": discriminative,
        "tokens_shared_across_families": shared,
    }


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _prior_majority(labels: Mapping[str, str], case_ids: Sequence[str]) -> str:
    counts = Counter(labels[case_id] for case_id in case_ids)
    return min(counts, key=lambda label: (-counts[label], label))


def classify_descriptions_loo(
    features_by_case: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, str],
) -> dict[str, Any]:
    """Classifier A: leave-one-out majority vote over description tokens.

    For each case the keyword table is rebuilt from the other 31 cases only. Every incident token
    of the held-out case that is discriminative in that table casts one vote for its family; the
    family with the most votes wins, ties broken lexically. A case whose descriptions contribute
    no discriminative token abstains rather than falling back to the class prior, so per-family
    accuracy reads as "descriptions carried the family here" and not as an artifact of which
    family happens to be most common.

    The nearest-neighbour variant is recorded alongside it for reference: it never abstains, so
    any accuracy it adds over the majority-vote form comes from the prior, not from the text.
    """
    case_ids = sorted(features_by_case)
    folds: list[dict[str, Any]] = []
    for case_id in case_ids:
        training = [other for other in case_ids if other != case_id]
        if len(training) != len(case_ids) - 1 or case_id in training:
            raise LeakageProbeError("leave-one-out fold retained the held-out case")
        table = _keyword_table(features_by_case, labels, training)
        held_out = features_by_case[case_id]["incident_tokens"]
        votes: Counter[str] = Counter()
        matched: dict[str, list[str]] = {}
        for label in LABELS:
            hits = [token for token in held_out if token in table["discriminative_tokens"][label]]
            if hits:
                votes[label] = len(hits)
                matched[label] = hits
        prediction = min(votes, key=lambda label: (-votes[label], label)) if votes else ABSTAIN
        similarities = [
            (_jaccard(held_out, features_by_case[other]["incident_tokens"]), other)
            for other in training
        ]
        best = max(score for score, _ in similarities)
        neighbours = [other for score, other in similarities if score == best]
        neighbour_votes = Counter(labels[other] for other in neighbours)
        nn_prediction = min(neighbour_votes, key=lambda label: (-neighbour_votes[label], label))
        folds.append(
            {
                "case_id": case_id,
                "training_case_ids": training,
                "incident_tokens": held_out,
                "votes": dict(sorted(votes.items())),
                "matched_tokens": {label: matched[label] for label in sorted(matched)},
                "prediction": prediction,
                "nearest_neighbour_prediction": nn_prediction,
                "nearest_neighbour_similarity": best,
            }
        )
    return {
        "predictions": {fold["case_id"]: fold["prediction"] for fold in folds},
        "nearest_neighbour_predictions": {
            fold["case_id"]: fold["nearest_neighbour_prediction"] for fold in folds
        },
        "folds": folds,
        "display_keyword_table": {
            "note": (
                "Computed over all 32 cases for human inspection only. Predictions above use the "
                "per-fold tables in `folds`, each built from 31 training cases."
            ),
            **_keyword_table(features_by_case, labels, case_ids),
        },
    }


def root_signal_features(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Project a packet down to the one declared numeric root signal per family.

    Reuses `_feature_values(..., "root_signal", ...)`, so the channel, the target service and the
    field are exactly the ones `ROOT_SIGNAL_FEATURES` declares. No description text is read.
    """
    validate_observation_packet_v3(packet)
    case_id = str(packet["case_id"])
    per_label: dict[str, Any] = {}
    for label in LABELS:
        kind, field, quantum = ROOT_SIGNAL_FEATURES[label]
        healthy = _feature_values(packet, label, "root_signal", "healthy")
        fault = _feature_values(packet, label, "root_signal", "fault")
        healthy_median = float(median(healthy))
        excess = max(fault) - healthy_median
        threshold = float(quantum)
        fraction = RELATIVE_ROOT_SIGNAL_FLOORS.get(label)
        relative_floor = None
        if fraction is not None:
            relative_floor = healthy_median * fraction
            threshold = max(threshold, relative_floor)
        per_label[label] = {
            "kind": kind,
            "field": field,
            "service": TARGET_SERVICES[label],
            "quantum": float(quantum),
            "relative_floor_fraction": fraction,
            "relative_floor": relative_floor,
            "healthy_median": healthy_median,
            "fault_max": max(fault),
            "incident_excess": excess,
            "threshold": threshold,
            "qualifies": excess >= threshold,
            "standardized_excess": (excess - threshold) / max(threshold, float(quantum)),
        }
    features = {"case_id": case_id, "labels": per_label}
    _assert_no_forbidden_input(features, classifier="B", case_id=case_id)
    return features


def root_signal_qualification_detail(
    signal_by_case: Mapping[str, Mapping[str, Any]],
    truth: Mapping[str, str],
) -> dict[str, Any]:
    """Separate B's threshold test from B's ranking step.

    B's headline accuracy conflates two things: whether the declared numeric channel *separates*
    the true family from its own healthy baseline, and whether that family then *outranks* every
    other qualifying family. This records both, because they fail for different reasons and only
    the first is a statement about the dataset.

    A label qualifying on cases that are not its own is a threshold artifact of this probe -- B
    compares against the bare per-family quantum, not the leave-one-case-out healthy p99 that
    `build_deterministic_thresholds_v3` uses -- so a quantum below ambient drift lets a family
    qualify almost everywhere and dominate the ranking. Recorded, not corrected: this probe does
    not touch thresholds.
    """
    per_label_qualifies: Counter[str] = Counter()
    true_label_qualifies: Counter[str] = Counter()
    support: Counter[str] = Counter()
    for case_id, features in signal_by_case.items():
        actual = truth[case_id]
        support[actual] += 1
        for label, entry in features["labels"].items():
            if entry["qualifies"]:
                per_label_qualifies[label] += 1
        if features["labels"][actual]["qualifies"]:
            true_label_qualifies[actual] += 1
    total = len(signal_by_case)
    qualified = sum(true_label_qualifies.values())
    return {
        "true_label_qualification_rate": qualified / total if total else 0.0,
        "per_family": {
            label: {
                "support": support[label],
                "true_label_qualifies": true_label_qualifies[label],
                "qualifies_in_cases": per_label_qualifies[label],
                "false_qualifications": per_label_qualifies[label] - true_label_qualifies[label],
            }
            for label in LABELS
        },
        "note": (
            "A high `false_qualifications` count means this probe's bare-quantum threshold sits "
            "below ambient drift for that family, so it qualifies on other families' cases and "
            "distorts B's ranking. Read B's per-family accuracy against this, and read "
            "`true_label_qualification_rate` as the honest statement of whether the declared "
            "numeric channel separates each fault from its own healthy window."
        ),
    }


def classify_root_signal(features: Mapping[str, Any]) -> str:
    """Classifier B: the qualifying family with the largest standardized excess."""
    qualified = [
        (float(entry["standardized_excess"]), label)
        for label, entry in features["labels"].items()
        if entry["qualifies"]
    ]
    if not qualified:
        return ABSTAIN
    return min(qualified, key=lambda item: (-item[0], item[1]))[1]


def _confusion(truth: Mapping[str, str], predicted: Mapping[str, str]) -> dict[str, Any]:
    matrix = {label: dict.fromkeys((*LABELS, ABSTAIN), 0) for label in LABELS}
    for case_id, actual in truth.items():
        matrix[actual][predicted[case_id]] += 1
    return matrix


def _scores(truth: Mapping[str, str], predicted: Mapping[str, str]) -> dict[str, Any]:
    matrix = _confusion(truth, predicted)
    total = len(truth)
    correct = sum(1 for case_id, actual in truth.items() if predicted[case_id] == actual)
    per_family: dict[str, Any] = {}
    f1_values: list[float] = []
    for label in LABELS:
        support = sum(matrix[label].values())
        true_positive = matrix[label][label]
        predicted_positive = sum(matrix[other][label] for other in LABELS)
        precision = true_positive / predicted_positive if predicted_positive else 0.0
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1_values.append(f1)
        per_family[label] = {
            "support": support,
            "correct": true_positive,
            "accuracy": recall,
            "precision": precision,
            "f1": f1,
        }
    grouped = {}
    for name, group in (
        ("trace_errors_families", TRACE_ERROR_LABELS),
        ("other_families", OTHER_LABELS),
    ):
        support = sum(per_family[label]["support"] for label in group)
        hits = sum(per_family[label]["correct"] for label in group)
        grouped[name] = {
            "families": list(group),
            "support": support,
            "correct": hits,
            "accuracy": hits / support if support else 0.0,
        }
    return {
        "n": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else 0.0,
        "abstentions": sum(1 for value in predicted.values() if value == ABSTAIN),
        "per_family": per_family,
        "grouped_accuracy": grouped,
        "confusion_matrix": matrix,
    }


def _verdict(a: Mapping[str, Any], b: Mapping[str, Any], c: Mapping[str, Any]) -> dict[str, Any]:
    margin = float(a["accuracy"]) - float(c["accuracy"])
    trio = float(a["grouped_accuracy"]["trace_errors_families"]["accuracy"])
    other = float(a["grouped_accuracy"]["other_families"]["accuracy"])
    if margin <= LEAK_MARGIN_OVER_MAJORITY:
        code = "no_leakage_detected"
        finding = (
            "A does not beat the majority-class floor by more than "
            f"{LEAK_MARGIN_OVER_MAJORITY:.2f}; descriptions carry no usable shortcut."
        )
    elif trio >= LOCALIZED_TRIO_FLOOR and other <= trio - LOCALIZED_SEPARATION:
        code = "localized_leakage_trace_errors_families"
        finding = (
            f"Descriptions alone reach {trio:.4f} on {', '.join(TRACE_ERROR_LABELS)} versus "
            f"{other:.4f} on the other three. The shortcut is confined to the families whose "
            "root signal shares the `trace_errors` kind; redaction there is sufficient."
        )
    else:
        code = "global_leakage"
        finding = (
            f"Descriptions alone reach {float(a['accuracy']):.4f} overall against a "
            f"{float(c['accuracy']):.4f} floor, and the advantage is not confined to the "
            "`trace_errors` families. The text channel leaks across family boundaries."
        )
    return {
        "code": code,
        "finding": finding,
        "descriptions_accuracy": float(a["accuracy"]),
        "root_signal_accuracy": float(b["accuracy"]),
        "majority_class_accuracy": float(c["accuracy"]),
        "margin_over_majority_class": margin,
        "descriptions_minus_root_signal": float(a["accuracy"]) - float(b["accuracy"]),
        "root_signal_comparison_caveat": (
            "The A-minus-B difference is not evidence either way. B thresholds against the bare "
            "per-family quantum instead of the frozen leave-one-case-out healthy p99, so a "
            "quantum below ambient drift lets one family qualify on most cases and dominate B's "
            "ranking. The verdict is therefore decided against C and against the trio/other "
            "split, never against B. See classifiers.B_root_signal_only.qualification_detail."
        ),
        "trace_errors_family_accuracy": trio,
        "other_family_accuracy": other,
        "criteria": {
            "no_leakage": f"A - C <= {LEAK_MARGIN_OVER_MAJORITY}",
            "localized": (
                f"trio >= {LOCALIZED_TRIO_FLOOR} and other <= trio - {LOCALIZED_SEPARATION}"
            ),
            "global": "leaky but not confined to the trio",
        },
        "bias_note": (
            "Boundaries are set to report leakage on doubt: a false positive costs one redaction "
            "pass, a false negative builds every downstream decision on sand."
        ),
    }


def run_leakage_probe(
    document: Mapping[str, Any],
    *,
    source_run: str,
    source_run_invalidated: bool,
) -> dict[str, Any]:
    """Run all three classifiers over a landed metric-v3 scenario document."""
    cases = scenario_cases_v3(document)
    if len(cases) != 32:
        raise LeakageProbeError("metric v3 leakage probe requires exactly 32 cases")
    truth: dict[str, str] = {}
    for case_id, case in cases.items():
        root_cause = str(case["ground_truth"]["root_cause"])
        if root_cause not in LABELS:
            raise LeakageProbeError(f"unknown sealed label in dataset: {root_cause}")
        if case["ground_truth"] != ground_truth_v3(case_id, root_cause):
            raise LeakageProbeError(f"ground truth for {case_id} is not kind-derived")
        truth[case_id] = root_cause

    description_by_case = {
        case_id: description_features(case["packet"]) for case_id, case in sorted(cases.items())
    }
    signal_by_case = {
        case_id: root_signal_features(case["packet"]) for case_id, case in sorted(cases.items())
    }
    # Labels reach the evaluator only. The keyword table is a training statistic over 31 other
    # cases; no classifier ever sees the held-out case's own label.
    probe_a = classify_descriptions_loo(description_by_case, truth)
    predictions_a = probe_a["predictions"]
    predictions_b = {case_id: classify_root_signal(signal_by_case[case_id]) for case_id in truth}
    majority = _prior_majority(truth, sorted(truth))
    predictions_c = dict.fromkeys(truth, majority)

    scores_a = _scores(truth, predictions_a)
    scores_a_nn = _scores(truth, probe_a["nearest_neighbour_predictions"])
    scores_b = _scores(truth, predictions_b)
    scores_c = _scores(truth, predictions_c)
    return {
        "diagnostic_only": True,
        "source_run": source_run,
        "source_run_invalidated": source_run_invalidated,
        "metric_version": METRIC_VERSION,
        "n_cases": len(cases),
        "generated_at": datetime.now(UTC).isoformat(),
        "probe": "metric-v3 trace_errors.descriptions leakage",
        "question": (
            "Can the free-text `trace_errors.descriptions` strings alone name the fault family, "
            "without reading `error_count` or `connection_error_count`?"
        ),
        "promotion": (
            "diagnostic_only: never promotable to readiness evidence, per AMD-0005 and ADR-0014 "
            "as limited by commit 1c46820."
        ),
        "model_calls": 0,
        "evidence_kinds_in_packet": list(EVIDENCE_KINDS),
        "label_distribution": dict(sorted(Counter(truth.values()).items())),
        "majority_class": majority,
        "classifiers": {
            "A_descriptions_only": {
                "reads": f"{DESCRIPTION_KIND}.services[*].descriptions (text only)",
                "method": "leave-one-out discriminative-token majority vote, abstains on no vote",
                "scores": scores_a,
            },
            "A_descriptions_nearest_neighbour": {
                "reads": f"{DESCRIPTION_KIND}.services[*].descriptions (text only)",
                "method": (
                    "leave-one-out nearest neighbour by incident-token Jaccard, never abstains; "
                    "accuracy above the majority-vote form comes from the class prior"
                ),
                "scores": scores_a_nn,
            },
            "B_root_signal_only": {
                "reads": "the single ROOT_SIGNAL_FEATURES numeric channel per family",
                "method": (
                    "max(fault) - median(healthy) against the family quantum, or the "
                    "RELATIVE_ROOT_SIGNAL_FLOORS relative floor where one is registered"
                ),
                "scores": scores_b,
                "qualification_detail": root_signal_qualification_detail(signal_by_case, truth),
                "note": (
                    "B is a reference point for A, not a measurement of the metric's own "
                    "deterministic baseline: it thresholds against the bare per-family quantum "
                    "rather than the leave-one-case-out healthy p99 that "
                    "`build_deterministic_thresholds_v3` freezes. See `qualification_detail` "
                    "before reading B's accuracy as the numeric channel's strength."
                ),
            },
            "C_majority_class": {
                "reads": "nothing",
                "method": f"constant prediction of {majority}",
                "scores": scores_c,
                "note": (
                    "Constant, as specified. A leave-one-out majority-class baseline would score "
                    "0.0 here because the two largest families are tied at 8 cases, so dropping "
                    "any case flips the majority away from that case's own family."
                ),
            },
        },
        "keyword_table": probe_a["display_keyword_table"],
        "folds": probe_a["folds"],
        "root_signal_detail": signal_by_case,
        "description_samples": {
            case_id: {
                "root_cause": truth[case_id],
                "fault_texts": description_by_case[case_id]["fault_texts"],
                "healthy_texts": description_by_case[case_id]["healthy_texts"],
            }
            for case_id in sorted(truth)
        },
        "verdict": _verdict(scores_a, scores_b, scores_c),
        "forbidden_public_keys_checked": sorted(FORBIDDEN_PUBLIC_KEYS),
    }


def run_leakage_probe_from_path(dataset: Path, output: Path) -> dict[str, Any]:
    """Load a scenarios.json, run the probe, and write the diagnostic artifact."""
    try:
        document = json.loads(dataset.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LeakageProbeError(f"leakage probe dataset is unreadable: {dataset}") from error
    if not isinstance(document, dict):
        raise LeakageProbeError(f"leakage probe dataset root is not an object: {dataset}")
    run_name = dataset.parent.name
    report = run_leakage_probe(
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
