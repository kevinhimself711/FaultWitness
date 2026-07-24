"""G02 baseline, scoring, and resumable trial contracts.

The module deliberately keeps the Iteration runner offline.  Gate code may provide a live
adapter, but the journal and scoring semantics are identical for both paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data

QUALITY_FLOORS: dict[str, dict[str, float | str]] = {
    "core_e2e": {"operator": ">=", "value": "max(0.70,best_baseline+0.10)"},
    "root_cause_top3": {"operator": ">=", "value": 0.85},
    "evidence_precision": {"operator": ">=", "value": 0.90},
    "unsupported_critical_claim": {"operator": "<=", "value": 0.02},
    "tool_schema_validity": {"operator": ">=", "value": 0.99},
    "dead_no_progress_loop": {"operator": "<", "value": 0.01},
    "fault_family_success": {"operator": ">=", "value": 0.55},
}

MODEL_ID = "qwen3.7-plus-2026-05-26"
BASELINES = ("deterministic", "naive_react", "no_rag")


class LiveInfrastructureError(RuntimeError):
    """A retryable provider/transport failure that remains trial-local."""


class LiveConfigurationError(RuntimeError):
    """A deterministic credential/route/attribution failure that blocks the run."""


RESULT_SCHEMA = {
    "type": "object",
    "properties": {
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
    "required": ["root_cause", "root_cause_candidates", "evidence", "claims"],
    "additionalProperties": False,
}


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


def validate_threshold_registry(thresholds: Mapping[str, Any]) -> None:
    if dict(thresholds) != QUALITY_FLOORS:
        raise GovernanceError("G02 seven-value quality floor registry drifted")


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


def build_baseline_prompt(baseline: str, packet: Mapping[str, Any]) -> list[dict[str, str]]:
    packet = canonical_observation_packet(packet)
    if baseline not in {"naive_react", "no_rag"}:
        raise GovernanceError(f"unknown G02 live baseline: {baseline}")
    mode = (
        "Use a minimal ReAct-style diagnosis over only the supplied packet. "
        "Do not reveal private reasoning; return only the final structured diagnosis."
        if baseline == "naive_react"
        else "Use no retrieval and no tools. Diagnose only from the supplied packet."
    )
    return [
        {
            "role": "system",
            "content": (
                mode + " Never infer or request ground truth or locked-test data. "
                "Return exactly one JSON object using these exact keys: root_cause (string), "
                "root_cause_candidates (array of at most three strings), evidence (array of "
                "observation ID strings), and claims (array of objects with claim and supported). "
                "Do not rename evidence to evidence_ids and do not add keys."
            ),
        },
        {"role": "user", "content": json.dumps(packet, sort_keys=True)},
    ]


def make_bailian_adapter(
    root: Path, baseline: str
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Create the exact-route paid adapter; construction performs no network call."""
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
            "messages": build_baseline_prompt(baseline, packet),
            "response_format": {"type": "json_object"},
            "max_tokens": limits["max_output_tokens"],
            "enable_thinking": False,
        }
        last_infra: str | None = None
        for attempt in range(2):
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
                last_infra = f"transport:{type(exc).__name__}"
                if attempt == 0:
                    continue
                raise LiveInfrastructureError(last_infra) from exc
            if response.status_code == 429 or response.status_code >= 500:
                last_infra = f"upstream_http_{response.status_code}"
                if attempt == 0:
                    continue
                raise LiveInfrastructureError(last_infra)
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
                        "schema_version": "1.0.0",
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
        raise LiveInfrastructureError(last_infra or "unknown infrastructure failure")

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


