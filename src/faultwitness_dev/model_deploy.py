# ruff: noqa: E501 -- audited remote scripts and manifests remain literal.

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    default_sops_executable,
    load_secret_bundle,
)
from faultwitness_dev.control_api_deploy import (
    _context,
    _stage_base_image,
    _stage_file,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import run_remote_script
from faultwitness_dev.provenance import producer_provenance


def _tracked_files(root: Path) -> list[Path]:
    files = [
        root / "deploy/model-gateway/Dockerfile",
        root / "deploy/control-api/requirements.lock",
        root / "config/models/catalog.yaml",
        root / "pyproject.toml",
        root / "README.md",
    ]
    files.extend(path for path in sorted((root / "src").rglob("*")) if path.is_file())
    return files


def deploy_model_gateway(root: Path) -> dict[str, Any]:
    files = _tracked_files(root)
    provenance = producer_provenance(root, files)
    payload, bundle_digest = _context(root, files)
    paths = BootstrapPaths.defaults()
    artifact = paths.config_root / "artifacts" / "model-gateway" / "context.tgz"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(payload)
    _stage_base_image(root)
    _stage_file(artifact, "faultwitness-model-gateway-context.tgz")
    secret = load_secret_bundle(paths, default_sops_executable())
    credential_encoded = base64.b64encode(secret.bailian_api_key.encode()).decode()
    image = (
        "docker.io/faultwitness/model-gateway:"
        f"{provenance.producer_sha[:12]}-{bundle_digest[:12]}"
    )
    manifest = base64.b64encode(
        _manifest(provenance.producer_sha, bundle_digest, image).encode()
    ).decode()
    script = f"""set -eu
work=$(mktemp -d /tmp/faultwitness-model-gateway.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
docker load -i /tmp/faultwitness-control-api-python-base.tar >/dev/null
install -m 0600 /tmp/faultwitness-model-gateway-context.tgz "$work/context.tgz"
test "$(sha256sum "$work/context.tgz" | awk '{{print $1}}')" = {bundle_digest}
tar -xzf "$work/context.tgz" -C "$work"
docker build --pull=false --label faultwitness.producer={provenance.producer_sha} --label faultwitness.source-digest={bundle_digest} -t {image} -f "$work/deploy/model-gateway/Dockerfile" "$work" >/dev/null
docker save {image} -o "$work/model-gateway.tar"
/usr/local/bin/k3s ctr images import "$work/model-gateway.tar" >/dev/null
umask 077
printf %s {credential_encoded} | base64 -d >"$work/credential"
{{
  printf 'BAILIAN_API_KEY='
  cat "$work/credential"
  printf '\nMODEL_CATALOG_PATH=/opt/faultwitness/config/models/catalog.yaml\n'
  printf 'BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n'
  printf 'FW_OIDC_ISSUER=http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness\n'
  printf 'FW_OIDC_AUDIENCE=faultwitness-api\n'
  printf 'FW_OIDC_JWKS_URL=http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness/protocol/openid-connect/certs\n'
}} >"$work/model.env"
rm -f "$work/credential"
/usr/local/bin/k3s kubectl -n fw-control create secret generic fw-model-env --from-env-file="$work/model.env" --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f - >/dev/null
rm -f "$work/model.env"
printf %s {manifest} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl -n fw-control rollout status deployment/model-gateway >/dev/null
"""
    run_remote_script(script, privileged=True)
    return {
        "producer_sha": provenance.producer_sha,
        "source_digest": provenance.source_digest,
        "dirty": provenance.dirty,
        "bundle_sha256": bundle_digest,
        "image": image,
    }


def inspect_model_gateway() -> dict[str, Any]:
    output = run_remote_script(
        r"""set -eu
available=$(/usr/local/bin/k3s kubectl -n fw-control get deployment model-gateway -o jsonpath='{.status.availableReplicas}')
ready=$(/usr/local/bin/k3s kubectl -n fw-control get deployment model-gateway -o jsonpath='{.status.readyReplicas}')
service_type=$(/usr/local/bin/k3s kubectl -n fw-control get service model-gateway -o jsonpath='{.spec.type}')
image=$(/usr/local/bin/k3s kubectl -n fw-control get deployment model-gateway -o jsonpath='{.spec.template.spec.containers[0].image}')
producer=$(/usr/local/bin/k3s kubectl -n fw-control get deployment model-gateway -o jsonpath='{.spec.template.metadata.annotations.faultwitness\.io/producer-sha}')
source_digest=$(/usr/local/bin/k3s kubectl -n fw-control get deployment model-gateway -o jsonpath='{.spec.template.metadata.annotations.faultwitness\.io/source-digest}')
status=$(/usr/local/bin/k3s kubectl -n fw-control exec deployment/model-gateway -- python -c 'import httpx; print(httpx.get("http://127.0.0.1:8002/health/ready",timeout=5).status_code)')
test "$available" = 1
test "$ready" = 1
test "$service_type" = ClusterIP
test "$status" = 200
printf '%s %s %s %s %s %s\n' "$available" "$ready" "$service_type" "$image" "$producer" "$source_digest"
""",
        privileged=True,
    ).strip()
    fields = output.split()
    if len(fields) != 6 or fields[:3] != ["1", "1", "ClusterIP"]:
        raise GovernanceError("Model Gateway deployment is not Ready")
    return {
        "available": 1,
        "ready": 1,
        "service_type": "ClusterIP",
        "image": fields[3],
        "producer_sha": fields[4],
        "source_digest": fields[5],
    }


def run_model_gateway_smoke() -> dict[str, Any]:
    image = run_remote_script(
        "/usr/local/bin/k3s kubectl -n fw-control get deployment model-gateway "
        "-o jsonpath='{.spec.template.spec.containers[0].image}'\n",
        privileged=True,
    ).strip()
    if not image:
        raise GovernanceError("Model Gateway workload has no observed image")
    encoded = base64.b64encode(_smoke_manifest(image).encode()).decode()
    script = f"""set -eu
/usr/local/bin/k3s kubectl -n fw-system get secret fw-synthetic-users -o json | python3 -c 'import json,sys; d=json.load(sys.stdin); d["metadata"]={{"name":"fw-model-smoke-users","namespace":"fw-control"}}; d.pop("type",None); print(json.dumps(d))' | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl -n fw-control delete job model-gateway-smoke --ignore-not-found --wait=true >/dev/null
printf %s {encoded} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
while :; do
  succeeded=$(/usr/local/bin/k3s kubectl -n fw-control get job model-gateway-smoke -o jsonpath='{{.status.succeeded}}')
  failed=$(/usr/local/bin/k3s kubectl -n fw-control get job model-gateway-smoke -o jsonpath='{{.status.failed}}')
  test "$succeeded" = 1 && break
  test "$failed" = 1 && exit 1
  sleep 2
done
/usr/local/bin/k3s kubectl -n fw-control logs job/model-gateway-smoke
"""
    output = run_remote_script(script, privileged=True).strip()
    try:
        result = json.loads(output.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise GovernanceError("Model Gateway smoke returned malformed evidence") from error
    if result != {
        "family": "qwen",
        "model": "qwen3.7-plus-2026-05-26",
        "status": 200,
        "usage_attributed": True,
    }:
        raise GovernanceError("Model Gateway smoke did not satisfy its frozen outcome")
    return {"image": image, **result}


def _manifest(producer_sha: str, source_digest: str, image: str) -> str:
    return f"""apiVersion: v1
kind: ServiceAccount
metadata: {{name: model-gateway, namespace: fw-control}}
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata: {{name: model-gateway, namespace: fw-control}}
spec:
  replicas: 1
  selector: {{matchLabels: {{app.kubernetes.io/name: model-gateway}}}}
  template:
    metadata:
      labels: {{app.kubernetes.io/name: model-gateway}}
      annotations:
        faultwitness.io/producer-sha: "{producer_sha}"
        faultwitness.io/source-digest: "{source_digest}"
    spec:
      serviceAccountName: model-gateway
      automountServiceAccountToken: false
      securityContext: {{seccompProfile: {{type: RuntimeDefault}}}}
      containers:
        - name: model-gateway
          image: {image}
          imagePullPolicy: Never
          envFrom: [{{secretRef: {{name: fw-model-env}}}}]
          ports: [{{name: http, containerPort: 8002}}]
          readinessProbe: {{httpGet: {{path: /health/ready, port: http}}, periodSeconds: 5, timeoutSeconds: 3, failureThreshold: 12}}
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
metadata: {{name: model-gateway, namespace: fw-control}}
spec:
  type: ClusterIP
  selector: {{app.kubernetes.io/name: model-gateway}}
  ports: [{{name: http, port: 8002, targetPort: http}}]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: model-gateway-explicit-traffic, namespace: fw-control}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: model-gateway}}}}
  policyTypes: [Ingress, Egress]
  ingress:
    - from: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}}}]
      ports: [{{protocol: TCP, port: 8002}}]
  egress:
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: kube-system}}}}}}]
      ports: [{{protocol: UDP, port: 53}}, {{protocol: TCP, port: 53}}]
    - to:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-system}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: keycloak}}}}
      ports: [{{protocol: TCP, port: 8080}}]
    - to: [{{ipBlock: {{cidr: 0.0.0.0/0, except: [10.42.0.0/16, 10.43.0.0/16]}}}}]
      ports: [{{protocol: TCP, port: 443}}]
"""


def _smoke_manifest(image: str) -> str:
    return f"""apiVersion: v1
kind: ConfigMap
metadata: {{name: model-gateway-smoke, namespace: fw-control}}
data:
  smoke.py: |
    import json, os, time, httpx
    identity = "http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness/protocol/openid-connect/token"
    while True:
      try:
        token_response = httpx.post(identity, data={{"grant_type":"password","client_id":"faultwitness-api","username":"tenant-a-operator","password":os.environ["TENANT_A_OPERATOR"]}}, timeout=10)
        token_response.raise_for_status()
        token = token_response.json()["access_token"]
        break
      except httpx.TransportError:
        time.sleep(1)
    body = {{"correlation_id":"corr_01ARZ3NDEKTSV4RRFFQ69G5FAV","model_family":"qwen","messages":[{{"role":"user","content":"Reply with exactly OK."}}],"target_json_schema":None,"tool_schemas":[]}}
    response = httpx.post("http://model-gateway.fw-control.svc.cluster.local:8002/internal/v1/models/complete", headers={{"Authorization":"Bearer "+token}}, json=body, timeout=180)
    document = response.json()
    print(json.dumps({{"status":response.status_code,"family":(document.get("route") or {{}}).get("model_family"),"model":(document.get("route") or {{}}).get("resolved_model"),"usage_attributed":document.get("usage") is not None}}, sort_keys=True))
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: model-gateway-smoke-egress, namespace: fw-control}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: model-gateway-smoke}}}}
  policyTypes: [Egress]
  egress:
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: kube-system}}}}}}]
      ports: [{{protocol: UDP, port: 53}}, {{protocol: TCP, port: 53}}]
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}}}]
      ports: [{{protocol: TCP, port: 8002}}]
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-system}}}}}}]
      ports: [{{protocol: TCP, port: 8080}}]
---
apiVersion: batch/v1
kind: Job
metadata: {{name: model-gateway-smoke, namespace: fw-control}}
spec:
  backoffLimit: 0
  template:
    metadata: {{labels: {{app.kubernetes.io/name: model-gateway-smoke}}}}
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      containers:
        - name: smoke
          image: {image}
          imagePullPolicy: Never
          command: [python, /config/smoke.py]
          env:
            - name: TENANT_A_OPERATOR
              valueFrom: {{secretKeyRef: {{name: fw-model-smoke-users, key: tenant_a_operator}}}}
          volumeMounts: [{{name: script, mountPath: /config, readOnly: true}}]
          securityContext: {{allowPrivilegeEscalation: false, runAsNonRoot: true, capabilities: {{drop: [ALL]}}}}
      volumes: [{{name: script, configMap: {{name: model-gateway-smoke}}}}]
"""
