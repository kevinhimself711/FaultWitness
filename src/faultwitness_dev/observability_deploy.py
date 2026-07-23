# ruff: noqa: E501 -- remote shell and Kubernetes manifests remain literal for auditability.

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from faultwitness.observability.exporters import LangSmithExporter
from faultwitness.observability.sanitizer import SanitizedTrace
from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    record_live_api_verification,
)
from faultwitness_dev.control_api_deploy import (
    FULL_SHA,
    _assert_candidate,
    _context,
    _stage_base_image,
    _stage_file,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import _remote_arguments, run_remote_script


def _tracked_files(root: Path) -> list[Path]:
    files = [
        root / "deploy" / "observability" / "Dockerfile",
        root / "deploy" / "control-api" / "requirements.lock",
        root / "pyproject.toml",
        root / "README.md",
    ]
    files.extend(path for path in sorted((root / "src").rglob("*")) if path.is_file())
    return files


def deploy_trace_service(root: Path, candidate_sha: str) -> dict[str, Any]:
    files = _tracked_files(root)
    _assert_candidate(root, candidate_sha, files)
    payload, bundle_digest = _context(root, files)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise GovernanceError("APPDATA is required for private deployment staging")
    context_path = Path(appdata) / "FaultWitness" / "artifacts" / "I-0013" / "context.tgz"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_bytes(payload)
    _stage_base_image(root)
    _stage_file(context_path, "faultwitness-i0013-context.tgz")
    image = f"docker.io/faultwitness/trace-service:{candidate_sha}"
    manifest = base64.b64encode(_manifest(candidate_sha, image).encode()).decode()
    project = f"faultwitness-g01-{candidate_sha[:12]}"
    script = f"""set -eu
work=$(mktemp -d /tmp/faultwitness-i0013-build.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
docker load -i /tmp/faultwitness-i0012-python-base.tar >/dev/null
install -m 0600 /tmp/faultwitness-i0013-context.tgz "$work/context.tgz"
test "$(sha256sum "$work/context.tgz" | awk '{{print $1}}')" = {bundle_digest}
tar -xzf "$work/context.tgz" -C "$work"
docker build --pull=false --label faultwitness.candidate={candidate_sha} -t {image} -f "$work/deploy/observability/Dockerfile" "$work" >/dev/null
docker save {image} -o "$work/trace-service.tar"
/usr/local/bin/k3s ctr images import "$work/trace-service.tar" >/dev/null
/usr/local/bin/k3s kubectl create namespace fw-control --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl label namespace fw-control kubernetes.io/metadata.name=fw-control faultwitness.io/boundary=control faultwitness.io/data-client=true faultwitness.io/telemetry-client=true --overwrite >/dev/null
umask 077
envfile="$work/trace.env"
decode_secret() {{ /usr/local/bin/k3s kubectl -n "$1" get secret "$2" -o "jsonpath={{.data.$3}}" | base64 -d; }}
postgres_user=$(decode_secret fw-data fw-postgres-env POSTGRES_USER)
postgres_password=$(decode_secret fw-data fw-postgres-env POSTGRES_PASSWORD)
postgres_db=$(decode_secret fw-data fw-postgres-env POSTGRES_DB)
minio_user=$(decode_secret fw-data fw-minio-env MINIO_ROOT_USER)
minio_password=$(decode_secret fw-data fw-minio-env MINIO_ROOT_PASSWORD)
if /usr/local/bin/k3s kubectl -n fw-control get secret fw-trace-env >/dev/null 2>&1; then
  payload_key=$(decode_secret fw-control fw-trace-env TRACE_PAYLOAD_KEY_B64)
  reference_key=$(decode_secret fw-control fw-trace-env TRACE_REFERENCE_KEY_B64)
  ingest_token=$(decode_secret fw-control fw-trace-env TRACE_INGEST_TOKEN)
else
  payload_key=$(openssl rand -base64 32 | tr -d '\n')
  reference_key=$(openssl rand -base64 32 | tr -d '\n')
  ingest_token=$(openssl rand -hex 32)
fi
{{
  printf 'POSTGRES_USER=%s\n' "$postgres_user"
  printf 'POSTGRES_PASSWORD=%s\n' "$postgres_password"
  printf 'POSTGRES_DB=%s\n' "$postgres_db"
  printf 'MINIO_ACCESS_KEY=%s\n' "$minio_user"
  printf 'MINIO_SECRET_KEY=%s\n' "$minio_password"
  printf 'TRACE_PAYLOAD_KEY_B64=%s\n' "$payload_key"
  printf 'TRACE_REFERENCE_KEY_B64=%s\n' "$reference_key"
  printf 'TRACE_INGEST_TOKEN=%s\n' "$ingest_token"
  printf 'TRACE_KEY_ID=i0013-v1\n'
  printf 'TRACE_BUFFER_CAPACITY=10000\n'
  printf 'LANGSMITH_PROJECT={project}\n'
  printf 'LANGSMITH_EXPORT_MODE=operator_relay\n'
  printf 'OTLP_HTTP_ENDPOINT=http://otel-collector.fw-observability.svc.cluster.local:4318\n'
  printf 'MINIO_ENDPOINT=http://minio.fw-data.svc.cluster.local:9000\n'
}} >"$envfile"
/usr/local/bin/k3s kubectl -n fw-control create secret generic fw-trace-env --from-env-file="$envfile" --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f - >/dev/null
rm -f "$envfile"
printf %s {manifest} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl -n fw-control rollout status deployment/trace-service --timeout=5m >/dev/null
"""
    run_remote_script(script, privileged=True, timeout=900)
    return {
        "candidate_sha": candidate_sha,
        "bundle_sha256": bundle_digest,
        "image": image,
        "project": project,
    }


def inspect_trace_service(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    script = f"""set -eu
available=$(/usr/local/bin/k3s kubectl -n fw-control get deployment trace-service -o jsonpath='{{.status.availableReplicas}}')
ready=$(/usr/local/bin/k3s kubectl -n fw-control get deployment trace-service -o jsonpath='{{.status.readyReplicas}}')
binding=$(/usr/local/bin/k3s kubectl -n fw-control get configmap fw-trace-candidate -o jsonpath='{{.data.candidate_sha}}')
service_type=$(/usr/local/bin/k3s kubectl -n fw-control get service trace-service -o jsonpath='{{.spec.type}}')
status=$(/usr/local/bin/k3s kubectl -n fw-control exec deployment/trace-service -- python -c 'import httpx; print(httpx.get("http://127.0.0.1:8001/health/ready",timeout=5).status_code)')
test "$available" = 1
test "$ready" = 1
test "$binding" = {candidate_sha}
test "$service_type" = ClusterIP
test "$status" = 200
printf '%s %s %s\n' "$available" "$ready" "$service_type"
"""
    fields = run_remote_script(script, privileged=True).strip().split()
    if fields != ["1", "1", "ClusterIP"]:
        raise GovernanceError("trace service deployment is not Ready")
    return {"candidate_sha": candidate_sha, "available": 1, "ready": 1, "service_type": "ClusterIP"}


def diagnose_trace_service() -> str:
    return run_remote_script(
        """set -eu
/usr/local/bin/k3s kubectl -n fw-control get pods -l app.kubernetes.io/name=trace-service -o wide
/usr/local/bin/k3s kubectl -n fw-control logs deployment/trace-service --tail=80 2>&1 | sed -E 's#(postgresql://)[^@ ]+@#\\1[REDACTED]@#g; s/(Bearer )[A-Za-z0-9._-]+/\\1[REDACTED]/g'
/usr/local/bin/k3s kubectl -n fw-control get events --sort-by=.metadata.creationTimestamp | tail -30
""",
        privileged=True,
    )


def run_trace_service_smoke(
    candidate_sha: str, *, inject_uncertain_ack: bool = False
) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    manifest = base64.b64encode(_smoke_manifest(candidate_sha).encode()).decode()
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-control get configmap fw-trace-candidate -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
/usr/local/bin/k3s kubectl -n fw-control delete job trace-service-smoke --ignore-not-found --wait=true >/dev/null
printf %s {manifest} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
for attempt in $(seq 1 90); do
  succeeded=$(/usr/local/bin/k3s kubectl -n fw-control get job trace-service-smoke -o jsonpath='{{.status.succeeded}}')
  failed=$(/usr/local/bin/k3s kubectl -n fw-control get job trace-service-smoke -o jsonpath='{{.status.failed}}')
  test "$succeeded" = 1 && break
  test "$failed" = 1 && exit 1
  sleep 2
done
test "$succeeded" = 1
/usr/local/bin/k3s kubectl -n fw-control logs job/trace-service-smoke
"""
    output = run_remote_script(script, privileged=True, timeout=240).strip()
    try:
        result = json.loads(output)
    except json.JSONDecodeError as error:
        raise GovernanceError("trace service smoke returned invalid sanitized JSON") from error
    expected = {
        "accepted": 202,
        "duplicate": 202,
        "duplicate_flag": True,
        "canary_rejected": 422,
        "pending_traces": 1,
        "pending_langsmith": 1,
        "pending_otlp": 0,
        "pending_archive": 0,
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise GovernanceError("trace service smoke did not satisfy the frozen outcome matrix")
    relay = relay_langsmith(candidate_sha, inject_uncertain_ack=inject_uncertain_ack)
    if relay["pending_traces"] != 0 or relay["pending_langsmith"] != 0:
        raise GovernanceError("LangSmith operator relay did not drain the candidate buffer")
    if result["langsmith_trace_id"] not in relay["langsmith_trace_ids"]:
        raise GovernanceError("candidate LangSmith trace was not acknowledged by the relay")
    result.update(relay)
    record_live_api_verification(
        BootstrapPaths.defaults(), secret_name="langsmith.api_key", iteration="I-0013"
    )
    return {"candidate_sha": candidate_sha, **result}


def relay_langsmith(candidate_sha: str, *, inject_uncertain_ack: bool = False) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    private = run_remote_script(
        "set -eu\n"
        "binding=$(/usr/local/bin/k3s kubectl -n fw-control get configmap fw-trace-candidate -o jsonpath='{.data.candidate_sha}')\n"
        f'test "$binding" = {candidate_sha}\n'
        "service_ip=$(/usr/local/bin/k3s kubectl -n fw-control get service trace-service -o jsonpath='{.spec.clusterIP}')\n"
        "token=$(/usr/local/bin/k3s kubectl -n fw-control get secret fw-trace-env -o jsonpath='{.data.TRACE_INGEST_TOKEN}' | base64 -d)\n"
        'printf \'service_ip=%s\\ntoken=%s\\n\' "$service_ip" "$token"\n',
        privileged=True,
    )
    values = dict(line.split("=", 1) for line in private.splitlines() if "=" in line)
    service_ip = values.get("service_ip")
    token = values.get("token")
    if not service_ip or not token:
        raise GovernanceError("private trace relay prerequisites are incomplete")
    paths = BootstrapPaths.defaults()
    bundle, arguments = _remote_arguments(paths)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        local_port = listener.getsockname()[1]
    tunnel_arguments = [
        *arguments[:-1],
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:{service_ip}:8001",
        arguments[-1],
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    tunnel = subprocess.Popen(
        tunnel_arguments,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    base = f"http://127.0.0.1:{local_port}"
    headers = {"x-faultwitness-ingest-token": token}
    exported: list[str] = []
    export_attempts = 0
    uncertain_replay: tuple[str, str, str] | None = None
    try:
        with httpx.Client(timeout=10) as client:
            for _ in range(30):
                if tunnel.poll() is not None:
                    raise GovernanceError("private trace relay tunnel exited before readiness")
                try:
                    if client.get(base + "/health/ready").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            else:
                raise GovernanceError("private trace relay tunnel did not become ready")
            for _ in range(100):
                response = client.post(base + "/internal/v1/relay/langsmith/claim", headers=headers)
                if response.status_code == 204:
                    break
                if response.status_code != 200:
                    raise GovernanceError("private Trace Service rejected a relay claim")
                trace = SanitizedTrace.from_document(response.json())
                exporter = LangSmithExporter(
                    bundle.langsmith_api_key,
                    project=f"faultwitness-g01-{trace.candidate_sha[:12]}",
                )
                try:
                    summary = asyncio.run(exporter.export(trace))
                    export_attempts += 1
                except Exception as error:
                    client.post(
                        base + f"/internal/v1/relay/langsmith/{trace.trace_ref}/retry",
                        headers=headers,
                    )
                    raise GovernanceError("LangSmith operator relay failed") from error
                if inject_uncertain_ack and uncertain_replay is None:
                    retry = client.post(
                        base + f"/internal/v1/relay/langsmith/{trace.trace_ref}/retry",
                        headers=headers,
                    )
                    if retry.status_code != 204:
                        raise GovernanceError("Trace Service rejected uncertain-ACK replay")
                    uncertain_replay = (
                        trace.trace_ref,
                        trace.payload_digest,
                        summary["remote_trace_id"],
                    )
                    continue
                if uncertain_replay is not None and not exported:
                    expected_ref, expected_digest, expected_remote = uncertain_replay
                    if (
                        trace.trace_ref != expected_ref
                        or trace.payload_digest != expected_digest
                        or summary["remote_trace_id"] != expected_remote
                    ):
                        raise GovernanceError("uncertain-ACK replay changed trace identity")
                ack = client.post(
                    base + f"/internal/v1/relay/langsmith/{trace.trace_ref}/ack",
                    headers=headers,
                )
                if ack.status_code != 204:
                    raise GovernanceError("Trace Service did not acknowledge LangSmith relay")
                exported.append(summary["remote_trace_id"])
            else:
                raise GovernanceError("LangSmith relay exceeded its bounded drain limit")
            status_response = client.get(base + "/internal/v1/status", headers=headers)
            if status_response.status_code != 200:
                raise GovernanceError("Trace Service relay status is unavailable")
            status = status_response.json()
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tunnel.kill()
            tunnel.wait(timeout=5)
    return {
        **status,
        "relayed_langsmith_traces": len(exported),
        "langsmith_trace_ids": exported,
        "langsmith_export_attempts": export_attempts,
        "uncertain_ack_replay_count": 1 if uncertain_replay is not None else 0,
    }


def _manifest(candidate_sha: str, image: str) -> str:
    return f"""apiVersion: v1
kind: ConfigMap
metadata: {{name: fw-trace-candidate, namespace: fw-control}}
data: {{candidate_sha: "{candidate_sha}"}}
---
apiVersion: v1
kind: ServiceAccount
metadata: {{name: trace-service, namespace: fw-control}}
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata: {{name: trace-service, namespace: fw-control}}
spec:
  replicas: 1
  selector: {{matchLabels: {{app.kubernetes.io/name: trace-service}}}}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: trace-service
        faultwitness.io/platform-client: "true"
        faultwitness.io/candidate: "{candidate_sha}"
    spec:
      serviceAccountName: trace-service
      automountServiceAccountToken: false
      securityContext: {{seccompProfile: {{type: RuntimeDefault}}}}
      containers:
        - name: trace-service
          image: {image}
          imagePullPolicy: Never
          envFrom: [{{secretRef: {{name: fw-trace-env}}}}]
          ports: [{{name: http, containerPort: 8001}}]
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
metadata: {{name: trace-service, namespace: fw-control}}
spec:
  type: ClusterIP
  selector: {{app.kubernetes.io/name: trace-service}}
  ports: [{{name: http, port: 8001, targetPort: http}}]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: trace-service-explicit-traffic, namespace: fw-control}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: trace-service}}}}
  policyTypes: [Ingress, Egress]
  ingress:
    - from: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}}}]
      ports: [{{protocol: TCP, port: 8001}}]
  egress:
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: kube-system}}}}}}]
      ports: [{{protocol: UDP, port: 53}}, {{protocol: TCP, port: 53}}]
    - to:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-data}}}}
          podSelector:
            matchExpressions:
              - {{key: app.kubernetes.io/name, operator: In, values: [postgres, minio]}}
      ports: [{{protocol: TCP, port: 5432}}, {{protocol: TCP, port: 9000}}]
    - to:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-observability}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: otel-collector}}}}
      ports: [{{protocol: TCP, port: 4318}}]
    - to: [{{ipBlock: {{cidr: 0.0.0.0/0, except: [10.42.0.0/16, 10.43.0.0/16]}}}}]
      ports: [{{protocol: TCP, port: 443}}]
