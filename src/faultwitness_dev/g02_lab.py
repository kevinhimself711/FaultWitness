from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import yaml

from faultwitness_dev.bootstrap import BootstrapPaths, ssh_failure_category
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import (
    InfraPaths,
    _ensure_crane,
    _remote_arguments,
    run_remote_script,
)
from faultwitness_dev.schemas import validate_repository_schemas

SUT_RELEASE = "2.2.0"
SUT_COMMIT = "b74a7bc7bbe66099c61951f42b24dab8b6f02d18"
SEED_DOMAIN = "G02-seed-id-v1"
FAMILIES = ("change_config", "resource_capacity", "dependency_network", "runtime_data")
DIFFICULTIES = ("Easy", "Medium", "Hard", "OOD", "Adversarial")
FAULT_CLASSES = (
    "productCatalogFailure",
    "adHighCpu",
    "emailMemoryLeak",
    "paymentFailure",
    "paymentUnreachable",
    "kafkaQueueProblems",
)
TRACE_QUERY_SERVICES = {
    "productCatalogFailure": "product-catalog",
    "adHighCpu": "ad",
    "emailMemoryLeak": "email",
    "paymentFailure": "payment",
    "paymentUnreachable": "checkout",
    "kafkaQueueProblems": "fraud-detection",
}
FULL_DIGEST_REFERENCE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PROBE_IMAGE_NAMES = ("busybox", "minio_mc")

K8S_SOURCE_IMAGES: dict[str, tuple[str, ...]] = {
    "accounting": ("ghcr.io/open-telemetry/demo:2.1.3-accounting",),
    "ad": ("ghcr.io/open-telemetry/demo:2.1.3-ad",),
    "cart": ("ghcr.io/open-telemetry/demo:2.1.3-cart",),
    "checkout": ("ghcr.io/open-telemetry/demo:2.1.3-checkout",),
    "currency": ("ghcr.io/open-telemetry/demo:2.1.3-currency",),
    "email": ("ghcr.io/open-telemetry/demo:2.1.3-email",),
    "flagd-ui": ("ghcr.io/open-telemetry/demo:2.1.3-flagd-ui",),
    "fraud-detection": ("ghcr.io/open-telemetry/demo:2.1.3-fraud-detection",),
    "frontend": ("ghcr.io/open-telemetry/demo:2.1.3-frontend",),
    "frontend-proxy": ("ghcr.io/open-telemetry/demo:2.1.3-frontend-proxy",),
    "image-provider": ("ghcr.io/open-telemetry/demo:2.1.3-image-provider",),
    "kafka": ("ghcr.io/open-telemetry/demo:2.1.3-kafka",),
    "load-generator": ("ghcr.io/open-telemetry/demo:2.1.3-load-generator",),
    "payment": ("ghcr.io/open-telemetry/demo:2.1.3-payment",),
    "postgres": ("ghcr.io/open-telemetry/demo:2.1.3-postgresql",),
    "product-catalog": ("ghcr.io/open-telemetry/demo:2.1.3-product-catalog",),
    "quote": ("ghcr.io/open-telemetry/demo:2.1.3-quote",),
    "recommendation": ("ghcr.io/open-telemetry/demo:2.1.3-recommendation",),
    "shipping": ("ghcr.io/open-telemetry/demo:2.1.3-shipping",),
    "flagd": ("ghcr.io/open-feature/flagd:v0.12.8",),
    "otel-collector": ("otel/opentelemetry-collector-contrib:0.135.0",),
    "busybox": ("busybox:latest", "busybox"),
    "grafana": ("docker.io/grafana/grafana:12.1.1",),
    "jaeger": ("jaegertracing/all-in-one:1.53.0",),
    "opensearch": ("opensearchproject/opensearch:3.2.0",),
    "valkey": ("valkey/valkey:8.1.3-alpine",),
    "k8s-sidecar": ("quay.io/kiwigrid/k8s-sidecar:1.30.10",),
    "prometheus": ("quay.io/prometheus/prometheus:v3.6.0",),
}


class OracleState(StrEnum):
    HEALTHY = "HEALTHY"
    FAULT_ACTIVE = "FAULT_ACTIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FaultAdapter:
    family: str
    flag_key: str
    variant: str
    required_fields: tuple[str, ...]


ADAPTERS = {
    "productCatalogFailure": FaultAdapter(
        "change_config", "productCatalogFailure", "on", ("journey_failed", "correlated_error")
    ),
    "adHighCpu": FaultAdapter(
        "resource_capacity", "adHighCpu", "on", ("cpu_rate", "baseline_cpu_max", "correlated_span")
    ),
    "emailMemoryLeak": FaultAdapter(
        "resource_capacity", "emailMemoryLeak", "100x", ("working_set",)
    ),
    "paymentFailure": FaultAdapter(
        "dependency_network", "paymentFailure", "100%", ("checkout_failed", "payment_error")
    ),
    "paymentUnreachable": FaultAdapter(
        "dependency_network",
        "paymentUnreachable",
        "on",
        ("checkout_failed", "connection_error"),
    ),
    "kafkaQueueProblems": FaultAdapter(
        "runtime_data", "kafkaQueueProblems", "on", ("consumer_lag", "baseline_lag", "kafka_error")
    ),
}


class FlagDocumentClient(Protocol):
    def read(self) -> dict[str, Any]: ...

    def write(self, document: Mapping[str, Any]) -> None: ...


class TrialJournalProtocol(Protocol):
    def read(self, trial_id: str) -> dict[str, Any] | None: ...

    def write(self, trial_id: str, status: str, payload: Mapping[str, Any]) -> dict[str, Any]: ...


Observation = Mapping[str, Any]
Observer = Callable[[str, str], Observation]


class RemoteFlagClient:
    def __init__(self, candidate_sha: str) -> None:
        if not FULL_SHA.fullmatch(candidate_sha):
            raise GovernanceError("remote flag client requires a full candidate SHA")
        self.candidate_sha = candidate_sha

    def _prelude(self) -> str:
        candidate = shlex.quote(self.candidate_sha)
        return f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-sut \
  get configmap fw-g02-candidate-binding -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate}
cluster_ip=$(/usr/local/bin/k3s kubectl -n fw-sut \
  get service flagd -o jsonpath='{{.spec.clusterIP}}')
endpoint="http://$cluster_ip:4000"
"""

    def read(self) -> dict[str, Any]:
        output = run_remote_script(
            self._prelude() + 'curl -fsS "$endpoint/api/read"\n', privileged=True
        )
        try:
            document = json.loads(output)
        except json.JSONDecodeError as error:
            raise GovernanceError("flagd UI returned malformed JSON") from error
        if not isinstance(document, dict) or not isinstance(document.get("flags"), dict):
            raise GovernanceError("flagd UI returned an invalid flag document")
        return document

    def write(self, document: Mapping[str, Any]) -> None:
        body = base64.b64encode(
            json.dumps({"data": document}, separators=(",", ":")).encode()
        ).decode("ascii")
        output = run_remote_script(
            self._prelude()
            + f"printf %s {shlex.quote(body)} | base64 -d | "
            + "curl -fsS -H 'content-type: application/json' --data-binary @- "
            + '"$endpoint/api/write" >/dev/null\n'
            + 'curl -fsS "$endpoint/api/read"\n',
            privileged=True,
        )
        try:
            readback = json.loads(output)
        except json.JSONDecodeError as error:
            raise GovernanceError("flagd UI write readback was malformed") from error
        if canonical_json(readback) != canonical_json(document):
            raise GovernanceError("flagd UI write readback drifted")


class LiveScenarioObserver:
    def __init__(self, candidate_sha: str, fault_class: str) -> None:
        self.candidate_sha = candidate_sha
        self.fault_class = fault_class
        self.baseline_cpu = 0.0
        self.baseline_lag = 0.0
        self.fault_started: datetime | None = None
        self.recovery_started: datetime | None = None
        self.fault_samples: list[dict[str, Any]] = []
        self.recovery_samples: list[dict[str, Any]] = []

    def _sample(self, since: datetime) -> dict[str, Any]:
        payload = base64.b64encode(
            json.dumps(
                {
                    "candidate_sha": self.candidate_sha,
                    "fault_class": self.fault_class,
                    "trace_service": TRACE_QUERY_SERVICES[self.fault_class],
                    "since_micros": int(since.timestamp() * 1_000_000),
                    "since_rfc3339": since.isoformat().replace("+00:00", "Z"),
                }
            ).encode()
        ).decode("ascii")
        script = f"""set -eu
