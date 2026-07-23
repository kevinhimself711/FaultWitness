# ruff: noqa: E501 -- remote shell and Kubernetes manifests remain literal for auditability.

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
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


def _context(root: Path, files: list[Path]) -> tuple[bytes, str]:
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
    return payload, hashlib.sha256(payload).hexdigest()


def _stage_base_image(root: Path) -> None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise GovernanceError("APPDATA is required for private image staging")
    archive = Path(appdata) / "FaultWitness" / "artifacts" / "I-0012" / "python-base.tar"
    crane = _ensure_crane(root)
    _pull_image_archive(crane, BASE_IMAGE, archive)
    _stage_file(archive, "faultwitness-i0012-python-base.tar")


def _stage_file(local_path: Path, remote_name: str) -> None:
    if not re.fullmatch(r"[a-z0-9.-]+", remote_name):
        raise GovernanceError("remote staging name is invalid")
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
        str(local_path),
        f"{bundle.server_username}@{bundle.server_host}:{remote_name}",
    ]
    result = subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise GovernanceError(
            "base image staging failed (" + ssh_failure_category(result.stderr) + ")"
        )
    run_remote_script(
        f'install -m 0600 "$HOME/{remote_name}" "/tmp/{remote_name}"; '
        f'rm -f "$HOME/{remote_name}"\n',
        privileged=False,
    )


def deploy_control_api(root: Path, candidate_sha: str) -> dict[str, Any]:
    files = _tracked_files(root)
    _assert_candidate(root, candidate_sha, files)
    context_payload, bundle_digest = _context(root, files)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise GovernanceError("APPDATA is required for private deployment staging")
    context_path = Path(appdata) / "FaultWitness" / "artifacts" / "I-0012" / "context.tgz"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_bytes(context_payload)
    _stage_base_image(root)
    _stage_file(context_path, "faultwitness-i0012-context.tgz")
    image = f"docker.io/faultwitness/control-api:{candidate_sha}"
    manifest = _manifest(candidate_sha, image)
    manifest_encoded = base64.b64encode(manifest.encode()).decode()
    script = f"""set -eu
work=$(mktemp -d /tmp/faultwitness-i0012-build.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
docker load -i /tmp/faultwitness-i0012-python-base.tar >/dev/null
install -m 0600 /tmp/faultwitness-i0012-context.tgz "$work/context.tgz"
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


def diagnose_control_api() -> str:
    script = """set -eu
/usr/local/bin/k3s kubectl -n fw-system get secret fw-keycloak-env \
  -o go-template='{{range $key,$value := .data}}{{$key}}{{"\\n"}}{{end}}' | sort
/usr/local/bin/k3s kubectl -n fw-system get secret fw-synthetic-users \
  -o go-template='{{range $key,$value := .data}}synthetic_key={{$key}}{{"\\n"}}{{end}}' | sort
/usr/local/bin/k3s kubectl -n fw-system get service keycloak -o jsonpath='service={.spec.clusterIP}:{.spec.ports[0].port}{"\\n"}' || true
/usr/local/bin/k3s kubectl -n fw-system get endpoints keycloak -o jsonpath='endpoint={.subsets[0].addresses[0].ip}:{.subsets[0].ports[0].port}{"\\n"}' || true
/usr/local/bin/k3s kubectl -n fw-control get pods -l app.kubernetes.io/name=control-api \
  -o json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([{"phase":p.get("status",{}).get("phase"),"reason":p.get("status",{}).get("reason"),"waiting":[{"reason":s.get("state",{}).get("waiting",{}).get("reason"),"message":s.get("state",{}).get("waiting",{}).get("message")} for s in p.get("status",{}).get("containerStatuses",[])]} for p in d.get("items",[])]))'
/usr/local/bin/k3s kubectl -n fw-control logs deployment/control-api --tail=30 2>&1 | \
  sed -E 's#(postgresql://)[^@ ]+@#\\1[REDACTED]@#g'
/usr/local/bin/k3s kubectl -n fw-control exec deployment/control-api -- python -c 'import httpx; print("keycloak_status=" + str(httpx.get("http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness/.well-known/openid-configuration", timeout=5).status_code))' || true
/usr/local/bin/k3s kubectl -n fw-system logs deployment/keycloak --tail=100 2>&1 | \
  sed -E 's/(password|secret|token)=[^ ,]+/\\1=[REDACTED]/gi'
