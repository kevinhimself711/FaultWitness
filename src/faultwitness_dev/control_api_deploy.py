# ruff: noqa: E501 -- remote shell and Kubernetes manifests remain literal for auditability.

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import os
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from faultwitness_dev.bootstrap import BootstrapPaths
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import (
    _ensure_crane,
    _pull_image_archive,
    _remote_arguments,
    run_remote_script,
    ssh_failure_category,
)

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
BASE_IMAGE = "python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49"


def _tracked_files(root: Path) -> list[Path]:
    files = [
        root / "deploy" / "control-api" / "Dockerfile",
        root / "deploy" / "control-api" / "requirements.lock",
        root / "pyproject.toml",
        root / "README.md",
    ]
    files.extend(path for path in sorted((root / "src").rglob("*")) if path.is_file())
    return files


def _assert_candidate(root: Path, candidate_sha: str, files: list[Path]) -> None:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if head != candidate_sha:
        raise GovernanceError("candidate SHA does not match repository HEAD")
    relative = [str(path.relative_to(root)) for path in files]
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *relative],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if dirty.strip():
        raise GovernanceError("Control API deployment inputs differ from immutable candidate")


def _context(root: Path, files: list[Path]) -> tuple[str, str]:
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in files:
            name = path.relative_to(root).as_posix()
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with path.open("rb") as source:
                archive.addfile(info, source)
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressed:
        compressed.write(tar_stream.getvalue())
    payload = stream.getvalue()
    return base64.b64encode(payload).decode(), hashlib.sha256(payload).hexdigest()


def _stage_base_image(root: Path) -> None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise GovernanceError("APPDATA is required for private image staging")
    archive = Path(appdata) / "FaultWitness" / "artifacts" / "I-0012" / "python-base.tar"
    crane = _ensure_crane(root)
    _pull_image_archive(crane, BASE_IMAGE, archive)
    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    arguments = [
        "scp",
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
        str(archive),
        f"{bundle.server_username}@{bundle.server_host}:faultwitness-i0012-python-base.tar",
    ]
    result = subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise GovernanceError(
            "base image staging failed (" + ssh_failure_category(result.stderr) + ")"
        )
    run_remote_script(
        'install -m 0600 "$HOME/faultwitness-i0012-python-base.tar" '
        "/tmp/faultwitness-i0012-python-base.tar; "
        'rm -f "$HOME/faultwitness-i0012-python-base.tar"\n',
        privileged=False,
    )


def deploy_control_api(root: Path, candidate_sha: str) -> dict[str, Any]:
    files = _tracked_files(root)
    _assert_candidate(root, candidate_sha, files)
    encoded, bundle_digest = _context(root, files)
    _stage_base_image(root)
    image = f"docker.io/faultwitness/control-api:{candidate_sha}"
    manifest = _manifest(candidate_sha, image)
    manifest_encoded = base64.b64encode(manifest.encode()).decode()
    script = f"""set -eu
work=$(mktemp -d /tmp/faultwitness-i0012-build.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
docker load -i /tmp/faultwitness-i0012-python-base.tar >/dev/null
printf %s {encoded} | base64 -d >"$work/context.tgz"
test "$(sha256sum "$work/context.tgz" | awk '{{print $1}}')" = {bundle_digest}
tar -xzf "$work/context.tgz" -C "$work"
docker build --pull=false --label faultwitness.candidate={candidate_sha} -t {image} -f "$work/deploy/control-api/Dockerfile" "$work" >/dev/null
docker save {image} -o "$work/control-api.tar"
/usr/local/bin/k3s ctr images import "$work/control-api.tar" >/dev/null
/usr/local/bin/k3s kubectl create namespace fw-control --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl label namespace fw-control kubernetes.io/metadata.name=fw-control faultwitness.io/boundary=control --overwrite >/dev/null
/usr/local/bin/k3s kubectl -n fw-data get secret fw-postgres-env -o json | python3 -c 'import json,sys; d=json.load(sys.stdin); d["metadata"]={{"name":"fw-control-postgres-env","namespace":"fw-control"}}; d.pop("type",None); print(json.dumps(d))' | /usr/local/bin/k3s kubectl apply -f - >/dev/null
printf %s {manifest_encoded} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl -n fw-control rollout status deployment/control-api --timeout=5m >/dev/null
"""
    run_remote_script(script, privileged=True, timeout=900)
    return {
        "candidate_sha": candidate_sha,
        "bundle_sha256": bundle_digest,
        "image": image,
    }


