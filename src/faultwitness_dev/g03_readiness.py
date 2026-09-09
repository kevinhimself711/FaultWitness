"""Frozen metric-v3 readiness dataset, baselines, scorer, and aggregate.

This module is intentionally separate from the frozen metric-v1/v2 routes in
``g02_baselines``. Result wire schema 2.0.0 is shared; evaluation semantics are not.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import random
import shutil
import socket
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Protocol

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from faultwitness_dev.errors import GovernanceError, InfrastructureFailure
from faultwitness_dev.experiment import (
    ExperimentInfrastructureError,
    ExperimentRunner,
    ExperimentUnit,
    TrialJournal,
    semantic_cache_key,
)
from faultwitness_dev.g02_baselines import (
    MODEL_ID,
    QUALITY_FLOORS,
    RESULT_SCHEMA_V2,
    ROOT_CAUSE_LABELS,
    LiveConfigurationError,
    LiveInfrastructureError,
    resolve_quality_floor,
    token_cost,
)
from faultwitness_dev.g02_lab import (
    ADAPTERS,
    FULL_SHA,
    V3_FAULT_SAMPLE_INTERVAL_SECONDS,
    V3_TRACE_QUERY_SERVICES,
    LiveReadinessObserverV3,
    OracleState,
    RemoteFlagClient,
    _mutated_document,
    canonical_json,
    fault_state,
    load_lab_config,
    recovery_state,
    seed_catalog,
    validate_lab_bootstrap,
    validate_live_readiness_collector_checkpoint,
    validate_seed_catalog,
)
from faultwitness_dev.schemas import load_data

METRIC_VERSION = 3
WIRE_SCHEMA_VERSION = "2.0.0"
REGISTERED_METRIC_VERSIONS = frozenset({METRIC_VERSION})
EVIDENCE_KINDS = (
    "journey_window",
    "trace_activity",
    "trace_errors",
    "cpu_window",
    "memory_window",
    "queue_window",
)
GROUP_FIELDS: dict[str, frozenset[str]] = {
    "journey_window": frozenset({"id", "kind", "source", "samples"}),
    "trace_activity": frozenset(
        {"id", "kind", "source", "service_scope", "samples"}
    ),
    "trace_errors": frozenset(
        {"id", "kind", "source", "service_scope", "samples"}
    ),
    "cpu_window": frozenset(
        {"id", "kind", "source", "service", "metric", "unit", "samples"}
    ),
    "memory_window": frozenset(
        {"id", "kind", "source", "service", "metric", "unit", "samples"}
    ),
    "queue_window": frozenset(
        {"id", "kind", "source", "service", "metric", "unit", "samples"}
    ),
}
GROUP_SAMPLE_FIELDS: dict[str, frozenset[str]] = {
    "journey_window": frozenset({"window_index", "ready", "status_code"}),
    "trace_activity": frozenset({"window_index", "services"}),
    "trace_errors": frozenset({"window_index", "services"}),
    "cpu_window": frozenset({"window_index", "cpu_cores"}),
    "memory_window": frozenset({"window_index", "working_set_bytes"}),
    "queue_window": frozenset(
        {
            "window_index",
            "consumer_lag",
            "consumer_poll_lag_seconds",
            "consumer_record_lag",
        }
    ),
}
HEALTHY_WINDOW_COUNT = 5
FAULT_WINDOW_COUNT = 2
REFERENCE_REPETITIONS = 3
MAX_REFERENCE_REPETITIONS = 5
BOOTSTRAP_RESAMPLES = 2000
MAX_CUMULATIVE_INPUT_TOKENS = 65_536
MAX_CUMULATIVE_OUTPUT_TOKENS = 8_192
MAX_COMPLETION_TOKENS = 2_048
FOUR_TURN_INPUT_LIMIT = 58_982
REQUIRED_INPUT_HEADROOM = 6_554
MESSAGE_FRAMING_ALLOWANCE = 64
REQUEST_TEMPLATE_ALLOWANCE = 256
DETERMINISTIC_PERCENTILE = 0.99

RESULT_SCHEMA_V3 = deepcopy(RESULT_SCHEMA_V2)
RESULT_SCHEMA_V3["properties"]["metric_version"] = {"const": METRIC_VERSION}
RESULT_SCHEMA_V3["required"] = [
    "schema_version",
    "metric_version",
    "case_id",
    "status",
    "root_cause",
    "root_cause_candidates",
    "evidence",
    "claims",
]


def require_v3_metric_version(metric_version: int) -> int:
    """Reject non-v3 semantics before credentials, I/O, statistics, or artifacts."""
    if metric_version not in REGISTERED_METRIC_VERSIONS:
        raise GovernanceError(f"unsupported G03 readiness metric version: {metric_version}")
    return metric_version


def wire_schema_for_v3(metric_version: int) -> str:
    require_v3_metric_version(metric_version)
    return WIRE_SCHEMA_VERSION


def load_baseline_config_v3(root: Path, *, metric_version: int = METRIC_VERSION) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    config = load_data(root / "config" / "g03" / "baselines-v3.yaml")
    expected = {
        "schema_version": "1.0.0",
        "metric_version": 3,
        "model_id": MODEL_ID,
        "budgets": {
            "cumulative_input_tokens": MAX_CUMULATIVE_INPUT_TOKENS,
            "cumulative_output_tokens": MAX_CUMULATIVE_OUTPUT_TOKENS,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
        },
        "arms": {
            "no_rag": {"min_turns": 1, "max_turns": 1, "registered": True},
            "naive_react": {"min_turns": 2, "max_turns": 4, "registered": True},
            "naive_react_single": {"min_turns": 1, "max_turns": 1, "registered": False},
        },
        "max_tool_calls": 6,
    }
    if config != expected:
        raise GovernanceError("metric v3 baseline configuration drifted")
    return config


class LiveTrialFailure(GovernanceError):
    def __init__(
        self,
        failure_class: str,
        reason: str,
        *,
        input_tokens: int,
        output_tokens: int,
        telemetry: Mapping[str, Any],
    ) -> None:
        super().__init__(reason)
        self.failure_class = failure_class
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.telemetry = _json_copy(telemetry)


class DatasetIncompleteError(GovernanceError):
    """A fresh replay is structurally incomplete and cannot enter a denominator."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"dataset_incomplete: {reason}")


REQUIRED_KINDS: dict[str, tuple[str, str]] = {
    "productCatalogFailure": ("trace_activity", "trace_errors"),
    "paymentFailure": ("trace_activity", "trace_errors"),
    "paymentUnreachable": ("trace_activity", "trace_errors"),
    "adHighCpu": ("trace_activity", "cpu_window"),
    "emailMemoryLeak": ("trace_activity", "memory_window"),
    "kafkaQueueProblems": ("trace_activity", "queue_window"),
}

TARGET_SERVICES = {
    "productCatalogFailure": "product-catalog",
    "paymentFailure": "payment",
    "paymentUnreachable": "checkout",
    "adHighCpu": "ad",
    "emailMemoryLeak": "email",
    "kafkaQueueProblems": "fraud-detection",
}

# label -> signal kind, public scalar field, measurement quantum
ROOT_SIGNAL_FEATURES: dict[str, tuple[str, str, float]] = {
    "productCatalogFailure": ("trace_errors", "error_count", 1.0),
    "paymentFailure": ("trace_errors", "error_count", 1.0),
    "paymentUnreachable": ("trace_errors", "connection_error_count", 1.0),
    "adHighCpu": ("cpu_window", "cpu_cores", 0.000001),
    "emailMemoryLeak": ("memory_window", "working_set_bytes", 1.0),
    "kafkaQueueProblems": ("queue_window", "consumer_poll_lag_seconds", 0.001),
}

# Root signals whose healthy baseline is a large non-zero level rather than a floor at zero.
# `working_set_bytes` is the only one: a mail worker holds ~50 MB resident while healthy, so an
# absolute cutoff derived from healthy drift cannot separate a leak from ambient movement. Two
# facts force a relative floor here. First, `email` and `fraud-detection` are both Kafka consumers,
# so a queue fault genuinely grows email's working set -- real cross-talk, not a data defect.
# Second, that cross-talk is not even stable in sign: case SEED-G02-0028 measured -1,085,440 B on
# 2026-07-29 and +135,168 B in r5, the same case under the same fault class. A leak is a fraction
# of the working set, which is scale-free and therefore comparable across runs, hosts, and
# differently sized services; a byte count is not.
#
# Calibrated on 56 case-measurements pooled from two independent runs (r5 and the 2026-07-29
# diagnostic scan): true leaks are >= 10.39% of the healthy median, every non-leak case is <=
# 3.87%. Every value in [0.04, 0.10] gives zero false qualifications and zero missed leaks, so this
# sits mid-plateau rather than on a cliff edge. It raises the floor only; the absolute cutoff still
# applies when it is the stricter of the two.
#
# AMD-0006's first stated reason for retiring metric v1 was that "the ambient `working_set` field
# intercepted three unrelated fault classes". Metric v2 removed the presence shortcut but left the
# same ambient signal able to intercept through a magnitude cutoff. This closes that second form.
RELATIVE_ROOT_SIGNAL_FLOORS: dict[str, float] = {
    "emailMemoryLeak": 0.05,
}

FORBIDDEN_PUBLIC_KEYS = {
    "answer",
    "checkout_failed",
    "connection_error",
    "correlated_error",
    "correlated_span",
    "fault_action",
    "fault_class",
    "fault_stimulus",
    "ground_truth",
    "ground_truth_ref",
    "journey_failed",
    "kafka_error",
    "kafka_fault_log",
    "kafka_log_error",
    "locked_test",
    "payment_error",
    "sealed_truth",
}