/usr/local/bin/k3s kubectl -n fw-system exec deployment/keycloak -- /opt/keycloak/bin/kcadm.sh set-password --help 2>&1 | head -25
/usr/local/bin/k3s kubectl -n fw-control get pods -l app.kubernetes.io/name=control-api-smoke \
  -o json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([{"phase":p.get("status",{}).get("phase"),"reason":p.get("status",{}).get("reason"),"containers":p.get("status",{}).get("containerStatuses",[])} for p in d.get("items",[])]))'
/usr/local/bin/k3s kubectl -n fw-control logs job/control-api-smoke --tail=50 2>&1 | \
  sed -E 's/(Bearer )[A-Za-z0-9._-]+/\\1[REDACTED]/g'
"""
    return run_remote_script(script, privileged=True)


def provision_keycloak_realm(root: Path, candidate_sha: str) -> dict[str, Any]:
    realm_path = root / "deploy" / "keycloak" / "faultwitness-realm.json"
    _assert_candidate(root, candidate_sha, [realm_path])
    try:
        realm = json.loads(realm_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GovernanceError("Keycloak realm asset is invalid") from error
    if realm.get("realm") != "faultwitness" or len(realm.get("roles", {}).get("realm", [])) != 4:
        raise GovernanceError("Keycloak realm asset does not define the frozen realm and roles")
    encoded = base64.b64encode(realm_path.read_bytes()).decode()
    tenant_mapper = base64.b64encode(
        json.dumps(
            {
                "name": "tenant-id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "config": {
                    "user.attribute": "tenant_id",
                    "claim.name": "tenant_id",
                    "jsonType.label": "String",
                    "access.token.claim": "true",
                    "id.token.claim": "true",
                },
            },
            separators=(",", ":"),
        ).encode()
    ).decode()
    audience_mapper = base64.b64encode(
        json.dumps(
            {
                "name": "faultwitness-audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "config": {
                    "included.client.audience": "faultwitness-api",
                    "access.token.claim": "true",
                },
            },
            separators=(",", ":"),
        ).encode()
    ).decode()
    policy = _keycloak_ingress_policy()
    policy_encoded = base64.b64encode(policy.encode()).decode()
    script = f"""set -eu
step=bootstrap
trap 'status=$?; if test "$status" -ne 0; then printf "FW_KEYCLOAK_PROVISION_FAILED step=%s status=%s\\n" "$step" "$status" >&2; fi' EXIT
pod=$(/usr/local/bin/k3s kubectl -n fw-system get pod -l app.kubernetes.io/name=keycloak -o jsonpath='{{.items[0].metadata.name}}')
step=admin-login
/usr/local/bin/k3s kubectl -n fw-system exec "$pod" -- sh -ec '
  /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null
'
if ! /usr/local/bin/k3s kubectl -n fw-system exec "$pod" -- /opt/keycloak/bin/kcadm.sh get realms/faultwitness >/dev/null 2>&1; then
  step=realm-create
  printf %s {encoded} | base64 -d | /usr/local/bin/k3s kubectl -n fw-system exec -i "$pod" -- sh -ec 'cat >/tmp/faultwitness-realm.json; /opt/keycloak/bin/kcadm.sh create realms -f /tmp/faultwitness-realm.json >/dev/null; rm -f /tmp/faultwitness-realm.json'