def deterministic_baseline(packet: Mapping[str, Any]) -> dict[str, Any]:
    packet = canonical_observation_packet(packet)
    observation_keys = {
        str(key) for item in packet["observations"] if isinstance(item, dict) for key in item
    }
    signatures = (
        ({"journey_failed", "correlated_error"}, "productCatalogFailure"),
        ({"cpu_rate", "baseline_cpu_max", "correlated_span"}, "adHighCpu"),
        ({"working_set"}, "emailMemoryLeak"),
        ({"checkout_failed", "payment_error"}, "paymentFailure"),
        ({"checkout_failed", "connection_error"}, "paymentUnreachable"),
        ({"consumer_lag", "baseline_lag", "kafka_error"}, "kafkaQueueProblems"),
    )
    root = "unknown"
    for required, candidate in signatures:
        if required.issubset(observation_keys):
            root = candidate
            break
    evidence = [
        str(item.get("id"))
        for item in packet["observations"]
        if isinstance(item, dict) and item.get("id")
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


def validate_result(result: Mapping[str, Any]) -> None:
    allowed = {
        "schema_version",
        "case_id",
        "root_cause",
        "root_cause_candidates",
        "evidence",
        "claims",
        "status",
        "baseline",
        "model_id",
        "fallback_count",
        "input_tokens",
        "output_tokens",
        "latency_ms",
    }
    unexpected = sorted(set(result) - allowed)
    if unexpected:
        raise GovernanceError("baseline result has unexpected fields: " + ", ".join(unexpected))
    if not isinstance(result.get("case_id"), str) or not result["case_id"]:
        raise GovernanceError("baseline result lacks case_id")
    if not isinstance(result.get("root_cause"), str):
        raise GovernanceError("baseline result lacks root_cause")
    if result.get("status") not in {"ok", "failed"}:
        raise GovernanceError("baseline result has invalid status")
    if (
        not isinstance(result.get("root_cause_candidates"), list)
        or len(result["root_cause_candidates"]) > 3
    ):
        raise GovernanceError("baseline result lacks valid root_cause_candidates")
    if "evidence" not in result or not isinstance(result["evidence"], list):
        raise GovernanceError("baseline evidence must be a list")
    if "claims" not in result or not isinstance(result["claims"], list):
        raise GovernanceError("baseline claims must be a list")
    for claim in result["claims"]:
        if (
            not isinstance(claim, dict)
            or not isinstance(claim.get("claim"), str)
            or not isinstance(claim.get("supported"), bool)
        ):
            raise GovernanceError("baseline claim does not satisfy the frozen schema")


def score_result(result: Mapping[str, Any], ground_truth: Mapping[str, Any]) -> dict[str, Any]:
    """Score one structured answer; malformed answers are scored failures, never retried."""
    try:
        validate_result(result)
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


def percentile_cluster_bootstrap(
    rows: Iterable[Mapping[str, Any]], metric: str, *, B: int = 2000, seed: str = ""
) -> dict[str, float]:
    """95% percentile CI, resampling case clusters and retaining their repetitions."""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(str(row["case_id"]), []).append(float(row.get(metric, 0.0)))
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
) -> list[dict[str, Any]]:
    """Run trial-local adapters with atomic persistence; no outer wall-clock timeout."""
    from faultwitness_dev.g02_eval import TrialJournal

    journal = TrialJournal(root)
    completed: list[dict[str, Any]] = []
    for spec in trials:
        trial_id = str(spec["trial_id"])
        previous = journal.read(trial_id)
        if previous and previous.get("status") == "pass":
            completed.append(previous)
            continue
        packet = canonical_observation_packet(spec["packet"])
        journal.write(
            trial_id, "running", {"baseline": spec.get("baseline"), "case_id": packet["case_id"]}
        )
        result: dict[str, Any] | None = None
        try:
            result = dict(adapter(packet) if adapter else deterministic_baseline(packet))
            validate_result(result)
            record = journal.write(
                trial_id,
                "pass",
                {
                    "case_id": packet["case_id"],
                    "result": result,
                    "input_tokens": int(result.get("input_tokens", 0)),
                    "output_tokens": int(result.get("output_tokens", 0)),
                    "cost_cny": token_cost(
                        int(result.get("input_tokens", 0)), int(result.get("output_tokens", 0))
                    ),
                },
            )
        except LiveInfrastructureError as exc:
            record = journal.write(
                trial_id,
                "infra_failed",
                {"case_id": packet["case_id"], "reason": str(exc)},
            )
        except GovernanceError as exc:
            input_tokens = int(result.get("input_tokens", 0)) if result else 0
            output_tokens = int(result.get("output_tokens", 0)) if result else 0
            record = journal.write(
                trial_id,
                "pass",
                {
                    "case_id": packet["case_id"],
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
                },
            )
        completed.append(record)
    return completed


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
    trials: Iterable[Mapping[str, Any]], dataset_digest: str
) -> dict[str, Any]:
    rows = list(trials)
    metrics = {}
    for metric in (
        "core_e2e",
        "root_cause_top3",
        "evidence_precision",
        "unsupported_critical_claim",
        "tool_schema_validity",
    ):
        metrics[metric] = percentile_cluster_bootstrap(rows, metric, B=2000, seed=dataset_digest)
    return {
        "confidence": 0.95,
        "cluster_key": "case_id",
        "case_clusters": len({str(row["case_id"]) for row in rows}),
        "metrics": metrics,
        "input_tokens": sum(int(row.get("input_tokens", 0)) for row in rows),
        "output_tokens": sum(int(row.get("output_tokens", 0)) for row in rows),
        "cost_cny": sum(float(row.get("cost_cny", 0.0)) for row in rows),
    }