python3 - <<'PY'
import base64
import json
import subprocess
import sys
import urllib.parse
import urllib.request

request = json.loads(base64.b64decode({payload!r}))

def kubectl(*args):
    return subprocess.run(
        ["/usr/local/bin/k3s", "kubectl", "-n", "fw-sut", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

binding = kubectl(
    "get", "configmap", "fw-g02-candidate-binding", "-o",
    "jsonpath={{.data.candidate_sha}}",
)
if binding != request["candidate_sha"]:
    raise SystemExit("candidate binding drift")

deployments = json.loads(kubectl("get", "deployment", "-o", "json"))["items"]
ready = all(
    item.get("status", {{}}).get("readyReplicas", 0) == item["spec"].get("replicas", 1)
    for item in deployments
)
frontend = json.loads(kubectl("get", "service", "frontend-proxy", "-o", "json"))
frontend_url = "http://" + frontend["spec"]["clusterIP"] + ":8080/"
try:
    journey_status = urllib.request.urlopen(frontend_url).status
except Exception:
    journey_status = 0

prometheus = json.loads(kubectl("get", "service", "prometheus", "-o", "json"))
prometheus_url = "http://" + prometheus["spec"]["clusterIP"] + ":9090/api/v1/query"

def promql(query):
    url = prometheus_url + "?" + urllib.parse.urlencode({{"query": query}})
    result = json.load(urllib.request.urlopen(url))["data"]["result"]
    return float(result[0]["value"][1]) if result else 0.0

cpu_rate = promql(
    'sum(rate(container_cpu_usage_seconds_total{{namespace="fw-sut",pod=~"ad-.*",container="ad"}}[2m]))'
)
working_set = promql(
    'max(container_memory_working_set_bytes{{namespace="fw-sut",pod=~"email-.*",container="email"}})'
)
consumer_record_lag = promql(
    'max(kafka_consumer_records_lag{{service_name="fraud-detection"}})'
)
consumer_poll_lag_seconds = promql(
    'max(kafka_consumer_last_poll_seconds_ago{{service_name="fraud-detection"}})'
)
consumer_lag = max(consumer_record_lag, consumer_poll_lag_seconds)

jaeger = json.loads(kubectl("get", "endpoints", "jaeger-query", "-o", "json"))
jaeger_ip = jaeger["subsets"][0]["addresses"][0]["ip"]
query = {{
    "service": request["trace_service"],
    "limit": "100",
    "start": str(request["since_micros"]),
    "lookback": "custom",
}}
url = "http://" + jaeger_ip + ":16686/jaeger/ui/api/traces?" + urllib.parse.urlencode(query)
traces = json.load(urllib.request.urlopen(url)).get("data") or []
descriptions = []
error_spans = 0
checkout_error_spans = 0
payment_connection_errors = 0
for trace in traces:
    processes = trace.get("processes", {{}})
    trace_has_checkout_error = False
    trace_has_payment_client_error = False
    trace_has_connection_error = False
    for span in trace.get("spans", []):
        tags = {{tag["key"]: tag.get("value") for tag in span.get("tags", [])}}
        is_error = tags.get("error") is True or tags.get("otel.status_code") == "ERROR"
        description = str(tags.get("otel.status_description", ""))
        service_name = processes.get(span.get("processID"), {{}}).get("serviceName")
        if is_error:
            error_spans += 1
            if (
                service_name == "checkout"
                and tags.get("rpc.service") == "oteldemo.CheckoutService"
                and tags.get("rpc.method") == "PlaceOrder"
            ):
                checkout_error_spans += 1
                trace_has_checkout_error = True
            if (
                service_name == "checkout"
                and tags.get("rpc.service") == "oteldemo.PaymentService"
                and tags.get("rpc.method") == "Charge"
            ):
                trace_has_payment_client_error = True
        if description:
            descriptions.append(description)
            lowered = description.lower()
            if any(token in lowered for token in (
                "connection refused", "connection error", "unavailable",
                "error while dialing", "connect:",
            )):
                trace_has_connection_error = True
    if (
        trace_has_checkout_error
        and trace_has_payment_client_error
        and trace_has_connection_error
    ):
        payment_connection_errors += 1

logs = kubectl(
    "logs", "deployment/fraud-detection", "--since-time=" + request["since_rfc3339"],
) if request["fault_class"] == "kafkaQueueProblems" else ""

now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
print(json.dumps({{
    "recorded_at": now,
    "ready": ready,
    "journey_status": journey_status,
    "cpu_rate": cpu_rate,
    "working_set": working_set,
    "consumer_lag": consumer_lag,
    "consumer_record_lag": consumer_record_lag,
    "consumer_poll_lag_seconds": consumer_poll_lag_seconds,
    "trace_count": len(traces),
    "error_spans": error_spans,
    "checkout_error_spans": checkout_error_spans,
    "payment_connection_errors": payment_connection_errors,
    "descriptions": descriptions,
    "kafka_log_error": "error" in logs.lower(),
    "kafka_fault_log": "FeatureFlag 'kafkaQueueProblems' is enabled, sleeping" in logs,
}}, sort_keys=True))
PY
"""
        output = run_remote_script(script, privileged=True)
        return json.loads(output)

    def _active_observation(self, sample: Mapping[str, Any]) -> dict[str, Any]:
        descriptions = "\n".join(str(item) for item in sample["descriptions"])
        if self.fault_class == "productCatalogFailure":
            found = "Product Catalog Fail Feature Flag Enabled" in descriptions
            return {**sample, "journey_failed": found, "correlated_error": found}
        if self.fault_class == "adHighCpu":
            return {
                **sample,
                "cpu_rate": sample["cpu_rate"],
                "baseline_cpu_max": self.baseline_cpu,
                "correlated_span": sample["trace_count"] > 0,
            }
        if self.fault_class == "emailMemoryLeak":
            return {**sample, "working_set": sample["working_set"]}
        if self.fault_class == "paymentFailure":
            found = "Payment" in descriptions and sample["error_spans"] > 0
            return {**sample, "checkout_failed": found, "payment_error": found}
        if self.fault_class == "paymentUnreachable":
            return {
                **sample,
                "checkout_failed": sample["checkout_error_spans"] > 0,
                "connection_error": sample["payment_connection_errors"] > 0,
            }
        if self.fault_class == "kafkaQueueProblems":
            return {
                **sample,
                "consumer_lag": sample["consumer_lag"],
                "baseline_lag": self.baseline_lag,
                "kafka_error": (
                    sample["kafka_log_error"]
                    or sample["kafka_fault_log"]
                    or sample["error_spans"] > 0
                ),
            }
        raise GovernanceError("unsupported live fault observer")

    def __call__(self, phase: str, fault_class: str) -> Observation:
        if fault_class != self.fault_class:
            raise GovernanceError("live observer fault class drifted")
        if phase == "control":
            sample = self._sample(datetime.now(UTC) - timedelta(minutes=2))
            self.baseline_cpu = float(sample["cpu_rate"])
            self.baseline_lag = float(sample["consumer_lag"])
            healthy = sample["ready"] and sample["journey_status"] == 200
            return {"state": OracleState.HEALTHY if healthy else OracleState.UNKNOWN}
        if phase == "fault":
            if self.fault_started is None:
                self.fault_started = datetime.now(UTC)
            elif self.fault_samples:
                time.sleep(30)
            deadline = time.monotonic() + 90
            while True:
                observation = self._active_observation(self._sample(self.fault_started))
                active = (
                    fault_state(fault_class, [observation, observation]) == OracleState.FAULT_ACTIVE
                )
                if active:
                    self.fault_samples.append(observation)
                    return observation
                if time.monotonic() >= deadline:
                    return observation
                time.sleep(5)
        if phase == "recovery":
            if self.recovery_started is None:
                self.recovery_started = datetime.now(UTC)
            elif self.recovery_samples:
                time.sleep(30)
            deadline = time.monotonic() + 90
            while True:
                sample = self._sample(self.recovery_started)
                signal_ok = True
                if self.fault_class == "adHighCpu":
                    signal_ok = float(sample["cpu_rate"]) <= max(
                        self.baseline_cpu, float(self.fault_samples[-1]["cpu_rate"])
                    )
                elif self.fault_class == "emailMemoryLeak":
                    signal_ok = float(sample["working_set"]) <= float(
                        self.fault_samples[-1]["working_set"]
                    )
                elif self.fault_class == "kafkaQueueProblems":
                    signal_ok = float(sample["consumer_lag"]) <= float(
                        self.fault_samples[-1]["consumer_lag"]
                    )
                observation = {
                    **sample,
                    "ready": bool(sample["ready"]),
                    "journey_healthy": sample["journey_status"] == 200,
                    "signal_not_worsening": signal_ok,
                }
                required = ("ready", "journey_healthy", "signal_not_worsening")
                if all(observation[key] for key in required):
                    self.recovery_samples.append(observation)
                    return observation
                if time.monotonic() >= deadline:
                    return observation
                time.sleep(5)
        raise GovernanceError("unknown live observer phase")


def _operation_root() -> Path:
    return InfraPaths.defaults().evidence_dir.parent.parent / "artifacts" / "I-0017" / "operations"


def _operation_path(operation_id: str) -> Path:
    if not re.fullmatch(r"op-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", operation_id):
        raise GovernanceError("invalid G02 fault operation ID")
    return _operation_root() / f"{operation_id}.json"


def inject_live_fault(candidate_sha: str, fault_class: str) -> dict[str, Any]:
    adapter = ADAPTERS.get(fault_class)
    if adapter is None:
        raise GovernanceError("G02 live injection uses an unknown fault class")
    client = RemoteFlagClient(candidate_sha)
    original = client.read()
    flags = original["flags"]
    if adapter.flag_key not in flags:
        raise GovernanceError("G02 live flag is absent from the candidate document")
    mutated = copy.deepcopy(original)
    mutated["flags"][adapter.flag_key]["defaultVariant"] = adapter.variant
    changed = [key for key in flags if original["flags"][key] != mutated["flags"][key]]
    if changed != [adapter.flag_key]:
        raise GovernanceError("G02 live injection must change exactly one allowlisted flag")
    timestamp = datetime.now(UTC)
    operation_id = (
        "op-"
        + timestamp.strftime("%Y%m%dT%H%M%SZ-")
        + hashlib.sha256(
            (candidate_sha + fault_class + canonical_json(original)).encode()
        ).hexdigest()[:12]
    )
    record = {
        "operation_id": operation_id,
        "candidate_sha": candidate_sha,
        "fault_class": fault_class,
        "flag_key": adapter.flag_key,
        "original": original,
        "original_digest": hashlib.sha256(canonical_json(original).encode()).hexdigest(),
        "injected_digest": hashlib.sha256(canonical_json(mutated).encode()).hexdigest(),
        "started_at": timestamp.isoformat(),
        "status": "prepared",
    }
    _write_json(_operation_path(operation_id), record)
    client.write(mutated)
    record["status"] = "injected"
    record["injected_at"] = datetime.now(UTC).isoformat()
    _write_json(_operation_path(operation_id), record)
    public_keys = (
        "operation_id",
        "fault_class",
        "original_digest",
        "injected_digest",
        "status",
    )
    return {key: record[key] for key in public_keys}


def restore_live_fault(candidate_sha: str, operation_id: str) -> dict[str, Any]:
    path = _operation_path(operation_id)
    if not path.is_file():
        raise GovernanceError("G02 fault operation record is missing")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("candidate_sha") != candidate_sha or record.get("status") != "injected":
        raise GovernanceError("G02 fault operation is not restorable on this candidate")
    client = RemoteFlagClient(candidate_sha)
    client.write(record["original"])
    restored = client.read()
    restored_digest = hashlib.sha256(canonical_json(restored).encode()).hexdigest()
    if restored_digest != record["original_digest"]:
        raise GovernanceError("G02 exact flag restoration failed")
    record["status"] = "restored"
    record["restored_at"] = datetime.now(UTC).isoformat()
    record["restored_digest"] = restored_digest
    _write_json(path, record)
    return {"operation_id": operation_id, "restored_digest": restored_digest, "status": "restored"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _slot_rows() -> list[tuple[str, str, str]]:
    standard = (
        ("easy-1", "Easy"),
        ("easy-2", "Easy"),
        ("medium-1", "Medium"),
        ("medium-2", "Medium"),
        ("hard-1", "Hard"),
        ("hard-2", "Hard"),
        ("ood", "OOD"),
        ("adversarial", "Adversarial"),
    )
    rows: list[tuple[str, str, str]] = []
    for slot, _difficulty_name in standard:
        rows.append(("change_config", slot, "productCatalogFailure"))
        rows.append(("runtime_data", slot, "kafkaQueueProblems"))
        resource_fault = "adHighCpu" if slot.endswith("-1") or slot == "ood" else "emailMemoryLeak"
        dependency_fault = (
            "paymentFailure" if slot.endswith("-1") or slot == "ood" else "paymentUnreachable"
        )
        rows.append(("resource_capacity", slot, resource_fault))
        rows.append(("dependency_network", slot, dependency_fault))
    return rows


def _difficulty(slot: str) -> str:
    return {
        "easy-1": "Easy",
        "easy-2": "Easy",
        "medium-1": "Medium",
        "medium-2": "Medium",
        "hard-1": "Hard",
        "hard-2": "Hard",
        "ood": "OOD",
        "adversarial": "Adversarial",
    }[slot]


def seed_catalog(image_set_digest: str) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-f]{64}", image_set_digest):
        raise GovernanceError("seed catalogue requires a complete image-set digest")
    ranked = sorted(
        _slot_rows(),
        key=lambda row: hashlib.sha256(
            (SEED_DOMAIN + canonical_json(row)).encode("utf-8")
        ).hexdigest(),
    )
    seeds: list[dict[str, Any]] = []
    for index, (family, slot, fault_class) in enumerate(ranked, 1):
        adapter = ADAPTERS[fault_class]
        seeds.append(
            {
                "schema_version": "1.0.0",
                "scenario_id": f"SEED-G02-{index:04d}",
                "family": family,
                "difficulty": _difficulty(slot),
                "sut_release": SUT_RELEASE,
                "sut_commit": SUT_COMMIT,
                "image_set_digest": image_set_digest,
                "problem_brief": (
                    f"Investigate the {_difficulty(slot).lower()} service incident using only the "
                    "provided canonical observation packet."
                ),
                "control_journey": "frontend-checkout",
                "fault_action": {
                    "class": fault_class,
                    "flag_key": adapter.flag_key,
                    "variant": adapter.variant,
                },
                "observation_contract": {
                    "required": list(adapter.required_fields),
                    "sample_count": 2,
                    "sample_interval_seconds": 30,
                    "deadline_seconds": 90,
                },
                "fault_oracle": fault_class,
                "recovery_oracle": "exact-flag-readback-and-healthy-journey",
                "ground_truth_ref": (
                    f"s3://faultwitness-eval/g02/ground-truth/SEED-G02-{index:04d}.json"
                ),
                "catalog_slot": slot,
            }
        )
    return seeds


def load_lab_config(root: Path) -> dict[str, Any]:
    path = root / "config" / "g02" / "lab.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise GovernanceError("G02 lab config must be an object")
    return document


def load_gate_probe_images(root: Path) -> dict[str, str]:
    path = root / "config" / "g02" / "gate-probes.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != "1.0.0":
        raise GovernanceError("G02 gate probe config must be a versioned object")
    images = document.get("images")
    if not isinstance(images, dict) or set(images) != set(PROBE_IMAGE_NAMES):
        raise GovernanceError("G02 gate probe config must declare exactly busybox and minio_mc")
    normalized: dict[str, str] = {}
    for name in PROBE_IMAGE_NAMES:
        reference = images.get(name)
        if not isinstance(reference, str) or not FULL_DIGEST_REFERENCE.fullmatch(reference):
            raise GovernanceError(f"G02 probe image is not digest-pinned: {reference}")
        if not containerd_normalized_reference(reference).startswith("docker.io/"):
            raise GovernanceError(f"G02 probe image is outside the frozen Docker Hub path: {name}")
        normalized[name] = reference
    return normalized


def build_offline_staging_inventory(
    config: Mapping[str, Any], probe_images: Mapping[str, str]
) -> dict[str, str]:
    """Build one digest-safe Docker Hub inventory without changing the SUT image set."""
    images = config.get("images")
    if not isinstance(images, list) or not images:
        raise GovernanceError("G02 lab image set is empty")
    if set(probe_images) != set(PROBE_IMAGE_NAMES):
        raise GovernanceError("G02 staging requires exactly the two frozen probe images")

    candidates: list[tuple[str, str]] = []
    for item in images:
        if not isinstance(item, dict):
            raise GovernanceError("G02 lab image entry must be an object")
        name = item.get("name")
        reference = item.get("reference")
        if not isinstance(name, str) or not name or not isinstance(reference, str):
            raise GovernanceError("G02 lab staging image lacks a name or reference")
        if containerd_normalized_reference(reference).startswith("docker.io/"):
            candidates.append((name, reference))
    candidates.extend(
        (f"probe-{name.replace('_', '-')}", str(probe_images[name]))
        for name in PROBE_IMAGE_NAMES
    )

    inventory: dict[str, str] = {}
    key_to_normalized: dict[str, str] = {}
    normalized_to_key: dict[str, str] = {}
    repository_digests: dict[str, str] = {}
    for key, reference in candidates:
        if not FULL_DIGEST_REFERENCE.fullmatch(reference):
            raise GovernanceError(f"G02 staging image is not digest-pinned: {reference}")
        normalized = containerd_normalized_reference(reference)
        if not normalized.startswith("docker.io/"):
            raise GovernanceError(f"G02 staging image is outside Docker Hub: {reference}")
        repository, digest = normalized.rsplit("@", 1)
        prior_digest = repository_digests.get(repository)
        if prior_digest is not None and prior_digest != digest:
            raise GovernanceError(f"G02 staging image digest drift for {repository}")
        repository_digests[repository] = digest

        prior_for_key = key_to_normalized.get(key)
        if prior_for_key is not None and prior_for_key != normalized:
            raise GovernanceError(f"G02 staging archive key collision: {key}")
        if normalized in normalized_to_key:
            continue
        inventory[key] = reference
        key_to_normalized[key] = normalized
        normalized_to_key[normalized] = key
    return inventory


def offline_staging_inventory(root: Path, config: Mapping[str, Any]) -> dict[str, str]:
    return build_offline_staging_inventory(config, load_gate_probe_images(root))


def image_set_digest(config: Mapping[str, Any]) -> str:
    images = config.get("images")
    if not isinstance(images, list) or not images:
        raise GovernanceError("G02 lab image set is empty")
    normalized: list[dict[str, str]] = []
    for image in images:
        if not isinstance(image, dict):
            raise GovernanceError("G02 lab image entry must be an object")
        reference = image.get("reference")
        if image.get("platform") != "linux/amd64" or not isinstance(reference, str):
            raise GovernanceError("G02 lab images must declare linux/amd64 references")
        if not FULL_DIGEST_REFERENCE.fullmatch(reference):
            raise GovernanceError(f"G02 lab image is not digest-pinned: {reference}")
        normalized.append({"name": str(image.get("name")), "reference": reference})
    canonical = canonical_json(sorted(normalized, key=lambda item: item["name"]))
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_lab_bootstrap(config: Mapping[str, Any]) -> dict[str, Any]:
    if config.get("sut_release") != SUT_RELEASE or config.get("sut_commit") != SUT_COMMIT:
        raise GovernanceError("G02 lab SUT release or commit drifted")
    if config.get("profile") not in {"k3s", "docker-compose-minimal"}:
        raise GovernanceError("G02 lab profile is not frozen")
    source = config.get("source")
    if not isinstance(source, dict) or not re.fullmatch(
        r"[0-9a-f]{64}", str(source.get("sha256", ""))
    ):
        raise GovernanceError("G02 lab source lacks a frozen digest")
    digest = image_set_digest(config)
    names = {str(item["name"]) for item in config["images"]}
    missing = sorted(set(K8S_SOURCE_IMAGES).difference(names))
    if missing:
        raise GovernanceError("G02 lab image set lacks source replacements: " + ", ".join(missing))
    return {
        "status": "pass",
        "profile": config["profile"],
        "sut_commit": SUT_COMMIT,
        "image_count": len(config["images"]),
        "image_set_digest": digest,
    }


def render_k3s_bootstrap_script(config: Mapping[str, Any], candidate_sha: str) -> str:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("G02 lab candidate must be a full Git SHA")
    validation = validate_lab_bootstrap(config)
    if validation["profile"] != "k3s":
        raise GovernanceError("K3s bootstrap runner cannot execute the fallback profile")
    source = config["source"]
    by_name = {str(item["name"]): str(item["reference"]) for item in config["images"]}
    replacements: list[tuple[str, str]] = []
    for name, source_references in K8S_SOURCE_IMAGES.items():
        target = by_name[name]
        for source_reference in source_references:
            replacements.append((source_reference, target))
    image_map = dict(replacements)
    encoded_image_map = base64.b64encode(canonical_json(image_map).encode()).decode()
    workspace = f"/tmp/faultwitness-g02-{candidate_sha[:12]}"
    return f"""set -eu
workspace={shlex.quote(workspace)}
manifest="$workspace/opentelemetry-demo.yaml"
test -f "$manifest"
printf '%s  %s\n' {shlex.quote(str(source["sha256"]))} "$manifest" | sha256sum -c -
sed -i 's|namespace: otel-demo|namespace: fw-sut|g; s|name: otel-demo|name: fw-sut|g' "$manifest"
python3 - "$manifest" <<'PY'
import base64
import json
import sys

path = sys.argv[1]
mapping = json.loads(base64.b64decode("{encoded_image_map}"))
output = []
with open(path, encoding="utf-8") as source_file:
    for line in source_file:
        if line.lstrip().startswith("image:"):
            indent, raw = line.split("image:", 1)
            value = raw.strip()
            quote = value[0] if value[:1] in {{"'", '"'}} else ""
            reference = value[1:-1] if quote and value.endswith(quote) else value
            if reference in mapping:
                line = f"{{indent}}image: {{quote}}{{mapping[reference]}}{{quote}}\\n"
        output.append(line)
text = "".join(output)
if '"emailMemoryLeak"' not in text:
    needle = '      "flags": {{\\n        "productCatalogFailure": {{'
    email_flag = '''      "flags": {{
        "emailMemoryLeak": {{
          "description": "Memory leak in the email service.",
          "state": "ENABLED",
          "variants": {{
            "off": 0,
            "1x": 1,
            "10x": 10,
            "100x": 100,
            "1000x": 1000,
            "10000x": 10000
          }},
          "defaultVariant": "off"
        }},
        "productCatalogFailure": {{'''
    if text.count(needle) != 1:
        raise SystemExit("FW_G02_EMAIL_FLAG_ANCHOR_DRIFT")
    text = text.replace(needle, email_flag)
with open(path, "w", encoding="utf-8", newline="\\n") as target_file:
    target_file.write(text)
PY
if grep -E '^[[:space:]]*image:[[:space:]]*' "$manifest" | grep -v '@sha256:'; then
  echo FW_G02_UNPINNED_IMAGE >&2
  exit 41
fi
/usr/local/bin/k3s kubectl apply -n fw-sut -f "$manifest"
if ! /usr/local/bin/k3s kubectl -n fw-sut exec deployment/flagd -c flagd-ui -- \
  grep -q '"emailMemoryLeak"' /app/data/demo.flagd.json; then
  /usr/local/bin/k3s kubectl -n fw-sut rollout restart deployment/flagd
fi
/usr/local/bin/k3s kubectl -n fw-sut create configmap fw-g02-candidate-binding \
  --from-literal=candidate_sha={candidate_sha} \
  --from-literal=image_set_digest={validation["image_set_digest"]} \
  --from-literal=sut_commit={SUT_COMMIT} \
  --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -
while true; do
  pending=$(/usr/local/bin/k3s kubectl -n fw-sut get deployment -o json | python3 -c '
import json
import sys

items = json.load(sys.stdin)["items"]
for item in items:
    desired = item["spec"].get("replicas", 1)
    status = item.get("status", {{}})
    if not (
        status.get("observedGeneration", 0) >= item["metadata"]["generation"]
        and status.get("updatedReplicas", 0) == desired
        and status.get("readyReplicas", 0) == desired
        and status.get("availableReplicas", 0) == desired
    ):
        print(item["metadata"]["name"])
')
  test -z "$pending" && break
  printf 'waiting for Deployments: %s\n' "$pending" >&2
  sleep 5
done
while true; do
  pending=$(/usr/local/bin/k3s kubectl -n fw-sut get statefulset opensearch -o json | python3 -c '
import json
import sys

item = json.load(sys.stdin)
desired = item["spec"].get("replicas", 1)
status = item.get("status", {{}})
ready = (
    status.get("observedGeneration", 0) >= item["metadata"]["generation"]
    and status.get("updatedReplicas", 0) == desired
    and status.get("readyReplicas", 0) == desired
    and status.get("currentRevision") == status.get("updateRevision")
)
print("" if ready else item["metadata"]["name"])
')
  test -z "$pending" && break
  printf 'waiting for StatefulSet: %s\n' "$pending" >&2
  sleep 5
done
binding=$(/usr/local/bin/k3s kubectl -n fw-sut \
  get configmap fw-g02-candidate-binding \
  -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
ready=$(/usr/local/bin/k3s kubectl -n fw-sut get deployment \
  -o jsonpath='{{range .items[*]}}{{.metadata.name}}={{.status.readyReplicas}}{{"\\n"}}{{end}}')
printf 'candidate_sha=%s\nimage_set_digest=%s\n%s' \
  "$binding" {validation["image_set_digest"]} "$ready"
"""


def _stage_lab_manifest(config: Mapping[str, Any], candidate_sha: str) -> None:
    source = config["source"]
    with urllib.request.urlopen(str(source["uri"])) as response:  # noqa: S310
        payload = response.read()
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != source["sha256"]:
        raise GovernanceError("G02 upstream manifest digest drifted on the owner host")
    appdata = Path.home() / "AppData" / "Local"
    cache = appdata / "FaultWitness" / "artifacts" / "I-0017" / "opentelemetry-demo.yaml"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(payload)

    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    remote_name = f"fw-g02-manifest-{candidate_sha[:12]}.yaml"
    common = [
        "-P",
        str(bundle.server_port),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={paths.known_hosts_file}",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(paths.ssh_private_key),
    ]
    result = subprocess.run(
        [
            "scp",
            *common,
            str(cache),
            f"{bundle.server_username}@{bundle.server_host}:{remote_name}",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise GovernanceError(
            "G02 manifest staging failed (" + ssh_failure_category(result.stderr) + ")"
        )
    workspace = f"/tmp/faultwitness-g02-{candidate_sha[:12]}"
    owner = shlex.quote(bundle.server_username)
    run_remote_script(
        f"remote_home=$(getent passwd {owner} | cut -d: -f6); "
        f'test -n "$remote_home"; '
        f"install -d -m 0700 -o {owner} -g $(id -gn {owner}) {workspace}; "
        f"install -m 0600 -o {owner} -g $(id -gn {owner}) "
        f'"$remote_home/{remote_name}" {workspace}/opentelemetry-demo.yaml; '
        f'rm -f "$remote_home/{remote_name}"\n',
        privileged=True,
    )


def _stage_lab_images(root: Path, config: Mapping[str, Any], candidate_sha: str) -> None:
    images = offline_staging_inventory(root, config)
    crane = _ensure_crane(root)
    private_root = InfraPaths.defaults().evidence_dir.parent.parent
    archive_root = private_root / "artifacts" / "I-0017" / "images"
    archives = {name: archive_root / f"{name}.oci.tar" for name in images}
    for name, image in images.items():
        _pull_oci_image_archive(crane, image, archives[name])
    archive_digests = {name: _file_sha256(path) for name, path in archives.items()}
    remote_names = {name: f"{name}-{archive_digests[name]}.oci.tar" for name in archives}

    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    remote_root = "/tmp/faultwitness-g02-images"
    owner = shlex.quote(bundle.server_username)
    migration_script = (
        f'group=$(id -gn {owner}); install -d -m 0700 -o {owner} -g "$group" {remote_root}\n'
    )
    for name, remote_name in remote_names.items():
        expected = shlex.quote(archive_digests[name])
        target = f"{remote_root}/{remote_name}"
        migration_script += (
            f"if ! test -f {target}; then\n"
            f"  for candidate in /tmp/faultwitness-g02-images-*/{name}.tar; do\n"
            '    test -f "$candidate" || continue\n'
            f'    test "$(sha256sum "$candidate" | cut -d" " -f1)" = {expected} || continue\n'
            f'    ln "$candidate" {target} 2>/dev/null || cp "$candidate" {target}\n'
            f'    chown {owner}:"$group" {target}; chmod 0600 {target}; break\n'
            "  done\n"
            "fi\n"
        )
    run_remote_script(migration_script, privileged=True)
    inventory = run_remote_script(
        "\n".join(
            f'test -f {remote_root}/{remote_name} && printf "{name}=%s\\n" '
            f'"$(stat -c %s {remote_root}/{remote_name})" || true'
            for name, remote_name in remote_names.items()
        )
        + "\n",
        privileged=True,
    )
    remote_sizes = {
        name: int(size)
        for name, size in (line.split("=", 1) for line in inventory.splitlines() if "=" in line)
    }
    common = [
        "-P",
        str(bundle.server_port),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={paths.known_hosts_file}",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(paths.ssh_private_key),
    ]
    for name, archive in archives.items():
        if remote_sizes.get(name) == archive.stat().st_size:
            continue
        remote_name = remote_names[name]
        result = subprocess.run(
            [
                "scp",
                *common,
                str(archive),
                f"{bundle.server_username}@{bundle.server_host}:{remote_root}/{remote_name}",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode:
            raise GovernanceError(
                "G02 offline image staging failed (" + ssh_failure_category(result.stderr) + ")"
            )
    import_script = "set -eu\n" + "\n".join(
        f"/usr/local/bin/k3s ctr images import {remote_root}/{remote_names[name]}"
        for name in remote_names
    )
    for reference in images.values():
        normalized = containerd_normalized_reference(reference)
        expected_digest = reference.rsplit("@", 1)[1]
        target = shlex.quote(normalized)
        digest = shlex.quote(expected_digest)
        candidates = " ".join(
            shlex.quote(candidate) for candidate in containerd_registry_aliases(reference)
        )
        import_script += (
            "\nsource_ref=\n"
            f"for candidate_ref in {candidates}; do\n"
            "  observed_digest=$(/usr/local/bin/k3s ctr images list | "
            "awk -v ref=\"$candidate_ref\" '$1 == ref {print $3; exit}')\n"
            f'  if test "$observed_digest" = {digest}; then '
            'source_ref="$candidate_ref"; break; fi\n'
            "done\n"
            'test -n "$source_ref"\n'
            f'if test "$source_ref" != {target}; then\n'
            f"  /usr/local/bin/k3s ctr images tag --force \"$source_ref\" {target}\n"
            "fi\n"
            f'test "$(/usr/local/bin/k3s ctr images list | '
            f"awk -v ref={target} '$1 == ref {{print $3; exit}}')\" = {digest}"
        )
    run_remote_script(import_script, privileged=True)


def containerd_normalized_reference(reference: str) -> str:
    prefix = "index.docker.io/"
    if not reference.startswith(prefix):
        return reference
    return "docker.io/" + reference.removeprefix(prefix)


def containerd_registry_aliases(reference: str) -> tuple[str, ...]:
    if not FULL_DIGEST_REFERENCE.fullmatch(reference):
        raise GovernanceError(f"containerd source reference is not digest-pinned: {reference}")
    docker_prefix = "docker.io/"
    index_prefix = "index.docker.io/"
    if reference.startswith(docker_prefix):
        return (reference, index_prefix + reference.removeprefix(docker_prefix))
    if reference.startswith(index_prefix):
        return (reference, docker_prefix + reference.removeprefix(index_prefix))
    return (reference,)


def select_containerd_import_source(
    reference: str, inventory: Mapping[str, str]
) -> str:
    candidates = containerd_registry_aliases(reference)
    expected_digest = reference.rsplit("@", 1)[1]
    for candidate in candidates:
        if inventory.get(candidate) == expected_digest:
            return candidate
    raise GovernanceError(
        "containerd import lacks an exact repository-and-digest source for " + reference
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _pull_oci_image_archive(crane: Path, image: str, destination: Path) -> None:
    marker = destination.with_suffix(".json")
    if destination.is_file() and marker.is_file():
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
        if (
            metadata.get("image") == image
            and metadata.get("format") == "oci"
            and metadata.get("tar_sha256") == _file_sha256(destination)
        ):
            return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = destination.with_suffix(".download")
    with tempfile.TemporaryDirectory(prefix="fw-g02-oci-") as temporary:
        layout = Path(temporary) / "layout"
        result = subprocess.run(
            [
                str(crane),
                "pull",
                "--platform",
                "linux/amd64",
                "--format",
                "oci",
                "--annotate-ref",
                image,
                str(layout),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode:
            raise GovernanceError("pinned G02 OCI image pull failed")
        with tarfile.open(temporary_archive, mode="w") as archive:
            for path in sorted(layout.rglob("*")):
                archive.add(path, arcname=path.relative_to(layout).as_posix(), recursive=False)
    temporary_archive.replace(destination)
    marker.write_text(
        json.dumps(
            {
                "format": "oci",
                "image": image,
                "tar_sha256": _file_sha256(destination),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _validate_lab_checkout(
    root: Path, candidate_sha: str, evidence_head_sha: str | None = None
) -> str:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("G02 lab candidate must be a full Git SHA")
    expected_head = evidence_head_sha or candidate_sha
    if not FULL_SHA.fullmatch(expected_head):
        raise GovernanceError("G02 lab evidence head must be a full Git SHA")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if head != expected_head:
        raise GovernanceError("G02 lab checkout must equal the validated evidence head")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, expected_head],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        raise GovernanceError("G02 lab evidence head is not a candidate descendant")
    return expected_head


def deploy_g02_lab(
    root: Path, candidate_sha: str, evidence_head_sha: str | None = None
) -> dict[str, Any]:
    _validate_lab_checkout(root, candidate_sha, evidence_head_sha)
    if subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True).stdout:
        raise GovernanceError("G02 lab deployment requires a clean candidate worktree")
    config = load_lab_config(root)
    validation = validate_lab_bootstrap(config)
    _stage_lab_manifest(config, candidate_sha)
    _stage_lab_images(root, config, candidate_sha)
    output = run_remote_script(render_k3s_bootstrap_script(config, candidate_sha), privileged=True)
    ready = {
        key: int(value or "0")
        for key, value in (
            line.split("=", 1)
            for line in output.splitlines()
            if "=" in line and not line.startswith(("candidate_sha=", "image_set_digest="))
        )
    }
    if not ready or any(count < 1 for count in ready.values()):
        raise GovernanceError("G02 lab bootstrap completed without all deployments ready")
    return {
        **validation,
        "candidate_sha": candidate_sha,
        "namespace": "fw-sut",
        "ready_deployments": ready,
    }


def validate_seed_catalog(seeds: Sequence[Mapping[str, Any]], expected_digest: str) -> None:
    if len(seeds) != 32:
        raise GovernanceError("G02 seed catalogue must contain exactly 32 scenarios")
    if [seed.get("scenario_id") for seed in seeds] != [
        f"SEED-G02-{index:04d}" for index in range(1, 33)
    ]:
        raise GovernanceError("G02 seed IDs are not the complete opaque sequence")
    required = {
        "schema_version",
        "scenario_id",
        "family",
        "difficulty",
        "sut_release",
        "sut_commit",
        "image_set_digest",
        "problem_brief",
        "control_journey",
        "fault_action",
        "observation_contract",
        "fault_oracle",
        "recovery_oracle",
        "ground_truth_ref",
        "catalog_slot",
    }
    for seed in seeds:
        missing = required.difference(seed)
        if missing:
            raise GovernanceError(f"G02 scenario lacks fields: {sorted(missing)}")
        fault_action = seed["fault_action"]
        fault_class = fault_action.get("class") if isinstance(fault_action, dict) else None
        adapter = ADAPTERS.get(str(fault_class))
        if adapter is None:
            raise GovernanceError(f"G02 scenario uses unknown fault action: {fault_class}")
        if seed["family"] != adapter.family or fault_action.get("flag_key") != adapter.flag_key:
            raise GovernanceError("G02 scenario family or flag mapping drifted")
        if fault_action.get("variant") != adapter.variant:
            raise GovernanceError("G02 scenario injection variant drifted")
        if seed["image_set_digest"] != expected_digest:
            raise GovernanceError("G02 scenario image-set digest drifted")
    counts = {(family, difficulty): 0 for family in FAMILIES for difficulty in DIFFICULTIES}
    for seed in seeds:
        counts[(str(seed["family"]), str(seed["difficulty"]))] += 1
    if set(counts.values()) != {1, 2}:
        raise GovernanceError("G02 family/difficulty allocation drifted")
    for family in FAMILIES:
        if sum(count for (item_family, _), count in counts.items() if item_family == family) != 8:
            raise GovernanceError(f"G02 family does not contain eight seeds: {family}")


def fault_state(fault_class: str, observations: Sequence[Observation]) -> OracleState:
    if len(observations) != 2:
        return OracleState.UNKNOWN
    adapter = ADAPTERS.get(fault_class)
    if adapter is None or any(
        field not in item for item in observations for field in adapter.required_fields
    ):
        return OracleState.UNKNOWN
    first, second = observations
    active = False
    if fault_class == "productCatalogFailure":
        active = all(item["journey_failed"] and item["correlated_error"] for item in observations)
    elif fault_class == "adHighCpu":
        active = all(
            item["cpu_rate"] > item["baseline_cpu_max"] and item["correlated_span"]
            for item in observations
        )
    elif fault_class == "emailMemoryLeak":
        active = first["working_set"] < second["working_set"]
    elif fault_class == "paymentFailure":
        active = all(item["checkout_failed"] and item["payment_error"] for item in observations)
    elif fault_class == "paymentUnreachable":
        active = all(item["checkout_failed"] and item["connection_error"] for item in observations)
    elif fault_class == "kafkaQueueProblems":
        active = all(
            item["consumer_lag"] > item["baseline_lag"] and item["kafka_error"]
            for item in observations
        )
    return OracleState.FAULT_ACTIVE if active else OracleState.HEALTHY


def recovery_state(observations: Sequence[Observation]) -> OracleState:
    if len(observations) != 2:
        return OracleState.UNKNOWN
    required = ("ready", "journey_healthy", "signal_not_worsening")
    if any(field not in item for item in observations for field in required):
        return OracleState.UNKNOWN
    return (
        OracleState.HEALTHY
        if all(all(bool(item[field]) for field in required) for item in observations)
        else OracleState.FAULT_ACTIVE
    )


def _mutated_document(original: Mapping[str, Any], adapter: FaultAdapter) -> dict[str, Any]:
    document = copy.deepcopy(dict(original))
    flags = document.get("flags")
    if not isinstance(flags, dict) or adapter.flag_key not in flags:
        raise GovernanceError(f"flag document lacks allowlisted key: {adapter.flag_key}")
    flag = flags[adapter.flag_key]
    if not isinstance(flag, dict) or adapter.variant not in flag.get("variants", {}):
        raise GovernanceError("flag document lacks the frozen injection variant")
    flag["defaultVariant"] = adapter.variant
    changed = [key for key in flags if flags[key] != original["flags"][key]]
    if changed != [adapter.flag_key]:
        raise GovernanceError("scenario mutation changed more than one flag")
    return document


def run_scenario(
    scenario: Mapping[str, Any],
    client: FlagDocumentClient,
    observer: Observer,
    *,
    precondition_recovery: Sequence[Observation] | None = None,
) -> dict[str, Any]:
    action = scenario.get("fault_action")
    fault_class = action.get("class") if isinstance(action, dict) else None
    adapter = ADAPTERS.get(str(fault_class))
    if adapter is None:
        raise GovernanceError(f"scenario uses unknown fault action: {fault_class}")
    original = client.read()
    if precondition_recovery is None:
        if observer("control", fault_class).get("state") != OracleState.HEALTHY:
            raise GovernanceError("scenario healthy precondition is not proven")
        precondition_source = "control-observation"
    else:
        if recovery_state(precondition_recovery) != OracleState.HEALTHY:
            raise GovernanceError("prior scenario recovery does not prove a healthy precondition")
        precondition_source = "prior-scenario-recovery"
    fault_observations: list[Observation] = []
    recovery_observations: list[Observation] = []
    cleanup_error: Exception | None = None
    try:
        injected = _mutated_document(original, adapter)
        client.write(injected)
        if client.read() != injected:
            raise GovernanceError("fault injection readback mismatch")
        fault_observations = [observer("fault", fault_class), observer("fault", fault_class)]
        if fault_state(str(fault_class), fault_observations) != OracleState.FAULT_ACTIVE:
            raise GovernanceError("fault oracle did not reach FAULT_ACTIVE")
    finally:
        try:
            client.write(original)
            if client.read() != original:
                raise GovernanceError("exact flag restoration readback mismatch")
            recovery_observations = [
                observer("recovery", str(fault_class)),
                observer("recovery", str(fault_class)),
            ]
            if recovery_state(recovery_observations) != OracleState.HEALTHY:
                raise GovernanceError("recovery oracle did not reach HEALTHY")
        except Exception as error:  # cleanup must dominate the primary trial result
            cleanup_error = error
    if cleanup_error is not None:
        raise GovernanceError(f"scenario cleanup blocked and quarantined the SUT: {cleanup_error}")
    return {
        "scenario_id": scenario["scenario_id"],
        "family": scenario["family"],
        "fault_class": fault_class,
        "precondition_source": precondition_source,
        "state_sequence": ["HEALTHY", "FAULT_ACTIVE", "HEALTHY"],
        "original_digest": hashlib.sha256(canonical_json(original).encode()).hexdigest(),
        "restored_digest": hashlib.sha256(canonical_json(client.read()).encode()).hexdigest(),
        "fault_observations": fault_observations,
        "recovery_observations": recovery_observations,
    }


def run_gate_scenario_matrix(
    root: Path,
    candidate_sha: str,
    journal: TrialJournalProtocol,
    *,
    client_factory: Callable[[str], FlagDocumentClient] = RemoteFlagClient,
    observer_factory: Callable[[str, str], Observer] = LiveScenarioObserver,
) -> dict[str, Any]:
    """Execute the frozen 32-seed Gate matrix with trial-local continuation."""
    config = load_lab_config(root)
    bootstrap = validate_lab_bootstrap(config)
    seeds = seed_catalog(bootstrap["image_set_digest"])
    validate_seed_catalog(seeds, bootstrap["image_set_digest"])
    completed: list[dict[str, Any]] = []
    packets: list[dict[str, Any]] = []
    precondition_recovery: Sequence[Observation] | None = None
    from faultwitness_dev.g02_baselines import build_observation_packet

    for scenario in seeds:
        trial_id = f"g02-scenario-{candidate_sha}-{scenario['scenario_id'].casefold()}"
        previous = journal.read(trial_id)
        if previous and previous.get("status") == "pass":
            payload = dict(previous["payload"])
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(
                result.get("recovery_observations"), list
            ):
                raise GovernanceError("passed scenario trial lacks recovery evidence")
            precondition_recovery = result["recovery_observations"]
            if recovery_state(precondition_recovery) != OracleState.HEALTHY:
                raise GovernanceError("passed scenario trial has unhealthy recovery evidence")
            completed.append(previous)
            packets.append(dict(payload["observation_packet"]))
            continue
        journal.write(
            trial_id,
            "running",
            {
                "scenario_id": scenario["scenario_id"],
                "fault_class": scenario["fault_action"]["class"],
            },
        )
        try:
            result = run_scenario(
                scenario,
                client_factory(candidate_sha),
                observer_factory(candidate_sha, str(scenario["fault_action"]["class"])),
                precondition_recovery=precondition_recovery,
            )
            packet = build_observation_packet(scenario, result["fault_observations"])
            record = journal.write(
                trial_id,
                "pass",
                {
                    "scenario_id": scenario["scenario_id"],
                    "fault_class": scenario["fault_action"]["class"],
                    "result": result,
                    "observation_packet": packet,
                },
            )
        except GovernanceError as exc:
            record = journal.write(
                trial_id,
                "metric_fail",
                {
                    "scenario_id": scenario["scenario_id"],
                    "fault_class": scenario["fault_action"]["class"],
                    "reason": str(exc),
                },
            )
            return {
                "status": "metric_fail",
                "validation": "V-G02-006",
                "scenario_count": len(completed),
                "failed_trial": trial_id,
                "trials": [*completed, record],
            }
        completed.append(record)
        packets.append(packet)
        precondition_recovery = result["recovery_observations"]
    if len(completed) != 32 or len(packets) != 32:
        raise GovernanceError("G02 Gate scenario matrix did not complete exactly 32 seeds")
    return {
        "status": "pass",
        "validation": "V-G02-006",
        "scenario_count": 32,
        "trials": completed,
        "observation_packets": packets,
    }


class MemoryFlagClient:
    def __init__(self, document: Mapping[str, Any], *, ignore_restore: bool = False) -> None:
        self.document = copy.deepcopy(dict(document))
        self.initial = copy.deepcopy(dict(document))
        self.ignore_restore = ignore_restore

    def read(self) -> dict[str, Any]:
        return copy.deepcopy(self.document)

    def write(self, document: Mapping[str, Any]) -> None:
        if self.ignore_restore and dict(document) == self.initial and self.document != self.initial:
            return
        self.document = copy.deepcopy(dict(document))


def base_flag_document() -> dict[str, Any]:
    variants = {
        "productCatalogFailure": {"off": False, "on": True},
        "adHighCpu": {"off": False, "on": True},
        "emailMemoryLeak": {"off": 0, "100x": 100},
        "paymentFailure": {"off": 0, "100%": 1},
        "paymentUnreachable": {"off": False, "on": True},
        "kafkaQueueProblems": {"off": 0, "on": 100},
    }
    return {
        "$schema": "https://flagd.dev/schema/v0/flags.json",
        "flags": {
            key: {
                "defaultVariant": "off",
                "description": f"G02 adapter contract for {key}",
                "state": "ENABLED",
                "variants": value,
            }
            for key, value in variants.items()
        },
    }


def scripted_observer(phase: str, fault_class: str) -> Observation:
    if phase == "control":
        return {"state": OracleState.HEALTHY}
    if phase == "recovery":
        return {"ready": True, "journey_healthy": True, "signal_not_worsening": True}
    return {
        "productCatalogFailure": {"journey_failed": True, "correlated_error": True},
        "adHighCpu": {"cpu_rate": 2.0, "baseline_cpu_max": 1.0, "correlated_span": True},
        "emailMemoryLeak": {"working_set": 2.0},
        "paymentFailure": {"checkout_failed": True, "payment_error": True},
        "paymentUnreachable": {"checkout_failed": True, "connection_error": True},
        "kafkaQueueProblems": {"consumer_lag": 2.0, "baseline_lag": 1.0, "kafka_error": True},
    }[fault_class]


def scripted_sequence_observer() -> Observer:
    memory_samples = iter((2.0, 3.0))

    def observe(phase: str, fault_class: str) -> Observation:
        if phase == "fault" and fault_class == "emailMemoryLeak":
            return {"working_set": next(memory_samples)}
        return scripted_observer(phase, fault_class)

    return observe


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate_i0017(root: Path, candidate_sha: str) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if head != candidate_sha:
        raise GovernanceError("EVAL-G02-002 candidate SHA must equal checked-out HEAD")
    if subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True).stdout:
        raise GovernanceError("EVAL-G02-002 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0017.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != "I-0017"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-002 requires I-0017 as the sole active Iteration")

    started_at = datetime.now(UTC).isoformat()
    config = load_lab_config(root)
    bootstrap = validate_lab_bootstrap(config)
    seeds = seed_catalog(bootstrap["image_set_digest"])
    validate_seed_catalog(seeds, bootstrap["image_set_digest"])

    by_fault = {seed["fault_action"]["class"]: seed for seed in seeds}
    adapter_results: list[dict[str, Any]] = []
    for fault_class in ADAPTERS:
        result = run_scenario(
            by_fault[fault_class],
            MemoryFlagClient(base_flag_document()),
            scripted_sequence_observer(),
        )
        adapter_results.append(result)

    smoke_faults = {
        "change_config": "productCatalogFailure",
        "resource_capacity": "adHighCpu",
        "dependency_network": "paymentFailure",
        "runtime_data": "kafkaQueueProblems",
    }
    smoke_results: list[dict[str, Any]] = []
    for family, fault_class in smoke_faults.items():
        scenario = copy.deepcopy(by_fault[fault_class])
        scenario["scenario_id"] = "SMOKE-G02-" + family.upper().replace("_", "-")
        result = run_scenario(
            scenario,
            RemoteFlagClient(candidate_sha),
            LiveScenarioObserver(candidate_sha, fault_class),
        )
        smoke_results.append(result)

    artifact_dir = root / "docs" / "evals" / "EVAL-G02-002" / "artifacts"
    _write_json(
        artifact_dir / "seed-registry.json",
        {
            "schema_version": "1.0.0",
            "candidate_sha": candidate_sha,
            "validation": "V-G02-004",
            "iteration_n": 32,
            "image_set_digest": bootstrap["image_set_digest"],
            "seeds": seeds,
            "status": "pass",
        },
    )
    _write_json(
        artifact_dir / "fault-oracle-contract.json",
        {
            "schema_version": "1.0.0",
            "candidate_sha": candidate_sha,
            "validation": "V-G02-005",
            "iteration_n": 6,
            "adapters": adapter_results,
            "status": "pass",
        },
    )
    _write_json(
        artifact_dir / "scenario-smoke.json",
        {
            "schema_version": "1.0.0",
            "candidate_sha": candidate_sha,
            "validation": "V-G02-006",
            "iteration_n": 4,
            "environment": "private-k3s-live",
            "scenarios": smoke_results,
            "owned_gate_runners": ["g02.lab_bootstrap", "g02.scenario_matrix"],
            "start_time": started_at,
            "end_time": datetime.now(UTC).isoformat(),
            "status": "pass",
            "open_evidence": [],
        },
    )
    return {
        "eval_id": "EVAL-G02-002",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {
            "seed_registry": "pass",
            "fault_oracle_contract": "pass",
            "scenario_smoke": "pass",
            "lab_bootstrap_runner": "pass",
        },
        "open_evidence": [],
    }