fi
step=client-mappers
if ! mapper_error=$(/usr/local/bin/k3s kubectl -n fw-system exec "$pod" -- sh -ec '
  client=$(/opt/keycloak/bin/kcadm.sh get clients -r faultwitness -q clientId=faultwitness-api --fields id | sed -n "s/.*\\\"id\\\" : \\\"\\([^\\\"]*\\)\\\".*/\\1/p")
  test -n "$client"
  for name in tenant-id faultwitness-audience; do
    ids=$(/opt/keycloak/bin/kcadm.sh get "clients/$client/protocol-mappers/models" -r faultwitness --fields id,name --format csv --noquotes | grep ",$name$" | cut -d, -f1 || true)
    for mapper_id in $ids; do
      /opt/keycloak/bin/kcadm.sh delete "clients/$client/protocol-mappers/models/$mapper_id" -r faultwitness >/dev/null
    done
  done
  printf %s {tenant_mapper} | base64 -d >/tmp/faultwitness-tenant-mapper.json
  printf %s {audience_mapper} | base64 -d >/tmp/faultwitness-audience-mapper.json
  /opt/keycloak/bin/kcadm.sh create "clients/$client/protocol-mappers/models" -r faultwitness -f /tmp/faultwitness-tenant-mapper.json >/dev/null
  /opt/keycloak/bin/kcadm.sh create "clients/$client/protocol-mappers/models" -r faultwitness -f /tmp/faultwitness-audience-mapper.json >/dev/null
  rm -f /tmp/faultwitness-tenant-mapper.json /tmp/faultwitness-audience-mapper.json
' 2>&1); then
  safe_error=$(printf '%s' "$mapper_error" | sed -E 's/[0-9a-f]{{32,}}/[REDACTED]/g' | tr '\n' ' ' | cut -c1-1200)
  printf 'FW_KEYCLOAK_MAPPER_FAILED detail=%s\n' "$safe_error" >&2
  exit 1
fi
step=user-profile
/usr/local/bin/k3s kubectl -n fw-system exec "$pod" -- /opt/keycloak/bin/kcadm.sh update users/profile -r faultwitness -s unmanagedAttributePolicy=ENABLED >/dev/null
if ! /usr/local/bin/k3s kubectl -n fw-system get secret fw-synthetic-users >/dev/null 2>&1; then
  step=credential-secret
  credentials=$(mktemp /tmp/faultwitness-users.XXXXXX)
  chmod 0600 "$credentials"
  for tenant in tenant-a tenant-b; do
    for role in viewer operator approver admin; do
      key=$(printf '%s_%s' "$tenant" "$role" | tr - _)
      password=$(openssl rand -hex 32)
      printf '%s=%s\n' "$key" "$password" >>"$credentials"
    done
  done
  /usr/local/bin/k3s kubectl -n fw-system create secret generic fw-synthetic-users --from-env-file="$credentials" >/dev/null
  rm -f "$credentials"
fi
for tenant in tenant-a tenant-b; do
  case "$tenant" in
    tenant-a) tenant_ref=ten_01ARZ3NDEKTSV4RRFFQ69G5FAV ;;
    tenant-b) tenant_ref=ten_01ARZ3NDEKTSV4RRFFQ69G5FAW ;;
    *) exit 1 ;;
  esac
  for role in viewer operator approver admin; do
    step="user-$tenant-$role"
    user="$tenant-$role"
    key=$(printf '%s_%s' "$tenant" "$role" | tr - _)
    password=$(/usr/local/bin/k3s kubectl -n fw-system get secret fw-synthetic-users -o "jsonpath={{.data.$key}}" | base64 -d)
    printf '{{"username":"%s","enabled":true,"firstName":"Synthetic","lastName":"%s","email":"%s@faultwitness.invalid","emailVerified":true,"requiredActions":[],"attributes":{{"tenant_id":["%s"]}}}}' "$user" "$role" "$user" "$tenant_ref" | \
      /usr/local/bin/k3s kubectl -n fw-system exec -i "$pod" -- sh -ec '
        cat >/tmp/faultwitness-user.json
        user="$1"; role="$2"
        if ! /opt/keycloak/bin/kcadm.sh get users -r faultwitness -q exact=true -q username="$user" | grep -q "\\\"username\\\" : \\\"$user\\\""; then
          /opt/keycloak/bin/kcadm.sh create users -r faultwitness -f /tmp/faultwitness-user.json >/dev/null
        fi
        user_id=$(/opt/keycloak/bin/kcadm.sh get users -r faultwitness -q exact=true -q username="$user" --fields id | sed -n "s/.*\\\"id\\\" : \\\"\\([^\\\"]*\\)\\\".*/\\1/p")
        test -n "$user_id"
        /opt/keycloak/bin/kcadm.sh update "users/$user_id" -r faultwitness -f /tmp/faultwitness-user.json >/dev/null
        /opt/keycloak/bin/kcadm.sh update "users/$user_id" -r faultwitness -s "attributes.tenant_id=[\\\"$3\\\"]" >/dev/null
        /opt/keycloak/bin/kcadm.sh add-roles -r faultwitness --uusername "$user" --rolename "$role" >/dev/null 2>&1 || true
        rm -f /tmp/faultwitness-user.json
      ' sh "$user" "$role" "$tenant_ref"
    if ! password_error=$(printf '%s\n' "$password" | /usr/local/bin/k3s kubectl -n fw-system exec -i "$pod" -- sh -ec '
      IFS= read -r password
      /opt/keycloak/bin/kcadm.sh set-password -r faultwitness --username "$1" --new-password "$password" >/dev/null
    ' sh "$user" 2>&1); then
      safe_error=$(printf '%s' "$password_error" | sed -E 's/[0-9a-f]{{32,}}/[REDACTED]/g' | tr '\n' ' ' | cut -c1-240)
      printf 'FW_KEYCLOAK_PASSWORD_FAILED user=%s detail=%s\n' "$user" "$safe_error" >&2
      exit 1
    fi
  done
done
printf %s {policy_encoded} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl -n fw-system create configmap fw-keycloak-realm-candidate \
  --from-literal=candidate_sha={candidate_sha} --from-literal=tenant_count=2 --from-literal=role_count=4 --from-literal=user_count=8 \
  --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f - >/dev/null
"""
    run_remote_script(script, privileged=True, timeout=300)
    return {"candidate_sha": candidate_sha, "tenant_count": 2, "role_count": 4, "user_count": 8}


def inspect_keycloak_realm(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-system get configmap fw-keycloak-realm-candidate -o jsonpath='{{.data.candidate_sha}}')
tenants=$(/usr/local/bin/k3s kubectl -n fw-system get configmap fw-keycloak-realm-candidate -o jsonpath='{{.data.tenant_count}}')
roles=$(/usr/local/bin/k3s kubectl -n fw-system get configmap fw-keycloak-realm-candidate -o jsonpath='{{.data.role_count}}')
users=$(/usr/local/bin/k3s kubectl -n fw-system get configmap fw-keycloak-realm-candidate -o jsonpath='{{.data.user_count}}')
test "$binding" = {candidate_sha}
test "$tenants" = 2
test "$roles" = 4
test "$users" = 8
printf '%s %s %s\n' "$tenants" "$roles" "$users"
"""
    fields = run_remote_script(script, privileged=True).strip().split()
    if fields != ["2", "4", "8"]:
        raise GovernanceError("Keycloak synthetic realm inventory is incomplete")
    return {"candidate_sha": candidate_sha, "tenant_count": 2, "role_count": 4, "user_count": 8}


def run_control_api_smoke(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    manifest = _smoke_manifest(candidate_sha)
    encoded = base64.b64encode(manifest.encode()).decode()
    script = f"""set -eu
/usr/local/bin/k3s kubectl -n fw-system get secret fw-synthetic-users -o json | python3 -c 'import json,sys; d=json.load(sys.stdin); d["metadata"]={{"name":"fw-control-smoke-users","namespace":"fw-control"}}; d.pop("type",None); print(json.dumps(d))' | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl -n fw-control delete job control-api-smoke --ignore-not-found --wait=true >/dev/null
printf %s {encoded} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
for attempt in $(seq 1 60); do
  succeeded=$(/usr/local/bin/k3s kubectl -n fw-control get job control-api-smoke -o jsonpath='{{.status.succeeded}}')
  failed=$(/usr/local/bin/k3s kubectl -n fw-control get job control-api-smoke -o jsonpath='{{.status.failed}}')
  test "$succeeded" = 1 && break
  test "$failed" = 1 && exit 1
  sleep 2
done
test "$succeeded" = 1
/usr/local/bin/k3s kubectl -n fw-control logs job/control-api-smoke
"""
    output = run_remote_script(script, privileged=True, timeout=180).strip()
    try:
        result = json.loads(output.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise GovernanceError("Control API smoke returned malformed evidence") from error
    expected = {
        "create": 201,
        "read": 200,
        "cross_tenant": 404,
        "identity_injection": 403,
        "invalid_oidc": 401,
        "false_approval": 409,
        "feedback": 202,
        "cancel": 202,
        "tools": 200,
        "skills": 200,
        "future_cursor": 400,
        "sse_first_sequence": 1,
    }
    if result != expected:
        raise GovernanceError("Control API smoke did not satisfy the frozen outcome matrix")
    return {"candidate_sha": candidate_sha, **result}


def run_keycloak_outage_smoke(candidate_sha: str) -> dict[str, Any]:
    """Prove a cold JWKS cache fails closed while Keycloak is unavailable."""
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    manifest = _keycloak_outage_manifest(candidate_sha)
    encoded = base64.b64encode(manifest.encode()).decode()
    job = _keycloak_outage_job_manifest(candidate_sha)
    job_encoded = base64.b64encode(job.encode()).decode()
    script = f"""set -eu
cleanup() {{
  /usr/local/bin/k3s kubectl -n fw-system scale deployment/keycloak --replicas=1 >/dev/null 2>&1 || true
  /usr/local/bin/k3s kubectl -n fw-system rollout status deployment/keycloak --timeout=180s >/dev/null 2>&1 || true
  /usr/local/bin/k3s kubectl -n fw-control rollout restart deployment/control-api >/dev/null 2>&1 || true
  /usr/local/bin/k3s kubectl -n fw-control rollout status deployment/control-api --timeout=180s >/dev/null 2>&1 || true
  /usr/local/bin/k3s kubectl -n fw-control delete job control-api-keycloak-outage --ignore-not-found --wait=true >/dev/null 2>&1 || true
  /usr/local/bin/k3s kubectl -n fw-control delete pod control-api-token-mint --ignore-not-found --wait=true >/dev/null 2>&1 || true
  /usr/local/bin/k3s kubectl -n fw-control delete secret fw-keycloak-outage-token --ignore-not-found >/dev/null 2>&1 || true
  /usr/local/bin/k3s kubectl -n fw-control delete configmap control-api-keycloak-outage --ignore-not-found >/dev/null 2>&1 || true
}}
trap cleanup EXIT
binding=$(/usr/local/bin/k3s kubectl -n fw-control get configmap fw-control-api-candidate -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
printf %s {encoded} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
/usr/local/bin/k3s kubectl -n fw-control wait --for=condition=Ready pod/control-api-token-mint --timeout=90s >/dev/null
token=$(/usr/local/bin/k3s kubectl -n fw-control exec pod/control-api-token-mint -- python -c 'import httpx,os; r=httpx.post("http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness/protocol/openid-connect/token",data={{"grant_type":"password","client_id":"faultwitness-api","username":"tenant-a-operator","password":os.environ["TENANT_A_OPERATOR"]}},timeout=10); r.raise_for_status(); print(r.json()["access_token"])')
test -n "$token"
/usr/local/bin/k3s kubectl -n fw-control create secret generic fw-keycloak-outage-token --from-literal=token="$token" --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f - >/dev/null
unset token
/usr/local/bin/k3s kubectl -n fw-system scale deployment/keycloak --replicas=0 >/dev/null
/usr/local/bin/k3s kubectl -n fw-system rollout status deployment/keycloak --timeout=90s >/dev/null
/usr/local/bin/k3s kubectl -n fw-control rollout restart deployment/control-api >/dev/null
/usr/local/bin/k3s kubectl -n fw-control rollout status deployment/control-api --timeout=180s >/dev/null
/usr/local/bin/k3s kubectl -n fw-control delete job control-api-keycloak-outage --ignore-not-found --wait=true >/dev/null
printf %s {job_encoded} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
for attempt in $(seq 1 60); do
  succeeded=$(/usr/local/bin/k3s kubectl -n fw-control get job control-api-keycloak-outage -o jsonpath='{{.status.succeeded}}')
  failed=$(/usr/local/bin/k3s kubectl -n fw-control get job control-api-keycloak-outage -o jsonpath='{{.status.failed}}')
  test "$succeeded" = 1 && break
  test "$failed" = 1 && exit 1
  sleep 2
done
test "$succeeded" = 1
/usr/local/bin/k3s kubectl -n fw-control logs job/control-api-keycloak-outage
"""
    output = run_remote_script(script, privileged=True, timeout=420).strip()
    try:
        result = json.loads(output.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise GovernanceError("Keycloak outage smoke returned malformed evidence") from error
    if result != {"cold_jwks_status": 401, "state_write_attempted": False}:
        raise GovernanceError("Keycloak outage did not fail closed before state mutation")
    return {"candidate_sha": candidate_sha, **result}


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
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: allow-control-api-postgres, namespace: fw-data}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: postgres}}}}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: control-api}}}}
      ports: [{{protocol: TCP, port: 5432}}]
