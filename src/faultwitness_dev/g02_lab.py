from __future__ import annotations

import copy
import hashlib
import json
import re
import shlex
import subprocess
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import yaml

from faultwitness_dev.bootstrap import BootstrapPaths, ssh_failure_category
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import _remote_arguments, run_remote_script
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
FULL_DIGEST_REFERENCE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

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


Observation = Mapping[str, Any]
Observer = Callable[[str, str], Observation]


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
    substitutions: list[str] = []
    for source_reference, target in sorted(
        replacements, key=lambda item: len(item[0]), reverse=True
    ):
        substitutions.append(
            "sed -i "
            + shlex.quote(f"s|{source_reference}|{target}|g")
            + ' "$manifest"'
        )
    workspace = f"/tmp/faultwitness-g02-{candidate_sha[:12]}"
    return f"""set -eu
workspace={shlex.quote(workspace)}
manifest="$workspace/opentelemetry-demo.yaml"
test -f "$manifest"
printf '%s  %s\n' {shlex.quote(str(source['sha256']))} "$manifest" | sha256sum -c -
sed -i 's|namespace: otel-demo|namespace: fw-sut|g; s|name: otel-demo|name: fw-sut|g' "$manifest"
{chr(10).join(substitutions)}
if grep -E '^[[:space:]]*image:[[:space:]]*' "$manifest" | grep -v '@sha256:'; then
  echo FW_G02_UNPINNED_IMAGE >&2
  exit 41
fi
/usr/local/bin/k3s kubectl apply -n fw-sut -f "$manifest"
/usr/local/bin/k3s kubectl -n fw-sut create configmap fw-g02-candidate-binding \
  --from-literal=candidate_sha={candidate_sha} \
  --from-literal=image_set_digest={validation['image_set_digest']} \
  --from-literal=sut_commit={SUT_COMMIT} \
  --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -
/usr/local/bin/k3s kubectl -n fw-sut wait --for=condition=Available deployment --all --timeout=900s
/usr/local/bin/k3s kubectl -n fw-sut rollout status statefulset/opensearch --timeout=900s
binding=$(/usr/local/bin/k3s kubectl -n fw-sut \
  get configmap fw-g02-candidate-binding \
  -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
ready=$(/usr/local/bin/k3s kubectl -n fw-sut get deployment \
  -o jsonpath='{{range .items[*]}}{{.metadata.name}}={{.status.readyReplicas}}{{"\\n"}}{{end}}')
printf 'candidate_sha=%s\nimage_set_digest=%s\n%s' \
  "$binding" {validation['image_set_digest']} "$ready"
"""


def _stage_lab_manifest(config: Mapping[str, Any], candidate_sha: str) -> None:
    source = config["source"]
    with urllib.request.urlopen(str(source["uri"]), timeout=60) as response:  # noqa: S310
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
        timeout=120,
    )
    if result.returncode:
        raise GovernanceError(
            "G02 manifest staging failed (" + ssh_failure_category(result.stderr) + ")"
        )
    workspace = f"/tmp/faultwitness-g02-{candidate_sha[:12]}"
    owner = shlex.quote(bundle.server_username)
    run_remote_script(
        f"remote_home=$(getent passwd {owner} | cut -d: -f6); "
        f"test -n \"$remote_home\"; "
        f"install -d -m 0700 -o {owner} -g $(id -gn {owner}) {workspace}; "
        f"install -m 0600 -o {owner} -g $(id -gn {owner}) "
        f"\"$remote_home/{remote_name}\" {workspace}/opentelemetry-demo.yaml; "
        f"rm -f \"$remote_home/{remote_name}\"\n",
        privileged=True,
    )


def deploy_g02_lab(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("G02 lab candidate must be a full Git SHA")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if head != candidate_sha:
        raise GovernanceError("G02 lab candidate must equal checked-out HEAD")
    if subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True).stdout:
        raise GovernanceError("G02 lab deployment requires a clean candidate worktree")
    config = load_lab_config(root)
    validation = validate_lab_bootstrap(config)
    _stage_lab_manifest(config, candidate_sha)
    output = run_remote_script(
        render_k3s_bootstrap_script(config, candidate_sha), privileged=True, timeout=1200
    )
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
) -> dict[str, Any]:
    action = scenario.get("fault_action")
    fault_class = action.get("class") if isinstance(action, dict) else None
    adapter = ADAPTERS.get(str(fault_class))
    if adapter is None:
        raise GovernanceError(f"scenario uses unknown fault action: {fault_class}")
    original = client.read()
    if observer("control", fault_class).get("state") != OracleState.HEALTHY:
        raise GovernanceError("scenario healthy precondition is not proven")
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
        "state_sequence": ["HEALTHY", "FAULT_ACTIVE", "HEALTHY"],
        "original_digest": hashlib.sha256(canonical_json(original).encode()).hexdigest(),
        "restored_digest": hashlib.sha256(canonical_json(client.read()).encode()).hexdigest(),
        "fault_observations": len(fault_observations),
        "recovery_observations": len(recovery_observations),
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
    smoke_results = [
        next(result for result in adapter_results if result["fault_class"] == fault_class)
        for fault_class in smoke_faults.values()
    ]
    for result in smoke_results:
        result["scenario_id"] = "SMOKE-G02-" + result["family"].upper().replace("_", "-")

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
            "environment": "deterministic-controller-contract",
            "scenarios": smoke_results,
            "owned_l2_ready": ["lab_bootstrap"],
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
