"""G02 baseline, scoring, and resumable trial contracts.

The module deliberately keeps the Iteration runner offline.  Gate code may provide a live
adapter, but the journal and scoring semantics are identical for both paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data

LEGACY_METRIC_VERSION = 1
METRIC_VERSION = 2
G02_METRIC_VERSIONS = frozenset({LEGACY_METRIC_VERSION, METRIC_VERSION})
WIRE_SCHEMA_BY_METRIC = {
    LEGACY_METRIC_VERSION: "1.0.0",
    METRIC_VERSION: "2.0.0",
}
ROOT_CAUSE_LABELS = (
    "productCatalogFailure",
    "adHighCpu",
    "emailMemoryLeak",
    "paymentFailure",
    "paymentUnreachable",
    "kafkaQueueProblems",
)


def require_g02_metric_version(metric_version: int) -> int:
    """Reject non-G02 metric versions before any side effect or semantic fallback."""
    if metric_version not in G02_METRIC_VERSIONS:
        raise GovernanceError(f"unsupported G02 metric version: {metric_version}")
    return metric_version


def wire_schema_for_metric(metric_version: int) -> str:
    require_g02_metric_version(metric_version)
    return WIRE_SCHEMA_BY_METRIC[metric_version]

QUALITY_FLOORS: dict[str, dict[str, float | str]] = {
    "core_e2e": {"operator": ">=", "value": "max(0.70,best_baseline+0.10)"},
    "root_cause_top3": {"operator": ">=", "value": 0.85},
    "evidence_precision": {"operator": ">=", "value": 0.90},
    "unsupported_critical_claim": {"operator": "<=", "value": 0.02},
    "tool_schema_validity": {"operator": ">=", "value": 0.99},
    "dead_no_progress_loop": {"operator": "<", "value": 0.01},
    "fault_family_success": {"operator": ">=", "value": 0.55},
}

QUALITY_FLOOR_EVIDENCE_V2: dict[str, dict[str, Any]] = {
    "core_e2e": {
        "status": "measured",
        "runner": "g02.aggregate_gate_baselines",
        "artifact_field": "baselines.*.metrics.core_e2e",
    },
    "root_cause_top3": {
        "status": "measured",
        "runner": "g02.aggregate_gate_baselines",
        "artifact_field": "baselines.*.metrics.root_cause_top3",
    },
    "evidence_precision": {
        "status": "measured",
        "runner": "g02.score_result",
        "artifact_field": "baselines.*.metrics.evidence_precision",
    },
    "unsupported_critical_claim": {
        "status": "measured",
        "runner": "g02.score_result",
        "artifact_field": "baselines.*.metrics.unsupported_critical_claim",
    },
    "tool_schema_validity": {
        "status": "not_applicable",
        "reason": "G02 baselines make no applicable tool calls",
        "proof_obligation": {
            "gate": "G03",
            "runner": "g03.tool_contract_matrix",
            "required_artifact": "per-call schema verdicts",
        },
    },
    "dead_no_progress_loop": {
        "status": "not_applicable",
        "reason": "no Agent loop exists before G03",
        "proof_obligation": {
            "gate": "G03",
            "runner": "g03.termination_guard_matrix",
            "required_artifact": "per-trial terminal reasons and progress digests",
        },
    },
    "fault_family_success": {
        "status": "measured",
        "runner": "g02.aggregate_gate_baselines",
        "artifact_field": "baselines.*.fault_family_success",
    },
}

MODEL_ID = "qwen3.7-plus-2026-05-26"
BASELINES = ("deterministic", "naive_react", "no_rag")


class LiveInfrastructureError(RuntimeError):
    """A retryable provider/transport failure that remains trial-local."""


class LiveConfigurationError(RuntimeError):
    """A deterministic credential/route/attribution failure that blocks the run."""


_RESULT_METADATA_PROPERTIES = {
    "schema_version": {"type": "string"},
    "case_id": {"type": "string", "minLength": 1},
    "status": {"enum": ["ok", "failed"]},
    "baseline": {"type": "string"},
    "model_id": {"type": "string"},
    "fallback_count": {"type": "integer", "minimum": 0},
    "input_tokens": {"type": "integer", "minimum": 0},
    "output_tokens": {"type": "integer", "minimum": 0},
    "latency_ms": {"type": "number", "minimum": 0},
}

RESULT_SCHEMA_V1 = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        **_RESULT_METADATA_PROPERTIES,
        "root_cause": {"type": "string"},
        "root_cause_candidates": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 3,
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "supported": {"type": "boolean"},
                },
                "required": ["claim", "supported"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "case_id",
        "status",
        "root_cause",
        "root_cause_candidates",
        "evidence",
        "claims",
    ],
    "additionalProperties": False,
}

RESULT_SCHEMA_V2 = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        **_RESULT_METADATA_PROPERTIES,
        "schema_version": {"const": "2.0.0"},
        "root_cause": {"type": "string", "minLength": 1},
        "root_cause_candidates": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "maxItems": 3,
            "uniqueItems": True,
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "uniqueItems": True,
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_type": {"const": "root_cause"},
                    "value": {"type": "string", "minLength": 1},
                    "evidence_refs": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                },
                "required": ["claim_type", "value", "evidence_refs"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 1,
        },
    },
    "required": [
        "schema_version",
        "case_id",
        "status",
        "root_cause",
        "root_cause_candidates",
        "evidence",
        "claims",
    ],
    "additionalProperties": False,
}

# Kept as the public name used by the current scorer. Unlike the G02-era constant,
# this schema is executed by validate_result rather than serving as dead documentation.
RESULT_SCHEMA = RESULT_SCHEMA_V2


def load_baseline_config(root: Path) -> dict[str, Any]:
    config = load_data(root / "config" / "g02" / "baselines.yaml")
    model = config.get("model", {})
    if model != {
        "channel": "bailian",
        "family": "qwen",
        "model_id": MODEL_ID,
        "fallback_profiles": [],
        "transient_retries": 1,
        "orchestration_timeout_seconds": None,
    }:
        raise GovernanceError("G02 live model route or retry semantics drifted")
    expected = {
        "naive_react": {
            "max_turns": 4,
            "max_tool_calls": 6,
            "max_input_tokens": 8000,
            "max_output_tokens": 1024,
        },
        "no_rag": {
            "max_turns": 1,
            "max_tool_calls": 0,
            "max_input_tokens": 4000,
            "max_output_tokens": 512,
        },
    }
    if config.get("baselines") != expected:
        raise GovernanceError("G02 baseline token or turn budgets drifted")
    if config.get("bootstrap") != {
        "confidence": 0.95,
        "resamples": 2000,
        "cluster_key": "case_id",
        "seed_source": "dataset_digest",
    }:
        raise GovernanceError("G02 clustered bootstrap contract drifted")
    return config


def validate_threshold_registry(
    thresholds: Mapping[str, Any],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
    evidence: Mapping[str, Any] | None = None,
) -> None:
    require_g02_metric_version(metric_version)
    if dict(thresholds) != QUALITY_FLOORS:
        raise GovernanceError("G02 seven-value quality floor registry drifted")
    if metric_version == LEGACY_METRIC_VERSION:
        return
    if evidence is None or dict(evidence) != QUALITY_FLOOR_EVIDENCE_V2:
        raise GovernanceError("metric v2 quality floors lack exact runner evidence")


def resolve_quality_floor(metric: str, *, best_baseline: float) -> float:
    """Resolve the frozen floor without evaluating an arbitrary expression."""
    if metric not in QUALITY_FLOORS:
        raise GovernanceError(f"unknown quality floor: {metric}")
    value = QUALITY_FLOORS[metric]["value"]
    if metric == "core_e2e":
        if value != "max(0.70,best_baseline+0.10)":
            raise GovernanceError("Core E2E quality floor expression drifted")
        if not 0.0 <= best_baseline <= 1.0:
            raise GovernanceError("best baseline must be a probability")
        return max(0.70, best_baseline + 0.10)
    if not isinstance(value, (int, float)):
        raise GovernanceError(f"quality floor is not numeric: {metric}")
    return float(value)


def validate_quality_floor_coverage(
    computed_metrics: Iterable[str],
    *,
    evidence: Mapping[str, Any] = QUALITY_FLOOR_EVIDENCE_V2,
) -> None:
    """Fail when a registered floor is neither measured nor explicitly inapplicable."""
    validate_threshold_registry(
        QUALITY_FLOORS,
        metric_version=METRIC_VERSION,
        evidence=evidence,
    )
    computed = set(computed_metrics)
    for metric, proof in evidence.items():
        status = proof.get("status")
        if status == "measured":
            if metric not in computed:
                raise GovernanceError(
                    f"quality floor has no computed metric evidence: {metric}"
                )
        elif status == "not_applicable":
            obligation = proof.get("proof_obligation")
            if not proof.get("reason") or not isinstance(obligation, Mapping):
                raise GovernanceError(
                    f"quality floor lacks an inapplicability proof obligation: {metric}"
                )
            if not {"gate", "runner", "required_artifact"}.issubset(obligation):
                raise GovernanceError(
                    f"quality floor proof obligation is incomplete: {metric}"
                )
        else:
            raise GovernanceError(f"quality floor has an invalid evidence status: {metric}")


def resumable_trial_ids(document: Mapping[str, Any]) -> list[str]:
    trials = document.get("trials")
    if not isinstance(trials, list):
        raise GovernanceError("G02 journal snapshot lacks trials")
    allowed = {"pending", "running", "pass", "scored_failure", "infra_failed"}
    if any(not isinstance(item, dict) or item.get("status") not in allowed for item in trials):
        raise GovernanceError("G02 journal snapshot contains an invalid trial status")
    return [
        str(item["trial_id"])
        for item in trials
        if item.get("status") in {"pending", "infra_failed"}
    ]


def build_baseline_prompt(
    baseline: str,
    packet: Mapping[str, Any],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> list[dict[str, str]]:
    require_g02_metric_version(metric_version)
    packet = canonical_observation_packet(packet)
    if baseline not in {"naive_react", "no_rag"}:
        raise GovernanceError(f"unknown G02 live baseline: {baseline}")
    mode = (
        "Use a minimal ReAct-style diagnosis over only the supplied packet. "
        "Do not reveal private reasoning; return only the final structured diagnosis."
        if baseline == "naive_react"
        else "Use no retrieval and no tools. Diagnose only from the supplied packet."
    )
    if metric_version == METRIC_VERSION:
        labels = ", ".join(ROOT_CAUSE_LABELS)
        contract = (
            f"Choose only from this closed root-cause label set: {labels}. "
            "Return exactly one JSON object with root_cause, root_cause_candidates, evidence, "
            "and claims. root_cause and every candidate must use an exact label from the set. "
            "evidence must contain only IDs present in the packet and only evidence that directly "
            "supports the diagnosis. claims must contain exactly one object shaped as "
            '{"claim_type":"root_cause","value":"<exact label>",'
            '"evidence_refs":["<supporting evidence ID>"]}. '
            "Do not emit a supported flag, do not rename fields, and do not add keys."
        )
    else:
        contract = (
            "Return exactly one JSON object using these exact keys: root_cause (string), "
            "root_cause_candidates (array of at most three strings), evidence (array of "
            "observation ID strings), and claims (array of objects with claim and supported). "
            "Do not rename evidence to evidence_ids and do not add keys."
        )
    return [
        {
            "role": "system",
            "content": (
                mode + " Never infer or request ground truth or locked-test data. "
                + contract
            ),
        },
        {"role": "user", "content": json.dumps(packet, sort_keys=True)},
    ]


def make_bailian_adapter(
    root: Path,
    baseline: str,
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Create the exact-route paid adapter; construction performs no network call."""
    require_g02_metric_version(metric_version)
    from faultwitness_dev.bootstrap import (
        BootstrapPaths,
        default_sops_executable,
        load_secret_bundle,
    )

    config = load_baseline_config(root)
    bundle = load_secret_bundle(BootstrapPaths.defaults(), default_sops_executable())
    limits = config["baselines"][baseline]

    def invoke(packet: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = {
            "model": MODEL_ID,
            "messages": build_baseline_prompt(
                baseline,
                packet,
                metric_version=metric_version,
            ),
            "response_format": {"type": "json_object"},
            "max_tokens": limits["max_output_tokens"],
            "enable_thinking": False,
        }
        started = time.perf_counter()
        try:
            with httpx.Client(
                timeout=None,
                headers={"Authorization": f"Bearer {bundle.bailian_api_key}"},
            ) as client:
                response = client.post(
                    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    json=payload,
                )
        except httpx.TransportError as exc:
            raise LiveInfrastructureError(f"transport:{type(exc).__name__}") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise LiveInfrastructureError(f"upstream_http_{response.status_code}")
        if response.status_code >= 400:
            raise LiveConfigurationError(
                f"Bailian rejected the frozen route: HTTP {response.status_code}"
            )
        try:
            body = response.json()
            resolved = str(body.get("model") or MODEL_ID)
            if resolved != MODEL_ID:
                raise LiveConfigurationError("G02 live baseline resolved a different model")
            content = body["choices"][0]["message"]["content"]
            result = json.loads(content)
            usage = body.get("usage")
            if not isinstance(result, dict):
                raise ValueError("result root")
            if not isinstance(usage, dict) or not {
                "prompt_tokens",
                "completion_tokens",
            }.issubset(usage):
                raise LiveConfigurationError(
                    "G02 live baseline response omitted attributable usage"
                )
            result.update(
                {
                    "schema_version": wire_schema_for_metric(metric_version),
                    "case_id": packet["case_id"],
                    "status": "ok",
                    "baseline": baseline,
                    "model_id": MODEL_ID,
                    "fallback_count": 0,
                    "input_tokens": int(usage.get("prompt_tokens", 0)),
                    "output_tokens": int(usage.get("completion_tokens", 0)),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
            if result["input_tokens"] > limits["max_input_tokens"]:
                raise GovernanceError("baseline input token budget exhausted")
            if result["output_tokens"] > limits["max_output_tokens"]:
                raise GovernanceError("baseline output token budget exhausted")
            return result
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GovernanceError("baseline returned malformed structured output") from exc

    return invoke


def canonical_observation_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return the public packet, rejecting sealed fields."""
    required = {"schema_version", "case_id", "problem_brief", "observations"}
    missing = sorted(required - set(packet))
    if missing:
        raise GovernanceError(f"observation packet lacks {', '.join(missing)}")
    forbidden = {"ground_truth", "ground_truth_ref", "fault_action", "locked_test", "answer"}
    leaked = sorted(forbidden.intersection(packet))
    if leaked:
        raise GovernanceError("observation packet contains sealed fields: " + ", ".join(leaked))
    if not isinstance(packet["observations"], list) or not packet["observations"]:
        raise GovernanceError("observation packet observations must be a non-empty list")
    return json.loads(json.dumps(packet, sort_keys=True))


def build_observation_packet(
    scenario: Mapping[str, Any], observations: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Build the only packet shape visible to baselines from a sealed scenario run."""
    case_id = str(scenario.get("scenario_id", ""))
    brief = scenario.get("problem_brief")
    if not case_id or not isinstance(brief, str) or not brief:
        raise GovernanceError("scenario cannot produce a canonical observation packet")
    public_observations = []
    for index, observation in enumerate(observations, 1):
        if not isinstance(observation, Mapping):
            raise GovernanceError("scenario observation is not an object")
        public_observations.append(
            {"id": f"{case_id}-OBS-{index:02d}", **json.loads(json.dumps(observation))}
        )
    packet = {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "problem_brief": brief,
        "observations": public_observations,
    }
    canonical = canonical_observation_packet(packet)
    canonical["packet_digest"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return canonical


def _filtered_descriptions(
    observation: Mapping[str, Any], needles: tuple[str, ...]
) -> list[str]:
    descriptions = observation.get("descriptions", [])
    if not isinstance(descriptions, list):
        return []
    return [
        str(item)
        for item in descriptions
        if any(needle.casefold() in str(item).casefold() for needle in needles)
    ]


def _evidence_samples(
    observations: list[Mapping[str, Any]],
    fields: tuple[str, ...],
    *,
    description_needles: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for observation in observations:
        sample = {
            field: json.loads(json.dumps(observation[field]))
            for field in fields
            if field in observation
        }
        if description_needles:
            sample["descriptions"] = _filtered_descriptions(
                observation,
                description_needles,
            )
        samples.append(sample)
    return samples


def normalize_observation_packet_v2(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Turn mixed probe snapshots into six atomic, non-oracle evidence groups.

    The transformation uses the same fixed field projection for every case. It does
    not receive the sealed fault label, and it removes evaluator-derived booleans
    such as ``payment_error`` and ``kafka_error`` that made the v1 packet a label
    shortcut.
    """
    source = canonical_observation_packet(packet)
    observations = [
        item for item in source["observations"] if isinstance(item, Mapping)
    ]
    if len(observations) != len(source["observations"]):
        raise GovernanceError("metric v2 packet contains a non-object observation")
    case_id = str(source["case_id"])
    evidence = [
        {
            "id": f"{case_id}-EVID-01",
            "kind": "catalog_error_trace",
            "source": "trace_and_journey",
            "service": "productcatalogservice",
            "samples": _evidence_samples(
                observations,
                ("recorded_at", "journey_status", "trace_count", "error_spans"),
                description_needles=("product catalog", "feature flag enabled"),
            ),
        },
        {
            "id": f"{case_id}-EVID-02",
            "kind": "cpu_timeseries",
            "source": "prometheus",
            "service": "adservice",
            "metric": "container_cpu_usage_rate",
            "unit": "cpu_cores",
            "samples": _evidence_samples(
                observations,
                ("recorded_at", "cpu_rate", "baseline_cpu_max", "trace_count"),
            ),
        },
        {
            "id": f"{case_id}-EVID-03",
            "kind": "memory_timeseries",
            "source": "prometheus",
            "service": "emailservice",
            "metric": "container_memory_working_set",
            "unit": "bytes",
            "samples": _evidence_samples(
                observations,
                ("recorded_at", "working_set", "baseline_working_set"),
            ),
        },
        {
            "id": f"{case_id}-EVID-04",
            "kind": "payment_application_error",
            "source": "trace",
            "service": "paymentservice",
            "samples": _evidence_samples(
                observations,
                ("recorded_at", "checkout_error_spans", "error_spans"),
                description_needles=("invalid token", "payment request failed"),
            ),
        },
        {
            "id": f"{case_id}-EVID-05",
            "kind": "payment_connectivity_error",
            "source": "trace",
            "service": "paymentservice",
            "samples": _evidence_samples(
                observations,
                (
                    "recorded_at",
                    "checkout_error_spans",
                    "payment_connection_errors",
                ),
                description_needles=("name resolver", "zero addresses", "unavailable"),
            ),
        },
        {
            "id": f"{case_id}-EVID-06",
            "kind": "kafka_lag_timeseries",
            "source": "prometheus_and_logs",
            "service": "kafka",
            "metric": "consumer_poll_lag",
            "unit": "seconds",
            "samples": _evidence_samples(
                observations,
                (
                    "recorded_at",
                    "consumer_lag",
                    "baseline_lag",
                    "consumer_poll_lag_seconds",
                    "consumer_record_lag",
                ),
            ),
        },
    ]
    normalized = {
        "schema_version": "2.0.0",
        "case_id": case_id,
        "problem_brief": source["problem_brief"],
        "evidence_catalog_version": "g02-baseline-v2",
        "observations": evidence,
    }
    normalized["packet_digest"] = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return canonical_observation_packet(normalized)


def _v2_ground_truth(root_cause: str) -> dict[str, Any]:
    try:
        index = ROOT_CAUSE_LABELS.index(root_cause) + 1
    except ValueError as exc:
        raise GovernanceError(f"metric v2 received an unknown sealed label: {root_cause}") from exc
    return {
        "root_cause": root_cause,
        "required_evidence_suffix": f"EVID-{index:02d}",
    }


def _v2_evidence_id(packet: Mapping[str, Any], suffix: str) -> str:
    expected = f"{packet['case_id']}-{suffix}"
    available = {
        str(item.get("id"))
        for item in packet["observations"]
        if isinstance(item, Mapping)
    }
    if expected not in available:
        raise GovernanceError(f"metric v2 packet lacks expected evidence group: {suffix}")
    return expected


def _samples_for_kind(packet: Mapping[str, Any], kind: str) -> tuple[str, list[Mapping[str, Any]]]:
    matches = [
        item
        for item in packet["observations"]
        if isinstance(item, Mapping) and item.get("kind") == kind
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("samples"), list):
        raise GovernanceError(f"metric v2 packet lacks one {kind} evidence group")
    samples = [item for item in matches[0]["samples"] if isinstance(item, Mapping)]
    return str(matches[0]["id"]), samples


def _any_description(samples: Iterable[Mapping[str, Any]], *needles: str) -> bool:
    return any(
        any(
            needle.casefold() in str(description).casefold()
            for needle in needles
        )
        for sample in samples
        for description in sample.get("descriptions", [])
        if isinstance(sample.get("descriptions"), list)
    )


def _deterministic_v2(packet: Mapping[str, Any]) -> tuple[str, str]:
    catalog_id, catalog = _samples_for_kind(packet, "catalog_error_trace")
    cpu_id, cpu = _samples_for_kind(packet, "cpu_timeseries")
    memory_id, memory = _samples_for_kind(packet, "memory_timeseries")
    payment_id, payment = _samples_for_kind(packet, "payment_application_error")
    connectivity_id, connectivity = _samples_for_kind(
        packet,
        "payment_connectivity_error",
    )
    kafka_id, kafka = _samples_for_kind(packet, "kafka_lag_timeseries")

    if _any_description(catalog, "product catalog", "feature flag enabled"):
        return "productCatalogFailure", catalog_id
    if _any_description(connectivity, "name resolver", "zero addresses", "unavailable"):
        return "paymentUnreachable", connectivity_id
    if _any_description(payment, "invalid token", "payment request failed"):
        return "paymentFailure", payment_id
    if len(kafka) >= 2 and all(
        float(sample.get("consumer_lag", 0.0))
        > float(sample.get("baseline_lag", math.inf))
        for sample in kafka
    ):
        return "kafkaQueueProblems", kafka_id
    if len(cpu) >= 2 and all(
        float(sample.get("cpu_rate", 0.0))
        >= max(
            0.5,
            float(sample.get("baseline_cpu_max", math.inf)) * 5.0,
        )
        for sample in cpu
    ):
        return "adHighCpu", cpu_id
    working_sets = [
        float(sample["working_set"])
        for sample in memory
        if isinstance(sample.get("working_set"), (int, float))
        and float(sample["working_set"]) > 0
    ]
    baseline_sets = [
        float(sample["baseline_working_set"])
        for sample in memory
        if isinstance(sample.get("baseline_working_set"), (int, float))
        and float(sample["baseline_working_set"]) > 0
    ]
    if len(working_sets) >= 2 and baseline_sets:
        baseline = max(baseline_sets)
        minimum_growth = max(1024 * 1024, baseline * 0.05)
        if (
            working_sets[-1] - baseline >= minimum_growth
            and working_sets[-1] - working_sets[0] >= minimum_growth
        ):
            return "emailMemoryLeak", memory_id
    return "unknown", str(packet["observations"][0]["id"])


def deterministic_baseline(
    packet: Mapping[str, Any],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, Any]:
    require_g02_metric_version(metric_version)
    packet = canonical_observation_packet(packet)
    if metric_version == METRIC_VERSION:
        root, evidence_id = _deterministic_v2(packet)
        return {
            "schema_version": "2.0.0",
            "case_id": packet["case_id"],
            "root_cause": root,
            "root_cause_candidates": [root],
            "evidence": [evidence_id],
            "claims": [
                {
                    "claim_type": "root_cause",
                    "value": root,
                    "evidence_refs": [evidence_id],
                }
            ],
            "status": "ok",
            "baseline": "deterministic",
        }
    observations = [
        item for item in packet["observations"] if isinstance(item, Mapping)
    ]
    signatures: tuple[tuple[Callable[[list[Mapping[str, Any]]], bool], str], ...] = (
        (
            lambda rows: all(
                bool(item.get("journey_failed") and item.get("correlated_error"))
                for item in rows
            ),
            "productCatalogFailure",
        ),
        (
            lambda rows: all(
                bool(item.get("correlated_span"))
                and float(item.get("cpu_rate", 0.0))
                > float(item.get("baseline_cpu_max", math.inf))
                for item in rows
            ),
            "adHighCpu",
        ),
        (
            lambda rows: len(rows) >= 2
            and all("email_stimulus_count" in item for item in rows)
            and float(rows[-1].get("working_set", 0.0))
            > float(rows[0].get("working_set", 0.0)),
            "emailMemoryLeak",
        ),
        (
            lambda rows: all(
                bool(item.get("checkout_failed") and item.get("payment_error"))
                for item in rows
            ),
            "paymentFailure",
        ),
        (
            lambda rows: all(
                bool(item.get("checkout_failed") and item.get("connection_error"))
                for item in rows
            ),
            "paymentUnreachable",
        ),
        (
            lambda rows: all(
                bool(item.get("kafka_error"))
                and float(item.get("consumer_lag", 0.0))
                > float(item.get("baseline_lag", math.inf))
                for item in rows
            ),
            "kafkaQueueProblems",
        ),
    )
    root = next(
        (candidate for predicate, candidate in signatures if predicate(observations)),
        "unknown",
    )
    evidence = [
        str(item.get("id")) for item in observations if item.get("id")
    ]
    return {
        "schema_version": "1.0.0",
        "case_id": packet["case_id"],
        "root_cause": root,
        "root_cause_candidates": [root],
        "evidence": evidence,
        "claims": [],
        "status": "ok",
        "baseline": "deterministic",
    }


def validate_result(
    result: Mapping[str, Any],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> None:
    require_g02_metric_version(metric_version)
    schema = {
        LEGACY_METRIC_VERSION: RESULT_SCHEMA_V1,
        METRIC_VERSION: RESULT_SCHEMA,
    }.get(metric_version)
    if schema is None:  # pragma: no cover - guarded mapping exhaustiveness
        raise GovernanceError(f"missing result schema for metric version: {metric_version}")
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(dict(result))
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise GovernanceError(
            f"baseline result violates metric v{metric_version} schema at {location}: "
            f"{exc.message}"
        ) from exc


def _score_result_v1(
    result: Mapping[str, Any], ground_truth: Mapping[str, Any]
) -> dict[str, Any]:
    """Preserve the exact closed-G02 scorer for historical evidence reproduction."""
    try:
        validate_result(result, metric_version=LEGACY_METRIC_VERSION)
    except GovernanceError as exc:
        return {
            "status": "scored_failure",
            "failure_class": "malformed",
            "reason": str(exc),
            "core_e2e": 0.0,
        }
    expected = str(ground_truth.get("root_cause", ground_truth.get("fault_class", "")))
    actual = str(result.get("root_cause"))
    candidates = [str(item) for item in result.get("root_cause_candidates", [])]
    top3 = actual == expected or expected in candidates[:3]
    unsupported = int(
        any(
            bool(claim.get("supported") is False)
            for claim in result.get("claims", [])
            if isinstance(claim, dict)
        )
    )
    evidence = result.get("evidence", [])
    precision = (
        1.0
        if evidence
        and all(
            str(item) in {str(x) for x in ground_truth.get("evidence", evidence)}
            for item in evidence
        )
        else 0.0
    )
    return {
        "status": "scored",
        "failure_class": None if actual == expected else "wrong_root_cause",
        "core_e2e": 1.0 if actual == expected and precision >= 1.0 else 0.0,
        "root_cause_top3": 1.0 if top3 else 0.0,
        "evidence_precision": precision,
        "unsupported_critical_claim": float(unsupported),
        "tool_schema_validity": 1.0,
    }


def _metric_v2_failure(reason: str) -> dict[str, Any]:
    return {
        "status": "scored_failure",
        "failure_class": "malformed",
        "reason": reason,
        "core_e2e": 0.0,
        "root_cause_top3": 0.0,
        "evidence_precision": 0.0,
        "unsupported_critical_claim": 1.0,
        "tool_schema_validity": None,
        "output_schema_validity": 0.0,
    }


def _score_result_v2(
    result: Mapping[str, Any], ground_truth: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        validate_result(result, metric_version=METRIC_VERSION)
    except GovernanceError as exc:
        return _metric_v2_failure(str(exc))

    expected = str(ground_truth.get("root_cause", ""))
    required = {str(item) for item in ground_truth.get("required_evidence", [])}
    distractors = {str(item) for item in ground_truth.get("distractor_evidence", [])}
    if expected not in ROOT_CAUSE_LABELS or not required or required.intersection(distractors):
        raise GovernanceError("metric v2 ground truth is incomplete or contradictory")
    universe = required | distractors

    actual = str(result["root_cause"])
    candidates = [str(item) for item in result["root_cause_candidates"]]
    claim = result["claims"][0]
    claim_value = str(claim["value"])
    labels = [actual, *candidates, claim_value]
    invalid_labels = sorted({label for label in labels if label not in ROOT_CAUSE_LABELS})
    if invalid_labels:
        failure = _metric_v2_failure(
            "closed root-cause labels were not used: " + ", ".join(invalid_labels)
        )
        failure["failure_class"] = "invalid_label"
        failure["output_schema_validity"] = 1.0
        return failure
    if claim_value != actual:
        failure = _metric_v2_failure("typed root-cause claim does not match root_cause")
        failure["failure_class"] = "claim_contract"
        failure["output_schema_validity"] = 1.0
        return failure

    selected = {str(item) for item in result["evidence"]}
    claim_refs = {str(item) for item in claim["evidence_refs"]}
    unknown = sorted((selected | claim_refs) - universe)
    if unknown:
        failure = _metric_v2_failure(
            "diagnosis references unknown evidence: " + ", ".join(unknown)
        )
        failure["failure_class"] = "unknown_evidence"
        failure["output_schema_validity"] = 1.0
        return failure

    supported_citations = len(selected.intersection(required))
    precision = supported_citations / len(selected) if selected else 0.0
    complete = required.issubset(selected)
    claim_supported = (
        actual == expected
        and required.issubset(claim_refs)
        and not claim_refs.intersection(distractors)
    )
    unsupported = 0.0 if claim_supported else 1.0
    top3 = actual == expected or expected in candidates[:3]
    core = (
        actual == expected
        and complete
        and not selected.intersection(distractors)
        and unsupported == 0.0
    )
    if selected.intersection(distractors) or claim_refs.intersection(distractors):
        failure_class = "distractor_evidence"
    elif actual != expected:
        failure_class = "wrong_root_cause"
    elif not complete:
        failure_class = "missing_required_evidence"
    elif unsupported:
        failure_class = "unsupported_critical_claim"
    else:
        failure_class = None
    return {
        "status": "scored",
        "failure_class": failure_class,
        "core_e2e": 1.0 if core else 0.0,
        "root_cause_top3": 1.0 if top3 else 0.0,
        "evidence_precision": precision,
        "unsupported_critical_claim": unsupported,
        "tool_schema_validity": None,
        "output_schema_validity": 1.0,
    }


def score_result(
    result: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, Any]:
    """Score one answer while keeping closed G02 metric v1 reproducible."""
    require_g02_metric_version(metric_version)
    if metric_version == LEGACY_METRIC_VERSION:
        return _score_result_v1(result, ground_truth)
    if metric_version == METRIC_VERSION:
        return _score_result_v2(result, ground_truth)
    raise GovernanceError(f"unreachable G02 metric version: {metric_version}")


def percentile_cluster_bootstrap(
    rows: Iterable[Mapping[str, Any]], metric: str, *, B: int = 2000, seed: str = ""
) -> dict[str, float]:
    """95% percentile CI, resampling case clusters and retaining their repetitions."""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if metric not in row or row[metric] is None:
            raise GovernanceError(f"bootstrap metric was not computed: {metric}")
        grouped.setdefault(str(row["case_id"]), []).append(float(row[metric]))
    if not grouped:
        raise GovernanceError("bootstrap requires at least one case cluster")
    clusters = list(grouped.values())
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


def token_cost(
    input_tokens: int,
    output_tokens: int,
    input_cny_per_million: float = 2.0,
    output_cny_per_million: float = 8.0,
) -> float:
    if input_tokens < 0 or output_tokens < 0:
        raise GovernanceError("token counts cannot be negative")
    return (
        input_tokens / 1_000_000 * input_cny_per_million
        + output_tokens / 1_000_000 * output_cny_per_million
    )


def run_live_trials(
    root: Path,
    trials: Iterable[Mapping[str, Any]],
    adapter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    *,
    producer_sha: str,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> list[dict[str, Any]]:
    """Run trial-local adapters with atomic persistence; no outer wall-clock timeout."""
    require_g02_metric_version(metric_version)
    from faultwitness_dev.experiment import (
        ExperimentInfrastructureError,
        ExperimentRunner,
        ExperimentUnit,
        TrialJournal,
    )

    specs = [dict(spec) for spec in trials]
    journal = TrialJournal(root)
    units: list[ExperimentUnit] = []
    handlers: dict[str, Callable[..., Mapping[str, Any]]] = {}
    for spec in specs:
        trial_id = str(spec["trial_id"])
        packet = canonical_observation_packet(spec["packet"])
        input_digest = hashlib.sha256(
            json.dumps(
                {
                    "baseline": spec.get("baseline"),
                    "metric_version": metric_version,
                    "packet": packet,
                    "repetition": spec.get("repetition"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        units.append(
            ExperimentUnit(
                unit_id=trial_id,
                required_checkpoints=("model_route",),
                depends_on=(),
                input_digest=input_digest,
            )
        )

        def execute(_execution, *, frozen_spec=spec, frozen_packet=packet):  # type: ignore[no-untyped-def]
            result: dict[str, Any] | None = None
            try:
                result = dict(
                    adapter(frozen_packet)
                    if adapter
                    else deterministic_baseline(
                        frozen_packet,
                        metric_version=metric_version,
                    )
                )
                validate_result(result, metric_version=metric_version)
                payload = {
                    "case_id": frozen_packet["case_id"],
                    "baseline": frozen_spec.get("baseline"),
                    "repetition": frozen_spec.get("repetition"),
                    "result": result,
                    "input_tokens": int(result.get("input_tokens", 0)),
                    "output_tokens": int(result.get("output_tokens", 0)),
                    "cost_cny": token_cost(
                        int(result.get("input_tokens", 0)),
                        int(result.get("output_tokens", 0)),
                    ),
                }
            except LiveInfrastructureError as exc:
                raise ExperimentInfrastructureError(str(exc)) from exc
            except LiveConfigurationError:
                raise
            except GovernanceError as exc:
                input_tokens = int(result.get("input_tokens", 0)) if result else 0
                output_tokens = int(result.get("output_tokens", 0)) if result else 0
                payload = {
                    "case_id": frozen_packet["case_id"],
                    "baseline": frozen_spec.get("baseline"),
                    "repetition": frozen_spec.get("repetition"),
                    "result": {
                        "status": "scored_failure",
                        "failure_class": "malformed",
                        "reason": str(exc),
                        "model_id": result.get("model_id") if result else None,
                        "fallback_count": result.get("fallback_count") if result else 0,
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
        {"model_route": f"{MODEL_ID}:metric-v{metric_version}"},
        producer_sha=producer_sha,
    ).run(handlers)
    records = {record["trial_id"]: record for record in run.records}
    return [records[str(spec["trial_id"])] for spec in specs]


def _scenario_cases(
    document: Mapping[str, Any],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, dict[str, Any]]:
    require_g02_metric_version(metric_version)
    trials = document.get("trials")
    if not isinstance(trials, list) or len(trials) != 32:
        raise GovernanceError("G02 baseline input requires exactly 32 scenario trials")
    cases: dict[str, dict[str, Any]] = {}
    for trial in trials:
        if not isinstance(trial, dict) or trial.get("status") != "pass":
            raise GovernanceError("G02 baseline input contains an incomplete scenario")
        payload = trial.get("payload")
        if not isinstance(payload, dict):
            raise GovernanceError("G02 scenario trial lacks a payload")
        packet = canonical_observation_packet(payload.get("observation_packet", {}))
        case_id = str(packet["case_id"])
        fault_class = str(payload.get("fault_class", ""))
        result = payload.get("result", {})
        if not fault_class or not isinstance(result, dict):
            raise GovernanceError("G02 scenario trial lacks sealed evaluator truth")
        if metric_version == METRIC_VERSION:
            packet = normalize_observation_packet_v2(packet)
            truth = _v2_ground_truth(fault_class)
            required = _v2_evidence_id(
                packet,
                str(truth["required_evidence_suffix"]),
            )
            all_evidence = {
                str(item["id"])
                for item in packet["observations"]
                if isinstance(item, Mapping)
            }
            ground_truth = {
                "root_cause": fault_class,
                "required_evidence": [required],
                "distractor_evidence": sorted(all_evidence - {required}),
            }
        elif metric_version == LEGACY_METRIC_VERSION:
            evidence = [
                str(item.get("id"))
                for item in packet["observations"]
                if isinstance(item, dict) and item.get("id")
            ]
            ground_truth = {"root_cause": fault_class, "evidence": evidence}
        else:
            raise GovernanceError(f"unsupported metric version: {metric_version}")
        cases[case_id] = {
            "packet": packet,
            "ground_truth": ground_truth,
            "family": str(result.get("family", "")),
        }
    if len(cases) != 32:
        raise GovernanceError("G02 baseline input case IDs are not unique")
    return cases


def metric_v2_dataset_digest(scenario_document: Mapping[str, Any]) -> str:
    cases = _scenario_cases(scenario_document, metric_version=METRIC_VERSION)
    subject = {
        case_id: {
            "packet_digest": case["packet"]["packet_digest"],
            "ground_truth": case["ground_truth"],
            "family": case["family"],
        }
        for case_id, case in sorted(cases.items())
    }
    return hashlib.sha256(
        json.dumps(subject, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_json_artifact(path: Path, document: Mapping[str, Any]) -> str:
    """Persist a reviewable experiment artifact atomically and return its digest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def run_gate_deterministic_matrix(
    producer_sha: str,
    scenario_document: Mapping[str, Any],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, Any]:
    require_g02_metric_version(metric_version)
    cases = _scenario_cases(scenario_document, metric_version=metric_version)
    rows = []
    for case_id in sorted(cases):
        case = cases[case_id]
        result = deterministic_baseline(
            case["packet"],
            metric_version=metric_version,
        )
        rows.append(
            {
                "case_id": case_id,
                "family": case["family"],
                "ground_truth_access": False,
                "result": result,
                **score_result(
                    result,
                    case["ground_truth"],
                    metric_version=metric_version,
                ),
            }
        )
    document = {
        "producer_sha": producer_sha,
        "validation": "V-G02-014",
        "N": 32,
        "rows": rows,
        "status": "pass",
    }
    if metric_version == METRIC_VERSION:
        document["metric_version"] = METRIC_VERSION
    validate_deterministic_matrix(document)
    return document


def _gate_trial_specs(
    dataset_digest: str,
    cases: Mapping[str, Mapping[str, Any]],
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, list[dict[str, Any]]]:
    require_g02_metric_version(metric_version)
    specs = {"naive_react": [], "no_rag": []}
    for baseline in specs:
        for case_id in sorted(cases):
            for repetition in range(1, 4):
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
                        "trial_id": f"g02-v{metric_version}-"
                        + hashlib.sha256(
                            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest(),
                        "baseline": baseline,
                        "case_id": case_id,
                        "repetition": repetition,
                        "packet": cases[case_id]["packet"],
                    }
                )
    return specs


def run_gate_live_matrix(
    root: Path,
    producer_sha: str,
    dataset_digest: str,
    scenario_document: Mapping[str, Any],
    journal_root: Path,
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, Any]:
    require_g02_metric_version(metric_version)
    cases = _scenario_cases(scenario_document, metric_version=metric_version)
    records = []
    for baseline, specs in _gate_trial_specs(
        dataset_digest,
        cases,
        metric_version=metric_version,
    ).items():
        records.extend(
            run_live_trials(
                journal_root,
                specs,
                make_bailian_adapter(
                    root,
                    baseline,
                    metric_version=metric_version,
                ),
                producer_sha=producer_sha,
                metric_version=metric_version,
            )
        )
    rows = []
    for record in records:
        payload = record.get("payload", {})
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        trial_status = record.get("status")
        if trial_status == "pass" and result.get("status") == "scored_failure":
            matrix_status = "scored_failure"
        else:
            matrix_status = trial_status
        rows.append(
            {
                "trial_id": record.get("trial_id"),
                "baseline": payload.get("baseline"),
                "case_id": payload.get("case_id"),
                "repetition": payload.get("repetition"),
                "status": matrix_status,
                "fallback_count": result.get("fallback_count", 0),
                "input_tokens": payload.get("input_tokens", 0),
                "output_tokens": payload.get("output_tokens", 0),
                "cost_cny": payload.get("cost_cny", 0.0),
                "result": result,
            }
        )
    unresolved = [row for row in rows if row["status"] == "infra_failed"]
    document = {
        "producer_sha": producer_sha,
        "dataset_digest": dataset_digest,
        "model_id": MODEL_ID,
        "trial_count": len(rows),
        "trials": rows,
        "status": "infra_failed" if unresolved else "pass",
    }
    if metric_version == METRIC_VERSION:
        document["metric_version"] = METRIC_VERSION
    if not unresolved:
        validate_live_matrix(document)
    return document


def aggregate_gate_baselines(
    scenario_document: Mapping[str, Any],
    deterministic_document: Mapping[str, Any],
    live_document: Mapping[str, Any],
    dataset_digest: str,
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, Any]:
    require_g02_metric_version(metric_version)
    cases = _scenario_cases(scenario_document, metric_version=metric_version)
    live_trials = live_document.get("trials")
    if not isinstance(live_trials, list) or len(live_trials) != 192:
        raise GovernanceError("G02 aggregate requires exactly 192 live trials")
    scored_live = []
    for trial in live_trials:
        case_id = str(trial["case_id"])
        result = trial.get("result", {})
        if trial.get("status") == "pass" and isinstance(result, dict):
            score = score_result(
                result,
                cases[case_id]["ground_truth"],
                metric_version=metric_version,
            )
        else:
            score = (
                _metric_v2_failure("trial did not produce a scoreable result")
                if metric_version == METRIC_VERSION
                else {
                    "core_e2e": 0.0,
                    "root_cause_top3": 0.0,
                    "evidence_precision": 0.0,
                    "unsupported_critical_claim": 1.0,
                    "tool_schema_validity": 0.0,
                }
            )
        scored_live.append({**trial, "family": cases[case_id]["family"], **score})
    baselines = {}
    for baseline in ("naive_react", "no_rag"):
        rows = [row for row in scored_live if row["baseline"] == baseline]
        baselines[baseline] = aggregate_live_metrics(
            rows,
            dataset_digest,
            metric_version=metric_version,
        )
    deterministic_rows = deterministic_document.get("rows")
    if not isinstance(deterministic_rows, list) or len(deterministic_rows) != 32:
        raise GovernanceError("G02 aggregate requires exactly 32 deterministic rows")
    if metric_version == METRIC_VERSION:
        deterministic_scored = [
            {**row, "family": cases[str(row["case_id"])]["family"]}
            for row in deterministic_rows
        ]
        baselines["deterministic"] = aggregate_live_metrics(
            deterministic_scored,
            dataset_digest,
            metric_version=metric_version,
        ) | {
            "case_count": 32,
            "trial_count": 32,
        }
        measured = {
            "core_e2e",
            "root_cause_top3",
            "evidence_precision",
            "unsupported_critical_claim",
            "fault_family_success",
        }
        validate_quality_floor_coverage(measured)
        estimates = {
            baseline: float(values["metrics"]["core_e2e"]["estimate"])
            for baseline, values in baselines.items()
        }
        best_name = max(estimates, key=estimates.__getitem__)
        best_value = estimates[best_name]
        comparison_floor = best_value + 0.05
        return {
            "status": "pass",
            "metric_version": METRIC_VERSION,
            "confidence": 0.95,
            "resamples": 2000,
            "cluster_key": "case_id",
            "case_clusters": 32,
            "dataset_digest": dataset_digest,
            "quality_floors": QUALITY_FLOORS,
            "quality_floor_evidence": QUALITY_FLOOR_EVIDENCE_V2,
            "best_baseline": {
                "name": best_name,
                "core_e2e": best_value,
            },
            "g03_comparison": {
                "operator": ">=",
                "margin": 0.05,
                "minimum_core_e2e": comparison_floor,
                "feasible_on_unit_interval": comparison_floor <= 1.0,
            },
            "future_core_e2e_floor": resolve_quality_floor(
                "core_e2e",
                best_baseline=best_value,
            ),
            "baselines": baselines,
            "scored_live_trials": scored_live,
        }
    if metric_version != LEGACY_METRIC_VERSION:
        raise GovernanceError(f"unsupported metric version: {metric_version}")
    baselines["deterministic"] = {
        "case_count": 32,
        "core_e2e": sum(float(row.get("core_e2e", 0.0)) for row in deterministic_rows) / 32,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_cny": 0.0,
    }
    return {
        "status": "pass",
        "confidence": 0.95,
        "resamples": 2000,
        "cluster_key": "case_id",
        "case_clusters": 32,
        "baselines": baselines,
        "scored_live_trials": scored_live,
    }


def validate_deterministic_matrix(document: Mapping[str, Any]) -> dict[str, Any]:
    rows = document.get("rows")
    if not isinstance(rows, list) or len(rows) != 32:
        raise GovernanceError("G02 deterministic Gate matrix must contain exactly 32 rows")
    case_ids = {str(row.get("case_id")) for row in rows if isinstance(row, dict)}
    if len(case_ids) != 32 or any(not case_id.startswith("SEED-G02-") for case_id in case_ids):
        raise GovernanceError("G02 deterministic matrix case registry drifted")
    if any(row.get("ground_truth_access") is not False for row in rows):
        raise GovernanceError("G02 deterministic baseline accessed ground truth")
    return {"status": "pass", "case_count": 32, "validation": "V-G02-014"}


def validate_live_matrix(document: Mapping[str, Any]) -> dict[str, Any]:
    trials = document.get("trials")
    if not isinstance(trials, list) or len(trials) != 192:
        raise GovernanceError("G02 live Gate matrix must contain exactly 192 trials")
    expected = {
        (baseline, f"SEED-G02-{case:04d}", repetition)
        for baseline in ("naive_react", "no_rag")
        for case in range(1, 33)
        for repetition in range(1, 4)
    }
    actual = {
        (str(row.get("baseline")), str(row.get("case_id")), int(row.get("repetition", 0)))
        for row in trials
        if isinstance(row, dict)
    }
    if actual != expected:
        raise GovernanceError("G02 live trial registry drifted")
    unresolved = [
        row.get("trial_id") for row in trials if row.get("status") not in {"pass", "scored_failure"}
    ]
    if unresolved:
        raise GovernanceError("G02 live matrix has unresolved trials")
    if any(row.get("fallback_count") != 0 for row in trials):
        raise GovernanceError("G02 live matrix used a fallback route")
    return {"status": "pass", "trial_count": 192, "case_clusters": 32, "validation": "V-G02-015"}


def aggregate_live_metrics(
    trials: Iterable[Mapping[str, Any]],
    dataset_digest: str,
    *,
    metric_version: int = LEGACY_METRIC_VERSION,
) -> dict[str, Any]:
    require_g02_metric_version(metric_version)
    rows = list(trials)
    metrics = {}
    metric_names = (
        (
            "core_e2e",
            "root_cause_top3",
            "evidence_precision",
            "unsupported_critical_claim",
        )
        if metric_version == METRIC_VERSION
        else (
            "core_e2e",
            "root_cause_top3",
            "evidence_precision",
            "unsupported_critical_claim",
            "tool_schema_validity",
        )
    )
    for metric in metric_names:
        metrics[metric] = percentile_cluster_bootstrap(rows, metric, B=2000, seed=dataset_digest)
    result = {
        "confidence": 0.95,
        "cluster_key": "case_id",
        "case_clusters": len({str(row["case_id"]) for row in rows}),
        "metrics": metrics,
        "input_tokens": sum(int(row.get("input_tokens", 0)) for row in rows),
        "output_tokens": sum(int(row.get("output_tokens", 0)) for row in rows),
        "cost_cny": sum(float(row.get("cost_cny", 0.0)) for row in rows),
    }
    if metric_version == METRIC_VERSION:
        families = sorted({str(row["family"]) for row in rows})
        if not families or any(not family for family in families):
            raise GovernanceError("metric v2 rows lack fault-family attribution")
        result["metric_version"] = METRIC_VERSION
        result["trial_count"] = len(rows)
        result["fault_family_success"] = {
            family: percentile_cluster_bootstrap(
                [row for row in rows if row["family"] == family],
                "core_e2e",
                B=2000,
                seed=f"{dataset_digest}:{family}",
            )
            for family in families
        }
        result["not_applicable"] = {
            metric: QUALITY_FLOOR_EVIDENCE_V2[metric]
            for metric in ("tool_schema_validity", "dead_no_progress_loop")
        }
    return result