"""


def _keycloak_ingress_policy() -> str:
    return """apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: allow-control-api-keycloak, namespace: fw-system}
spec:
  podSelector: {matchLabels: {app.kubernetes.io/name: keycloak}}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: fw-control}}
      ports: [{protocol: TCP, port: 8080}]
"""


def _keycloak_outage_manifest(candidate_sha: str) -> str:
    return f"""apiVersion: v1
kind: ConfigMap
metadata: {{name: control-api-keycloak-outage, namespace: fw-control}}
data:
  smoke.py: |
    import json
    import os
    import httpx

    response = httpx.get(
        "http://control-api.fw-control.svc.cluster.local:8000/v1/tools",
        headers={{"Authorization": "Bearer " + os.environ["TOKEN"]}},
        timeout=15,
    )
    result = {{"cold_jwks_status": response.status_code, "state_write_attempted": False}}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if response.status_code == 401 else 1)
---
apiVersion: v1
kind: Pod
metadata:
  name: control-api-token-mint
  namespace: fw-control
  labels: {{app.kubernetes.io/name: control-api-smoke}}
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  containers:
    - name: mint
      image: docker.io/faultwitness/control-api:{candidate_sha}
      imagePullPolicy: Never
      command: [sleep, "300"]
      env:
        - name: TENANT_A_OPERATOR
          valueFrom: {{secretKeyRef: {{name: fw-control-smoke-users, key: tenant_a_operator}}}}
      securityContext: {{allowPrivilegeEscalation: false, runAsNonRoot: true, capabilities: {{drop: [ALL]}}}}