"""


def _smoke_manifest(candidate_sha: str) -> str:
    return f"""apiVersion: v1
kind: ConfigMap
metadata: {{name: trace-service-smoke, namespace: fw-control}}
data:
  smoke.py: |
    import copy
    import datetime
    import json
    import os
    import secrets
    import time
    import httpx

    now = datetime.datetime.now(datetime.timezone.utc)
    end = now + datetime.timedelta(milliseconds=100)
    child_start = now + datetime.timedelta(milliseconds=20)
    child_end = now + datetime.timedelta(milliseconds=80)
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    new_id = lambda prefix: prefix + "".join(secrets.choice(alphabet) for _ in range(26))
    root_span = new_id("span_")
    child_span = new_id("span_")
    base = {{
      "trace_id":new_id("trace_"),
      "tenant_id":new_id("ten_"),
      "correlation_id":new_id("corr_"),
      "incident_id":new_id("inc_"),
      "contracts_version":"1.1.0",
      "candidate_sha":"{candidate_sha}",
      "spans":[
        {{"span_id":root_span,"parent_span_id":None,"name":"api.incident.create","stage":"api","started_at":now.isoformat(),"ended_at":end.isoformat(),"status":"ok","attributes":{{"http.request.method":"POST","http.route":"/v1/incidents","http.response.status_code":201}}}},
        {{"span_id":child_span,"parent_span_id":root_span,"name":"state.incident.create","stage":"state_transition","started_at":child_start.isoformat(),"ended_at":child_end.isoformat(),"status":"ok","attributes":{{"state.from":"NEW","state.to":"QUEUED"}}}}
      ],
      "emitted_at":end.isoformat()
    }}
    headers = {{"x-faultwitness-ingest-token":os.environ["TRACE_INGEST_TOKEN"]}}
    api = "http://trace-service.fw-control.svc.cluster.local:8001"
    accepted = None
    for _ in range(30):
      try:
        accepted = httpx.post(api + "/internal/v1/traces", headers=headers, json=base, timeout=10)
        break
      except httpx.TransportError:
        time.sleep(1)
    if accepted is None:
      raise SystemExit("trace service did not become reachable")
    duplicate = httpx.post(api + "/internal/v1/traces", headers=headers, json=base, timeout=10)
    canary = copy.deepcopy(base)
    canary["trace_id"] = new_id("trace_")
    canary["spans"][0]["span_id"] = new_id("span_")
    canary["spans"][1]["span_id"] = new_id("span_")
    canary["spans"][1]["parent_span_id"] = canary["spans"][0]["span_id"]
    canary["spans"][0]["attributes"] = {{"outcome":"FW_SECRET_CANARY-live-smoke"}}
    rejected = httpx.post(api + "/internal/v1/traces", headers=headers, json=canary, timeout=10)
    state = None
    for _ in range(60):
      httpx.post(api + "/internal/v1/drain", headers=headers, timeout=30)
      state = httpx.get(api + "/internal/v1/status", headers=headers, timeout=10).json()
      if state["pending_otlp"] == 0 and state["pending_archive"] == 0:
        break
      time.sleep(1)
    print(json.dumps({{
      "accepted":accepted.status_code,
      "duplicate":duplicate.status_code,
      "duplicate_flag":duplicate.json().get("duplicate"),
      "canary_rejected":rejected.status_code,
      "trace_ref":accepted.json().get("trace_ref"),
      "langsmith_trace_id":accepted.json().get("langsmith_trace_id"),
      "otlp_trace_id":accepted.json().get("otlp_trace_id"),
      **(state or {{}})
    }}, sort_keys=True))
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: trace-service-smoke-egress, namespace: fw-control}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: trace-service-smoke}}}}
  policyTypes: [Egress]
  egress:
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: kube-system}}}}}}]
      ports: [{{protocol: UDP, port: 53}}, {{protocol: TCP, port: 53}}]
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}}}]
      ports: [{{protocol: TCP, port: 8001}}]
---
apiVersion: batch/v1
kind: Job
metadata: {{name: trace-service-smoke, namespace: fw-control}}
spec:
  backoffLimit: 0
  template:
    metadata: {{labels: {{app.kubernetes.io/name: trace-service-smoke}}}}
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      containers:
        - name: smoke
          image: docker.io/faultwitness/trace-service:{candidate_sha}
          imagePullPolicy: Never
          command: [python, /config/smoke.py]
          env:
            - name: TRACE_INGEST_TOKEN
              valueFrom: {{secretKeyRef: {{name: fw-trace-env, key: TRACE_INGEST_TOKEN}}}}
          volumeMounts: [{{name: script, mountPath: /config, readOnly: true}}]
          securityContext: {{allowPrivilegeEscalation: false, runAsNonRoot: true, capabilities: {{drop: [ALL]}}}}
      volumes: [{{name: script, configMap: {{name: trace-service-smoke}}}}]
"""