def inspect_control_api(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    script = f"""set -eu
available=$(/usr/local/bin/k3s kubectl -n fw-control get deployment control-api -o jsonpath='{{.status.availableReplicas}}')
ready=$(/usr/local/bin/k3s kubectl -n fw-control get deployment control-api -o jsonpath='{{.status.readyReplicas}}')
binding=$(/usr/local/bin/k3s kubectl -n fw-control get configmap fw-control-api-candidate -o jsonpath='{{.data.candidate_sha}}')
service_type=$(/usr/local/bin/k3s kubectl -n fw-control get service control-api -o jsonpath='{{.spec.type}}')
test "$available" = 1
test "$ready" = 1
test "$binding" = {candidate_sha}
test "$service_type" = ClusterIP
printf '%s %s %s\n' "$available" "$ready" "$service_type"
"""
    fields = run_remote_script(script, privileged=True).strip().split()
    if fields != ["1", "1", "ClusterIP"]:
        raise GovernanceError("Control API deployment is not Ready")
    return {"candidate_sha": candidate_sha, "available": 1, "ready": 1, "service_type": "ClusterIP"}


def _manifest(candidate_sha: str, image: str) -> str:
    return f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: fw-control-api-candidate
  namespace: fw-control
data:
  candidate_sha: {candidate_sha}
---
apiVersion: v1
kind: ServiceAccount
metadata: {{name: control-api, namespace: fw-control}}
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: control-api
  namespace: fw-control
spec:
  replicas: 1
  selector: {{matchLabels: {{app.kubernetes.io/name: control-api}}}}
  template:
    metadata: {{labels: {{app.kubernetes.io/name: control-api, faultwitness.io/candidate: "{candidate_sha}"}}}}
    spec:
      serviceAccountName: control-api
      automountServiceAccountToken: false
      securityContext: {{seccompProfile: {{type: RuntimeDefault}}}}
      containers:
        - name: control-api
          image: {image}
          imagePullPolicy: Never
          envFrom: [{{secretRef: {{name: fw-control-postgres-env}}}}]
          env:
            - {{name: FW_OIDC_ISSUER, value: "http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness"}}
            - {{name: FW_OIDC_AUDIENCE, value: "faultwitness-api"}}
            - {{name: FW_OIDC_JWKS_URL, value: "http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness/protocol/openid-connect/certs"}}
          ports: [{{name: http, containerPort: 8000}}]
          readinessProbe: {{tcpSocket: {{port: http}}, periodSeconds: 5, failureThreshold: 12}}
          livenessProbe: {{tcpSocket: {{port: http}}, periodSeconds: 15, failureThreshold: 3}}
          resources:
            requests: {{cpu: 100m, memory: 192Mi}}
            limits: {{cpu: "1", memory: 512Mi}}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            capabilities: {{drop: [ALL]}}
---
apiVersion: v1
kind: Service
metadata: {{name: control-api, namespace: fw-control}}
spec:
  type: ClusterIP
  selector: {{app.kubernetes.io/name: control-api}}
  ports: [{{name: http, port: 8000, targetPort: http}}]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: control-api-default-deny, namespace: fw-control}}
spec: {{podSelector: {{}}, policyTypes: [Ingress, Egress]}}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: control-api-explicit-traffic, namespace: fw-control}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: control-api}}}}
  policyTypes: [Ingress, Egress]
  ingress:
    - from: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}}}]
      ports: [{{protocol: TCP, port: 8000}}]
  egress:
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: kube-system}}}}}}]
      ports: [{{protocol: UDP, port: 53}}, {{protocol: TCP, port: 53}}]
    - to:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-data}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: postgres}}}}
      ports: [{{protocol: TCP, port: 5432}}]
    - to:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-system}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: keycloak}}}}
      ports: [{{protocol: TCP, port: 8080}}]
"""