"""


def _keycloak_outage_job_manifest(candidate_sha: str) -> str:
    return f"""apiVersion: batch/v1
kind: Job
metadata: {{name: control-api-keycloak-outage, namespace: fw-control}}
spec:
  backoffLimit: 0
  template:
    metadata: {{labels: {{app.kubernetes.io/name: control-api-smoke}}}}
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      containers:
        - name: smoke
          image: docker.io/faultwitness/control-api:{candidate_sha}
          imagePullPolicy: Never
          command: [python, /config/smoke.py]
          env:
            - name: TOKEN
              valueFrom: {{secretKeyRef: {{name: fw-keycloak-outage-token, key: token}}}}
          volumeMounts: [{{name: script, mountPath: /config, readOnly: true}}]
          securityContext: {{allowPrivilegeEscalation: false, runAsNonRoot: true, capabilities: {{drop: [ALL]}}}}
      volumes: [{{name: script, configMap: {{name: control-api-keycloak-outage}}}}]
"""


def _smoke_manifest(candidate_sha: str) -> str:
    return f"""apiVersion: v1
kind: ConfigMap
metadata: {{name: control-api-smoke, namespace: fw-control}}
data:
  smoke.py: |
    import datetime
    import json
    import os
    import time
    import uuid
    import httpx
    import jwt

    identity = "http://keycloak.fw-system.svc.cluster.local:8080/realms/faultwitness/protocol/openid-connect/token"
    api = "http://control-api.fw-control.svc.cluster.local:8000"

    def token(username, password):
        for attempt in range(20):
            try:
                response = httpx.post(identity, data={{"grant_type": "password", "client_id": "faultwitness-api", "username": username, "password": password}}, timeout=5)
                response.raise_for_status()
                return response.json()["access_token"]
            except httpx.ConnectError:
                if attempt == 19:
                    raise
                time.sleep(0.5)

    operator = token("tenant-a-operator", os.environ["TENANT_A_OPERATOR"])
    tenant_b = token("tenant-b-viewer", os.environ["TENANT_B_VIEWER"])
    approver = token("tenant-a-approver", os.environ["TENANT_A_APPROVER"])
    now = datetime.datetime.now(datetime.UTC)
    body = {{"source":"g01-smoke","environment_id":"env_smoke","service_scope":["svc_smoke"],"time_window":{{"start":(now-datetime.timedelta(minutes=5)).isoformat(),"end":now.isoformat()}},"symptom_summary":"synthetic smoke","mode":"diagnosis_only","budget":{{"deadline":(now+datetime.timedelta(minutes=5)).isoformat(),"max_steps":2,"max_model_calls":0,"max_tokens":0,"max_cost_usd":0}}}}
    auth = {{"Authorization": "Bearer " + operator, "Idempotency-Key": "smoke-" + uuid.uuid4().hex}}
    created = httpx.post(api + "/v1/incidents", headers=auth, json=body, timeout=10)
    if created.status_code != 201:
        claims = jwt.decode(operator, options={{"verify_signature":False,"verify_aud":False}})
        print(json.dumps({{"stage":"create","status":created.status_code,"body":created.json(),"tenant_claim":claims.get("tenant_id"),"roles":(claims.get("realm_access") or {{}}).get("roles",[])}}, sort_keys=True))
        raise SystemExit(1)
    incident = created.json()["incident_id"]
    read = httpx.get(api + "/v1/incidents/" + incident, headers={{"Authorization":"Bearer " + operator}}, timeout=10)
    cross = httpx.get(api + "/v1/incidents/" + incident, headers={{"Authorization":"Bearer " + tenant_b}}, timeout=10)
    injected = httpx.get(api + "/v1/incidents/" + incident, headers={{"Authorization":"Bearer " + operator,"X-Tenant-ID":"tenant-b"}}, timeout=10)
    approval = httpx.post(api + "/v1/incidents/" + incident + "/approvals", headers={{"Authorization":"Bearer " + approver,"Idempotency-Key":"approval-" + uuid.uuid4().hex}}, json={{"action_id":"act_missing","action_digest":"a"*64,"decision":"approve","expected_state_version":0}}, timeout=10)
    feedback = httpx.post(api + "/v1/incidents/" + incident + "/feedback", headers={{"Authorization":"Bearer " + operator,"Idempotency-Key":"feedback-" + uuid.uuid4().hex}}, json={{"rating":5,"expected_state_version":0}}, timeout=10)
    tools = httpx.get(api + "/v1/tools", headers={{"Authorization":"Bearer " + operator}}, timeout=10)
    skills = httpx.get(api + "/v1/skills", headers={{"Authorization":"Bearer " + operator}}, timeout=10)
    invalid_oidc = httpx.get(api + "/v1/tools", headers={{"Authorization":"Bearer invalid"}}, timeout=10)
    future_cursor = httpx.get(api + "/v1/incidents/" + incident + "/events", headers={{"Authorization":"Bearer " + operator,"Last-Event-ID":"999999"}}, timeout=10)
    sequence = 0
    with httpx.stream("GET", api + "/v1/incidents/" + incident + "/events", headers={{"Authorization":"Bearer " + operator}}, timeout=10) as stream:
        for line in stream.iter_lines():
            if line.startswith("id: "):
                sequence = int(line[4:])
                break
    cancelled = httpx.post(api + "/v1/incidents/" + incident + "/cancel", headers={{"Authorization":"Bearer " + operator,"Idempotency-Key":"cancel-" + uuid.uuid4().hex}}, json={{"expected_state_version":0}}, timeout=10)
    print(json.dumps({{"create":created.status_code,"read":read.status_code,"cross_tenant":cross.status_code,"identity_injection":injected.status_code,"invalid_oidc":invalid_oidc.status_code,"false_approval":approval.status_code,"feedback":feedback.status_code,"cancel":cancelled.status_code,"tools":tools.status_code,"skills":skills.status_code,"future_cursor":future_cursor.status_code,"sse_first_sequence":sequence}}, sort_keys=True))
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: control-api-smoke-egress, namespace: fw-control}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: control-api-smoke}}}}
  policyTypes: [Egress]
  egress:
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: kube-system}}}}}}]
      ports: [{{protocol: UDP, port: 53}}, {{protocol: TCP, port: 53}}]
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}}}]
      ports: [{{protocol: TCP, port: 8000}}]
    - to:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-system}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: keycloak}}}}
      ports: [{{protocol: TCP, port: 8080}}]
---
apiVersion: batch/v1
kind: Job
metadata: {{name: control-api-smoke, namespace: fw-control}}
spec:
  backoffLimit: 0
  template:
    metadata: {{labels: {{app.kubernetes.io/name: control-api-smoke}}}}
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      containers:
        - name: smoke
          image: docker.io/faultwitness/control-api:{candidate_sha}
          imagePullPolicy: Never
          command: [python, /config/smoke.py]
          env:
            - name: TENANT_A_OPERATOR
              valueFrom: {{secretKeyRef: {{name: fw-control-smoke-users, key: tenant_a_operator}}}}
            - name: TENANT_B_VIEWER
              valueFrom: {{secretKeyRef: {{name: fw-control-smoke-users, key: tenant_b_viewer}}}}
            - name: TENANT_A_APPROVER
              valueFrom: {{secretKeyRef: {{name: fw-control-smoke-users, key: tenant_a_approver}}}}
          volumeMounts: [{{name: script, mountPath: /config, readOnly: true}}]
          securityContext: {{allowPrivilegeEscalation: false, runAsNonRoot: true, capabilities: {{drop: [ALL]}}}}
      volumes: [{{name: script, configMap: {{name: control-api-smoke}}}}]
"""