class ReadinessObserver(Protocol):
    def __call__(self, phase: str, fault_class: str) -> Mapping[str, Any]: ...

    def collect_healthy_window(self) -> Mapping[str, Any]: ...


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def _digest_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _walk_forbidden(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key)
            if name in FORBIDDEN_PUBLIC_KEYS or "stimulus" in name.casefold():
                found.add(name)
            found.update(_walk_forbidden(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_walk_forbidden(child))
    return found


def _finite_measurement(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def evidence_id_v3(
    case_id: str,
    kind: str,
    *,
    metric_version: int = METRIC_VERSION,
) -> str:
    require_v3_metric_version(metric_version)
    if kind not in EVIDENCE_KINDS:
        raise GovernanceError(f"metric v3 received an unknown evidence kind: {kind}")
    subject = f"{case_id}\0{metric_version}\0{kind}".encode()
    return "ev3-" + hashlib.sha256(subject).hexdigest()[:24]


def _public_window(sample: Mapping[str, Any], window: str) -> dict[str, Any]:
    if window not in {"healthy", "fault"}:
        raise DatasetIncompleteError("metric v3 window has an invalid phase")
    required = {
        "recorded_at",
        "ready",
        "journey_status",
        "cpu_rate",
        "working_set",
        "consumer_lag",
        "consumer_record_lag",
        "consumer_poll_lag_seconds",
        "trace_activity",
        "trace_errors",
    }
    missing = sorted(required - set(sample))
    if missing:
        raise DatasetIncompleteError(
            "metric v3 collector omitted public measurements: " + ", ".join(missing)
        )
    # Every window must carry all six groups for every label, so a null
    # measurement cannot be projected: emitting one group as null only for the
    # labels whose series happened to be absent would itself leak the label.
    #
    # This is a residual invariant, not the live handling of a scrape gap. The
    # collector already polls until every series is present and only raises once
    # one is still absent at the observation deadline, so reaching here means the
    # window arrived incomplete despite that wait.
    absent = sorted(
        name
        for name in (
            "cpu_rate",
            "working_set",
            "consumer_lag",
            "consumer_record_lag",
            "consumer_poll_lag_seconds",
        )
        if sample[name] is None
    )
    if absent:
        raise InfrastructureFailure(
            "metric v3 collector reported absent Prometheus series: " + ", ".join(absent)
        )
    activity = sample["trace_activity"]
    errors = sample["trace_errors"]
    expected_services = set(V3_TRACE_QUERY_SERVICES)
    if not isinstance(activity, Mapping) or set(activity) != expected_services:
        raise DatasetIncompleteError(
            "metric v3 trace activity does not cover the fixed service set"
        )
    if not isinstance(errors, Mapping) or set(errors) != expected_services:
        raise DatasetIncompleteError(
            "metric v3 trace errors do not cover the fixed service set"
        )
    public_errors: dict[str, dict[str, Any]] = {}
    for service in V3_TRACE_QUERY_SERVICES:
        item = errors[service]
        if not isinstance(item, Mapping):
            raise DatasetIncompleteError(
                "metric v3 trace error measurement is not an object"
            )
        descriptions = item.get("descriptions")
        if not isinstance(descriptions, list):
            raise DatasetIncompleteError(
                "metric v3 trace error descriptions are not a list"
            )
        public_errors[service] = {
            "connection_error_count": int(item.get("connection_error_count", 0)),
            "descriptions": [str(value) for value in descriptions],
            "error_count": int(item.get("error_count", 0)),
        }
    return {
        "phase": window,
        "recorded_at": str(sample["recorded_at"]),
        "ready": bool(sample["ready"]),
        "journey_status": int(sample["journey_status"]),
        "cpu_cores": float(sample["cpu_rate"]),
        "working_set_bytes": float(sample["working_set"]),
        "consumer_lag": float(sample["consumer_lag"]),
        "consumer_record_lag": float(sample["consumer_record_lag"]),
        "consumer_poll_lag_seconds": float(sample["consumer_poll_lag_seconds"]),
        "trace_activity": {service: int(activity[service]) for service in V3_TRACE_QUERY_SERVICES},
        "trace_errors": public_errors,
    }


def build_observation_packet_v3(
    scenario: Mapping[str, Any],
    healthy_windows: Sequence[Mapping[str, Any]],
    fault_windows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    case_id = str(scenario.get("scenario_id", ""))
    brief = scenario.get("problem_brief")
    if not case_id or not isinstance(brief, str) or not brief:
        raise DatasetIncompleteError("metric v3 scenario cannot produce a public packet")
    if len(healthy_windows) != HEALTHY_WINDOW_COUNT:
        raise DatasetIncompleteError("metric v3 requires exactly five healthy windows")
    if len(fault_windows) != FAULT_WINDOW_COUNT:
        raise DatasetIncompleteError("metric v3 requires exactly two fault windows")
    projected_windows = [
        *(_public_window(item, "healthy") for item in healthy_windows),
        *(_public_window(item, "fault") for item in fault_windows),
    ]
    windows = [
        {
            "index": index,
            "phase": item["phase"],
            "recorded_at": item["recorded_at"],
        }
        for index, item in enumerate(projected_windows)
    ]
    evidence = [
        {
            "id": evidence_id_v3(case_id, "journey_window"),
            "kind": "journey_window",
            "source": "frontend-proxy",
            "samples": [
                {
                    "window_index": index,
                    "ready": item["ready"],
                    "status_code": item["journey_status"],
                }
                for index, item in enumerate(projected_windows)
            ],
        },
        {
            "id": evidence_id_v3(case_id, "trace_activity"),
            "kind": "trace_activity",
            "source": "jaeger",
            "service_scope": list(V3_TRACE_QUERY_SERVICES),
            "samples": [
                {
                    "window_index": index,
                    "services": {
                        service: {"trace_count": item["trace_activity"][service]}
                        for service in V3_TRACE_QUERY_SERVICES
                    },
                }
                for index, item in enumerate(projected_windows)
            ],
        },
        {
            "id": evidence_id_v3(case_id, "trace_errors"),
            "kind": "trace_errors",
            "source": "jaeger",
            "service_scope": list(V3_TRACE_QUERY_SERVICES),
            "samples": [
                {
                    "window_index": index,
                    "services": item["trace_errors"],
                }
                for index, item in enumerate(projected_windows)
            ],
        },
        {
            "id": evidence_id_v3(case_id, "cpu_window"),
            "kind": "cpu_window",
            "source": "prometheus",
            "service": "ad",
            "metric": "container_cpu_usage_rate",
            "unit": "cpu_cores",
            "samples": [
                {
                    "window_index": index,
                    "cpu_cores": item["cpu_cores"],
                }
                for index, item in enumerate(projected_windows)
            ],
        },
        {
            "id": evidence_id_v3(case_id, "memory_window"),
            "kind": "memory_window",
            "source": "prometheus",
            "service": "email",
            "metric": "container_memory_working_set",
            "unit": "bytes",
            "samples": [
                {
                    "window_index": index,
                    "working_set_bytes": item["working_set_bytes"],
                }
                for index, item in enumerate(projected_windows)
            ],
        },
        {
            "id": evidence_id_v3(case_id, "queue_window"),
            "kind": "queue_window",
            "source": "prometheus",
            "service": "fraud-detection",
            "metric": "consumer_poll_lag",
            "unit": "seconds",
            "samples": [
                {
                    "window_index": index,
                    "consumer_lag": item["consumer_lag"],
                    "consumer_poll_lag_seconds": item["consumer_poll_lag_seconds"],
                    "consumer_record_lag": item["consumer_record_lag"],
                }
                for index, item in enumerate(projected_windows)
            ],
        },
    ]
    packet = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "metric_version": METRIC_VERSION,
        "case_id": case_id,
        "problem_brief": brief,
        "evidence_catalog_version": "g03-readiness-v3",
        "windows": windows,
        "observations": evidence,
    }
    packet["packet_digest"] = _digest_json(packet)
    validate_observation_packet_v3(packet)
    return packet


def validate_observation_packet_v3(packet: Mapping[str, Any]) -> dict[str, Any]:
    expected_top = {
        "schema_version",
        "metric_version",
        "case_id",
        "problem_brief",
        "evidence_catalog_version",
        "windows",
        "observations",
        "packet_digest",
    }
    if set(packet) != expected_top:
        raise DatasetIncompleteError("metric v3 public packet top-level shape drifted")
    if packet.get("schema_version") != WIRE_SCHEMA_VERSION:
        raise DatasetIncompleteError("metric v3 wire schema version drifted")
    if packet.get("metric_version") != METRIC_VERSION:
        raise DatasetIncompleteError("metric v3 semantic version drifted")
    windows = packet.get("windows")
    if (
        not isinstance(windows, list)
        or len(windows) != HEALTHY_WINDOW_COUNT + FAULT_WINDOW_COUNT
        or [item.get("index") for item in windows if isinstance(item, Mapping)] != list(range(7))
        or [item.get("phase") for item in windows if isinstance(item, Mapping)]
        != ["healthy"] * 5 + ["fault"] * 2
        or any(
            not isinstance(item, Mapping)
            or set(item) != {"index", "phase", "recorded_at"}
            or not isinstance(item.get("recorded_at"), str)
            or not item.get("recorded_at")
            for item in windows
        )
    ):
        raise DatasetIncompleteError("metric v3 packet window registry is incomplete")
    observations = packet.get("observations")
    if not isinstance(observations, list) or len(observations) != len(EVIDENCE_KINDS):
        raise DatasetIncompleteError(
            "metric v3 packet must contain exactly six evidence groups"
        )
    kinds = [str(item.get("kind")) for item in observations if isinstance(item, Mapping)]
    if set(kinds) != set(EVIDENCE_KINDS) or len(kinds) != len(EVIDENCE_KINDS):
        raise DatasetIncompleteError(
            "metric v3 evidence kinds are incomplete or duplicated"
        )
    case_id = str(packet.get("case_id", ""))
    signatures = []
    for item in observations:
        if not isinstance(item, Mapping):
            raise DatasetIncompleteError("metric v3 evidence group is not an object")
        kind = str(item["kind"])
        if set(item) != GROUP_FIELDS[kind]:
            raise DatasetIncompleteError(
                f"metric v3 evidence group fields drifted for {kind}"
            )
        if item.get("id") != evidence_id_v3(case_id, kind):
            raise GovernanceError("metric v3 evidence ID is not kind-derived and opaque")
        samples = item.get("samples")
        if not isinstance(samples, list) or len(samples) != 7:
            raise DatasetIncompleteError(
                "metric v3 evidence group must contain seven real samples"
            )
        if any(
            not isinstance(sample, Mapping)
            or set(sample) != GROUP_SAMPLE_FIELDS[kind]
            for sample in samples
        ):
            raise DatasetIncompleteError(
                f"metric v3 evidence sample fields drifted for {kind}"
            )
        sample_indices = [
            sample.get("window_index") for sample in samples if isinstance(sample, Mapping)
        ]
        if sample_indices != list(range(7)):
            raise DatasetIncompleteError(
                "metric v3 evidence samples do not cover all seven windows"
            )
        if kind == "journey_window":
            if any(
                type(sample["ready"]) is not bool
                or type(sample["status_code"]) is not int
                for sample in samples
            ):
                raise DatasetIncompleteError(
                    "metric v3 journey samples contain invalid measurements"
                )
        elif kind in {"trace_activity", "trace_errors"}:
            if item.get("service_scope") != list(V3_TRACE_QUERY_SERVICES):
                raise DatasetIncompleteError(
                    f"metric v3 {kind} service scope drifted"
                )
            for sample in samples:
                services = sample["services"]
                if not isinstance(services, Mapping) or set(services) != set(
                    V3_TRACE_QUERY_SERVICES
                ):
                    raise DatasetIncompleteError(
                        f"metric v3 {kind} sample service set drifted"
                    )
                for service in V3_TRACE_QUERY_SERVICES:
                    measurement = services[service]
                    if not isinstance(measurement, Mapping):
                        raise DatasetIncompleteError(
                            f"metric v3 {kind} service measurement is not an object"
                        )
                    if kind == "trace_activity":
                        valid = set(measurement) == {"trace_count"} and _finite_measurement(
                            measurement.get("trace_count")
                        )
                    else:
                        descriptions = measurement.get("descriptions")
                        valid = (
                            set(measurement)
                            == {
                                "connection_error_count",
                                "descriptions",
                                "error_count",
                            }
                            and _finite_measurement(
                                measurement.get("connection_error_count")
                            )
                            and _finite_measurement(measurement.get("error_count"))
                            and isinstance(descriptions, list)
                            and all(isinstance(value, str) for value in descriptions)
                        )
                    if not valid:
                        raise DatasetIncompleteError(
                            f"metric v3 {kind} service fields drifted"
                        )
        else:
            measurement_fields = GROUP_SAMPLE_FIELDS[kind] - {"window_index"}
            if any(
                not all(_finite_measurement(sample[field]) for field in measurement_fields)
                for sample in samples
            ):
                raise DatasetIncompleteError(
                    f"metric v3 {kind} samples contain invalid measurements"
                )
        signatures.append(bool(samples))
    forbidden = sorted(_walk_forbidden(packet))
    if forbidden:
        raise GovernanceError(
            "metric v3 public packet contains sealed/evaluator fields: " + ", ".join(forbidden)
        )
    subject = {key: _json_copy(value) for key, value in packet.items() if key != "packet_digest"}
    if packet.get("packet_digest") != _digest_json(subject):
        raise GovernanceError("metric v3 packet digest is stale")
    return {"status": "pass", "signature": signatures}


def _group_by_kind(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    validate_observation_packet_v3(packet)
    return {str(item["kind"]): item for item in packet["observations"] if isinstance(item, Mapping)}


def ground_truth_v3(case_id: str, root_cause: str) -> dict[str, Any]:
    try:
        required_kinds = set(REQUIRED_KINDS[root_cause])
    except KeyError as error:
        raise GovernanceError(
            f"metric v3 received an unknown sealed label: {root_cause}"
        ) from error
    all_kinds = set(EVIDENCE_KINDS)
    distractor_kinds = all_kinds - required_kinds
    return {
        "case_id": case_id,
        "root_cause": root_cause,
        "required_evidence": sorted(evidence_id_v3(case_id, kind) for kind in required_kinds),
        "distractor_evidence": sorted(evidence_id_v3(case_id, kind) for kind in distractor_kinds),
        "required_kinds": sorted(required_kinds),
        "distractor_kinds": sorted(distractor_kinds),
    }


def _contains_observed_nonzero(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value)) and float(value) != 0.0
    if isinstance(value, Mapping):
        return any(
            _contains_observed_nonzero(child)
            for key, child in value.items()
            if key != "window_index"
        )
    if isinstance(value, list):
        return any(_contains_observed_nonzero(child) for child in value)
    return False


def scenario_cases_v3(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    trials = document.get("trials")
    if not isinstance(trials, list) or len(trials) != 32:
        raise DatasetIncompleteError(
            "metric v3 dataset requires exactly 32 fresh scenario trials"
        )
    cases: dict[str, dict[str, Any]] = {}
    canonical_fields: dict[str, tuple[str, ...]] | None = None
    for record in trials:
        if not isinstance(record, Mapping) or record.get("status") != "pass":
            raise DatasetIncompleteError("metric v3 dataset contains an incomplete scenario")
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise DatasetIncompleteError("metric v3 scenario trial lacks a payload")
        packet = payload.get("observation_packet")
        if not isinstance(packet, Mapping):
            raise DatasetIncompleteError("metric v3 scenario trial lacks a public packet")
        validate_observation_packet_v3(packet)
        case_id = str(packet["case_id"])
        root_cause = str(payload.get("fault_class", ""))
        truth = ground_truth_v3(case_id, root_cause)
        groups = _group_by_kind(packet)
        fields = {
            kind: tuple(sorted(str(key) for key in groups[kind]["samples"][0]))
            for kind in EVIDENCE_KINDS
        }
        if canonical_fields is None:
            canonical_fields = fields
        elif fields != canonical_fields:
            raise DatasetIncompleteError("metric v3 sample fields differ across cases")
        distractor_nonzero = [
            kind
            for kind in truth["distractor_kinds"]
            if _contains_observed_nonzero(groups[kind]["samples"])
        ]
        if not distractor_nonzero:
            raise DatasetIncompleteError(
                f"metric v3 case {case_id} lacks a real non-zero distractor signal"
            )
        cases[case_id] = {
            "packet": _json_copy(packet),
            "ground_truth": truth,
            "family": str(payload.get("family") or payload.get("result", {}).get("family", "")),
            "nonzero_distractor_kinds": sorted(distractor_nonzero),
        }
    if len(cases) != 32:
        raise DatasetIncompleteError("metric v3 case IDs are not unique")
    return cases


def dataset_digest_v3(document: Mapping[str, Any]) -> str:
    cases = scenario_cases_v3(document)
    subject = {
        case_id: {
            "packet_digest": case["packet"]["packet_digest"],
            "ground_truth": case["ground_truth"],
            "family": case["family"],
        }
        for case_id, case in sorted(cases.items())
    }
    return _digest_json({"metric_version": METRIC_VERSION, "cases": subject})


def presence_only_probe_v3(document: Mapping[str, Any]) -> dict[str, Any]:
    cases = scenario_cases_v3(document)
    signature_labels: dict[tuple[str, ...], Counter[str]] = {}
    for case in cases.values():
        packet = case["packet"]
        signature = tuple(
            sorted(
                str(group["kind"])
                for group in packet["observations"]
                if isinstance(group, Mapping) and bool(group.get("samples"))
            )
        )
        signature_labels.setdefault(signature, Counter()).update(
            [str(case["ground_truth"]["root_cause"])]
        )
    top1 = 0
    top3 = 0
    for counts in signature_labels.values():
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        top1 += ordered[0][1]
        top3 += sum(count for _, count in ordered[:3])
    return {
        "classifier": "nonempty-group-signature-majority-prior",
        "group_completeness": {
            "status": "pass",
            "required_groups": list(EVIDENCE_KINDS),
            "complete_case_count": len(cases),
            "incomplete_case_ids": [],
        },
        "signature_count": len(signature_labels),
        "case_count": len(cases),
        "top1_count": top1,
        "top1": top1 / len(cases),
        "top3_count": top3,
        "top3": top3 / len(cases),
        "expected_top1_count": 8,
        "maximum_top3_count": 20,
        "status": "pass" if top1 == 8 and top3 <= 20 else "fail",
    }


def _samples_for_kind_v3(
    packet: Mapping[str, Any], kind: str
) -> tuple[str, list[Mapping[str, Any]]]:
    group = _group_by_kind(packet).get(kind)
    if group is None:
        raise GovernanceError(f"metric v3 packet lacks evidence kind: {kind}")
    samples = group.get("samples")
    if not isinstance(samples, list):
        raise GovernanceError(f"metric v3 evidence kind lacks samples: {kind}")
    return str(group["id"]), [sample for sample in samples if isinstance(sample, Mapping)]


def _sample_phase(packet: Mapping[str, Any], sample: Mapping[str, Any]) -> str:
    index = sample.get("window_index")
    windows = packet.get("windows")
    if (
        not isinstance(index, int)
        or not isinstance(windows, list)
        or index not in range(len(windows))
    ):
        raise GovernanceError("metric v3 sample has an invalid window index")
    window = windows[index]
    if not isinstance(window, Mapping) or window.get("index") != index:
        raise GovernanceError("metric v3 packet window registry drifted")
    return str(window.get("phase"))


def _feature_values(
    packet: Mapping[str, Any], label: str, feature: str, window: str
) -> list[float]:
    service = TARGET_SERVICES[label]
    if feature == "trace_activity":
        _, samples = _samples_for_kind_v3(packet, "trace_activity")
        values = [
                float(sample["services"][service]["trace_count"])
                for sample in samples
                if _sample_phase(packet, sample) == window
        ]
    elif feature == "root_signal":
        kind, field, _quantum = ROOT_SIGNAL_FEATURES[label]
        _, samples = _samples_for_kind_v3(packet, kind)
        if kind == "trace_errors":
            values = [
                float(sample["services"][service][field])
                for sample in samples
                if _sample_phase(packet, sample) == window
            ]
        else:
            values = [
                float(sample[field])
                for sample in samples
                if _sample_phase(packet, sample) == window
            ]
    else:
        raise GovernanceError(f"metric v3 received an unknown deterministic feature: {feature}")
    expected = HEALTHY_WINDOW_COUNT if window == "healthy" else FAULT_WINDOW_COUNT
    if len(values) != expected or any(not math.isfinite(value) for value in values):
        raise GovernanceError("metric v3 deterministic feature window is incomplete")
    return values


def _positive_consecutive_drifts(values: Sequence[float]) -> list[float]:
    if len(values) != HEALTHY_WINDOW_COUNT:
        raise GovernanceError("metric v3 healthy drift requires five values")
    return [
        max(0.0, float(right) - float(left))
        for left, right in zip(values[:-1], values[1:], strict=True)
    ]


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values or not 0.0 < percentile <= 1.0:
        raise GovernanceError("metric v3 percentile input is invalid")
    ordered = sorted(float(value) for value in values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def build_deterministic_thresholds_v3(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    cases = scenario_cases_v3(document)
    registry: dict[str, Any] = {}
    for case_id in sorted(cases):
        per_label: dict[str, Any] = {}
        other_packets = [
            case["packet"] for other_id, case in sorted(cases.items()) if other_id != case_id
        ]
        if len(other_packets) != 31:
            raise GovernanceError("metric v3 leave-one-case-out registry is incomplete")
        for label in ROOT_CAUSE_LABELS:
            signal_kind, signal_field, signal_quantum = ROOT_SIGNAL_FEATURES[label]
            feature_specs = {
                "trace_activity": {
                    "quantum": 1.0,
                    "kind": "trace_activity",
                    "field": "trace_count",
                },
                "root_signal": {
                    "quantum": signal_quantum,
                    "kind": signal_kind,
                    "field": signal_field,
                },
            }
            frozen: dict[str, Any] = {}
            for feature, spec in feature_specs.items():
                healthy_drifts = [
                    drift
                    for packet in other_packets
                    for drift in _positive_consecutive_drifts(
                        _feature_values(packet, label, feature, "healthy")
                    )
                ]
                p99 = _nearest_rank(healthy_drifts, DETERMINISTIC_PERCENTILE)
                entry = {
                    **spec,
                    "healthy_drift_count": len(healthy_drifts),
                    "healthy_p99": p99,
                    "threshold": p99 + float(spec["quantum"]),
                }
                # Relative floor for a signal with a large non-zero healthy baseline. Derived from
                # the current case's own healthy median, so it is recorded per case in the frozen
                # registry rather than applied invisibly at comparison time. Raises the cutoff only.
                fraction = RELATIVE_ROOT_SIGNAL_FLOORS.get(label)
                if feature == "root_signal" and fraction is not None:
                    healthy_level = float(
                        median(_feature_values(cases[case_id]["packet"], label, feature, "healthy"))
                    )
                    floor = healthy_level * fraction
                    entry["relative_floor_fraction"] = fraction
                    entry["relative_floor_healthy_median"] = healthy_level
                    entry["relative_floor"] = floor
                    entry["threshold"] = max(float(entry["threshold"]), floor)
                frozen[feature] = entry
            per_label[label] = {
                "target_service": TARGET_SERVICES[label],
                "features": frozen,
            }
        registry[case_id] = per_label
    document_out = {
        "metric_version": METRIC_VERSION,
        "method": "leave-one-case-out healthy consecutive positive drift",
        "percentile": DETERMINISTIC_PERCENTILE,
        "percentile_method": "nearest_rank",
        "threshold_formula": (
            "max(healthy_p99 + measurement_quantum, relative_floor) where a relative floor is "
            "registered for the label"
        ),
        "relative_root_signal_floors": dict(sorted(RELATIVE_ROOT_SIGNAL_FLOORS.items())),
        "incident_excess_formula": "max(fault) - median(healthy)",
        "candidate_rule": (
            "both features reach threshold (>=); the quantum term in the threshold carries the "
            "strictness"
        ),
        "ranking": "descending weakest standardized excess; label lexical tie-break",
        "quanta": {
            "count": 1,
            "cpu_cores": 0.000001,
            "memory_bytes": 4096,
            "lag_seconds": 0.001,
        },
        "cases": registry,
    }
    document_out["registry_digest"] = _digest_json(document_out)
    return document_out


def deterministic_candidates_v3(
    packet: Mapping[str, Any],
    case_thresholds: Mapping[str, Any],
) -> list[dict[str, Any]]:
    validate_observation_packet_v3(packet)
    candidates: list[dict[str, Any]] = []
    for label in ROOT_CAUSE_LABELS:
        threshold = case_thresholds.get(label)
        if not isinstance(threshold, Mapping):
            raise GovernanceError("metric v3 deterministic threshold registry lacks a label")
        observations: dict[str, Any] = {}
        standardized = []
        qualifies = True
        for feature in ("trace_activity", "root_signal"):
            feature_threshold = threshold["features"][feature]
            healthy = _feature_values(packet, label, feature, "healthy")
            fault = _feature_values(packet, label, feature, "fault")
            excess = max(fault) - float(median(healthy))
            cutoff = float(feature_threshold["threshold"])
            quantum = float(feature_threshold["quantum"])
            margin = excess - cutoff
            score = margin / max(cutoff, quantum)
            observations[feature] = {
                "healthy_median": float(median(healthy)),
                "fault_max": max(fault),
                "incident_excess": excess,
                "threshold": cutoff,
                "standardized_excess": score,
            }
            standardized.append(score)
            # `>=`, not `>`. The cutoff is already `healthy_p99 + measurement_quantum`, so clearing
            # it means the excess exceeds observed healthy noise by at least one minimum resolvable
            # unit -- the quantum term *is* the strictness. Also demanding a strict inequality
            # charged a second quantum, which on an integer counter meant a genuine one-count signal
            # was discarded: 9 of the 15 cases whose own true label failed to qualify in r5 failed
            # because the excess exactly equalled its cutoff (2 vs 2.0, 1 vs 1.0).
            #
            # This tightens discrimination rather than loosening the gate. Across r5, true-label
            # qualifications rise 17 -> 26 of 32 while false-label qualifications fall 4 -> 0 of the
            # 160 non-truth pairs; on the independent 2026-07-29 scan, 14 -> 19 of 24 true with
            # 6 -> 0 false. A relaxed threshold would have raised the false count, not zeroed it.
            qualifies = qualifies and excess >= cutoff
        if qualifies:
            candidates.append(
                {
                    "label": label,
                    "weakest_standardized_excess": min(standardized),
                    "observations": observations,
                }
            )
    return sorted(
        candidates,
        key=lambda item: (-float(item["weakest_standardized_excess"]), str(item["label"])),
    )


def deterministic_baseline_v3(
    packet: Mapping[str, Any],
    case_thresholds: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = deterministic_candidates_v3(packet, case_thresholds)
    case_id = str(packet["case_id"])
    if candidates:
        root = str(candidates[0]["label"])
        kinds = REQUIRED_KINDS[root]
    else:
        root = "unknown"
        kinds = EVIDENCE_KINDS
    evidence = sorted(evidence_id_v3(case_id, kind) for kind in kinds)
    result = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "metric_version": METRIC_VERSION,
        "case_id": case_id,
        "status": "ok",
        "baseline": "deterministic",
        "root_cause": root,
        "root_cause_candidates": [str(item["label"]) for item in candidates[:3]] or ["unknown"],
        "evidence": evidence,
        "claims": [
            {
                "claim_type": "root_cause",
                "value": root,
                "evidence_refs": evidence,
            }
        ],
    }
    return result, {
        "qualified_candidates": candidates,
        "examined_evidence_kinds": list(EVIDENCE_KINDS),
    }


def validate_result_v3(
    result: Mapping[str, Any],
    *,
    metric_version: int = METRIC_VERSION,
) -> None:
    require_v3_metric_version(metric_version)
    try:
        Draft202012Validator.check_schema(RESULT_SCHEMA_V3)
        Draft202012Validator(RESULT_SCHEMA_V3).validate(dict(result))
    except ValidationError as error:
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise GovernanceError(
            f"baseline result violates metric v3 schema at {location}: {error.message}"
        ) from error


def _failure_v3(reason: str, failure_class: str = "malformed") -> dict[str, Any]:
    return {
        "status": "scored_failure",
        "failure_class": failure_class,
        "reason": reason,
        "core_e2e": 0.0,
        "root_cause_top3": 0.0,
        "evidence_precision": 0.0,
        "unsupported_critical_claim": 1.0,
        "tool_schema_validity": None,
        "output_schema_validity": 0.0 if failure_class == "malformed" else 1.0,
    }


def score_result_v3(
    result: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
    *,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    try:
        validate_result_v3(result, metric_version=metric_version)
    except GovernanceError as error:
        return _failure_v3(str(error))
    expected_case = str(ground_truth.get("case_id", ""))
    if str(result["case_id"]) != expected_case:
        return _failure_v3(
            "result case_id does not match the sealed case",
            "case_id_mismatch",
        )
    expected = str(ground_truth.get("root_cause", ""))
    required = {str(item) for item in ground_truth.get("required_evidence", [])}
    distractors = {str(item) for item in ground_truth.get("distractor_evidence", [])}
    if (
        expected not in ROOT_CAUSE_LABELS
        or len(required) < 2
        or required.intersection(distractors)
        or len(required | distractors) != len(EVIDENCE_KINDS)
    ):
        raise GovernanceError("metric v3 ground truth is incomplete or contradictory")
    universe = required | distractors
    actual = str(result["root_cause"])
    candidates = [str(item) for item in result["root_cause_candidates"]]
    claim = result["claims"][0]
    claim_value = str(claim["value"])
    invalid_labels = sorted(
        {label for label in [actual, *candidates, claim_value] if label not in ROOT_CAUSE_LABELS}
    )
    if invalid_labels:
        return _failure_v3(
            "closed root-cause labels were not used: " + ", ".join(invalid_labels),
            "invalid_label",
        )
    if claim_value != actual:
        return _failure_v3(
            "typed root-cause claim does not match root_cause",
            "claim_contract",
        )
    selected = {str(item) for item in result["evidence"]}
    claim_refs = {str(item) for item in claim["evidence_refs"]}
    if selected != claim_refs:
        return _failure_v3(
            "top-level evidence and typed-claim evidence_refs differ",
            "claim_contract",
        )
    unknown = sorted(selected - universe)
    if unknown:
        return _failure_v3(
            "diagnosis references unknown evidence: " + ", ".join(unknown),
            "unknown_evidence",
        )
    cited_distractors = selected.intersection(distractors)
    complete = required.issubset(selected)
    supported = actual == expected and complete and not cited_distractors
    top3 = actual == expected or expected in candidates[:3]
    precision = len(selected.intersection(required)) / len(selected) if selected else 0.0
    if cited_distractors:
        failure_class = "distractor_evidence"
    elif actual != expected:
        failure_class = "wrong_root_cause"
    elif not complete:
        failure_class = "missing_required_evidence"
    elif not supported:
        failure_class = "unsupported_critical_claim"
    else:
        failure_class = None
    return {
        "status": "scored",
        "failure_class": failure_class,
        "core_e2e": 1.0 if supported else 0.0,
        "root_cause_top3": 1.0 if top3 else 0.0,
        "evidence_precision": precision,
        "unsupported_critical_claim": 0.0 if supported else 1.0,
        "tool_schema_validity": None,
        "output_schema_validity": 1.0,
    }


def run_deterministic_matrix_v3(
    producer_sha: str,
    scenario_document: Mapping[str, Any],
    dataset_digest: str,
    *,
    metric_definition_digest: str | None = None,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    cases = scenario_cases_v3(scenario_document)
    thresholds = build_deterministic_thresholds_v3(scenario_document)
    rows = []
    ambiguity_case_ids: list[str] = []
    ambiguity_labels: dict[str, list[str]] = {}
    for case_id in sorted(cases):
        case = cases[case_id]
        case_thresholds = thresholds["cases"][case_id]
        result, diagnostics = deterministic_baseline_v3(
            case["packet"],
            case_thresholds,
        )
        ambiguous = [
            str(item["label"])
            for item in diagnostics["qualified_candidates"]
            if item["label"] != case["ground_truth"]["root_cause"]
            and ROOT_SIGNAL_FEATURES[str(item["label"])][0]
            in case["ground_truth"]["distractor_kinds"]
        ]
        if ambiguous:
            ambiguity_case_ids.append(case_id)
            ambiguity_labels[case_id] = sorted(ambiguous)
            continue
        rows.append(
            {
                "case_id": case_id,
                "family": case["family"],
                "ground_truth_access": False,
                "result": result,
                "diagnostics": diagnostics,
                **score_result_v3(result, case["ground_truth"]),
            }
        )
    return {
        "status": "pass" if not ambiguity_case_ids else "diagnostic_only",
        "execution_status": "completed",
        "metric_version": metric_version,
        "metric_definition_digest": metric_definition_digest,
        "producer_sha": producer_sha,
        "dataset_digest": dataset_digest,
        "threshold_registry": thresholds,
        "N": len(rows),
        "expected_N": 32,
        "ambiguity_count": len(ambiguity_case_ids),
        "ambiguity_case_ids": ambiguity_case_ids,
        "ambiguity_labels": ambiguity_labels,
        "diagnostic_only": bool(ambiguity_case_ids),
        "rows": rows,
    }


def percentile_cluster_bootstrap_v3(
    rows: Iterable[Mapping[str, Any]],
    metric: str,
    *,
    seed: str,
    B: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if row.get(metric) is None:
            raise GovernanceError(f"metric v3 bootstrap metric was not computed: {metric}")
        grouped.setdefault(str(row["case_id"]), []).append(float(row[metric]))
    if not grouped:
        raise GovernanceError("metric v3 bootstrap requires case clusters")
    clusters = [grouped[key] for key in sorted(grouped)]
    point = sum(sum(values) / len(values) for values in clusters) / len(clusters)
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    samples = []
    for _ in range(B):
        picked = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        samples.append(sum(sum(values) / len(values) for values in picked) / len(picked))
    samples.sort()
    return {
        "estimate": point,
        "lower": samples[max(0, math.floor(0.025 * B) - 1)],
        "upper": samples[min(B - 1, math.floor(0.975 * B))],
        "B": B,
    }


def paired_cluster_bootstrap_v3(
    left_rows: Iterable[Mapping[str, Any]],
    right_rows: Iterable[Mapping[str, Any]],
    *,
    seed: str,
    B: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, float]:
    def indexed(
        rows: Iterable[Mapping[str, Any]],
    ) -> dict[tuple[str, int], float]:
        result: dict[tuple[str, int], float] = {}
        for row in rows:
            key = (str(row["case_id"]), int(row.get("repetition", 1)))
            if key in result:
                raise GovernanceError("metric v3 paired bootstrap found duplicate trial keys")
            result[key] = float(row["core_e2e"])
        return result

    left = indexed(left_rows)
    right = indexed(right_rows)
    if set(left) != set(right):
        raise GovernanceError("metric v3 paired bootstrap arms are not aligned")
    grouped: dict[str, list[float]] = {}
    for key in sorted(left):
        grouped.setdefault(key[0], []).append(left[key] - right[key])
    clusters = [grouped[key] for key in sorted(grouped)]
    if len(clusters) != 32:
        raise GovernanceError("metric v3 paired bootstrap requires 32 case clusters")
    point = sum(sum(values) / len(values) for values in clusters) / len(clusters)
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    samples = []
    for _ in range(B):
        picked = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        samples.append(sum(sum(values) / len(values) for values in picked) / len(picked))
    samples.sort()
    return {
        "estimate": point,
        "lower": samples[max(0, math.floor(0.025 * B) - 1)],
        "upper": samples[min(B - 1, math.floor(0.975 * B))],
        "B": B,
    }


_FAULT_PREDICATE_TERMS: dict[str, tuple[str, ...]] = {
    "productCatalogFailure": ("journey_failed", "correlated_error"),
    "adHighCpu": ("cpu_rate", "baseline_cpu_max", "correlated_span"),
    "emailMemoryLeak": ("working_set", "baseline_working_set"),
    "paymentFailure": ("checkout_failed", "payment_error", "error_spans"),
    "paymentUnreachable": (
        "checkout_failed",
        "connection_error",
        "checkout_error_spans",
        "payment_connection_errors",
    ),
    "kafkaQueueProblems": (
        "consumer_lag",
        "baseline_lag",
        "kafka_error",
        "kafka_log_error",
        "kafka_fault_log",
        "error_spans",
    ),
}
_RECOVERY_PREDICATE_TERMS = ("ready", "journey_healthy", "signal_not_worsening")


def _predicate_terms_v3(
    fault_class: str,
    observations: Sequence[Mapping[str, Any]],
    terms: Sequence[str],
) -> list[dict[str, Any]]:
    """Record each predicate term per observation so a failure explains itself."""
    return [
        {
            "observation_index": index,
            "recorded_at": str(item.get("recorded_at", "")),
            "terms": {term: _json_copy(item.get(term)) for term in terms},
        }
        for index, item in enumerate(observations)
    ]


def _scenario_failure_diagnostics_v3(
    fault_class: str,
    healthy_windows: Sequence[Mapping[str, Any]],
    fault_observations: Sequence[Mapping[str, Any]],
    recovery_observations: Sequence[Mapping[str, Any]],
    *,
    primary_error: Exception | None,
    cleanup_error: Exception | None,
) -> dict[str, Any]:
    """Everything needed to attribute a failure without a second live run.

    The previous failure path recorded only ``{scenario_id, fault_class,
    reason}``, so every failure required a separate manual diagnostic run — and
    a re-run is a different sample, which means the original failure could not
    be explained at all. This keeps the observations that were already taken.
    """
    fault_terms = _FAULT_PREDICATE_TERMS.get(fault_class, ())
    return {
        "fault_class": fault_class,
        "healthy_window_count": len(healthy_windows),
        "fault_observation_count": len(fault_observations),
        "recovery_observation_count": len(recovery_observations),
        "primary_error": None if primary_error is None else str(primary_error),
        "primary_error_type": (
            None if primary_error is None else type(primary_error).__name__
        ),
        "cleanup_error": None if cleanup_error is None else str(cleanup_error),
        "cleanup_error_type": (
            None if cleanup_error is None else type(cleanup_error).__name__
        ),
        "fault_state": str(fault_state(fault_class, fault_observations)),
        "recovery_state": str(recovery_state(recovery_observations)),
        "healthy_windows": _json_copy(list(healthy_windows)),
        "fault_observations": _json_copy(list(fault_observations)),
        "recovery_observations": _json_copy(list(recovery_observations)),
        "fault_predicate_terms": _predicate_terms_v3(
            fault_class, fault_observations, fault_terms
        ),
        "recovery_predicate_terms": _predicate_terms_v3(
            fault_class, recovery_observations, _RECOVERY_PREDICATE_TERMS
        ),
    }


def run_readiness_scenario_v3(
    scenario: Mapping[str, Any],
    client: Any,
    observer: ReadinessObserver,
    *,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    action = scenario.get("fault_action")
    fault_class = str(action.get("class", "")) if isinstance(action, Mapping) else ""
    adapter = ADAPTERS.get(fault_class)
    if adapter is None:
        raise GovernanceError(f"metric v3 scenario uses unknown fault action: {fault_class}")
    original = client.read()
    if observer("control", fault_class).get("state") != OracleState.HEALTHY:
        raise GovernanceError("metric v3 scenario healthy precondition is not proven")
    healthy_windows = [dict(observer.collect_healthy_window()) for _ in range(HEALTHY_WINDOW_COUNT)]
    fault_observations: list[Mapping[str, Any]] = []
    recovery_observations: list[Mapping[str, Any]] = []
    primary_error: Exception | None = None
    cleanup_error: Exception | None = None
    try:
        injected = _mutated_document(original, adapter)
        client.write(injected)
        if client.read() != injected:
            raise GovernanceError("metric v3 fault injection readback mismatch")
        fault_observations = [
            observer("fault", fault_class),
            observer("fault", fault_class),
        ]
        if fault_state(fault_class, fault_observations) != OracleState.FAULT_ACTIVE:
            raise GovernanceError("metric v3 fault oracle did not reach FAULT_ACTIVE")
    except Exception as error:
        primary_error = error
    finally:
        try:
            client.write(original)
            if client.read() != original:
                raise GovernanceError("metric v3 exact flag restoration readback mismatch")
            recovery_observations = [
                observer("recovery", fault_class),
                observer("recovery", fault_class),
            ]
            if recovery_state(recovery_observations) != OracleState.HEALTHY:
                raise GovernanceError("metric v3 recovery oracle did not reach HEALTHY")
        except Exception as error:
            cleanup_error = error
    if primary_error is not None or cleanup_error is not None:
        diagnostics = _scenario_failure_diagnostics_v3(
            fault_class,
            healthy_windows,
            fault_observations,
            recovery_observations,
            primary_error=primary_error,
            cleanup_error=cleanup_error,
        )
        # The primary error is the one that explains the case. Cleanup failures
        # used to be raised first, which hid the fault-oracle failure underneath
        # a recovery symptom whenever both occurred. Report the primary cause and
        # carry the cleanup failure alongside it.
        if primary_error is not None:
            raised: Exception = primary_error
            if cleanup_error is not None and not isinstance(
                primary_error, InfrastructureFailure
            ):
                raised = GovernanceError(
                    f"{primary_error}; cleanup also failed and quarantined the SUT: "
                    f"{cleanup_error}"
                )
                raised.__cause__ = primary_error
        elif isinstance(cleanup_error, InfrastructureFailure):
            raised = cleanup_error
        else:
            raised = GovernanceError(
                f"metric v3 scenario cleanup blocked and quarantined the SUT: {cleanup_error}"
            )
            raised.__cause__ = cleanup_error
        raised.scenario_diagnostics = diagnostics  # type: ignore[attr-defined]
        raise raised
    packet = build_observation_packet_v3(
        scenario,
        healthy_windows,
        fault_observations,
    )
    return {
        "scenario_id": scenario["scenario_id"],
        "family": scenario["family"],
        "fault_class": fault_class,
        "state_sequence": ["HEALTHY", "FAULT_ACTIVE", "HEALTHY"],
        "healthy_windows": [_public_window(item, "healthy") for item in healthy_windows],
        "fault_windows": [_public_window(item, "fault") for item in fault_observations],
        "recovery_observations": _json_copy(recovery_observations),
        "poll_stimuli": {
            "fault": int(getattr(observer, "fault_poll_stimuli", 0)),
            "recovery": int(getattr(observer, "recovery_poll_stimuli", 0)),
        },
        "original_digest": hashlib.sha256(canonical_json(original).encode()).hexdigest(),
        "restored_digest": hashlib.sha256(canonical_json(client.read()).encode()).hexdigest(),
        "observation_packet": packet,
    }


def replay_all_scenarios_v3(
    root: Path,
    producer_sha: str,
    journal: TrialJournal,
    *,
    sut_producer_sha: str,
    client_factory: Callable[[str], Any] = RemoteFlagClient,
    observer_factory: Callable[[str, str], ReadinessObserver] = LiveReadinessObserverV3,
    metric_version: int = METRIC_VERSION,
    continue_on_case_failure: bool = False,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    collector_contract = validate_live_readiness_collector_checkpoint()
    if not FULL_SHA.fullmatch(sut_producer_sha):
        raise GovernanceError("metric v3 replay requires a full SUT producer SHA")
    config = load_lab_config(root)
    bootstrap = validate_lab_bootstrap(config)
    seeds = seed_catalog(bootstrap["image_set_digest"])
    validate_seed_catalog(seeds, bootstrap["image_set_digest"])
    completed: list[dict[str, Any]] = []
    case_outcomes: list[dict[str, Any]] = []
    failed_records: list[dict[str, Any]] = []
    for scenario in seeds:
        case_id = str(scenario["scenario_id"])
        fault_class = str(scenario["fault_action"]["class"])
        trial_id = f"g03-readiness-v3-scenario-{case_id.casefold()}"
        cache_key = semantic_cache_key(
            {
                "sut": bootstrap["image_set_digest"],
                "trace_service": collector_contract["contract_digest"],
            },
            ("sut", "trace_service"),
            input_digest=_digest_json(
                {
                    "metric_version": METRIC_VERSION,
                    "scenario": scenario,
                    "sut_producer_sha": sut_producer_sha,
                    "healthy_windows": HEALTHY_WINDOW_COUNT,
                    "fault_windows": FAULT_WINDOW_COUNT,
                }
            ),
        )
        previous = journal.read(trial_id)
        if previous and previous.get("status") == "pass" and previous.get("cache_key") == cache_key:
            completed.append(previous)
            case_outcomes.append(
                {
                    "scenario_id": case_id,
                    "fault_class": fault_class,
                    "status": "pass",
                    "inherited": True,
                }
            )
            continue
        if (
            previous
            and previous.get("cache_key") == cache_key
            and previous.get("status") in {"metric_fail", "blocked"}
            and not continue_on_case_failure
        ):
            reason = str(previous.get("payload", {}).get("reason", ""))
            legacy_transport_misclassification = previous.get(
                "status"
            ) == "metric_fail" and reason.startswith(
                "metric v3 scenario cleanup blocked and quarantined the SUT: "
                "metric-v3 live observation collection produced no result:"
            )
            if not legacy_transport_misclassification:
                raise GovernanceError(
                    f"metric v3 scenario {case_id} needs a semantic fix before replay"
                )
        journal.begin(
            trial_id,
            producer_sha=producer_sha,
            cache_key=cache_key,
            payload={"scenario_id": case_id, "fault_class": fault_class},
        )
        try:
            result = run_readiness_scenario_v3(
                scenario,
                client_factory(sut_producer_sha),
                observer_factory(sut_producer_sha, fault_class),
                metric_version=metric_version,
            )
            record = journal.finish(
                trial_id,
                "pass",
                {
                    "scenario_id": case_id,
                    "fault_class": fault_class,
                    "family": scenario["family"],
                    "result": result,
                    "observation_packet": result["observation_packet"],
                },
            )
        except (InfrastructureFailure, DatasetIncompleteError, GovernanceError) as error:
            status = (
                "infra_failed"
                if isinstance(error, InfrastructureFailure)
                else "metric_fail"
            )
            payload: dict[str, Any] = {
                "scenario_id": case_id,
                "fault_class": fault_class,
                "reason": str(error),
            }
            if isinstance(error, DatasetIncompleteError):
                payload["failure_class"] = "dataset_incomplete"
            # Keep the observations that were already taken. Without them every
            # failure needs a separate live diagnostic run, and that re-run is a
            # different sample, so the original failure is never explained.
            diagnostics = getattr(error, "scenario_diagnostics", None)
            if diagnostics is not None:
                payload["scenario_diagnostics"] = _json_copy(diagnostics)
            record = journal.finish(trial_id, status, payload)
            case_outcomes.append(
                {
                    "scenario_id": case_id,
                    "fault_class": fault_class,
                    "status": status,
                    "inherited": False,
                    "reason": str(error),
                    "has_diagnostics": diagnostics is not None,
                }
            )
            failed_records.append(record)
            if not continue_on_case_failure:
                result_status = status
                outcome: dict[str, Any] = {
                    "status": result_status,
                    "execution_status": "incomplete",
                    "metric_version": metric_version,
                    "scenario_count": len(completed),
                    "failed_trial": trial_id,
                    "trials": [*completed, record],
                    "case_outcomes": case_outcomes,
                }
                if isinstance(error, DatasetIncompleteError):
                    outcome["failure_class"] = "dataset_incomplete"
                return outcome
            continue
        completed.append(record)
        case_outcomes.append(
            {
                "scenario_id": case_id,
                "fault_class": fault_class,
                "status": "pass",
                "inherited": False,
                "poll_stimuli": _json_copy(result.get("poll_stimuli", {})),
            }
        )
    if continue_on_case_failure and failed_records:
        # A diagnostic sweep is never gate evidence. AMD-0007 already declares
        # any result with N < 32 diagnostic_only; this makes such a result
        # something the runner can deliberately produce instead of a side effect.
        return {
            "status": "metric_fail",
            "execution_status": "diagnostic_scan",
            "metric_version": metric_version,
            "scenario_count": len(completed),
            "attempted_case_count": len(seeds),
            "failed_case_count": len(failed_records),
            "diagnostic_only": True,
            "promotable_to_gate_evidence": False,
            "trials": [*completed, *failed_records],
            "case_outcomes": case_outcomes,
        }
    if len(completed) != 32:
        raise GovernanceError("metric v3 scenario replay did not complete 32 cases")
    return {
        "status": "pass",
        "execution_status": "completed",
        "metric_version": metric_version,
        "scenario_count": 32,
        "inherited_case_count": sum(
            1 for item in case_outcomes if item.get("inherited") is True
        ),
        "replayed_case_count": sum(
            1 for item in case_outcomes if item.get("inherited") is False
        ),
        "trials": completed,
        "case_outcomes": case_outcomes,
        "observation_packets": [
            _json_copy(record["payload"]["observation_packet"]) for record in completed
        ],
    }


def build_baseline_prompt_v3(
    baseline: str,
    packet: Mapping[str, Any],
    *,
    prior_diagnoses: Sequence[Mapping[str, Any]] = (),
    metric_version: int = METRIC_VERSION,
) -> list[dict[str, str]]:
    require_v3_metric_version(metric_version)
    validate_observation_packet_v3(packet)
    if baseline not in {"naive_react", "naive_react_single", "no_rag"}:
        raise GovernanceError(f"metric v3 received an unknown live baseline: {baseline}")
    labels = ", ".join(ROOT_CAUSE_LABELS)
    mode = (
        "Use a minimal ReAct-style diagnosis over only the supplied packet. "
        "Do not reveal private reasoning; return only the final structured diagnosis."
        if baseline in {"naive_react", "naive_react_single"}
        else "Use no retrieval and no tools. Diagnose only from the supplied packet."
    )
    system = (
        f"{mode} Choose only from this closed root-cause label set: {labels}. "
        "Return exactly one JSON object with root_cause, root_cause_candidates, evidence, and "
        "claims. root_cause and every candidate must use an exact label from the set. "
        "evidence must contain only packet IDs that directly support the diagnosis and must equal "
        "the typed claim's evidence_refs as a set. evidence must be COMPLETE as well as correct: "
        "cite every observation ID that supports the diagnosis, including the trace observation "
        "that localises the failing service, not only the single most striking signal. A diagnosis "
        "naming the right cause with an incomplete evidence set is scored as a failure. Most "
        "incidents require more than one observation ID. claims must contain exactly one object "
        'shaped as {"claim_type":"root_cause","value":"<exact label>",'
        '"evidence_refs":["<ID>","<ID>",...]}. '
        "Do not add keys. Never infer or request ground truth or locked-test data."
    )
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(packet, sort_keys=True, separators=(",", ":")),
        },
    ]
    for prior_diagnosis in prior_diagnoses:
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": json.dumps(
                        prior_diagnosis,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Recheck the same packet and prior structured diagnosis. "
                        "Return a corrected canonical structured diagnosis only."
                    ),
                },
            ]
        )
    return messages


def _canonical_diagnosis(result: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("root_cause", "root_cause_candidates", "evidence", "claims")
    if any(key not in result for key in keys):
        raise GovernanceError("metric-v3 baseline returned an incomplete diagnosis")
    return {key: _json_copy(result[key]) for key in keys}


def four_turn_input_upper_bound_v3(
    packet: Mapping[str, Any],
    *,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    base = build_baseline_prompt_v3("naive_react", packet, metric_version=metric_version)
    correction = (
        "Recheck the same packet and prior structured diagnosis. "
        "Return a corrected canonical structured diagnosis only."
    )
    system_bytes = len(base[0]["content"].encode("utf-8"))
    packet_bytes = len(base[1]["content"].encode("utf-8"))
    correction_bytes = len(correction.encode("utf-8"))
    per_request = []
    for turn in range(1, 5):
        prior_count = turn - 1
        message_count = 2 + 2 * prior_count
        bound = (
            system_bytes
            + packet_bytes
            + correction_bytes * prior_count
            + MAX_COMPLETION_TOKENS * prior_count
            + MESSAGE_FRAMING_ALLOWANCE * message_count
            + REQUEST_TEMPLATE_ALLOWANCE
        )
        per_request.append(bound)
    total = sum(per_request)
    return {
        "case_id": packet["case_id"],
        "per_request": per_request,
        "four_turn_input_upper_bound": total,
        "limit": MAX_CUMULATIVE_INPUT_TOKENS,
        "maximum_allowed": FOUR_TURN_INPUT_LIMIT,
        "required_headroom": REQUIRED_INPUT_HEADROOM,
        "headroom": MAX_CUMULATIVE_INPUT_TOKENS - total,
        "status": "pass" if total <= FOUR_TURN_INPUT_LIMIT else "blocked",
    }


def token_preflight_v3(
    scenario_document: Mapping[str, Any],
    *,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    cases = scenario_cases_v3(scenario_document)
    rows = [
        four_turn_input_upper_bound_v3(
            cases[case_id]["packet"],
            metric_version=metric_version,
        )
        for case_id in sorted(cases)
    ]
    values = sorted(int(row["four_turn_input_upper_bound"]) for row in rows)
    p95 = values[max(0, math.ceil(0.95 * len(values)) - 1)]
    maximum = values[-1]
    blocked = [str(row["case_id"]) for row in rows if row["status"] != "pass"]
    return {
        "status": "pass" if not blocked else "blocked",
        "method": "utf8-byte-token-upper-bound-with-framing-and-max-drafts",
        "case_count": len(rows),
        "max": maximum,
        "p95": p95,
        "headroom_at_max": MAX_CUMULATIVE_INPUT_TOKENS - maximum,
        "maximum_allowed": FOUR_TURN_INPUT_LIMIT,
        "required_headroom": REQUIRED_INPUT_HEADROOM,
        "blocked_case_ids": blocked,
        "cases": rows,
    }


def metric_definition_v3(
    *,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    collector_contract = validate_live_readiness_collector_checkpoint()
    definition = {
        "metric_version": metric_version,
        "wire_schema_version": wire_schema_for_v3(metric_version),
        "evidence_kinds": list(EVIDENCE_KINDS),
        "group_definitions": {
            kind: {
                "group_fields": sorted(GROUP_FIELDS[kind]),
                "sample_fields": sorted(GROUP_SAMPLE_FIELDS[kind]),
            }
            for kind in EVIDENCE_KINDS
        },
        "trace_service_scope": list(V3_TRACE_QUERY_SERVICES),
        "trace_activity_service_fields": ["trace_count"],
        "trace_error_service_fields": [
            "connection_error_count",
            "descriptions",
            "error_count",
        ],
        "evidence_id_formula": "sha256(case_id + NUL + metric_version + NUL + kind)[:24]",
        "required_kinds": {key: list(value) for key, value in sorted(REQUIRED_KINDS.items())},
        "distractor_rule": "all evidence kinds minus required kinds",
        "target_services": dict(sorted(TARGET_SERVICES.items())),
        "root_signal_features": {
            key: {
                "kind": value[0],
                "field": value[1],
                "quantum": value[2],
            }
            for key, value in sorted(ROOT_SIGNAL_FEATURES.items())
        },
        "window_counts": {
            "healthy": HEALTHY_WINDOW_COUNT,
            "fault": FAULT_WINDOW_COUNT,
        },
        "collector": collector_contract,
        "fault_sample_interval_seconds": V3_FAULT_SAMPLE_INTERVAL_SECONDS,
        "healthy_drift_formula": "max(0,right-left) for four consecutive healthy pairs",
        "healthy_drift_count_per_leave_one_out_case": 124,
        "percentile": {
            "value": DETERMINISTIC_PERCENTILE,
            "method": "nearest-rank",
        },
        "quanta": {
            "count": 1,
            "cpu_cores": 0.000001,
            "memory_bytes": 4096,
            "lag_seconds": 0.001,
        },
        "threshold_formula": (
            "max(nearest_rank_p99(healthy_positive_drifts)+measurement_quantum,"
            "relative_floor_fraction*median(five_healthy_windows))"
        ),
        "relative_root_signal_floors": dict(sorted(RELATIVE_ROOT_SIGNAL_FLOORS.items())),
        "incident_excess_formula": "max(two_fault_windows)-median(five_healthy_windows)",
        "comparison": "greater_than_or_equal_to",
        "candidate_rule": "trace_activity and root_signal both reach threshold",
        "ranking": "descending minimum standardized excess; lexical label tie-break",
        "presence": {
            "group_completeness": "six non-empty groups, seven indexed real samples each",
            "top1_count": 8,
            "top3_maximum_count": 20,
        },
        "bootstrap": {
            "resamples": BOOTSTRAP_RESAMPLES,
            "method": "percentile",
            "cluster_key": "case_id",
            "paired_key": ["case_id", "repetition"],
        },
        "reference_repetitions": {
            "initial": REFERENCE_REPETITIONS,
            "maximum": MAX_REFERENCE_REPETITIONS,
            "upgrade_only_when": "all hard gates except deterministic-vs-live significance pass",
        },
        "live_budgets": {
            "cumulative_input_tokens": MAX_CUMULATIVE_INPUT_TOKENS,
            "cumulative_output_tokens": MAX_CUMULATIVE_OUTPUT_TOKENS,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
        },
        "result_schema_v3_digest": _digest_json(RESULT_SCHEMA_V3),
    }
    return {
        **definition,
        "metric_definition_digest": _digest_json(definition),
    }


def build_version_routing_inventory(root: Path) -> dict[str, Any]:
    """Inventory every active Python metric-version reference from the actual tree."""
    occurrences: list[dict[str, Any]] = []
    for base in (root / "src", root / "tests"):
        for path in sorted(base.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            lines = path.read_text(encoding="utf-8").splitlines()
            for line_number, line in enumerate(lines, start=1):
                if not any(token in line for token in ("METRIC_VERSION", "metric_version")):
                    continue
                stripped = line.strip()
                if relative.startswith("tests/"):
                    classification = "test-only"
                elif (
                    stripped.startswith("METRIC_VERSION =")
                    or stripped.startswith("LEGACY_METRIC_VERSION =")
                    or stripped.startswith("REGISTERED_METRIC_VERSIONS =")
                ):
                    classification = "version declaration"
                elif "WIRE_SCHEMA" in line or "schema_version" in line:
                    classification = "wire-schema selection"
                elif "RESULT_SCHEMA" in line or "validate_result" in line:
                    classification = "result-schema selection"
                elif '"metric_version"' in line or "'metric_version'" in line:
                    classification = "artifact metadata"
                else:
                    classification = "entry dispatcher"
                occurrences.append(
                    {
                        "path": relative,
                        "line": line_number,
                        "classification": classification,
                        "source": stripped,
                    }
                )
    counts = Counter(item["classification"] for item in occurrences)
    return {
        "schema_version": "1.0.0",
        "generated_from": ["src/**/*.py", "tests/**/*.py"],
        "actual_reference_count": len(occurrences),
        "classification_counts": dict(sorted(counts.items())),
        "occurrences": occurrences,
    }


def make_bailian_adapter_v3(
    root: Path,
    baseline: str,
    *,
    metric_version: int = METRIC_VERSION,
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    require_v3_metric_version(metric_version)
    config = load_baseline_config_v3(root, metric_version=metric_version)
    if baseline not in config["arms"]:
        raise GovernanceError(f"metric v3 received an unknown live baseline: {baseline}")
    from faultwitness_dev.bootstrap import (
        BootstrapPaths,
        default_sops_executable,
        load_secret_bundle,
    )

    bundle = load_secret_bundle(BootstrapPaths.defaults(), default_sops_executable())
    arm = config["arms"][baseline]
    budgets = config["budgets"]

    def invoke(packet: Mapping[str, Any]) -> Mapping[str, Any]:
        validate_observation_packet_v3(packet)
        started = time.perf_counter()
        drafts: list[dict[str, Any]] = []
        draft_digests: list[str] = []
        usage_rows: list[dict[str, Any]] = []
        cumulative_input = 0
        cumulative_output = 0
        terminal_reason = "max_turns"
        try:
            with httpx.Client(
                timeout=None,
                headers={"Authorization": f"Bearer {bundle.bailian_api_key}"},
            ) as client:
                for turn in range(1, int(arm["max_turns"]) + 1):
                    turn_started = time.perf_counter()
                    response = client.post(
                        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                        json={
                            "model": MODEL_ID,
                            "messages": build_baseline_prompt_v3(
                                baseline,
                                packet,
                                prior_diagnoses=drafts,
                                metric_version=metric_version,
                            ),
                            "response_format": {"type": "json_object"},
                            "max_tokens": budgets["max_completion_tokens"],
                            "enable_thinking": False,
                        },
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        raise LiveInfrastructureError(f"upstream_http_{response.status_code}")
                    if response.status_code >= 400:
                        raise LiveConfigurationError(
                            "Bailian rejected the frozen metric-v3 route: "
                            f"HTTP {response.status_code}"
                        )
                    try:
                        body = response.json()
                        resolved = str(body.get("model") or MODEL_ID)
                        if resolved != MODEL_ID:
                            raise LiveConfigurationError(
                                "metric-v3 live baseline resolved a different model"
                            )
                        choice = body["choices"][0]
                        usage = body.get("usage")
                        if not isinstance(usage, dict) or not {
                            "prompt_tokens",
                            "completion_tokens",
                        }.issubset(usage):
                            raise LiveConfigurationError(
                                "metric-v3 live response omitted attributable usage"
                            )
                        input_tokens = int(usage["prompt_tokens"])
                        output_tokens = int(usage["completion_tokens"])
                        cumulative_input += input_tokens
                        cumulative_output += output_tokens
                        usage_rows.append(
                            {
                                "turn": turn,
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "latency_ms": round(
                                    (time.perf_counter() - turn_started) * 1000,
                                    3,
                                ),
                                "finish_reason": str(choice.get("finish_reason") or ""),
                            }
                        )
                        telemetry = {
                            "drafts": drafts,
                            "draft_digests": draft_digests,
                            "turn_usage": usage_rows,
                        }
                        if (
                            cumulative_input >= int(budgets["cumulative_input_tokens"])
                            or cumulative_output >= int(budgets["cumulative_output_tokens"])
                        ):
                            raise LiveTrialFailure(
                                "budget_exhausted",
                                "metric-v3 cumulative trial token budget was reached",
                                input_tokens=cumulative_input,
                                output_tokens=cumulative_output,
                                telemetry=telemetry,
                            )
                        if choice.get("finish_reason") == "length":
                            raise LiveTrialFailure(
                                "output_truncated",
                                "metric-v3 completion ended with finish_reason=length",
                                input_tokens=cumulative_input,
                                output_tokens=cumulative_output,
                                telemetry=telemetry,
                            )
                        parsed = json.loads(choice["message"]["content"])
                        if not isinstance(parsed, dict):
                            raise ValueError("result root")
                        draft = _canonical_diagnosis(parsed)
                        candidate = {
                            **draft,
                            "schema_version": wire_schema_for_v3(metric_version),
                            "metric_version": metric_version,
                            "case_id": packet["case_id"],
                            "status": "ok",
                            "baseline": baseline,
                            "model_id": MODEL_ID,
                            "fallback_count": 0,
                            "input_tokens": cumulative_input,
                            "output_tokens": cumulative_output,
                            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        }
                        validate_result_v3(candidate, metric_version=metric_version)
                    except LiveTrialFailure:
                        raise
                    except LiveConfigurationError:
                        raise
                    except (
                        KeyError,
                        IndexError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as error:
                        raise LiveTrialFailure(
                            "malformed",
                            "metric-v3 baseline returned malformed structured output",
                            input_tokens=cumulative_input,
                            output_tokens=cumulative_output,
                            telemetry={
                                "drafts": drafts,
                                "draft_digests": draft_digests,
                                "turn_usage": usage_rows,
                            },
                        ) from error
                    except GovernanceError as error:
                        raise LiveTrialFailure(
                            "malformed",
                            str(error),
                            input_tokens=cumulative_input,
                            output_tokens=cumulative_output,
                            telemetry={
                                "drafts": drafts,
                                "draft_digests": draft_digests,
                                "turn_usage": usage_rows,
                            },
                        ) from error
                    drafts.append(draft)
                    draft_digests.append(_digest_json(draft))
                    if (
                        turn >= int(arm["min_turns"])
                        and len(draft_digests) >= 2
                        and draft_digests[-1] == draft_digests[-2]
                    ):
                        terminal_reason = "stable_diagnosis"
                        break
        except httpx.TransportError as error:
            raise LiveInfrastructureError(f"transport:{type(error).__name__}") from error
        if not drafts:
            raise LiveTrialFailure(
                "malformed",
                "metric-v3 live trial produced no structured draft",
                input_tokens=cumulative_input,
                output_tokens=cumulative_output,
                telemetry={"drafts": [], "draft_digests": [], "turn_usage": usage_rows},
            )
        result = {
            **drafts[-1],
            "schema_version": wire_schema_for_v3(metric_version),
            "metric_version": metric_version,
            "case_id": packet["case_id"],
            "status": "ok",
            "baseline": baseline,
            "model_id": MODEL_ID,
            "fallback_count": 0,
            "input_tokens": cumulative_input,
            "output_tokens": cumulative_output,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "_trial_telemetry": {
                "turn_count": len(drafts),
                "terminal_reason": terminal_reason,
                "drafts": drafts,
                "draft_digests": draft_digests,
                "turn_usage": usage_rows,
            },
        }
        return result

    return invoke


def trial_specs_v3(
    dataset_digest: str,
    cases: Mapping[str, Mapping[str, Any]],
    repetitions: int,
    *,
    metric_version: int = METRIC_VERSION,
) -> dict[str, list[dict[str, Any]]]:
    require_v3_metric_version(metric_version)
    if repetitions not in {REFERENCE_REPETITIONS, MAX_REFERENCE_REPETITIONS}:
        raise GovernanceError("metric v3 reference repetitions must be three or five")
    specs = {"naive_react": [], "naive_react_single": [], "no_rag": []}
    for baseline in specs:
        for case_id in sorted(cases):
            for repetition in range(1, repetitions + 1):
                identity = {
                    "dataset_digest": dataset_digest,
                    "metric_version": metric_version,
                    "baseline": baseline,
                    "model_id": MODEL_ID,
                    "case_id": case_id,
                    "repetition": repetition,
                }
                specs[baseline].append(
                    {
                        "trial_id": f"g03-readiness-v{metric_version}-"
                        + hashlib.sha256(
                            json.dumps(
                                identity,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "baseline": baseline,
                        "case_id": case_id,
                        "repetition": repetition,
                        "packet": cases[case_id]["packet"],
                    }
                )
    return specs


def _run_live_trials_v3(
    journal_root: Path,
    specs: Iterable[Mapping[str, Any]],
    adapter: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    *,
    producer_sha: str,
    metric_version: int = METRIC_VERSION,
) -> list[dict[str, Any]]:
    require_v3_metric_version(metric_version)
    frozen_specs = [dict(spec) for spec in specs]
    journal = TrialJournal(journal_root)
    units: list[ExperimentUnit] = []
    handlers: dict[str, Callable[..., Mapping[str, Any]]] = {}
    for spec in frozen_specs:
        trial_id = str(spec["trial_id"])
        packet = _json_copy(spec["packet"])
        validate_observation_packet_v3(packet)
        input_digest = _digest_json(
            {
                "baseline": spec["baseline"],
                "metric_version": metric_version,
                "packet": packet,
                "repetition": spec["repetition"],
            }
        )
        units.append(
            ExperimentUnit(
                unit_id=trial_id,
                required_checkpoints=("model_route",),
                depends_on=(),
                input_digest=input_digest,
            )
        )

        def execute(
            _execution: Any,
            *,
            frozen_spec: Mapping[str, Any] = spec,
            frozen_packet: Mapping[str, Any] = packet,
        ) -> Mapping[str, Any]:
            result: dict[str, Any] | None = None
            try:
                result = dict(adapter(frozen_packet))
                telemetry = result.pop("_trial_telemetry", {})
                validate_result_v3(result, metric_version=metric_version)
                payload = {
                    "case_id": frozen_packet["case_id"],
                    "baseline": frozen_spec["baseline"],
                    "repetition": frozen_spec["repetition"],
                    "result": result,
                    "input_tokens": int(result.get("input_tokens", 0)),
                    "output_tokens": int(result.get("output_tokens", 0)),
                    "cost_cny": token_cost(
                        int(result.get("input_tokens", 0)),
                        int(result.get("output_tokens", 0)),
                    ),
                    "trial_telemetry": _json_copy(telemetry),
                }
            except LiveTrialFailure as error:
                payload = {
                    "case_id": frozen_packet["case_id"],
                    "baseline": frozen_spec["baseline"],
                    "repetition": frozen_spec["repetition"],
                    "result": {
                        "status": "scored_failure",
                        "failure_class": error.failure_class,
                        "reason": str(error),
                        "model_id": MODEL_ID,
                        "fallback_count": 0,
                    },
                    "input_tokens": error.input_tokens,
                    "output_tokens": error.output_tokens,
                    "cost_cny": token_cost(error.input_tokens, error.output_tokens),
                    "trial_telemetry": _json_copy(error.telemetry),
                }
            except LiveInfrastructureError as error:
                raise ExperimentInfrastructureError(str(error)) from error
            except LiveConfigurationError:
                raise
            except GovernanceError as error:
                input_tokens = int(result.get("input_tokens", 0)) if result else 0
                output_tokens = int(result.get("output_tokens", 0)) if result else 0
                payload = {
                    "case_id": frozen_packet["case_id"],
                    "baseline": frozen_spec["baseline"],
                    "repetition": frozen_spec["repetition"],
                    "result": {
                        "status": "scored_failure",
                        "failure_class": "malformed",
                        "reason": str(error),
                        "model_id": result.get("model_id") if result else None,
                        "fallback_count": result.get("fallback_count", 0) if result else 0,
                    },
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_cny": token_cost(input_tokens, output_tokens),
                }
            return {"status": "pass", "payload": payload}

        handlers[trial_id] = execute
    run = ExperimentRunner(
        units,
        journal,
        {"model_route": f"{MODEL_ID}:metric-v3:frozen-arm-contract"},
        producer_sha=producer_sha,
    ).run(handlers)
    records = {record["trial_id"]: record for record in run.records}
    return [records[str(spec["trial_id"])] for spec in frozen_specs]


def run_reference_live_v3(
    root: Path,
    producer_sha: str,
    dataset_digest: str,
    scenario_document: Mapping[str, Any],
    journal_root: Path,
    *,
    repetitions: int,
    adapters: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] | None = None,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    cases = scenario_cases_v3(scenario_document)
    specs_by_baseline = trial_specs_v3(
        dataset_digest,
        cases,
        repetitions,
        metric_version=metric_version,
    )
    records = []
    for baseline, specs in specs_by_baseline.items():
        adapter = (
            adapters[baseline]
            if adapters is not None
            else make_bailian_adapter_v3(root, baseline, metric_version=metric_version)
        )
        records.extend(
            _run_live_trials_v3(
                journal_root,
                specs,
                adapter,
                producer_sha=producer_sha,
                metric_version=metric_version,
            )
        )
    rows = []
    for record in records:
        payload = record.get("payload", {})
        result = payload.get("result", {}) if isinstance(payload, Mapping) else {}
        trial_status = record.get("status")
        matrix_status = (
            "scored_failure"
            if trial_status == "pass"
            and isinstance(result, Mapping)
            and result.get("status") == "scored_failure"
            else trial_status
        )
        rows.append(
            {
                "trial_id": record.get("trial_id"),
                "baseline": payload.get("baseline"),
                "case_id": payload.get("case_id"),
                "repetition": payload.get("repetition"),
                "status": matrix_status,
                "fallback_count": (
                    result.get("fallback_count", 0) if isinstance(result, Mapping) else 0
                ),
                "input_tokens": payload.get("input_tokens", 0),
                "output_tokens": payload.get("output_tokens", 0),
                "cost_cny": payload.get("cost_cny", 0.0),
                "failure_class": (
                    result.get("failure_class") if isinstance(result, Mapping) else None
                ),
                "trial_telemetry": payload.get("trial_telemetry", {}),
                "result": result,
            }
        )
    unresolved = [row for row in rows if row["status"] == "infra_failed"]
    document = {
        "status": "infra_failed" if unresolved else "pass",
        "execution_status": "incomplete" if unresolved else "completed",
        "metric_version": metric_version,
        "producer_sha": producer_sha,
        "dataset_digest": dataset_digest,
        "model_id": MODEL_ID,
        "repetitions": repetitions,
        "trial_count": len(rows),
        "trials": rows,
    }
    if not unresolved:
        validate_reference_live_v3(document)
    return document


def validate_reference_live_v3(
    document: Mapping[str, Any],
    *,
    metric_version: int = METRIC_VERSION,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    if document.get("metric_version") != metric_version:
        raise GovernanceError("metric v3 live matrix semantic version drifted")
    repetitions = int(document.get("repetitions", 0))
    if repetitions not in {REFERENCE_REPETITIONS, MAX_REFERENCE_REPETITIONS}:
        raise GovernanceError("metric v3 live matrix has an invalid repetition count")
    trials = document.get("trials")
    expected_count = 3 * 32 * repetitions
    if not isinstance(trials, list) or len(trials) != expected_count:
        raise GovernanceError(f"metric v3 live matrix must contain exactly {expected_count} trials")
    expected = {
        (baseline, f"SEED-G02-{case:04d}", repetition)
        for baseline in ("naive_react", "naive_react_single", "no_rag")
        for case in range(1, 33)
        for repetition in range(1, repetitions + 1)
    }
    actual = {
        (str(row.get("baseline")), str(row.get("case_id")), int(row.get("repetition", 0)))
        for row in trials
        if isinstance(row, Mapping)
    }
    if actual != expected:
        raise GovernanceError("metric v3 live trial registry drifted")
    if any(row.get("status") not in {"pass", "scored_failure"} for row in trials):
        raise GovernanceError("metric v3 live matrix has unresolved trials")
    if any(row.get("fallback_count") != 0 for row in trials):
        raise GovernanceError("metric v3 live matrix used a fallback route")
    expected_baselines = {"naive_react", "naive_react_single", "no_rag"}
    per_arm = Counter(str(row.get("baseline")) for row in trials)
    if any(per_arm[baseline] != 32 * repetitions for baseline in expected_baselines):
        raise GovernanceError("metric v3 live matrix arm counts are incomplete")
    return {
        "status": "pass",
        "trial_count": expected_count,
        "case_clusters": 32,
        "per_arm_trial_count": dict(sorted(per_arm.items())),
    }


def _aggregate_arm_v3(
    rows: Sequence[Mapping[str, Any]],
    dataset_digest: str,
    baseline: str,
) -> dict[str, Any]:
    metrics = {
        metric: percentile_cluster_bootstrap_v3(
            rows,
            metric,
            seed=f"{dataset_digest}:{baseline}:{metric}",
        )
        for metric in (
            "core_e2e",
            "root_cause_top3",
            "evidence_precision",
            "unsupported_critical_claim",
        )
    }
    families = sorted({str(row["family"]) for row in rows})
    failures = Counter(
        str(row.get("failure_class"))
        for row in rows
        if row.get("failure_class") is not None
    )
    input_values = sorted(int(row.get("input_tokens", 0)) for row in rows)
    output_values = sorted(int(row.get("output_tokens", 0)) for row in rows)

    def token_stats(values: Sequence[int]) -> dict[str, int]:
        if not values:
            return {"max": 0, "p95": 0, "total": 0}
        return {
            "max": max(values),
            "p95": values[max(0, math.ceil(0.95 * len(values)) - 1)],
            "total": sum(values),
        }

    return {
        "metric_version": METRIC_VERSION,
        "confidence": 0.95,
        "cluster_key": "case_id",
        "case_clusters": len({str(row["case_id"]) for row in rows}),
        "trial_count": len(rows),
        "metrics": metrics,
        "fault_family_success": {
            family: percentile_cluster_bootstrap_v3(
                [row for row in rows if row["family"] == family],
                "core_e2e",
                seed=f"{dataset_digest}:{baseline}:family:{family}",
            )
            for family in families
        },
        "input_tokens": sum(input_values),
        "output_tokens": sum(output_values),
        "token_stats": {
            "input": token_stats(input_values),
            "output": token_stats(output_values),
        },
        "failure_counts": dict(sorted(failures.items())),
        "arm_wide_budget_failure": bool(rows)
        and failures.get("budget_exhausted", 0) == len(rows),
        "cost_cny": sum(float(row.get("cost_cny", 0.0)) for row in rows),
        "fallback_count": sum(int(row.get("fallback_count", 0)) for row in rows),
        "not_applicable": {
            "tool_schema_validity": {
                "status": "not_applicable",
                "reason": "metric-v3 reference baselines make no tool calls",
                "proof_obligation": {
                    "gate": "G03",
                    "runner": "g03.tool_contract_matrix",
                    "required_artifact": "per-call schema verdicts",
                },
            },
            "dead_no_progress_loop": {
                "status": "not_applicable",
                "reason": "reference correction turns are not the G03 Agent loop",
                "proof_obligation": {
                    "gate": "G03",
                    "runner": "g03.termination_guard_matrix",
                    "required_artifact": "per-trial terminal reasons and progress digests",
                },
            },
        },
    }


def aggregate_reference_v3(
    scenario_document: Mapping[str, Any],
    deterministic_document: Mapping[str, Any],
    live_document: Mapping[str, Any],
    dataset_digest: str,
) -> dict[str, Any]:
    cases = scenario_cases_v3(scenario_document)
    validate_reference_live_v3(live_document)
    repetitions = int(live_document["repetitions"])
    live_trials = live_document["trials"]
    scored_live = []
    for trial in live_trials:
        case_id = str(trial["case_id"])
        if case_id not in cases:
            raise GovernanceError("metric v3 live trial references an unknown case")
        result = trial.get("result")
        if trial.get("status") == "pass" and isinstance(result, Mapping):
            score = score_result_v3(result, cases[case_id]["ground_truth"])
        elif trial.get("status") == "scored_failure" and isinstance(result, Mapping):
            score = _failure_v3(
                str(result.get("reason") or "trial produced a scored failure"),
                str(result.get("failure_class") or "malformed"),
            )
        else:
            score = _failure_v3("trial did not produce a scoreable result")
        scored_live.append(
            {
                **trial,
                "family": cases[case_id]["family"],
                **score,
            }
        )
    deterministic_rows = deterministic_document.get("rows")
    if not isinstance(deterministic_rows, list) or len(deterministic_rows) != 32:
        raise GovernanceError("metric v3 deterministic matrix must contain 32 rows")
    deterministic_scored = [
        {
            **row,
            "repetition": 1,
            "family": cases[str(row["case_id"])]["family"],
        }
        for row in deterministic_rows
    ]
    arms: dict[str, list[Mapping[str, Any]]] = {
        "deterministic": deterministic_scored,
        "no_rag": [row for row in scored_live if row["baseline"] == "no_rag"],
        "naive_react": [row for row in scored_live if row["baseline"] == "naive_react"],
    }
    ablation_rows = [
        row for row in scored_live if row["baseline"] == "naive_react_single"
    ]
    baselines = {
        baseline: _aggregate_arm_v3(rows, dataset_digest, baseline)
        for baseline, rows in arms.items()
    }
    estimates = {
        baseline: float(values["metrics"]["core_e2e"]["estimate"])
        for baseline, values in baselines.items()
    }
    deterministic_paired = [
        {
            **row,
            "repetition": repetition,
        }
        for row in deterministic_scored
        for repetition in range(1, repetitions + 1)
    ]
    paired = {
        "no_rag_minus_deterministic": paired_cluster_bootstrap_v3(
            arms["no_rag"],
            deterministic_paired,
            seed=f"{dataset_digest}:no_rag-deterministic:r{repetitions}",
        ),
        "naive_react_minus_deterministic": paired_cluster_bootstrap_v3(
            arms["naive_react"],
            deterministic_paired,
            seed=f"{dataset_digest}:naive_react-deterministic:r{repetitions}",
        ),
        "naive_react_minus_no_rag": paired_cluster_bootstrap_v3(
            arms["naive_react"],
            arms["no_rag"],
            seed=f"{dataset_digest}:naive_react-no_rag:r{repetitions}",
        ),
        "naive_react_minus_single": paired_cluster_bootstrap_v3(
            arms["naive_react"],
            ablation_rows,
            seed=f"{dataset_digest}:naive_react-single:r{repetitions}",
        ),
    }
    ablation = _aggregate_arm_v3(
        ablation_rows,
        dataset_digest,
        "naive_react_single",
    )
    best_name = max(estimates, key=estimates.__getitem__)
    best_value = estimates[best_name]
    presence = presence_only_probe_v3(scenario_document)
    blockers: list[str] = []
    if best_value > 0.90:
        blockers.append("best_baseline_above_0_90")
    exact_all_equal = len(set(estimates.values())) == 1
    if exact_all_equal:
        blockers.append("registered_baseline_point_estimates_exactly_equal")
    for baseline, values in baselines.items():
        interval = values["metrics"]["core_e2e"]
        if float(interval["upper"]) <= float(interval["lower"]):
            blockers.append(f"zero_width_ci:{baseline}")
    deterministic_live_intervals = {
        name: paired[name]
        for name in (
            "no_rag_minus_deterministic",
            "naive_react_minus_deterministic",
        )
    }
    deterministic_live_significant = any(
        float(interval["lower"]) > 0.0 or float(interval["upper"]) < 0.0
        for interval in deterministic_live_intervals.values()
    )
    if not deterministic_live_significant:
        blockers.append("deterministic_live_significance_not_established")
    for baseline, values in baselines.items():
        if values["arm_wide_budget_failure"]:
            blockers.append(f"arm_wide_budget_failure:{baseline}")
    expected_registered_trials = {
        "deterministic": 32,
        "no_rag": 32 * repetitions,
        "naive_react": 32 * repetitions,
    }
    for baseline, expected_count in expected_registered_trials.items():
        if int(baselines[baseline]["trial_count"]) != expected_count:
            blockers.append(f"incomplete_trial_count:{baseline}")
    if presence["status"] != "pass":
        blockers.append("presence_probe_not_at_prior")
    execution_complete = not any(
        blocker.startswith(("incomplete_trial_count:", "arm_wide_budget_failure:"))
        for blocker in blockers
    )
    readiness = "ready" if not blockers else "blocked"
    if readiness == "ready":
        blocked_reason = None
    elif presence["status"] != "pass":
        blocked_reason = "leak_not_eliminated"
    elif not execution_complete or exact_all_equal:
        blocked_reason = "unclassified"
    elif estimates["no_rag"] > 0.90:
        blocked_reason = "dataset_too_easy"
    elif estimates["deterministic"] > 0.90:
        blocked_reason = "task_rule_solvable"
    elif blockers == ["deterministic_live_significance_not_established"]:
        blocked_reason = "instrument_underpowered"
    else:
        blocked_reason = "unclassified"
    return {
        "status": "pass",
        "execution_status": "completed",
        "readiness_status": readiness,
        "blocked_reason": blocked_reason,
        "readiness_blockers": blockers,
        "metric_version": METRIC_VERSION,
        "confidence": 0.95,
        "resamples": BOOTSTRAP_RESAMPLES,
        "cluster_key": "case_id",
        "case_clusters": 32,
        "repetitions": repetitions,
        "dataset_digest": dataset_digest,
        "presence_only_probe": presence,
        "baselines": baselines,
        "paired_differences": paired,
        "deterministic_live_significant": deterministic_live_significant,
        "findings": {
            "observed_order": [
                name
                for name, _value in sorted(estimates.items(), key=lambda item: item[1])
            ],
            "naive_react_minus_no_rag": paired["naive_react_minus_no_rag"],
            "multi_turn_delta": paired["naive_react_minus_single"],
            "naive_react_single": ablation,
        },
        "best_baseline": {
            "name": best_name,
            "core_e2e": best_value,
            "maximum_allowed": 0.90,
        },
        "baseline_order": {
            "estimates": estimates,
            "observational_only": True,
            "exact_all_equal": exact_all_equal,
        },
        "g03_comparison": {
            "operator": ">=",
            "margin": 0.05,
            "minimum_core_e2e": best_value + 0.05,
            "feasible_on_unit_interval": best_value + 0.05 <= 1.0,
        },
        "global_core_e2e_floor": {
            "definition": "max(0.70,best_baseline+0.10)",
            "minimum_core_e2e": resolve_quality_floor(
                "core_e2e",
                best_baseline=best_value,
            ),
            "feasible_on_unit_interval": best_value + 0.10 <= 1.0,
        },
        "quality_floors": QUALITY_FLOORS,
        "scored_live_trials": scored_live,
    }


def should_extend_reference_v3(aggregate: Mapping[str, Any]) -> bool:
    if aggregate.get("repetitions") != REFERENCE_REPETITIONS:
        return False
    if aggregate.get("readiness_status") != "blocked":
        return False
    blockers = aggregate.get("readiness_blockers")
    return blockers == ["deterministic_live_significance_not_established"]


def write_json_artifact_v3(path: Path, document: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def protected_asset_snapshot(root: Path) -> dict[str, Any]:
    groups = {
        "docs_audit": sorted(
            path for path in (root / "docs" / "audit").rglob("*") if path.is_file()
        ),
        "g02_frozen": sorted(
            [
                root / "docs" / "gates" / "G02" / "PLAN.md",
                root / "docs" / "gates" / "G02" / "REPORT.md",
                root / "docs" / "gates" / "G02" / "VALIDATIONS.yaml",
                *[
                    path
                    for directory in sorted((root / "docs" / "evals").glob("EVAL-G02-*"))
                    for path in directory.rglob("*")
                    if path.is_file()
                ],
            ]
        ),
    }
    snapshot: dict[str, Any] = {}
    for name, paths in groups.items():
        rows = [
            (
                path.relative_to(root).as_posix(),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in paths
        ]
        payload = "\n".join(f"{relative}\t{digest}" for relative, digest in rows).encode()
        snapshot[name] = {
            "count": len(rows),
            "digest": hashlib.sha256(payload).hexdigest(),
        }
    return snapshot


def assert_protected_assets_unchanged(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if dict(before) != dict(after):
        raise GovernanceError(
            "protected docs/audit or frozen G02 assets changed during metric-v3 execution"
        )


def runtime_environment_v3() -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(UTC).isoformat(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def _read_json_v3(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GovernanceError(f"metric v3 artifact is unreadable: {path}") from error
    if not isinstance(document, dict):
        raise GovernanceError(f"metric v3 artifact root is not an object: {path}")
    return document


def _source_inputs_v3(root: Path) -> list[Path]:
    return [
        root / "src" / "faultwitness_dev" / "g03_readiness.py",
        root / "src" / "faultwitness_dev" / "g02_lab.py",
        root / "src" / "faultwitness_dev" / "g02_baselines.py",
        root / "src" / "faultwitness_dev" / "cli.py",
        root / "config" / "g03" / "baselines-v3.yaml",
        root / "config" / "g02" / "lab.yaml",
        root / "docs" / "blueprint" / "AMENDMENTS" / "AMD-0007.md",
        root / "docs" / "gates" / "G03" / "PLAN.md",
        root / "docs" / "runbooks" / "G03_BASELINE_READINESS.md",
        root / "tests" / "g03" / "test_g03_readiness.py",
    ]


NEWLINE = "\n"


def host_identity_v3() -> dict[str, str]:
    """Identify the machine that produced an artifact, without recording how to reach it.

    ADR-0017 obliges recording the host alongside the kernel for every artifact: the original
    host was silently corrupting execution, so evidence from it cannot be compared with evidence
    from the replacement. The run manifest recorded `producer_sha` and the checkpoint identities
    but nothing about the machine, so two runs from different hosts were indistinguishable after
    the fact.

    What is recorded is a digest of the host's SSH **public** key plus the local kernel string.
    A host public key is non-secret by construction -- it is what a client verifies a server
    against -- and hashing it means the artifact carries a stable machine fingerprint while the
    address, username, port and every secret stay out of the record. The `known_hosts` line's
    first field is the host address and is deliberately never read into the digest.

    Never raises: a checkout with no bootstrap store (CI, a fresh clone, the test suite) records
    `unavailable` rather than failing a run over provenance metadata.
    """
    from faultwitness_dev.bootstrap import BootstrapPaths

    fingerprint = "unavailable"
    try:
        known_hosts = BootstrapPaths.defaults().known_hosts_file
        if known_hosts.is_file():
            keys: list[str] = []
            for line in known_hosts.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                fields = line.split()
                # fields[0] is the host address -- excluded on purpose.
                if len(fields) >= 3:
                    keys.append(f"{fields[1]} {fields[2]}")
            if keys:
                joined = NEWLINE.join(sorted(keys))
                fingerprint = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    except (OSError, GovernanceError):
        fingerprint = "unavailable"
    return {
        "host_key_digest": fingerprint,
        "runner_kernel": platform.platform(terse=True),
    }


def _run_identity_v3(root: Path) -> dict[str, Any]:
    from faultwitness_dev.provenance import producer_provenance

    require_v3_metric_version(METRIC_VERSION)
    config = load_baseline_config_v3(root)
    definition = metric_definition_v3()
    amd_path = root / "docs" / "blueprint" / "AMENDMENTS" / "AMD-0007.md"
    provenance = producer_provenance(root, _source_inputs_v3(root))
    state = load_data(root / "PROJECT_STATE.yaml")
    lab = validate_lab_bootstrap(load_lab_config(root))
    return {
        "metric_version": METRIC_VERSION,
        "wire_schema_version": WIRE_SCHEMA_VERSION,
        "producer_sha": provenance.producer_sha,
        "relevant_source_digest": provenance.source_digest,
        "dirty_worktree": provenance.dirty,
        "config_digest": _digest_json(config),
        "amd_digest": hashlib.sha256(amd_path.read_bytes()).hexdigest(),
        "metric_definition_digest": definition["metric_definition_digest"],
        "checkpoint_identities": {
            "sut_producer_sha": str(state["latest_release"]["producer_commit"]),
            "sut_image_set_digest": str(lab["image_set_digest"]),
            "model_id": MODEL_ID,
        },
        # ADR-0017: which host produced this evidence. Not part of the resume identity check --
        # a host swap mid-run is a real hazard, but the runner kernel string is environmental and
        # comparing it would refuse resumes for reasons unrelated to what is being measured.
        "host_identity": host_identity_v3(),
    }


def inherit_passing_trials_v3(
    root: Path,
    source_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Carry `pass` scenario records into a fresh preflight directory, auditably.

    A preflight demands a new empty directory so it cannot silently inherit
    unaudited state, and there is no in-place retry for a single case. Together
    those mean one attributable infrastructure failure — a momentary SSH refusal
    on a flag read, say — forces re-measuring the cases that already passed.
    AMD-0003 authorizes retrying attributable infrastructure failures, and
    re-measuring a passing case is not a retry of the failure; it is a different
    sample of something already established.

    Inheritance is safe because `cache_key` is *semantic*: it covers the SUT
    image set, the collector contract digest, the scenario, the SUT producer SHA
    and the window counts — not the repository state. The replay recomputes each
    key and only reuses a record whose key still matches, so a record that no
    longer describes the current measurement is re-run rather than trusted. This
    function therefore cannot make a stale record count; it only saves work the
    replay would otherwise redo.

    Every inherited trial is listed in the returned receipt, which the caller
    writes into the run directory, so the provenance of a reused case is on the
    record rather than implied by a file's presence.
    """
    source_trials = source_dir / "journals" / "scenarios" / "trials"
    if not source_trials.is_dir():
        raise GovernanceError("metric v3 trial inheritance source has no scenario journal")
    destination = output_dir / "journals" / "scenarios" / "trials"
    if destination.exists() and any(destination.iterdir()):
        raise GovernanceError("metric v3 trial inheritance target already holds trials")
    for ancestor in (source_dir, *source_dir.parents):
        if ancestor == root:
            break
        if (ancestor / "INVALIDATION.md").is_file() or "-invalidated-" in ancestor.name.casefold():
            raise GovernanceError("metric v3 cannot inherit trials from an invalidated run")
    destination.mkdir(parents=True, exist_ok=True)
    inherited: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for path in sorted(source_trials.glob("*.json")):
        record = _read_json_v3(path)
        status = str(record.get("status", ""))
        if status != "pass":
            skipped.append({"trial_id": str(record.get("trial_id", path.stem)), "status": status})
            continue
        shutil.copy2(path, destination / path.name)
        inherited.append(
            {
                "trial_id": str(record["trial_id"]),
                "cache_key": str(record["cache_key"]),
                "artifact_digest": str(record.get("artifact_digest", "")),
            }
        )
    return {
        "source_run": source_dir.relative_to(root).as_posix(),
        "inherited_count": len(inherited),
        "inherited_trials": inherited,
        "not_inherited": skipped,
        "revalidation": "each inherited record is reused only if its recomputed cache_key matches",
    }


def _validate_output_dir_v3(
    root: Path,
    output_dir: Path,
    *,
    resume: bool,
) -> Path:
    readiness_root = (root / ".audit" / "g03-readiness").resolve()
    candidate = output_dir.resolve()
    invalidated = (readiness_root / "invalidated").resolve()
    try:
        candidate.relative_to(readiness_root)
    except ValueError as error:
        raise GovernanceError(
            "metric v3 output directory must be under .audit/g03-readiness"
        ) from error
    if candidate == readiness_root:
        raise GovernanceError("metric v3 output directory cannot be the readiness root")
    relative_parts = candidate.relative_to(readiness_root).parts
    if any("-invalidated-" in part.casefold() for part in relative_parts):
        raise GovernanceError("metric v3 cannot read or resume an invalidated directory")
    for ancestor in (candidate, *candidate.parents):
        if ancestor == readiness_root.parent:
            break
        if (ancestor / "INVALIDATION.md").is_file():
            raise GovernanceError("metric v3 cannot read or resume an invalidated directory")
    try:
        candidate.relative_to(invalidated)
    except ValueError:
        pass
    else:
        raise GovernanceError("metric v3 cannot read or resume an invalidated directory")
    if resume:
        if not candidate.is_dir() or not any(candidate.iterdir()):
            raise GovernanceError("metric v3 --resume requires a non-empty active run directory")
        if not (candidate / "run-manifest.json").is_file():
            raise GovernanceError("metric v3 --resume target lacks an active run manifest")
    elif candidate.exists() and (not candidate.is_dir() or any(candidate.iterdir())):
        raise GovernanceError("metric v3 preflight requires a new empty output directory")
    return candidate


def _assert_resume_identity_v3(
    root: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _read_json_v3(output_dir / "run-manifest.json")
    # Refuse a diagnostic-only directory before anything else, so the reason is
    # named rather than surfacing as an incidental identity mismatch.
    preflight_probe = output_dir / "preflight-summary.json"
    if preflight_probe.is_file():
        probe = _read_json_v3(preflight_probe)
        if (
            probe.get("diagnostic_only") is True
            or probe.get("promotable_to_gate_evidence") is False
            or probe.get("execution_status") == "diagnostic_scan"
        ):
            raise GovernanceError(
                "metric v3 cannot resume a diagnostic-only scan; readiness requires a "
                "new empty directory and a clean 32-case replay"
            )
    current = _run_identity_v3(root)
    for key in (
        "metric_version",
        "wire_schema_version",
        "producer_sha",
        "relevant_source_digest",
        "config_digest",
        "amd_digest",
        "metric_definition_digest",
        "checkpoint_identities",
    ):
        if manifest.get(key) != current.get(key):
            raise GovernanceError(f"metric v3 --resume identity mismatch: {key}")
    frozen_definition = _read_json_v3(output_dir / "metric-definition.json")
    recomputed_definition = metric_definition_v3()
    if frozen_definition != recomputed_definition:
        raise GovernanceError("metric v3 runtime definition differs from frozen preflight")
    scenarios_path = output_dir / "scenarios.json"
    expected_artifact_digest = str(manifest.get("scenario_artifact_digest") or "")
    if hashlib.sha256(scenarios_path.read_bytes()).hexdigest() != expected_artifact_digest:
        raise GovernanceError("metric v3 scenario artifact bytes changed after preflight")
    scenarios = _read_json_v3(scenarios_path)
    if dataset_digest_v3(scenarios) != manifest.get("dataset_digest"):
        raise GovernanceError("metric v3 dataset digest changed after preflight")
    if scenarios.get("execution_status") == "diagnostic_scan":
        raise GovernanceError(
            "metric v3 cannot resume a diagnostic-only scan; readiness requires a "
            "new empty directory and a clean 32-case replay"
        )
    preflight = _read_json_v3(output_dir / "preflight-summary.json")
    if preflight.get("preflight_status") != "pass":
        raise GovernanceError("metric v3 live cannot resume a blocked preflight")
    return manifest, scenarios


def _update_cost_ledger_v3(root: Path, run_name: str, status: str, cost: float) -> None:
    path = root / ".audit" / "g03-readiness" / "cost-ledger.json"
    ledger = _read_json_v3(path)
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise GovernanceError("G03 readiness cost ledger is malformed")
    retained = [
        dict(entry)
        for entry in entries
        if isinstance(entry, Mapping)
        and entry.get("run") not in {"metric-v3-frozen", run_name}
    ]
    retained.append(
        {
            "run": run_name,
            "metric_version": METRIC_VERSION,
            "status": status,
            "cost": round(cost, 6),
        }
    )
    ledger["entries"] = retained
    ledger["total_cost"] = round(sum(float(entry["cost"]) for entry in retained), 6)
    write_json_artifact_v3(path, ledger)


def _preflight_blockers_v3(
    presence: Mapping[str, Any],
    deterministic: Mapping[str, Any],
    token_preflight: Mapping[str, Any],
    deterministic_ci: Mapping[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    if presence.get("status") != "pass":
        blockers.append("leak_not_eliminated")
    if int(deterministic.get("ambiguity_count", 0)):
        blockers.append("ambiguous_cases")
    if deterministic.get("N") != 32:
        blockers.append("deterministic_N_below_32")
    if token_preflight.get("status") != "pass":
        blockers.append("four_turn_token_headroom")
    if deterministic_ci is not None and float(deterministic_ci["estimate"]) == 1.0:
        blockers.append("deterministic_core_e2e_exactly_1_000")
    return blockers


def run_retest_baselines_v3(
    root: Path,
    output_dir: Path,
    *,
    skip_live: bool,
    resume: bool = False,
    repetitions: int | None = None,
    metric_version: int = METRIC_VERSION,
    continue_on_case_failure: bool = False,
    inherit_from: Path | None = None,
) -> dict[str, Any]:
    require_v3_metric_version(metric_version)
    if skip_live == resume:
        raise GovernanceError("metric v3 requires exactly one of --skip-live or --resume")
    if inherit_from is not None and not skip_live:
        raise GovernanceError("metric v3 trial inheritance applies only to a preflight")
    if inherit_from is not None and continue_on_case_failure:
        raise GovernanceError(
            "metric v3 diagnostic scan cannot inherit trials; it is never gate evidence"
        )
    if continue_on_case_failure and not skip_live:
        raise GovernanceError(
            "metric v3 diagnostic scan requires --skip-live and cannot be resumed"
        )
    output_dir = _validate_output_dir_v3(root, output_dir, resume=resume)
    if skip_live:
        if repetitions is not None:
            raise GovernanceError("metric v3 preflight does not accept a repetition count")
        output_dir.mkdir(parents=True, exist_ok=True)
        inheritance: dict[str, Any] | None = None
        if inherit_from is not None:
            source_dir = (
                inherit_from if inherit_from.is_absolute() else root / inherit_from
            )
            # Validated with resume=True: the source must be an existing run with a
            # manifest, and must not be invalidated. It is read-only here.
            source_dir = _validate_output_dir_v3(root, source_dir, resume=True)
            if source_dir == output_dir:
                raise GovernanceError(
                    "metric v3 trial inheritance source cannot be the output directory"
                )
            inheritance = inherit_passing_trials_v3(root, source_dir, output_dir)
        protected_start = protected_asset_snapshot(root)
        identity = _run_identity_v3(root)
        definition = metric_definition_v3(metric_version=metric_version)
        write_json_artifact_v3(
            root / ".audit" / "g03-readiness" / "version-routing-inventory.json",
            build_version_routing_inventory(root),
        )
        definition_artifact_digest = write_json_artifact_v3(
            output_dir / "metric-definition.json",
            definition,
        )
        manifest = {
            **identity,
            "schema_version": "1.0.0",
            "phase": "preflight_in_progress",
            "output_dir": output_dir.relative_to(root).as_posix(),
            "metric_definition_artifact_digest": definition_artifact_digest,
            "protected_assets_start": protected_start,
        }
        if inheritance is not None:
            manifest["inherited_trials"] = inheritance
        write_json_artifact_v3(output_dir / "run-manifest.json", manifest)
        scenarios = replay_all_scenarios_v3(
            root,
            str(identity["producer_sha"]),
            TrialJournal(output_dir / "journals" / "scenarios"),
            sut_producer_sha=str(identity["checkpoint_identities"]["sut_producer_sha"]),
            metric_version=metric_version,
            continue_on_case_failure=continue_on_case_failure,
        )
        scenarios = {
            **scenarios,
            "metric_definition_digest": identity["metric_definition_digest"],
            "config_digest": identity["config_digest"],
        }
        scenario_artifact_digest = write_json_artifact_v3(
            output_dir / "scenarios.json",
            scenarios,
        )
        if scenarios.get("status") != "pass":
            protected_end = protected_asset_snapshot(root)
            scenario_blocker = (
                "dataset_incomplete"
                if scenarios.get("failure_class") == "dataset_incomplete"
                else "scenario_replay_incomplete"
            )
            diagnostic_scan = scenarios.get("execution_status") == "diagnostic_scan"
            summary = {
                **identity,
                "non_gate_evidence": True,
                "execution_status": (
                    "diagnostic_scan" if diagnostic_scan else "incomplete"
                ),
                "preflight_status": "blocked",
                "readiness_status": "blocked",
                "blocked_reason": "unclassified",
                "readiness_blockers": [scenario_blocker],
                "protected_assets_start": protected_start,
                "protected_assets_end": protected_end,
            }
            if diagnostic_scan:
                # Never promotable: readiness still requires one fresh directory
                # with all 32 cases replayed clean under abort-on-first-failure.
                summary["diagnostic_only"] = True
                summary["promotable_to_gate_evidence"] = False
                summary["case_outcomes"] = _json_copy(
                    scenarios.get("case_outcomes", [])
                )
                summary["failed_case_count"] = scenarios.get("failed_case_count")
                summary["attempted_case_count"] = scenarios.get("attempted_case_count")
            write_json_artifact_v3(output_dir / "preflight-summary.json", summary)
            write_json_artifact_v3(output_dir / "summary.json", summary)
            assert_protected_assets_unchanged(protected_start, protected_end)
            if diagnostic_scan:
                raise GovernanceError(
                    "metric v3 diagnostic scan completed with "
                    f"{scenarios.get('failed_case_count')} failed cases; "
                    "diagnostic_only evidence is never promotable"
                )
            raise GovernanceError("metric v3 fresh scenario replay is incomplete")
        dataset_digest = dataset_digest_v3(scenarios)
        presence = presence_only_probe_v3(scenarios)
        deterministic = run_deterministic_matrix_v3(
            str(identity["producer_sha"]),
            scenarios,
            dataset_digest,
            metric_definition_digest=str(identity["metric_definition_digest"]),
            metric_version=metric_version,
        )
        deterministic_artifact_digest = write_json_artifact_v3(
            output_dir / "deterministic.json",
            deterministic,
        )
        token_preflight = token_preflight_v3(scenarios, metric_version=metric_version)
        deterministic_rows = deterministic.get("rows", [])
        deterministic_ci = (
            percentile_cluster_bootstrap_v3(
                deterministic_rows,
                "core_e2e",
                seed=f"{dataset_digest}:deterministic:preflight",
            )
            if len(deterministic_rows) == 32
            else None
        )
        blockers = _preflight_blockers_v3(
            presence,
            deterministic,
            token_preflight,
            deterministic_ci,
        )
        preflight_status = "pass" if not blockers else "blocked"
        protected_end = protected_asset_snapshot(root)
        manifest = {
            **manifest,
            "phase": "preflight_completed",
            "preflight_status": preflight_status,
            "dataset_digest": dataset_digest,
            "scenario_artifact_digest": scenario_artifact_digest,
            "deterministic_artifact_digest": deterministic_artifact_digest,
        }
        write_json_artifact_v3(output_dir / "run-manifest.json", manifest)
        summary = {
            **identity,
            "non_gate_evidence": True,
            "purpose": "G03 readiness metric-v3 preflight; not G02 Gate evidence",
            "environment": runtime_environment_v3(),
            "execution_status": "preflight_completed",
            "preflight_status": preflight_status,
            "readiness_status": "not_evaluated" if not blockers else "blocked",
            "blocked_reason": (
                None
                if not blockers
                else "dataset_too_easy"
                if blockers == ["deterministic_core_e2e_exactly_1_000"]
                else "unclassified"
            ),
            "readiness_blockers": blockers,
            "dataset_digest": dataset_digest,
            "metric_definition": definition,
            "presence_only_probe": presence,
            "ambiguity_count": deterministic.get("ambiguity_count", 0),
            "ambiguity_case_ids": deterministic.get("ambiguity_case_ids", []),
            "diagnostic_only": deterministic.get("diagnostic_only", False),
            "deterministic_core_e2e": deterministic_ci,
            "four_turn_token_preflight": token_preflight,
            "N": {
                "scenarios": 32,
                "deterministic": deterministic.get("N", 0),
                "live": 0,
            },
            "cost_cny": 0.0,
            "fallback_count": 0,
            "artifact_digests": {
                "metric-definition.json": definition_artifact_digest,
                "scenarios.json": scenario_artifact_digest,
                "deterministic.json": deterministic_artifact_digest,
            },
            "protected_assets_start": protected_start,
            "protected_assets_end": protected_end,
        }
        write_json_artifact_v3(output_dir / "preflight-summary.json", summary)
        write_json_artifact_v3(output_dir / "summary.json", summary)
        _update_cost_ledger_v3(root, output_dir.name, "preflight_completed", 0.0)
        assert_protected_assets_unchanged(protected_start, protected_end)
        if blockers:
            raise GovernanceError(
                "metric v3 preflight is blocked: " + ", ".join(blockers)
            )
        return summary

    if repetitions not in {REFERENCE_REPETITIONS, MAX_REFERENCE_REPETITIONS}:
        raise GovernanceError("metric v3 live resume requires --repetitions 3 or 5")
    manifest, scenarios = _assert_resume_identity_v3(root, output_dir)
    if repetitions == MAX_REFERENCE_REPETITIONS:
        aggregate_r3_path = output_dir / "aggregate-r3.json"
        if not aggregate_r3_path.is_file():
            raise GovernanceError("metric v3 r5 requires a completed r3 aggregate")
        aggregate_r3 = _read_json_v3(aggregate_r3_path)
        if aggregate_r3.get("extension_authorized") is not True:
            raise GovernanceError("metric v3 r5 is not authorized by the frozen r3 rule")
    protected_start = manifest["protected_assets_start"]
    deterministic = _read_json_v3(output_dir / "deterministic.json")
    dataset_digest = str(manifest["dataset_digest"])
    live = run_reference_live_v3(
        root,
        str(manifest["producer_sha"]),
        dataset_digest,
        scenarios,
        output_dir / "journals" / "live-reference",
        repetitions=repetitions,
        metric_version=metric_version,
    )
    live_digest = write_json_artifact_v3(
        output_dir / f"live-r{repetitions}.json",
        live,
    )
    if live.get("status") != "pass":
        write_json_artifact_v3(output_dir / "live.json", live)
        cost = sum(float(row.get("cost_cny", 0.0)) for row in live.get("trials", []))
        protected_end = protected_asset_snapshot(root)
        summary = {
            **manifest,
            "execution_status": "incomplete",
            "preflight_status": "pass",
            "readiness_status": "blocked",
            "blocked_reason": "unclassified",
            "readiness_blockers": ["live_reference_incomplete"],
            "cost_cny": cost,
            "protected_assets_end": protected_end,
        }
        write_json_artifact_v3(output_dir / "summary.json", summary)
        _update_cost_ledger_v3(root, output_dir.name, "live_incomplete", cost)
        assert_protected_assets_unchanged(protected_start, protected_end)
        raise GovernanceError("metric v3 live reference has resumable failures")
    aggregate = aggregate_reference_v3(
        scenarios,
        deterministic,
        live,
        dataset_digest,
    )
    aggregate["extension_authorized"] = should_extend_reference_v3(aggregate)
    aggregate_digest = write_json_artifact_v3(
        output_dir / f"aggregate-r{repetitions}.json",
        aggregate,
    )
    write_json_artifact_v3(output_dir / "live.json", live)
    write_json_artifact_v3(output_dir / "aggregate.json", aggregate)
    total_cost = sum(float(row.get("cost_cny", 0.0)) for row in live["trials"])
    total_fallback = sum(int(row.get("fallback_count", 0)) for row in live["trials"])
    protected_end = protected_asset_snapshot(root)
    summary = {
        **manifest,
        "non_gate_evidence": True,
        "purpose": "G03 readiness metric-v3 live reference; not G02 Gate evidence",
        "environment": runtime_environment_v3(),
        "execution_status": aggregate["execution_status"],
        "preflight_status": "pass",
        "readiness_status": aggregate["readiness_status"],
        "blocked_reason": aggregate["blocked_reason"],
        "readiness_blockers": aggregate["readiness_blockers"],
        "dataset_digest": dataset_digest,
        "presence_only_probe": aggregate["presence_only_probe"],
        "best_baseline": aggregate["best_baseline"],
        "baseline_order": aggregate["baseline_order"],
        "paired_differences": aggregate["paired_differences"],
        "findings": aggregate["findings"],
        "global_core_e2e_floor": aggregate["global_core_e2e_floor"],
        "g03_comparison": aggregate["g03_comparison"],
        "baseline_token_stats": {
            name: values["token_stats"] for name, values in aggregate["baselines"].items()
        },
        "N": {
            "scenarios": 32,
            "deterministic": 32,
            "registered_live": 2 * 32 * repetitions,
            "ablation_live": 32 * repetitions,
            "repetitions": repetitions,
        },
        "cost_cny": total_cost,
        "fallback_count": total_fallback,
        "artifact_digests": {
            f"live-r{repetitions}.json": live_digest,
            f"aggregate-r{repetitions}.json": aggregate_digest,
        },
        "protected_assets_start": protected_start,
        "protected_assets_end": protected_end,
    }
    write_json_artifact_v3(output_dir / "summary.json", summary)
    manifest = {
        **manifest,
        "phase": f"r{repetitions}_completed",
        "readiness_status": aggregate["readiness_status"],
        "extension_authorized": aggregate["extension_authorized"],
    }
    write_json_artifact_v3(output_dir / "run-manifest.json", manifest)
    _update_cost_ledger_v3(
        root,
        output_dir.name,
        str(aggregate["readiness_status"]),
        total_cost,
    )
    assert_protected_assets_unchanged(protected_start, protected_end)
    if aggregate["readiness_status"] != "ready":
        raise GovernanceError(
            "metric v3 reference completed but G03 readiness remains blocked: "
            + ", ".join(aggregate["readiness_blockers"])
        )
    return summary
