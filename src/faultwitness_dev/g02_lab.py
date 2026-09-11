from __future__ import annotations

import base64
import copy
import hashlib
import inspect
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
from faultwitness_dev.errors import GovernanceError, InfrastructureFailure
from faultwitness_dev.experiment import semantic_cache_key
from faultwitness_dev.infra import (
    InfraPaths,
    _ensure_crane,
    _remote_arguments,
    run_remote_script,
)
from faultwitness_dev.provenance import producer_provenance

SUT_RELEASE = "2.2.0"
SUT_COMMIT = "b74a7bc7bbe66099c61951f42b24dab8b6f02d18"
SEED_DOMAIN = "G02-seed-id-v1"
FAMILIES = ("change_config", "resource_capacity", "dependency_network", "runtime_data")
AD_CPU_ACTIVE_MIN_CORES = 0.5
AD_CPU_ACTIVE_MULTIPLIER = 5.0
EMAIL_MEMORY_MIN_GROWTH_BYTES = 1024 * 1024
EMAIL_MEMORY_MIN_GROWTH_RATIO = 0.05
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
# The first six are the injection targets, one per fault family, which made the observation
# scope 1:1 with the label set: every answer owned a private channel, and a zero-model
# classifier scored 0.9062 against the model arms' 0.9479. The last three are queried but
# never injected. They are upstream of the injected services -- frontend and recommendation
# call product-catalog, cart neighbours checkout -- so a non-zero error count on one of them
# is cross-service propagation rather than the family's own signal. Whether such propagation
# exists at all was previously unobservable: the all-zero off-diagonal co-occurrence matrix
# could equally mean faults do not spread or that nothing downstream was ever queried. See
# docs/engineering/diagnostics/g03-observation-scope-widening/PRE_REGISTRATION.md.
V3_TRACE_QUERY_SERVICES = (
    "ad",
    "checkout",
    "email",
    "fraud-detection",
    "payment",
    "product-catalog",
    "cart",
    "frontend",
    "recommendation",
)
V3_READINESS_COLLECTOR_CHECKPOINT = "g03-readiness-v3-label-blind-six-group-collector-v6"
V3_READINESS_COLLECTOR_SOURCE_SHA256 = (
    "b831184cf2d95d04ee8528fb47aefa93fa64f691732a07878ccb97fec6bac93a"
)
V3_READINESS_OBSERVER_SOURCE_SHA256 = (
    "9a918f3aaaf2c30db40669a65f1f9b68ce5182ca0582a6998cd67bfac378e2ac"
)
V3_FAULT_SAMPLE_INTERVAL_SECONDS = 65
# AMD-0007 appendix 3. The 90-second *activation* deadline below is frozen. The
# recovery observation deadline and the spacing between the two recovery samples
# were never pre-registered and were inconsistent with the 65-second fault
# spacing; naming them here makes both auditable without touching any predicate.
FAULT_ACTIVATION_DEADLINE_SECONDS = 90
FAULT_POLL_INTERVAL_SECONDS = 5
V3_RECOVERY_OBSERVATION_DEADLINE_SECONDS = 240
V3_RECOVERY_SAMPLE_INTERVAL_SECONDS = 65
# AMD-0007 appendix 4. The ad CPU query is a 2-minute `rate()`, and `recovery_state`
# only requires that the signal is not worsening -- not that it returned to rest --
# so an adHighCpu case ends with the pod still mid-decay. A later adHighCpu case that
# samples its baseline inside that lookback inherits an inflated `baseline_cpu`, and
# because the predicate multiplies the baseline by AD_CPU_ACTIVE_MULTIPLIER the
# activation bar can move out of physical reach. The baseline must therefore be
# measured on a quiesced pod. This is a false-negative removal only: the predicate,
# AD_CPU_ACTIVE_MIN_CORES, and AD_CPU_ACTIVE_MULTIPLIER are all unchanged.
V3_AD_CPU_QUIESCENT_MAX_CORES = 0.25
V3_AD_CPU_QUIESCENCE_DEADLINE_SECONDS = 240
# Bootstrap-only bound: a lab deploy that stops making progress must report which workload is
# pending instead of blocking forever. This governs infrastructure setup, not any measurement,
# so it is not one of the frozen metric deadlines above.
LAB_READINESS_DEADLINE_SECONDS = 1800
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
        "resource_capacity",
        "emailMemoryLeak",
        "100x",
        ("working_set", "baseline_working_set"),
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

    def begin(
        self,
        trial_id: str,
        *,
        producer_sha: str,
        cache_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def finish(self, trial_id: str, status: str, payload: Mapping[str, Any]) -> dict[str, Any]: ...


Observation = Mapping[str, Any]
Observer = Callable[[str, str], Observation]

# Transport retry for the flag control plane. `run_remote_script` opens three SSH sessions with
# ConnectTimeout=10 and no retry, and each privileged call decrypts the SOPS store; a concurrent
# decrypt or a momentary SSH refusal therefore fails the whole scenario on its first flag read,
# before any measurement has been taken. AMD-0003 already classifies that as an attributable
# infrastructure failure and authorizes a retry, so retrying here spends seconds instead of
# discarding a case and re-measuring it.
#
# This governs transport only. It is not one of the frozen metric deadlines, it never retries a
# measurement or an oracle evaluation, and it cannot mask a real fault: a read that keeps failing
# still raises InfrastructureFailure with the same reason. Deliberately not applied to `write`,
# where a retry could double-apply a mutation.
FLAG_TRANSPORT_ATTEMPTS = 4
FLAG_TRANSPORT_RETRY_DELAY_SECONDS = 6.0


class RemoteFlagClient:
    def __init__(self, producer_sha: str) -> None:
        if not FULL_SHA.fullmatch(producer_sha):
            raise GovernanceError("remote flag client requires a full producer SHA")
        self.producer_sha = producer_sha

    def _prelude(self) -> str:
        return """set -eu
cluster_ip=$(/usr/local/bin/k3s kubectl -n fw-sut \
  get service flagd -o jsonpath='{.spec.clusterIP}')
endpoint="http://$cluster_ip:4000"
"""

    def read(self) -> dict[str, Any]:
        last_error: GovernanceError | None = None
        for attempt in range(1, FLAG_TRANSPORT_ATTEMPTS + 1):
            try:
                output = run_remote_script(
                    self._prelude() + 'curl -fsS "$endpoint/api/read"\n',
                    privileged=True,
                )
                break
            except GovernanceError as error:
                last_error = error
                if attempt == FLAG_TRANSPORT_ATTEMPTS:
                    raise InfrastructureFailure(
                        f"remote flag read produced no result after "
                        f"{FLAG_TRANSPORT_ATTEMPTS} attempts: {error}"
                    ) from error
                time.sleep(FLAG_TRANSPORT_RETRY_DELAY_SECONDS)
        else:  # pragma: no cover - loop always breaks or raises
            raise InfrastructureFailure(
                f"remote flag read produced no result: {last_error}"
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
        try:
            output = run_remote_script(
                self._prelude()
                + f"printf %s {shlex.quote(body)} | base64 -d | "
                + "curl -fsS -H 'content-type: application/json' --data-binary @- "
                + '"$endpoint/api/write" >/dev/null\n'
                + 'curl -fsS "$endpoint/api/read"\n',
                privileged=True,
            )
        except GovernanceError as error:
            raise InfrastructureFailure(f"remote flag write produced no result: {error}") from error
        try:
            readback = json.loads(output)
        except json.JSONDecodeError as error:
            raise GovernanceError("flagd UI write readback was malformed") from error
        if canonical_json(readback) != canonical_json(document):
            raise GovernanceError("flagd UI write readback drifted")


class LiveScenarioObserver:
    fault_sample_interval_seconds = 30
    retain_terminal_fault_sample = False
    # Metric v1/v2 stimulate once per fault call and otherwise depend on ambient
    # load-generator traffic arriving inside the activation deadline. Metric v3
    # drives its own workload on every poll tick instead; see AMD-0007 appendix 3.
    restimulate_each_poll = False
    recovery_deadline_seconds = FAULT_ACTIVATION_DEADLINE_SECONDS
    recovery_sample_interval_seconds = 30
    # Metric v1/v2 accept the first healthy control sample as the baseline. Metric v3
    # additionally requires the ad pod to be quiescent first; see AMD-0007 appendix 4.
    require_ad_cpu_quiescent_baseline = False

    def __init__(self, producer_sha: str, fault_class: str) -> None:
        self.producer_sha = producer_sha
        self.fault_class = fault_class
        self.baseline_cpu = 0.0
        self.baseline_working_set = 0.0
        self.baseline_lag = 0.0
        self.fault_started: datetime | None = None
        self.recovery_started: datetime | None = None
        self.fault_poll_stimuli = 0
        self.recovery_poll_stimuli = 0
        self.ad_cpu_quiescent_cores: float | None = None
        self.fault_samples: list[dict[str, Any]] = []
        self.recovery_samples: list[dict[str, Any]] = []
        self.ad_fault_stimulus: dict[str, Any] | None = None
        self.ad_recovery_stimulus: dict[str, Any] | None = None
        self.product_stimulus: dict[str, Any] | None = None
        self.email_runtime_reset: dict[str, Any] | None = None
        self.email_fault_stimuli: list[dict[str, Any]] = []
        self.email_recovery_stimulus: dict[str, Any] | None = None
        self.kafka_stimulus: dict[str, Any] | None = None
        self.payment_stimulus: dict[str, Any] | None = None

    def _sample(self, since: datetime) -> dict[str, Any]:
        payload = base64.b64encode(
            json.dumps(
                {
                    "producer_sha": self.producer_sha,
                    "fault_class": self.fault_class,
                    "email_pod": (
                        self.email_runtime_reset.get("new_pod_name")
                        if self.email_runtime_reset is not None
                        else None
                    ),
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
email_pod = request.get("email_pod")
email_selector = (
    'pod="' + email_pod + '"'
    if isinstance(email_pod, str) and email_pod.startswith("email-")
    else 'pod=~"email-.*"'
)
working_set = promql(
    'max(container_memory_working_set_bytes{{namespace="fw-sut",'
    + email_selector
    + ',container="email"}})'
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
        try:
            output = run_remote_script(script, privileged=True)
        except GovernanceError as error:
            raise InfrastructureFailure(
                f"live observation collection produced no result: {error}"
            ) from error
        return json.loads(output)

    def _stimulate_checkout(self, *, allow_checkout_http_error: bool) -> dict[str, Any]:
        user_id = f"faultwitness-g02-{self.producer_sha[:12]}-" + datetime.now(UTC).strftime(
            "%Y%m%d%H%M%S%f"
        )
        payload = base64.b64encode(
            json.dumps(
                {
                    "producer_sha": self.producer_sha,
                    "allow_checkout_http_error": allow_checkout_http_error,
                    "user_id": user_id,
                    "product_id": "0PUK6V6EV0",
                    "checkout": {
                        "email": "faultwitness-g02@example.com",
                        "address": {
                            "streetAddress": "1600 Amphitheatre Parkway",
                            "city": "Mountain View",
                            "state": "CA",
                            "country": "United States",
                            "zipCode": "94043",
                        },
                        "creditCard": {
                            "creditCardNumber": "4432-8015-6152-0454",
                            "creditCardCvv": 672,
                            "creditCardExpirationYear": 2039,
                            "creditCardExpirationMonth": 1,
                        },
                        "userCurrency": "USD",
                    },
                },
                separators=(",", ":"),
            ).encode()
        ).decode("ascii")
        script = f"""set -eu
python3 - <<'PY'
import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request

request = json.loads(base64.b64decode({payload!r}))
kubectl = ["/usr/local/bin/k3s", "kubectl", "-n", "fw-sut"]
frontend = json.loads(subprocess.run(
    [*kubectl, "get", "service", "frontend-proxy", "-o", "json"],
    check=True,
    capture_output=True,
    text=True,
).stdout)
endpoint = "http://" + frontend["spec"]["clusterIP"] + ":8080"

def post(path, document, *, allow_http_error=False):
    body = json.dumps(document, separators=(",", ":")).encode()
    call = urllib.request.Request(
        endpoint + path,
        data=body,
        headers={{"content-type": "application/json"}},
        method="POST",
    )
    try:
        with urllib.request.urlopen(call) as response:
            status = response.status
            response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        error.read()
        if not allow_http_error:
            print("FW_G02_STIMULUS_HTTP_ERROR status=" + str(error.code), file=sys.stderr)
            raise SystemExit(42)
    if not allow_http_error and (status < 200 or status >= 300):
        raise SystemExit("checkout stimulus returned non-success")
    return status

cart_status = post("/api/cart", {{
    "userId": request["user_id"],
    "item": {{"productId": request["product_id"], "quantity": 1}},
}})
checkout = dict(request["checkout"])
checkout["userId"] = request["user_id"]
allow_checkout_http_error = request["allow_checkout_http_error"]
checkout_status = post(
    "/api/checkout", checkout, allow_http_error=allow_checkout_http_error
)
print(json.dumps({{
    "status": "pass",
    "checkout_count": 1,
    "cart_status": cart_status,
    "checkout_status": checkout_status,
}}, sort_keys=True))
PY
"""
        try:
            output = run_remote_script(script, privileged=True)
        except GovernanceError as error:
            deterministic = ("FW_G02_STIMULUS_HTTP_ERROR",)
            if any(marker in str(error) for marker in deterministic):
                raise
            raise InfrastructureFailure(
                f"checkout workload stimulus produced no result: {error}"
            ) from error
        document = json.loads(output)
        if document.get("status") != "pass" or document.get("checkout_count") != 1:
            raise GovernanceError("workload stimulus did not complete exactly one checkout")
        return document

    def _stimulate_kafka_fault(self) -> dict[str, Any]:
        return self._stimulate_checkout(allow_checkout_http_error=False)

    def _stimulate_product_fault(self) -> dict[str, Any]:
        script = """set -eu
python3 - <<'PY'
import json
import subprocess
import urllib.error
import urllib.request

kubectl = ["/usr/local/bin/k3s", "kubectl", "-n", "fw-sut"]
frontend = json.loads(subprocess.run(
    [*kubectl, "get", "service", "frontend-proxy", "-o", "json"],
    check=True,
    capture_output=True,
    text=True,
).stdout)
endpoint = (
    "http://" + frontend["spec"]["clusterIP"]
    + ":8080/api/products/OLJCESPC7Z"
)
try:
    with urllib.request.urlopen(endpoint) as response:
        status = response.status
        response.read()
except urllib.error.HTTPError as error:
    status = error.code
    error.read()
if status < 200 or status >= 600:
    raise SystemExit("product stimulus did not reach the frontend")
print(json.dumps({
    "status": "pass",
    "request_count": 1,
    "response_status": status,
}, sort_keys=True))
PY
"""
        try:
            output = run_remote_script(script, privileged=True)
        except GovernanceError as error:
            raise InfrastructureFailure(
                f"product workload stimulus produced no result: {error}"
            ) from error
        document = json.loads(output)
        if document.get("status") != "pass" or document.get("request_count") != 1:
            raise GovernanceError("product workload stimulus did not complete exactly one request")
        return document

    def _stimulate_email_request(self) -> dict[str, Any]:
        payload = base64.b64encode(
            json.dumps(
                {
                    "email": "faultwitness-g02@example.com",
                    "order": {
                        "order_id": "faultwitness-g02-memory",
                        "shipping_tracking_id": "faultwitness-g02-tracking",
                        "shipping_cost": {
                            "units": 1,
                            "nanos": 0,
                            "currency_code": "USD",
                        },
                        "shipping_address": {
                            "street_address_1": "1600 Amphitheatre Parkway",
                            "street_address_2": "",
                            "city": "Mountain View",
                            "country": "United States",
                            "zip_code": "94043",
                        },
                        "items": [],
                    },
                },
                separators=(",", ":"),
            ).encode()
        ).decode("ascii")
        script = f"""set -eu
python3 - <<'PY'
import base64
import json
import subprocess
import urllib.error
import urllib.request

document = json.loads(base64.b64decode({payload!r}))
kubectl = ["/usr/local/bin/k3s", "kubectl", "-n", "fw-sut"]
service = json.loads(subprocess.run(
    [*kubectl, "get", "service", "email", "-o", "json"],
    check=True,
    capture_output=True,
    text=True,
).stdout)
endpoint = (
    "http://" + service["spec"]["clusterIP"] + ":"
    + str(service["spec"]["ports"][0]["port"])
    + "/send_order_confirmation"
)
request = urllib.request.Request(
    endpoint,
    data=json.dumps(document, separators=(",", ":")).encode(),
    headers={{"content-type": "application/json"}},
    method="POST",
)
try:
    with urllib.request.urlopen(request) as response:
        status = response.status
        response.read()
except urllib.error.HTTPError as error:
    error.read()
    status = error.code
if status != 200:
    raise SystemExit("email stimulus returned non-success")
print(json.dumps({{
    "status": "pass",
    "request_count": 1,
    "response_status": status,
}}, sort_keys=True))
PY
"""
        try:
            output = run_remote_script(script, privileged=True)
        except GovernanceError as error:
            raise InfrastructureFailure(
                f"email workload stimulus produced no result: {error}"
            ) from error
        document = json.loads(output)
        if (
            document.get("status") != "pass"
            or document.get("request_count") != 1
            or document.get("response_status") != 200
        ):
            raise GovernanceError("email workload stimulus did not complete exactly one request")
        return document

    def _reset_email_runtime(self) -> dict[str, Any]:
        script = """set -eu
python3 - <<'PY'
import json
import subprocess
import time

kubectl = ["/usr/local/bin/k3s", "kubectl", "-n", "fw-sut"]

def email_pods():
    items = json.loads(subprocess.run(
        [*kubectl, "get", "pods", "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout)["items"]
    return [item for item in items if item["metadata"]["name"].startswith("email-")]

before = email_pods()
if len(before) != 1:
    raise SystemExit("email runtime reset requires exactly one source pod")
old_name = before[0]["metadata"]["name"]
old_uid = before[0]["metadata"]["uid"]
subprocess.run(
    [*kubectl, "delete", "pod", old_name, "--wait=true"],
    check=True,
    stdout=subprocess.DEVNULL,
)
while True:
    current = email_pods()
    if len(current) == 1:
        pod = current[0]
        waiting = [
            state.get("state", {}).get("waiting", {}).get("reason")
            for state in pod.get("status", {}).get("containerStatuses", [])
        ]
        terminal = {"CrashLoopBackOff", "ErrImagePull", "ImagePullBackOff", "CreateContainerError"}
        if any(reason in terminal for reason in waiting):
            raise SystemExit("replacement email pod entered a terminal waiting state")
        ready = any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in pod.get("status", {}).get("conditions", [])
        )
        if ready and pod["metadata"]["uid"] != old_uid:
            break
    time.sleep(2)
print(json.dumps({
    "status": "pass",
    "reset_count": 1,
    "old_pod_uid": old_uid,
    "new_pod_uid": pod["metadata"]["uid"],
    "new_pod_name": pod["metadata"]["name"],
    "ready": True,
}, sort_keys=True))
PY
"""
        try:
            output = run_remote_script(script, privileged=True)
        except GovernanceError as error:
            raise InfrastructureFailure(
                f"email runtime reset produced no result: {error}"
            ) from error
        document = json.loads(output)
        if (
            document.get("status") != "pass"
            or document.get("reset_count") != 1
            or document.get("ready") is not True
            or document.get("old_pod_uid") == document.get("new_pod_uid")
            or not str(document.get("new_pod_name", "")).startswith("email-")
        ):
            raise GovernanceError("email runtime reset did not replace one Ready pod")
        return document

    def _stimulate_ad_request(self) -> dict[str, Any]:
        script = """set -eu
python3 - <<'PY'
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

kubectl = ["/usr/local/bin/k3s", "kubectl", "-n", "fw-sut"]
frontend = json.loads(subprocess.run(
    [*kubectl, "get", "service", "frontend-proxy", "-o", "json"],
    check=True,
    capture_output=True,
    text=True,
).stdout)
endpoint = "http://" + frontend["spec"]["clusterIP"] + ":8080/api/data?" + urllib.parse.urlencode(
    {"contextKeys": "binoculars"}
)
try:
    with urllib.request.urlopen(endpoint) as response:
        status = response.status
        response.read()
except urllib.error.HTTPError as error:
    error.read()
    print("FW_G02_STIMULUS_HTTP_ERROR status=" + str(error.code), file=sys.stderr)
    raise SystemExit(42)
if status != 200:
    print("FW_G02_STIMULUS_HTTP_ERROR status=" + str(status), file=sys.stderr)
    raise SystemExit(42)
print(json.dumps({
    "status": "pass",
    "request_count": 1,
    "response_status": status,
}, sort_keys=True))
PY
"""
        try:
            output = run_remote_script(script, privileged=True)
        except GovernanceError as error:
            if "FW_G02_STIMULUS_HTTP_ERROR" in str(error):
                raise
            raise InfrastructureFailure(
                f"ad workload stimulus produced no result: {error}"
            ) from error
        document = json.loads(output)
        if (
            document.get("status") != "pass"
            or document.get("request_count") != 1
            or document.get("response_status") != 200
        ):
            raise GovernanceError("ad workload stimulus did not complete exactly one request")
        return document

    def _stimulate_payment_fault(self) -> dict[str, Any]:
        # A payment fault is expected to make checkout return an HTTP error. The
        # response still proves that exactly one request reached the candidate;
        # the fault oracle remains responsible for proving the correlated trace.
        return self._stimulate_checkout(allow_checkout_http_error=True)

    def _absent_series(self, sample: Mapping[str, Any]) -> tuple[str, ...]:
        """Name the absent series, label-blind.

        Every window must carry all six evidence groups for every label, so a
        window is only scoreable once all of them were scraped. Requiring the
        same set for every label also keeps the wait behaviour independent of
        the sealed fault class.
        """
        absent = set(sample.get("absent_series") or ())
        return tuple(
            name
            for name in (
                "cpu_rate",
                "working_set",
                "consumer_record_lag",
                "consumer_poll_lag_seconds",
            )
            if name in absent
        )

    def _await_ad_cpu_quiescence(self) -> None:
        """Wait until the ad pod's CPU rate leaves the previous case's burn behind.

        The collector's ad CPU query is a 2-minute ``rate()`` and ``recovery_state``
        only requires that the signal is not worsening, so every adHighCpu case ends
        with the pod still decaying from its burn. Sampling a baseline inside that
        lookback captures the *previous* case's load; multiplied by
        ``AD_CPU_ACTIVE_MULTIPLIER`` the activation bar then exceeds what the pod can
        physically reach, and the case fails for a reason that has nothing to do with
        the candidate.

        Waiting can only remove such false negatives. A quiescent baseline is a lower
        baseline, so it can never make an inactive fault look active, and the fault
        predicate itself is untouched.
        """
        deadline = time.monotonic() + V3_AD_CPU_QUIESCENCE_DEADLINE_SECONDS
        while True:
            sample = self._sample(datetime.now(UTC) - timedelta(minutes=2))
            absent = self._absent_series(sample)
            if not absent:
                cpu_rate = float(sample["cpu_rate"])
                if cpu_rate <= V3_AD_CPU_QUIESCENT_MAX_CORES:
                    self.ad_cpu_quiescent_cores = cpu_rate
                    return
            if time.monotonic() >= deadline:
                if absent:
                    raise self._absent_series_failure(absent)
                raise InfrastructureFailure(
                    "metric-v3 ad pod did not reach a quiescent CPU baseline within "
                    f"{V3_AD_CPU_QUIESCENCE_DEADLINE_SECONDS}s: last rate "
                    f"{float(sample['cpu_rate']):.4f} cores exceeds "
                    f"{V3_AD_CPU_QUIESCENT_MAX_CORES} cores"
                )
            time.sleep(FAULT_POLL_INTERVAL_SECONDS)

    def _absent_series_failure(self, absent: Sequence[str]) -> InfrastructureFailure:
        """A series still absent at the deadline is a missing instrument.

        AMD-0003 authorises unlimited retries for attributable infrastructure
        failures, so this is strictly safer than feeding a synthetic 0.0 into a
        fault predicate and recording a non-retryable ``metric_fail``. A brief
        scrape gap is waited out by the caller rather than reaching here.
        """
        return InfrastructureFailure(
            "metric-v3 Prometheus series stayed absent past the observation "
            f"deadline for {self.fault_class}: {', '.join(absent)}"
        )

    def _drive_label_workload(self, phase: str) -> None:
        """Issue exactly one candidate-bound request for this label.

        Called once per poll tick inside the fault and recovery windows so the
        oracle measures a workload the runner controls rather than whatever the
        ambient load generator happens to send. This cannot manufacture a false
        positive: with the flag off, checkout succeeds, no error span is
        recorded, fraud-detection keeps polling, and the ad service does not
        spin, so no additional request can satisfy a fault predicate. It removes
        false negatives only. Every predicate in ``fault_state`` and
        ``recovery_state`` is unchanged.
        """
        if self.fault_class == "adHighCpu":
            stimulus = self._stimulate_ad_request()
            if phase == "fault":
                self.ad_fault_stimulus = stimulus
            else:
                self.ad_recovery_stimulus = stimulus
        elif self.fault_class == "emailMemoryLeak":
            stimulus = self._stimulate_email_request()
            if phase == "fault":
                self.email_fault_stimuli.append(stimulus)
            else:
                self.email_recovery_stimulus = stimulus
        elif self.fault_class == "productCatalogFailure":
            self.product_stimulus = self._stimulate_product_fault()
        elif self.fault_class == "kafkaQueueProblems":
            self.kafka_stimulus = self._stimulate_kafka_fault()
        elif self.fault_class in {"paymentFailure", "paymentUnreachable"}:
            self.payment_stimulus = self._stimulate_payment_fault()
        else:
            raise GovernanceError("unsupported live fault observer")
        if phase == "fault":
            self.fault_poll_stimuli += 1
        else:
            self.recovery_poll_stimuli += 1

    def _active_observation(self, sample: Mapping[str, Any]) -> dict[str, Any]:
        descriptions = "\n".join(str(item) for item in sample["descriptions"])
        if self.fault_class == "productCatalogFailure":
            found = "Product Catalog Fail Feature Flag Enabled" in descriptions
            observation = {
                **sample,
                "journey_failed": found,
                "correlated_error": found,
            }
            if self.product_stimulus is not None:
                observation["product_stimulus"] = dict(self.product_stimulus)
            return observation
        if self.fault_class == "adHighCpu":
            observation = {
                **sample,
                "cpu_rate": sample["cpu_rate"],
                "baseline_cpu_max": self.baseline_cpu,
                "correlated_span": sample["trace_count"] > 0,
            }
            if self.ad_fault_stimulus is not None:
                observation["ad_stimulus"] = dict(self.ad_fault_stimulus)
            return observation
        if self.fault_class == "emailMemoryLeak":
            observation = {
                **sample,
                "working_set": sample["working_set"],
                "baseline_working_set": self.baseline_working_set,
                "metric_service": "emailservice",
                "working_set_unit": "bytes",
                "email_stimulus_count": len(self.email_fault_stimuli),
            }
            if self.email_runtime_reset is not None:
                observation["email_runtime_reset"] = dict(self.email_runtime_reset)
            return observation
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
            observation = {
                **sample,
                "consumer_lag": sample["consumer_lag"],
                "baseline_lag": self.baseline_lag,
                "kafka_error": (
                    sample["kafka_log_error"]
                    or sample["kafka_fault_log"]
                    or sample["error_spans"] > 0
                ),
            }
            if self.kafka_stimulus is not None:
                observation["kafka_stimulus"] = dict(self.kafka_stimulus)
            return observation
        raise GovernanceError("unsupported live fault observer")

    def __call__(self, phase: str, fault_class: str) -> Observation:
        if fault_class != self.fault_class:
            raise GovernanceError("live observer fault class drifted")
        if phase == "control":
            sample_since = datetime.now(UTC) - timedelta(minutes=2)
            if self.fault_class == "emailMemoryLeak":
                self.email_runtime_reset = self._reset_email_runtime()
                sample_since = datetime.now(UTC)
            elif self.fault_class == "adHighCpu":
                if self.require_ad_cpu_quiescent_baseline:
                    self._await_ad_cpu_quiescence()
                sample_since = datetime.now(UTC)
                self._stimulate_ad_request()
            deadline = time.monotonic() + FAULT_ACTIVATION_DEADLINE_SECONDS
            while True:
                sample = self._sample(sample_since)
                # An absent series here is the expected post-restart transient:
                # keep polling until the scrape lands rather than failing closed.
                signal_ready = not self._absent_series(sample)
                if signal_ready and self.fault_class == "emailMemoryLeak":
                    signal_ready = float(sample["working_set"]) > 0
                elif signal_ready and self.fault_class == "adHighCpu":
                    signal_ready = float(sample["cpu_rate"]) > 0
                healthy = sample["ready"] and sample["journey_status"] == 200
                if healthy and signal_ready:
                    break
                if time.monotonic() >= deadline:
                    return {"state": OracleState.UNKNOWN}
                time.sleep(FAULT_POLL_INTERVAL_SECONDS)
            self.baseline_cpu = float(sample["cpu_rate"] or 0.0)
            self.baseline_working_set = float(sample["working_set"] or 0.0)
            self.baseline_lag = float(sample["consumer_lag"] or 0.0)
            return {"state": OracleState.HEALTHY}
        if phase == "fault":
            if self.fault_started is None:
                self.fault_started = datetime.now(UTC)
                if self.fault_class == "productCatalogFailure":
                    self.product_stimulus = self._stimulate_product_fault()
                elif self.fault_class == "kafkaQueueProblems":
                    self.kafka_stimulus = self._stimulate_kafka_fault()
                elif self.fault_class in {"paymentFailure", "paymentUnreachable"}:
                    self.payment_stimulus = self._stimulate_payment_fault()
            elif self.fault_samples:
                time.sleep(self.fault_sample_interval_seconds)
            if self.fault_class == "adHighCpu":
                self.ad_fault_stimulus = self._stimulate_ad_request()
            elif self.fault_class == "emailMemoryLeak":
                self.email_fault_stimuli.append(self._stimulate_email_request())
            deadline = time.monotonic() + FAULT_ACTIVATION_DEADLINE_SECONDS
            while True:
                sample = self._sample(self.fault_started)
                absent = self._absent_series(sample)
                if absent:
                    # A momentarily unscraped series makes this window
                    # unscoreable, not failed. Wait for the scrape the same way
                    # the control phase does; only a series still absent at the
                    # deadline is a missing instrument.
                    if time.monotonic() >= deadline:
                        raise self._absent_series_failure(absent)
                    time.sleep(FAULT_POLL_INTERVAL_SECONDS)
                    if self.restimulate_each_poll:
                        self._drive_label_workload("fault")
                    continue
                observation = self._active_observation(sample)
                if self.fault_class == "emailMemoryLeak" and not self.fault_samples:
                    self.fault_samples.append(observation)
                    return observation
                comparison = (
                    [self.fault_samples[-1], observation]
                    if self.fault_class == "emailMemoryLeak"
                    else [observation, observation]
                )
                active = fault_state(fault_class, comparison) == OracleState.FAULT_ACTIVE
                if active:
                    self.fault_samples.append(observation)
                    return observation
                if time.monotonic() >= deadline:
                    if self.retain_terminal_fault_sample:
                        self.fault_samples.append(observation)
                    return observation
                time.sleep(FAULT_POLL_INTERVAL_SECONDS)
                if self.restimulate_each_poll:
                    self._drive_label_workload("fault")
        if phase == "recovery":
            if self.recovery_started is None:
                self.recovery_started = datetime.now(UTC)
                if self.fault_class == "adHighCpu":
                    self.ad_recovery_stimulus = self._stimulate_ad_request()
                elif self.fault_class == "emailMemoryLeak":
                    self.email_recovery_stimulus = self._stimulate_email_request()
            elif self.recovery_samples:
                time.sleep(self.recovery_sample_interval_seconds)
            deadline = time.monotonic() + self.recovery_deadline_seconds
            while True:
                sample = self._sample(self.recovery_started)
                absent = self._absent_series(sample)
                if absent:
                    # Same rule as the fault window: an unscraped series is not
                    # a recovery verdict.
                    if time.monotonic() >= deadline:
                        raise self._absent_series_failure(absent)
                    time.sleep(FAULT_POLL_INTERVAL_SECONDS)
                    if self.restimulate_each_poll:
                        self._drive_label_workload("recovery")
                    continue
                signal_ok = True
                if self.fault_class == "adHighCpu":
                    signal_ok = float(sample["cpu_rate"]) <= max(
                        self.baseline_cpu, float(self.fault_samples[-1]["cpu_rate"])
                    )
                elif self.fault_class == "emailMemoryLeak":
                    tolerated_drift = max(
                        EMAIL_MEMORY_MIN_GROWTH_BYTES,
                        self.baseline_working_set * EMAIL_MEMORY_MIN_GROWTH_RATIO,
                    )
                    signal_ok = (
                        float(sample["working_set"]) - float(self.fault_samples[-1]["working_set"])
                        < tolerated_drift
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
                if self.ad_recovery_stimulus is not None:
                    observation["ad_recovery_stimulus"] = dict(self.ad_recovery_stimulus)
                if self.email_recovery_stimulus is not None:
                    observation["email_recovery_stimulus"] = dict(self.email_recovery_stimulus)
                required = ("ready", "journey_healthy", "signal_not_worsening")
                if all(observation[key] for key in required):
                    self.recovery_samples.append(observation)
                    return observation
                if time.monotonic() >= deadline:
                    return observation
                time.sleep(FAULT_POLL_INTERVAL_SECONDS)
                if self.restimulate_each_poll:
                    self._drive_label_workload("recovery")
        raise GovernanceError("unknown live observer phase")


def render_live_readiness_observer_v3_script(
    producer_sha: str,
    since: datetime,
) -> str:
    """Render one label-blind collector script with exact current-pod selectors."""
    payload = base64.b64encode(
        json.dumps(
            {
                "producer_sha": producer_sha,
                "trace_services": list(V3_TRACE_QUERY_SERVICES),
                "since_micros": int(since.timestamp() * 1_000_000),
                "since_rfc3339": since.isoformat().replace("+00:00", "Z"),
            }
        ).encode()
    ).decode("ascii")
    return f"""set -eu
python3 - <<'PY'
import base64
import datetime
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

def current_pod(prefix):
    items = json.loads(kubectl("get", "pods", "-o", "json"))["items"]
    matches = [
        item["metadata"]["name"]
        for item in items
        if item["metadata"]["name"].startswith(prefix)
        and item["metadata"].get("deletionTimestamp") is None
    ]
    if len(matches) != 1:
        print(
            "FW_G03_COLLECTOR_POD_CARDINALITY "
            + prefix
            + " count="
            + str(len(matches)),
            file=sys.stderr,
        )
        raise SystemExit(42)
    return matches[0]

ad_pod = current_pod("ad-")
email_pod = current_pod("email-")
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
    # An absent series is a missing instrument, not an observed zero. Report it
    # as null so the caller can distinguish "not scraped yet" from a real 0.0
    # instead of feeding a synthetic zero into a fault-state predicate.
    url = prometheus_url + "?" + urllib.parse.urlencode({{"query": query}})
    result = json.load(urllib.request.urlopen(url))["data"]["result"]
    return float(result[0]["value"][1]) if result else None

cpu_rate = promql(
    'sum(rate(container_cpu_usage_seconds_total{{namespace="fw-sut",pod="'
    + ad_pod
    + '",container="ad"}}[2m]))'
)
working_set = promql(
    'max(container_memory_working_set_bytes{{namespace="fw-sut",pod="'
    + email_pod
    + '",container="email"}})'
)
consumer_record_lag = promql(
    'max(kafka_consumer_records_lag{{service_name="fraud-detection"}})'
)
consumer_poll_lag_seconds = promql(
    'max(kafka_consumer_last_poll_seconds_ago{{service_name="fraud-detection"}})'
)
consumer_lag = (
    None
    if consumer_record_lag is None or consumer_poll_lag_seconds is None
    else max(consumer_record_lag, consumer_poll_lag_seconds)
)
absent_series = sorted(
    name
    for name, value in (
        ("cpu_rate", cpu_rate),
        ("working_set", working_set),
        ("consumer_record_lag", consumer_record_lag),
        ("consumer_poll_lag_seconds", consumer_poll_lag_seconds),
    )
    if value is None
)

jaeger = json.loads(kubectl("get", "endpoints", "jaeger-query", "-o", "json"))
jaeger_ip = jaeger["subsets"][0]["addresses"][0]["ip"]
trace_activity = {{}}
trace_errors = {{}}
oracle_signals = {{}}
for requested_service in request["trace_services"]:
    query = {{
        "service": requested_service,
        "limit": "100",
        "start": str(request["since_micros"]),
        "lookback": "custom",
    }}
    url = (
        "http://" + jaeger_ip + ":16686/jaeger/ui/api/traces?"
        + urllib.parse.urlencode(query)
    )
    traces = json.load(urllib.request.urlopen(url)).get("data") or []
    trace_activity[requested_service] = len(traces)
    service_errors = 0
    service_connections = 0
    service_descriptions = []
    oracle_descriptions = []
    oracle_error_spans = 0
    oracle_checkout_error_spans = 0
    oracle_payment_connection_errors = 0
    for trace in traces:
        processes = trace.get("processes", {{}})
        trace_has_checkout_error = False
        trace_has_payment_client_error = False
        trace_has_connection_error = False
        for span in trace.get("spans", []):
            tags = {{tag["key"]: tag.get("value") for tag in span.get("tags", [])}}
            service_name = processes.get(span.get("processID"), {{}}).get("serviceName")
            is_error = tags.get("error") is True or tags.get("otel.status_code") == "ERROR"
            description = str(tags.get("otel.status_description", ""))
            lowered = description.lower()
            connection_error = any(token in lowered for token in (
                "connection refused", "connection error", "unavailable",
                "error while dialing", "connect:", "name resolver", "zero addresses",
            ))
            if description:
                oracle_descriptions.append(description)
            if is_error:
                oracle_error_spans += 1
                if (
                    service_name == "checkout"
                    and tags.get("rpc.service") == "oteldemo.CheckoutService"
                    and tags.get("rpc.method") == "PlaceOrder"
                ):
                    oracle_checkout_error_spans += 1
                    trace_has_checkout_error = True
                if (
                    service_name == "checkout"
                    and tags.get("rpc.service") == "oteldemo.PaymentService"
                    and tags.get("rpc.method") == "Charge"
                ):
                    trace_has_payment_client_error = True
            if description and any(token in lowered for token in (
                "connection refused", "connection error", "unavailable",
                "error while dialing", "connect:",
            )):
                trace_has_connection_error = True
            if service_name != requested_service:
                continue
            if description:
                service_descriptions.append(description)
            if is_error:
                service_errors += 1
            if connection_error:
                service_connections += 1
        if (
            trace_has_checkout_error
            and trace_has_payment_client_error
            and trace_has_connection_error
        ):
            oracle_payment_connection_errors += 1
    trace_errors[requested_service] = {{
        "error_count": service_errors,
        "connection_error_count": service_connections,
        "descriptions": service_descriptions,
    }}
    oracle_signals[requested_service] = {{
        "trace_count": len(traces),
        "error_spans": oracle_error_spans,
        "checkout_error_spans": oracle_checkout_error_spans,
        "payment_connection_errors": oracle_payment_connection_errors,
        "descriptions": oracle_descriptions,
    }}

logs = kubectl(
    "logs", "deployment/fraud-detection", "--since-time=" + request["since_rfc3339"],
)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
print(json.dumps({{
    "recorded_at": now,
    "ready": ready,
    "journey_status": journey_status,
    "cpu_rate": cpu_rate,
    "working_set": working_set,
    "consumer_lag": consumer_lag,
    "consumer_record_lag": consumer_record_lag,
    "consumer_poll_lag_seconds": consumer_poll_lag_seconds,
    "absent_series": absent_series,
    "metric_pods": {{"ad": ad_pod, "email": email_pod}},
    "trace_activity": trace_activity,
    "trace_errors": trace_errors,
    "oracle_signals": oracle_signals,
    "kafka_log_error": "error" in logs.lower(),
    "kafka_fault_log": "FeatureFlag 'kafkaQueueProblems' is enabled, sleeping" in logs,
}}, sort_keys=True))
PY
"""


def live_readiness_collector_source_digest() -> str:
    source = inspect.getsource(render_live_readiness_observer_v3_script).encode()
    return hashlib.sha256(source).hexdigest()


def live_readiness_observer_source_digest() -> str:
    source = inspect.getsource(LiveScenarioObserver.__call__).encode()
    return hashlib.sha256(source).hexdigest()


def validate_live_readiness_collector_checkpoint() -> dict[str, Any]:
    collector_actual = live_readiness_collector_source_digest()
    observer_actual = live_readiness_observer_source_digest()
    if collector_actual != V3_READINESS_COLLECTOR_SOURCE_SHA256:
        raise GovernanceError(
            "metric-v3 collector source changed without a checkpoint digest update"
        )
    if observer_actual != V3_READINESS_OBSERVER_SOURCE_SHA256:
        raise GovernanceError(
            "metric-v3 observer source changed without a checkpoint digest update"
        )
    contract = {
        "checkpoint": V3_READINESS_COLLECTOR_CHECKPOINT,
        "source_sha256": collector_actual,
        "observer_source_sha256": observer_actual,
        "fault_sample_interval_seconds": V3_FAULT_SAMPLE_INTERVAL_SECONDS,
        "terminal_fault_sample": "retained before deadline return for metric v3 only",
        "pod_selection": "exactly one non-terminating ad pod and email pod",
        "metric_selectors": "exact pod equality; regex selectors forbidden",
        "trace_services": list(V3_TRACE_QUERY_SERVICES),
        "fault_activation_deadline_seconds": FAULT_ACTIVATION_DEADLINE_SECONDS,
        "poll_interval_seconds": FAULT_POLL_INTERVAL_SECONDS,
        "restimulate_each_poll": True,
        "recovery_observation_deadline_seconds": (V3_RECOVERY_OBSERVATION_DEADLINE_SECONDS),
        "recovery_sample_interval_seconds": V3_RECOVERY_SAMPLE_INTERVAL_SECONDS,
        "absent_series": "reported as null and classified as infrastructure",
        "absent_series_wait": (
            "label-blind: a window is unscoreable until every series is present; "
            "only a series still absent at the observation deadline fails the case"
        ),
        "ad_cpu_quiescent_max_cores": V3_AD_CPU_QUIESCENT_MAX_CORES,
        "ad_cpu_quiescence_deadline_seconds": V3_AD_CPU_QUIESCENCE_DEADLINE_SECONDS,
    }
    return {
        **contract,
        "contract_digest": hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


class LiveReadinessObserverV3(LiveScenarioObserver):
    """Collect the same public service/metric surface for every sealed fault label."""

    fault_sample_interval_seconds = V3_FAULT_SAMPLE_INTERVAL_SECONDS
    retain_terminal_fault_sample = True
    restimulate_each_poll = True
    recovery_deadline_seconds = V3_RECOVERY_OBSERVATION_DEADLINE_SECONDS
    recovery_sample_interval_seconds = V3_RECOVERY_SAMPLE_INTERVAL_SECONDS
    require_ad_cpu_quiescent_baseline = True

    def _sample(self, since: datetime) -> dict[str, Any]:
        validate_live_readiness_collector_checkpoint()
        script = render_live_readiness_observer_v3_script(self.producer_sha, since)
        try:
            output = run_remote_script(script, privileged=True)
        except GovernanceError as error:
            # A fail-closed marker raised by the collector itself is a governance
            # verdict, not an infrastructure fault. Rewrapping it would launder a
            # deliberate refusal into the AMD-0003 unlimited-retry class.
            if "FW_G03_COLLECTOR_" in str(error):
                raise
            raise InfrastructureFailure(
                f"metric-v3 live observation collection produced no result: {error}"
            ) from error
        try:
            document = json.loads(output)
        except json.JSONDecodeError as error:
            raise InfrastructureFailure(
                "metric-v3 live observation collection returned malformed JSON"
            ) from error
        expected_services = set(V3_TRACE_QUERY_SERVICES)
        if set(document.get("trace_activity", {})) != expected_services:
            raise GovernanceError("metric-v3 trace activity service set drifted")
        if set(document.get("trace_errors", {})) != expected_services:
            raise GovernanceError("metric-v3 trace error service set drifted")
        if set(document.get("oracle_signals", {})) != expected_services:
            raise GovernanceError("metric-v3 oracle signal service set drifted")
        metric_pods = document.get("metric_pods")
        if (
            not isinstance(metric_pods, dict)
            or not str(metric_pods.get("ad", "")).startswith("ad-")
            or not str(metric_pods.get("email", "")).startswith("email-")
        ):
            raise GovernanceError("metric-v3 exact metric pod resolution drifted")
        selected_service = TRACE_QUERY_SERVICES[self.fault_class]
        oracle = document.pop("oracle_signals")[selected_service]
        document.update(oracle)
        return document

    def collect_healthy_window(self) -> dict[str, Any]:
        # Poll for a complete window rather than failing on the first scrape
        # gap; the packet needs all six groups, so an absent series only means
        # this sample is not yet usable.
        deadline = time.monotonic() + FAULT_ACTIVATION_DEADLINE_SECONDS
        while True:
            sample = self._sample(datetime.now(UTC) - timedelta(minutes=2))
            absent = self._absent_series(sample)
            if not absent:
                break
            if time.monotonic() >= deadline:
                raise self._absent_series_failure(absent)
            time.sleep(FAULT_POLL_INTERVAL_SECONDS)
            self._drive_label_workload("fault")
        if not sample.get("ready") or sample.get("journey_status") != 200:
            raise GovernanceError("metric-v3 healthy window is not healthy")
        return sample


def _operation_root() -> Path:
    return (
        InfraPaths.defaults().evidence_dir.parent.parent / "artifacts" / "fault-lab" / "operations"
    )


def _operation_path(operation_id: str) -> Path:
    if not re.fullmatch(r"op-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", operation_id):
        raise GovernanceError("invalid G02 fault operation ID")
    return _operation_root() / f"{operation_id}.json"


def inject_live_fault(producer_sha: str, fault_class: str) -> dict[str, Any]:
    adapter = ADAPTERS.get(fault_class)
    if adapter is None:
        raise GovernanceError("G02 live injection uses an unknown fault class")
    client = RemoteFlagClient(producer_sha)
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
            (producer_sha + fault_class + canonical_json(original)).encode()
        ).hexdigest()[:12]
    )
    record = {
        "operation_id": operation_id,
        "producer_sha": producer_sha,
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


def restore_live_fault(producer_sha: str, operation_id: str) -> dict[str, Any]:
    path = _operation_path(operation_id)
    if not path.is_file():
        raise GovernanceError("G02 fault operation record is missing")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("producer_sha") != producer_sha or record.get("status") != "injected":
        raise GovernanceError("G02 fault operation is not restorable for this producer")
    client = RemoteFlagClient(producer_sha)
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
        (f"probe-{name.replace('_', '-')}", str(probe_images[name])) for name in PROBE_IMAGE_NAMES
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


def render_k3s_bootstrap_script(config: Mapping[str, Any], producer_sha: str) -> str:
    if not FULL_SHA.fullmatch(producer_sha):
        raise GovernanceError("G02 lab producer must be a full Git SHA")
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
    workspace = f"/tmp/faultwitness-fault-lab-{producer_sha[:12]}"
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
load_users_anchor = '            - name: LOCUST_USERS\\n              value: "10"'
load_users_minimum = '            - name: LOCUST_USERS\\n              value: "1"'
if text.count(load_users_anchor) != 1:
    raise SystemExit("FW_G02_LOAD_USERS_ANCHOR_DRIFT")
text = text.replace(load_users_anchor, load_users_minimum)
with open(path, "w", encoding="utf-8", newline="\\n") as target_file:
    target_file.write(text)
PY
if grep -E '^[[:space:]]*image:[[:space:]]*' "$manifest" | grep -v '@sha256:'; then
  echo FW_G02_UNPINNED_IMAGE >&2
  exit 41
fi
/usr/local/bin/k3s kubectl delete namespace fw-sut --ignore-not-found --wait=true
/usr/local/bin/k3s kubectl create namespace fw-sut
/usr/local/bin/k3s kubectl apply -n fw-sut -f "$manifest"
if ! /usr/local/bin/k3s kubectl -n fw-sut exec deployment/flagd -c flagd-ui -- \
  grep -q '"emailMemoryLeak"' /app/data/demo.flagd.json; then
  /usr/local/bin/k3s kubectl -n fw-sut rollout restart deployment/flagd
fi
/usr/local/bin/k3s kubectl annotate namespace fw-sut \
  faultwitness.io/producer-sha={producer_sha} \
  faultwitness.io/image-set-digest={validation["image_set_digest"]} \
  faultwitness.io/sut-commit={SUT_COMMIT} --overwrite
deadline=$(($(date +%s) + {LAB_READINESS_DEADLINE_SECONDS}))
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
  if test "$(date +%s)" -ge "$deadline"; then
    printf 'FW_G02_LAB_DEPLOYMENT_TIMEOUT pending=%s\n' "$(echo $pending | tr '\\n' ',')"
    exit 43
  fi
  printf 'waiting for Deployments: %s\n' "$pending" >&2
  sleep 5
done
deadline=$(($(date +%s) + {LAB_READINESS_DEADLINE_SECONDS}))
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
  if test "$(date +%s)" -ge "$deadline"; then
    printf 'FW_G02_LAB_STATEFULSET_TIMEOUT pending=%s\n' "$pending"
    exit 44
  fi
  printf 'waiting for StatefulSet: %s\n' "$pending" >&2
  sleep 5
done
ready=$(/usr/local/bin/k3s kubectl -n fw-sut get deployment \
  -o jsonpath='{{range .items[*]}}{{.metadata.name}}={{.status.readyReplicas}}{{"\\n"}}{{end}}')
printf 'producer_sha=%s\nimage_set_digest=%s\n%s' \
  {producer_sha} {validation["image_set_digest"]} "$ready"
"""


def _host_stage_lab_manifest(config: Mapping[str, Any], producer_sha: str) -> None:
    """Fetch the pinned SUT manifest on the host itself, verifying the frozen digest there."""
    source = config["source"]
    workspace = f"/tmp/faultwitness-fault-lab-{producer_sha[:12]}"
    target = f"{workspace}/opentelemetry-demo.yaml"
    uri = shlex.quote(str(source["uri"]))
    expected = shlex.quote(str(source["sha256"]))
    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    owner = shlex.quote(bundle.server_username)
    script = f"""set -eu
group=$(id -gn {owner})
install -d -m 0700 -o {owner} -g "$group" {workspace}
target={target}
if test -f "$target" \\
    && test "$(sha256sum "$target" | cut -d' ' -f1)" = {expected}; then
  printf 'manifest=cached\\n'
  exit 0
fi
attempt=1
while test "$attempt" -le 5; do
  curl -sS -L -C - -m 900 -o "$target.part" {uri} || true
  if test -f "$target.part" \\
      && test "$(sha256sum "$target.part" | cut -d' ' -f1)" = {expected}; then
    mv -f "$target.part" "$target"
    chown {owner}:"$group" "$target"
    chmod 0600 "$target"
    printf 'manifest=fetched attempts=%s\\n' "$attempt"
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 5
done
printf 'FW_G02_MANIFEST_HOST_FETCH_FAILED\\n'
exit 1
"""
    output = run_remote_script(script, privileged=True)
    if "manifest=" not in output:
        raise GovernanceError("G02 manifest host staging produced no outcome line")


def _stage_lab_manifest(config: Mapping[str, Any], producer_sha: str) -> None:
    """Stage the manifest host-side; relay from the owner PC only if the host cannot fetch it."""
    try:
        _host_stage_lab_manifest(config, producer_sha)
        return
    except GovernanceError:
        pass
    _relay_lab_manifest_from_pc(config, producer_sha)


def _relay_lab_manifest_from_pc(config: Mapping[str, Any], producer_sha: str) -> None:
    source = config["source"]
    with urllib.request.urlopen(str(source["uri"])) as response:  # noqa: S310
        payload = response.read()
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != source["sha256"]:
        raise GovernanceError("G02 upstream manifest digest drifted on the owner host")
    appdata = Path.home() / "AppData" / "Local"
    cache = appdata / "FaultWitness" / "artifacts" / "fault-lab" / "opentelemetry-demo.yaml"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(payload)

    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    remote_name = f"fw-fault-lab-manifest-{producer_sha[:12]}.yaml"
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
    workspace = f"/tmp/faultwitness-fault-lab-{producer_sha[:12]}"
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


def render_host_image_staging_script(images: Mapping[str, str]) -> str:
    """Pull the Docker Hub staging set on the host and normalize each tag to its pinned ref.

    The owner PC sits behind a VPN that serves registry manifests but blocks layer blobs, so
    a PC-side pull plus scp relay is both slower and, for some registries, impossible. The
    host reaches every registry directly, and content it already holds needs no transfer.
    """
    script = "set -eu\nCTR=/usr/local/bin/k3s\n"
    for name in sorted(images):
        reference = images[name]
        normalized = containerd_normalized_reference(reference)
        digest = reference.rsplit("@", 1)[1]
        aliases = " ".join(
            shlex.quote(candidate) for candidate in containerd_registry_aliases(reference)
        )
        script += f"""
source_ref=
for candidate_ref in {aliases}; do
  observed=$($CTR ctr -n k8s.io images list 2>/dev/null | \\
    awk -v ref="$candidate_ref" '$1 == ref {{print $3; exit}}')
  if test "$observed" = {shlex.quote(digest)}; then source_ref="$candidate_ref"; break; fi
done
if test -z "$source_ref"; then
  attempt=1
  while test "$attempt" -le 4; do
    if $CTR ctr -n k8s.io images pull --platform linux/amd64 {shlex.quote(reference)} \\
        >/dev/null 2>&1; then
      break
    fi
    attempt=$((attempt + 1))
    sleep 5
  done
  for candidate_ref in {aliases}; do
    observed=$($CTR ctr -n k8s.io images list 2>/dev/null | \\
      awk -v ref="$candidate_ref" '$1 == ref {{print $3; exit}}')
    if test "$observed" = {shlex.quote(digest)}; then source_ref="$candidate_ref"; break; fi
  done
fi
if test -z "$source_ref"; then
  printf 'FW_G02_HOST_PULL_FAILED name={name}\\n'
  exit 42
fi
if test "$source_ref" != {shlex.quote(normalized)}; then
  $CTR ctr -n k8s.io images tag --force "$source_ref" {shlex.quote(normalized)} >/dev/null
fi
final=$($CTR ctr -n k8s.io images list 2>/dev/null | \\
  awk -v ref={shlex.quote(normalized)} '$1 == ref {{print $3; exit}}')
test "$final" = {shlex.quote(digest)}
printf 'staged={name}\\n'
"""
    return script


def _stage_lab_images(root: Path, config: Mapping[str, Any]) -> None:
    """Stage the Docker Hub image set host-side, relaying from the PC only as a fallback."""
    images = offline_staging_inventory(root, config)
    try:
        output = run_remote_script(render_host_image_staging_script(images), privileged=True)
    except GovernanceError:
        _relay_lab_images_from_pc(root, config)
        return
    staged = {line.split("=", 1)[1] for line in output.splitlines() if line.startswith("staged=")}
    missing = sorted(set(images).difference(staged))
    if missing:
        raise GovernanceError("G02 host image staging did not confirm: " + ", ".join(missing))


def _relay_lab_images_from_pc(root: Path, config: Mapping[str, Any]) -> None:
    images = offline_staging_inventory(root, config)
    crane = _ensure_crane(root)
    private_root = InfraPaths.defaults().evidence_dir.parent.parent
    archive_root = private_root / "artifacts" / "fault-lab" / "images"
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
            f'  /usr/local/bin/k3s ctr images tag --force "$source_ref" {target}\n'
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


def select_containerd_import_source(reference: str, inventory: Mapping[str, str]) -> str:
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


def deploy_g02_lab(root: Path) -> dict[str, Any]:
    """Deploy the fault lab from actual content, allowing targeted dirty-tree debug."""
    config = load_lab_config(root)
    validation = validate_lab_bootstrap(config)
    provenance = producer_provenance(
        root,
        [root / "config" / "g02", root / "src" / "faultwitness_dev" / "g02_lab.py"],
    )
    _stage_lab_manifest(config, provenance.producer_sha)
    _stage_lab_images(root, config)
    output = run_remote_script(
        render_k3s_bootstrap_script(config, provenance.producer_sha), privileged=True
    )
    ready = {
        key: int(value or "0")
        for key, value in (
            line.split("=", 1)
            for line in output.splitlines()
            if "=" in line and not line.startswith(("producer_sha=", "image_set_digest="))
        )
    }
    if not ready or any(count < 1 for count in ready.values()):
        raise GovernanceError("G02 lab bootstrap completed without all deployments ready")
    return {
        **validation,
        "producer_sha": provenance.producer_sha,
        "source_digest": provenance.source_digest,
        "dirty": provenance.dirty,
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
            item["cpu_rate"]
            >= max(
                AD_CPU_ACTIVE_MIN_CORES,
                item["baseline_cpu_max"] * AD_CPU_ACTIVE_MULTIPLIER,
            )
            and item["correlated_span"]
            for item in observations
        )
    elif fault_class == "emailMemoryLeak":
        baseline = max(
            float(first["baseline_working_set"]),
            float(second["baseline_working_set"]),
        )
        minimum_growth = max(
            EMAIL_MEMORY_MIN_GROWTH_BYTES,
            baseline * EMAIL_MEMORY_MIN_GROWTH_RATIO,
        )
        active = (
            float(second["working_set"]) - baseline >= minimum_growth
            and float(second["working_set"]) - float(first["working_set"]) >= minimum_growth
        )
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
    primary_error: Exception | None = None
    cleanup_error: Exception | None = None
    try:
        injected = _mutated_document(original, adapter)
        client.write(injected)
        if client.read() != injected:
            raise GovernanceError("fault injection readback mismatch")
        fault_observations = [observer("fault", fault_class), observer("fault", fault_class)]
        if fault_state(str(fault_class), fault_observations) != OracleState.FAULT_ACTIVE:
            raise GovernanceError("fault oracle did not reach FAULT_ACTIVE")
    except Exception as error:
        primary_error = error
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
        raise GovernanceError(
            f"scenario cleanup blocked and quarantined the SUT: {cleanup_error}"
        ) from cleanup_error
    if primary_error is not None:
        raise primary_error
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
    producer_sha: str,
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
        trial_id = f"g02-scenario-{scenario['scenario_id'].casefold()}"
        cache_key = semantic_cache_key(
            {
                "sut": bootstrap["image_set_digest"],
                "trace_service": hashlib.sha256(
                    b"g02-live-scenario-observer-contract-v2"
                ).hexdigest(),
            },
            ("sut", "trace_service"),
            input_digest=hashlib.sha256(canonical_json(scenario).encode()).hexdigest(),
        )
        previous = journal.read(trial_id)
        if previous and previous.get("status") == "pass" and previous.get("cache_key") == cache_key:
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
        if (
            previous
            and previous.get("cache_key") == cache_key
            and previous.get("status") in {"metric_fail", "blocked"}
        ):
            return {
                "status": previous["status"],
                "validation": "V-G02-006",
                "scenario_count": len(completed),
                "failed_trial": trial_id,
                "trials": [*completed, previous],
            }
        journal.begin(
            trial_id,
            producer_sha=producer_sha,
            cache_key=cache_key,
            payload={
                "scenario_id": scenario["scenario_id"],
                "fault_class": scenario["fault_action"]["class"],
            },
        )
        try:
            result = run_scenario(
                scenario,
                client_factory(producer_sha),
                observer_factory(producer_sha, str(scenario["fault_action"]["class"])),
                precondition_recovery=precondition_recovery,
            )
            packet = build_observation_packet(scenario, result["fault_observations"])
            record = journal.finish(
                trial_id,
                "pass",
                {
                    "scenario_id": scenario["scenario_id"],
                    "fault_class": scenario["fault_action"]["class"],
                    "result": result,
                    "observation_packet": packet,
                },
            )
        except InfrastructureFailure as exc:
            record = journal.finish(
                trial_id,
                "infra_failed",
                {
                    "scenario_id": scenario["scenario_id"],
                    "fault_class": scenario["fault_action"]["class"],
                    "reason": str(exc),
                },
            )
            return {
                "status": "infra_failed",
                "validation": "V-G02-006",
                "scenario_count": len(completed),
                "failed_trial": trial_id,
                "trials": [*completed, record],
            }
        except GovernanceError as exc:
            record = journal.finish(
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


def replay_resource_scenarios(
    root: Path,
    producer_sha: str,
    frozen_document: Mapping[str, Any],
    journal: TrialJournalProtocol,
    *,
    sut_producer_sha: str | None = None,
    client_factory: Callable[[str], FlagDocumentClient] = RemoteFlagClient,
    observer_factory: Callable[[str, str], Observer] = LiveScenarioObserver,
) -> dict[str, Any]:
    """Replay only the eight resource cases whose observation semantics changed."""
    frozen_trials = frozen_document.get("trials")
    if not isinstance(frozen_trials, list) or len(frozen_trials) != 32:
        raise GovernanceError("resource replay requires the frozen 32-case scenario artifact")
    frozen_by_case: dict[str, dict[str, Any]] = {}
    for record in frozen_trials:
        if not isinstance(record, dict) or record.get("status") != "pass":
            raise GovernanceError("resource replay cannot inherit an incomplete frozen case")
        payload = record.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("scenario_id"), str):
            raise GovernanceError("resource replay found a malformed frozen case")
        frozen_by_case[str(payload["scenario_id"])] = dict(record)
    if len(frozen_by_case) != 32:
        raise GovernanceError("resource replay found duplicate frozen case IDs")

    config = load_lab_config(root)
    bootstrap = validate_lab_bootstrap(config)
    seeds = seed_catalog(bootstrap["image_set_digest"])
    validate_seed_catalog(seeds, bootstrap["image_set_digest"])
    resource_ids = {
        str(seed["scenario_id"]) for seed in seeds if seed["family"] == "resource_capacity"
    }
    if len(resource_ids) != 8:
        raise GovernanceError("resource replay must select exactly eight cases")

    replacements: dict[str, dict[str, Any]] = {}
    observed_sut_sha = sut_producer_sha or producer_sha
    if not FULL_SHA.fullmatch(observed_sut_sha):
        raise GovernanceError("resource replay requires a full SUT producer SHA")
    from faultwitness_dev.g02_baselines import build_observation_packet

    for scenario in seeds:
        case_id = str(scenario["scenario_id"])
        if case_id not in resource_ids:
            continue
        fault_class = str(scenario["fault_action"]["class"])
        observer_contract = (
            b"g02-resource-observer-contract-email-v5"
            if fault_class == "emailMemoryLeak"
            else b"g02-resource-observer-contract-v4"
        )
        trial_id = f"g02-v2-resource-{case_id.casefold()}"
        cache_key = semantic_cache_key(
            {
                "sut": bootstrap["image_set_digest"],
                "trace_service": hashlib.sha256(observer_contract).hexdigest(),
            },
            ("sut", "trace_service"),
            input_digest=hashlib.sha256(canonical_json(scenario).encode()).hexdigest(),
        )
        previous = journal.read(trial_id)
        if previous and previous.get("status") == "pass" and previous.get("cache_key") == cache_key:
            replacements[case_id] = previous
            continue
        if (
            previous
            and previous.get("cache_key") == cache_key
            and previous.get("status") in {"metric_fail", "blocked"}
        ):
            raise GovernanceError(f"resource case {case_id} requires a semantic fix before replay")
        journal.begin(
            trial_id,
            producer_sha=producer_sha,
            cache_key=cache_key,
            payload={
                "scenario_id": case_id,
                "fault_class": fault_class,
            },
        )
        try:
            result = run_scenario(
                scenario,
                client_factory(observed_sut_sha),
                observer_factory(
                    observed_sut_sha,
                    fault_class,
                ),
            )
            packet = build_observation_packet(scenario, result["fault_observations"])
            record = journal.finish(
                trial_id,
                "pass",
                {
                    "scenario_id": case_id,
                    "fault_class": fault_class,
                    "result": result,
                    "observation_packet": packet,
                },
            )
        except InfrastructureFailure as exc:
            journal.finish(
                trial_id,
                "infra_failed",
                {
                    "scenario_id": case_id,
                    "fault_class": fault_class,
                    "reason": str(exc),
                },
            )
            raise
        except GovernanceError as exc:
            journal.finish(
                trial_id,
                "metric_fail",
                {
                    "scenario_id": case_id,
                    "fault_class": fault_class,
                    "reason": str(exc),
                },
            )
            raise
        replacements[case_id] = record

    combined = [
        replacements.get(str(seed["scenario_id"]), frozen_by_case[str(seed["scenario_id"])])
        for seed in seeds
    ]
    packets = [dict(record["payload"]["observation_packet"]) for record in combined]
    return {
        "status": "pass",
        "validation": "G03-READINESS-RESOURCE-REPLAY",
        "scenario_count": 32,
        "inherited_case_count": 24,
        "replayed_case_count": 8,
        "replayed_case_ids": sorted(resource_ids),
        "trials": combined,
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
        "adHighCpu": {"cpu_rate": 6.0, "baseline_cpu_max": 1.0, "correlated_span": True},
        "emailMemoryLeak": {
            "working_set": 3 * 1024 * 1024,
            "baseline_working_set": 1 * 1024 * 1024,
        },
        "paymentFailure": {"checkout_failed": True, "payment_error": True},
        "paymentUnreachable": {"checkout_failed": True, "connection_error": True},
        "kafkaQueueProblems": {"consumer_lag": 2.0, "baseline_lag": 1.0, "kafka_error": True},
    }[fault_class]


def scripted_sequence_observer() -> Observer:
    memory_samples = iter((3 * 1024 * 1024, 5 * 1024 * 1024))

    def observe(phase: str, fault_class: str) -> Observation:
        if phase == "fault" and fault_class == "emailMemoryLeak":
            return {
                "working_set": next(memory_samples),
                "baseline_working_set": 1 * 1024 * 1024,
            }
        return scripted_observer(phase, fault_class)

    return observe


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
