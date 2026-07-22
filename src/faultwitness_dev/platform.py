from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from faultwitness_dev.bootstrap import _atomic_write
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import run_remote_script

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE_NAME = "fw-platform"
NAMESPACE = "fw-system"
WORKLOAD_SELECTOR = "app.kubernetes.io/part-of=faultwitness-platform"
PLATFORM_NAMESPACES = {"fw-data", "fw-observability", "fw-system"}


@dataclass(frozen=True)
class PlatformPaths:
    evidence_dir: Path

    @classmethod
    def defaults(cls) -> PlatformPaths:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise GovernanceError("APPDATA is required for private platform evidence")
        return cls(Path(appdata) / "FaultWitness" / "evidence" / "I-0009")


def _assert_candidate(root: Path, candidate_sha: str, tracked_paths: list[Path]) -> None:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if head != candidate_sha:
        raise GovernanceError("candidate SHA does not match the checked-out repository HEAD")
    try:
        relative = [str(path.resolve().relative_to(root.resolve())) for path in tracked_paths]
    except ValueError as error:
        raise GovernanceError(
            "platform deployment inputs must remain inside the repository"
        ) from error
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *relative],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    if dirty.strip():
        raise GovernanceError("platform deployment inputs differ from the immutable candidate")


def _deployment_files(chart: Path, values: Path) -> list[tuple[Path, str]]:
    if not chart.is_dir() or not (chart / "Chart.yaml").is_file():
        raise GovernanceError("platform Helm chart or Chart.yaml is missing")
    if not values.is_file():
        raise GovernanceError("private-server Helm values are missing")
    files: list[tuple[Path, str]] = []
    for path in sorted(chart.rglob("*")):
        if path.is_symlink():
            raise GovernanceError("platform deployment inputs may not contain symlinks")
        if path.is_file():
            files.append((path, "chart/" + path.relative_to(chart).as_posix()))
    files.append((values, "values.yaml"))
    if not files:
        raise GovernanceError("platform deployment bundle is empty")
    return files


def _validate_values(values: Path) -> None:
    try:
        document = yaml.safe_load(values.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise GovernanceError("private-server values are not valid UTF-8 YAML") from error
    if not isinstance(document, dict):
        raise GovernanceError("private-server values must be a YAML mapping")


def _bundle(files: list[tuple[Path, str]]) -> tuple[str, str]:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path, name in files:
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with path.open("rb") as source:
                archive.addfile(info, source)
    payload = stream.getvalue()
    return base64.b64encode(payload).decode("ascii"), hashlib.sha256(payload).hexdigest()


def deploy_platform(
    root: Path,
    candidate_sha: str,
    *,
    chart: Path | None = None,
    values: Path | None = None,
    evidence_paths: PlatformPaths | None = None,
) -> dict[str, Any]:
    chart = chart or root / "deploy" / "charts" / "faultwitness-platform"
    values = values or root / "deploy" / "environments" / "private-server" / "values.yaml"
    _assert_candidate(root, candidate_sha, [chart, values])
    _validate_values(values)
    encoded, bundle_digest = _bundle(_deployment_files(chart, values))
    script = f"""set -eu
step=bootstrap
on_exit() {{
  status=$?
  if test "$status" -ne 0; then
    printf 'FW_PLATFORM_DEPLOY_FAILED step=%s status=%s\n' "$step" "$status" >&2
  fi
}}
trap on_exit EXIT
work=$(mktemp -d /tmp/faultwitness-i0009.XXXXXX)
cleanup() {{ rm -rf "$work"; }}
trap cleanup HUP INT TERM
step=dependency-secrets
for dependency in \
  fw-data/fw-postgres-env fw-data/fw-redis-env fw-data/fw-qdrant-env \
  fw-data/fw-minio-env fw-system/fw-keycloak-env fw-observability/fw-grafana-env; do
  namespace=${{dependency%/*}}
  name=${{dependency#*/}}
  if ! /usr/local/bin/k3s kubectl -n "$namespace" get secret "$name" >/dev/null 2>&1; then
    printf 'FW_PLATFORM_DEPENDENCY_MISSING kind=Secret namespace=%s name=%s\n' \
      "$namespace" "$name" >&2
    exit 1
  fi
done
step=decode-bundle
printf %s {encoded} | base64 -d >"$work/platform.tgz"
actual=$(sha256sum "$work/platform.tgz" | awk '{{print $1}}')
test "$actual" = {bundle_digest}
tar -xzf "$work/platform.tgz" -C "$work"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
step=helm-lint
/usr/local/bin/helm lint "$work/chart" -f "$work/values.yaml" >/dev/null
step=helm-upgrade
/usr/local/bin/helm upgrade --install {RELEASE_NAME} "$work/chart" \
  --namespace {NAMESPACE} --create-namespace -f "$work/values.yaml" \
  --atomic --wait --timeout 15m >/dev/null
step=candidate-binding
/usr/local/bin/k3s kubectl -n {NAMESPACE} create configmap fw-platform-candidate-binding \
  --from-literal=candidate_sha={candidate_sha} \
  --from-literal=bundle_sha256={bundle_digest} --dry-run=client -o yaml \
  | /usr/local/bin/k3s kubectl apply -f - >/dev/null
step=cleanup
cleanup
"""
    run_remote_script(script, privileged=True, timeout=1200)
    evidence = evidence_paths or PlatformPaths.defaults()
    evidence.evidence_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "captured_at": datetime.now(UTC).isoformat(),
        "release": RELEASE_NAME,
        "namespace": NAMESPACE,
        "deployment_bundle_sha256": bundle_digest,
        "status": "deployed",
    }
    _atomic_write(
        evidence.evidence_dir / "deployment-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def _sanitize_inventory(raw: str, candidate_sha: str) -> dict[str, Any]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GovernanceError("platform inventory returned invalid JSON") from error
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise GovernanceError("platform inventory contains no managed workloads")
    workloads: list[dict[str, Any]] = []
    failures: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise GovernanceError("platform inventory contains a malformed item")
        kind = item.get("kind")
        metadata = item.get("metadata", {})
        status = item.get("status", {})
        spec = item.get("spec", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace")
        labels = metadata.get("labels") or {}
        pod_labels = spec.get("template", {}).get("metadata", {}).get("labels") or {}
        if not isinstance(labels, dict) or not isinstance(pod_labels, dict):
            raise GovernanceError("platform inventory contains malformed labels")
        if namespace not in PLATFORM_NAMESPACES or (
            labels.get("app.kubernetes.io/part-of") != "faultwitness-platform"
            and pod_labels.get("app.kubernetes.io/part-of") != "faultwitness-platform"
        ):
            continue
        if kind not in {"Deployment", "StatefulSet", "DaemonSet"} or not all(
            isinstance(value, str) and value for value in (name, namespace)
        ):
            raise GovernanceError("platform inventory contains an unexpected resource")
        desired = (
            status.get("desiredNumberScheduled", 0)
            if kind == "DaemonSet"
            else spec.get("replicas", 1)
        )
        ready = (
            status.get("numberReady", 0) if kind == "DaemonSet" else status.get("readyReplicas", 0)
        )
        if not isinstance(desired, int) or not isinstance(ready, int):
            raise GovernanceError("platform inventory contains invalid readiness counters")
        record = {
            "kind": kind,
            "namespace": namespace,
            "name": name,
            "desired": desired,
            "ready": ready,
            "observed_generation": status.get("observedGeneration", 0),
            "generation": metadata.get("generation", 0),
        }
        workloads.append(record)
        if desired < 1 or ready != desired or record["observed_generation"] != record["generation"]:
            failures.append(f"{namespace}/{kind}/{name}")
    if not workloads:
        raise GovernanceError("platform inventory contains no managed workloads")
    workloads.sort(key=lambda item: (item["namespace"], item["kind"], item["name"]))
    if failures:
        raise GovernanceError("platform workloads are not Ready: " + ", ".join(sorted(failures)))
    return {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "captured_at": datetime.now(UTC).isoformat(),
        "selector": WORKLOAD_SELECTOR,
        "workload_count": len(workloads),
        "workloads": workloads,
        "status": "pass",
    }


def inspect_platform_readiness(
    root: Path,
    candidate_sha: str,
    *,
    stability_seconds: int = 0,
    evidence_paths: PlatformPaths | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if stability_seconds < 0 or stability_seconds > 3600:
        raise GovernanceError("stability seconds must be between 0 and 3600")
    _assert_candidate(root, candidate_sha, [])
    deadline = clock() + stability_seconds
    latest: dict[str, Any] | None = None
    while True:
        raw = run_remote_script(
            "set -eu\n"
            "binding=$(/usr/local/bin/k3s kubectl -n fw-system get configmap "
            "fw-platform-candidate-binding -o jsonpath='{.data.candidate_sha}')\n"
            f'if test "$binding" != {candidate_sha}; then\n'
            "  echo 'FW_PLATFORM_CANDIDATE_MISMATCH' >&2\n"
            "  exit 1\n"
            "fi\n"
            "/usr/local/bin/k3s kubectl get deployment,statefulset,daemonset -A -o json\n",
            privileged=True,
            timeout=120,
        )
        latest = _sanitize_inventory(raw, candidate_sha)
        now = clock()
        if now >= deadline:
            break
        sleeper(min(5.0, max(0.0, deadline - now)))
    assert latest is not None
    latest["stability_seconds"] = stability_seconds
    evidence = evidence_paths or PlatformPaths.defaults()
    evidence.evidence_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        evidence.evidence_dir / "readiness-summary.json",
        json.dumps(latest, indent=2, sort_keys=True) + "\n",
    )
    return latest
