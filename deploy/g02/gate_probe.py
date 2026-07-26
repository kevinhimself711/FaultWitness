#!/usr/bin/env python3
"""Candidate-bound remote probes for the frozen G02 L2 matrices.

The program runs only through the host-pinned privileged channel. It never prints credentials,
raw canaries, database rows, object bodies, logs, or provider payloads; stdout is one sanitized
JSON result and stderr contains only fixed reason codes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

UTC = timezone.utc

KUBECTL = "/usr/local/bin/k3s kubectl"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
PRINCIPALS = (
    "scenario-controller",
    "baseline-agent",
    "sealed-evaluator",
    "ordinary-developer",
)
TRACE_STAGES = ("api", "persistence", "outbox", "checkpoint", "model-stub", "export")
CANARY_SURFACES = (
    "process-stdout",
    "process-stderr",
    "control-http",
    "control-sse",
    "model-prompt",
    "application-log",
    "trace-buffer",
    "redis-stream",
    "postgresql-state",
    "minio-archive",
    "kubernetes-object",
    "langsmith-export",
    "otlp-trace",
    "otlp-metric",
    "otlp-log",
    "g02-scenario-object",
    "g02-trial-object",
    "g02-evidence-object",
)


class InfraFailure(RuntimeError):
    pass


class BlockedFailure(RuntimeError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def run(
    arguments: list[str], *, input_text: str | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            arguments,
            input=input_text,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as error:
        raise BlockedFailure("required_probe_command_missing") from error
    if check and result.returncode:
        lowered = (result.stderr + result.stdout).casefold()
        if any(
            marker in lowered
            for marker in (
                "connection refused",
                "connection reset",
                "i/o timeout",
                "temporary failure",
                "service unavailable",
                "no route to host",
            )
        ):
            raise InfraFailure("remote_dependency_unavailable")
        raise BlockedFailure("remote_command_failed")
    return result


def shell(script: str, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["/bin/sh", "-ec" if check else "-c", script], check=check)


def kubectl(
    arguments: list[str], *, input_text: str | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return run(["/usr/local/bin/k3s", "kubectl", *arguments], input_text=input_text, check=check)


def secret_value(namespace: str, name: str, key: str) -> str:
    result = kubectl(
        ["-n", namespace, "get", "secret", name, "-o", f"jsonpath={{.data.{key}}}"],
        check=True,
    )
    try:
        return base64.b64decode(result.stdout, validate=True).decode()
    except (ValueError, UnicodeDecodeError) as error:
        raise BlockedFailure("credential_secret_invalid") from error


def emit(document: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")


def artifact(request: dict[str, Any], phase: str, unit: str, evidence: Any) -> str:
    return (
        f"private://faultwitness/g02/{request['candidate_sha']}/{phase}/{unit}/"
        f"{digest(evidence)}"
    )


def validate_request(request: dict[str, Any]) -> None:
    if not FULL_SHA.fullmatch(str(request.get("candidate_sha", ""))):
        raise BlockedFailure("candidate_binding_invalid")
    if not DIGEST.fullmatch(str(request.get("environment_fingerprint", ""))):
        raise BlockedFailure("environment_binding_invalid")
    config = request.get("probe_config")
    if not isinstance(config, dict):
        raise BlockedFailure("probe_config_missing")
    images = config.get("images")
    if not isinstance(images, dict) or any("@sha256:" not in str(item) for item in images.values()):
        raise BlockedFailure("probe_image_not_pinned")


def binding_suffix(request: dict[str, Any]) -> str:
    return str(request["candidate_sha"])[:12]


def canaries(request: dict[str, Any]) -> tuple[str, str]:
    seed = hashlib.sha256(
        (
            f"{request['candidate_sha']}|{request['environment_fingerprint']}|g02-canary-v1"
        ).encode()
    ).hexdigest()[:24]
    return f"FW_SECRET_CANARY_{seed}", f"fw_pii_canary_{seed}@example.invalid"


def plan_resources(request: dict[str, Any]) -> dict[str, Any]:
    config = request["probe_config"]
    return {
        "schema_version": "1.0.0",
        "candidate_sha": request["candidate_sha"],
        "environment_fingerprint": request["environment_fingerprint"],
        "principals": list(PRINCIPALS),
        "prefixes": [
            "g02/scenarios/",
            "g02/trials/",
            "g02/ground-truth/",
            "g02/locked-tests/",
            "g02/evidence/",
        ],
        "namespaces": ["fw-sut", "fw-baseline", "fw-eval"],
        "credential_refs": [
            "secret://fw-sut/g02-scenario-controller-probe",
            "secret://fw-baseline/g02-baseline-agent-probe",
            "secret://fw-eval/g02-sealed-evaluator-probe",
            "secret://fw-eval/g02-ordinary-developer-probe",
        ],
        "images": config["images"],
        "schema_targets": config["schema_targets"],
        "observability_targets": config["observability_targets"],
        "probe_pods": config["probe_pods"],
        "secret_values": [],
    }


def apply_isolation(request: dict[str, Any]) -> None:
    manifest = request.get("isolation_manifest")
    if not isinstance(manifest, str) or "kind: Secret" in manifest:
        raise BlockedFailure("isolation_manifest_invalid")
    kubectl(["apply", "-f", "-"], input_text=manifest, check=True)
    for namespace in ("fw-sut", "fw-baseline", "fw-eval", "fw-data", "fw-observability"):
        kubectl(
            [
                "label",
                "namespace",
                namespace,
                f"kubernetes.io/metadata.name={namespace}",
                "--overwrite",
            ],
            check=True,
        )


def existing_secret_binding(namespace: str, name: str) -> tuple[str, str] | None:
    result = kubectl(["-n", namespace, "get", "secret", name, "-o", "json"])
    if result.returncode:
        return None
    document = json.loads(result.stdout)
    data = document.get("data", {})
    try:
        return (
            base64.b64decode(data["CANDIDATE_SHA"]).decode(),
            base64.b64decode(data["ENVIRONMENT_FINGERPRINT"]).decode(),
        )
    except (KeyError, ValueError, UnicodeDecodeError) as error:
        raise BlockedFailure("existing_probe_secret_unbound") from error


def ensure_principal_secret(request: dict[str, Any], principal: str) -> tuple[str, str, str, str]:
    namespace = {
        "scenario-controller": "fw-sut",
        "baseline-agent": "fw-baseline",
        "sealed-evaluator": "fw-eval",
        "ordinary-developer": "fw-eval",
    }[principal]
    name = f"g02-{principal}-probe"
    expected = (request["candidate_sha"], request["environment_fingerprint"])
    current = existing_secret_binding(namespace, name)
    if current is not None and current != expected:
        old_access = secret_value(namespace, name, "MINIO_ACCESS_KEY")
        old_role = secret_value(namespace, name, "POSTGRES_USER")
        disable_minio_user(old_access)
        disable_postgres_role(old_role)
        kubectl(["-n", namespace, "delete", "secret", name], check=True)
        current = None
    if current is None:
        role = "fw_g02_" + principal.replace("-", "_")
        access = "fwg02" + principal.replace("-", "")[:8] + binding_suffix(request)[:6]
        values = {
            "MINIO_ACCESS_KEY": access,
            "MINIO_SECRET_KEY": secrets.token_urlsafe(32),
            "POSTGRES_USER": role,
            "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "CANDIDATE_SHA": request["candidate_sha"],
            "ENVIRONMENT_FINGERPRINT": request["environment_fingerprint"],
        }
        arguments = ["-n", namespace, "create", "secret", "generic", name]
        for key, value in values.items():
            arguments.extend(["--from-literal", f"{key}={value}"])
        kubectl(arguments, check=True)
    return (
        namespace,
        secret_value(namespace, name, "MINIO_ACCESS_KEY"),
        secret_value(namespace, name, "MINIO_SECRET_KEY"),
        secret_value(namespace, name, "POSTGRES_PASSWORD"),
    )


def ensure_mc_pod(request: dict[str, Any]) -> None:
    image = request["probe_config"]["images"]["minio_mc"]
    manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "g02-mc-admin",
            "namespace": "fw-data",
            "labels": {"faultwitness.dev/eval-only": "g02-mc-admin"},
        },
        "spec": {
            "automountServiceAccountToken": False,
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "mc",
                    "image": image,
                    "command": ["/bin/sh", "-c", "sleep 2147483647"],
                    "envFrom": [{"secretRef": {"name": "fw-minio-env"}}],
                }
            ],
        },
    }
    current = kubectl(["-n", "fw-data", "get", "pod", "g02-mc-admin", "-o", "json"])
    if current.returncode == 0:
        document = json.loads(current.stdout)
        spec = document.get("spec", {})
        container = spec.get("containers", [{}])[0]
        labels = document.get("metadata", {}).get("labels", {})
        valid = (
            container.get("image") == image
            and container.get("envFrom") == [{"secretRef": {"name": "fw-minio-env"}}]
            and spec.get("automountServiceAccountToken") is False
            and labels.get("faultwitness.dev/eval-only") == "g02-mc-admin"
        )
        if not valid:
            kubectl(["-n", "fw-data", "delete", "pod", "g02-mc-admin", "--wait=true"], check=True)
            current = subprocess.CompletedProcess([], 1, "", "")
    if current.returncode:
        kubectl(["apply", "-f", "-"], input_text=json.dumps(manifest), check=True)
    while True:
        result = kubectl(["-n", "fw-data", "get", "pod", "g02-mc-admin", "-o", "json"], check=True)
        pod = json.loads(result.stdout)
        phase = pod.get("status", {}).get("phase")
        statuses = pod.get("status", {}).get("containerStatuses", [])
        if phase == "Running" and statuses and all(item.get("ready") for item in statuses):
            return
        if phase in {"Failed", "Succeeded"}:
            raise BlockedFailure("mc_admin_pod_terminal")
        reject_terminal_pod_wait(pod, "mc_admin_pod")
        time.sleep(2)


def mc_script(script: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    prelude = (
        "set -eu\n"
        "mc alias set root http://minio.fw-data.svc.cluster.local:9000 "
        '"$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null\n'
    )
    return kubectl(
        ["-n", "fw-data", "exec", "-i", "g02-mc-admin", "--", "/bin/sh", "-s"],
        input_text=prelude + script,
        check=check,
    )


def disable_minio_user(access: str) -> None:
    if kubectl(["-n", "fw-data", "get", "pod", "g02-mc-admin"]).returncode:
        return
    mc_script(f"mc admin user disable root {shlex.quote(access)} >/dev/null 2>&1 || true\n")


def disable_postgres_role(role: str) -> None:
    if not re.fullmatch(r"fw_g02_[a-z_]+", role):
        raise BlockedFailure("postgres_probe_role_invalid")
    command = (
        "PGPASSWORD=\"$POSTGRES_PASSWORD\" psql -q -v ON_ERROR_STOP=1 "
        '-U "$POSTGRES_USER" -d "$POSTGRES_DB"'
    )
    kubectl(
        ["-n", "fw-data", "exec", "-i", "postgres-0", "--", "sh", "-ec", command],
        input_text=f"ALTER ROLE {role} NOLOGIN PASSWORD NULL;\n",
        check=True,
    )


def policy_document(principal: str) -> dict[str, Any]:
    bucket = "arn:aws:s3:::faultwitness-eval"
    rules: dict[str, list[tuple[list[str], str]]] = {
        "scenario-controller": [
            (["s3:GetObject"], bucket + "/g02/scenarios/*"),
            (["s3:PutObject"], bucket + "/g02/trials/*"),
        ],
        "baseline-agent": [(["s3:PutObject"], bucket + "/g02/trials/baseline/*")],
        "sealed-evaluator": [
            (["s3:GetObject"], bucket + "/g02/trials/*"),
            (["s3:GetObject"], bucket + "/g02/ground-truth/*"),
            (["s3:GetObject"], bucket + "/g02/locked-tests/*"),
            (["s3:PutObject"], bucket + "/g02/evidence/*"),
        ],
        "ordinary-developer": [],
    }
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": actions, "Resource": resource}
            for actions, resource in rules[principal]
        ],
    }


def provision_minio(request: dict[str, Any], credentials: dict[str, tuple[str, str]]) -> None:
    mc_script("mc mb --ignore-existing root/faultwitness-eval >/dev/null\n")
    for principal, (access, secret) in credentials.items():
        policy_name = "g02-" + principal + "-" + binding_suffix(request)
        policy_value = policy_document(principal)
        script = (
            f"mc admin user remove root {shlex.quote(access)} >/dev/null 2>&1 || true\n"
        )
        if policy_value["Statement"]:
            policy = json.dumps(policy_value, sort_keys=True)
            script += (
                f"mc admin policy remove root {shlex.quote(policy_name)} "
                ">/dev/null 2>&1 || true\n"
                "cat >/tmp/g02-policy.json <<'FW_POLICY'\n"
                + policy
                + "\nFW_POLICY\n"
                + f"mc admin policy create root {shlex.quote(policy_name)} "
                + "/tmp/g02-policy.json >/dev/null\n"
            )
        script += (
            f"mc admin user add root {shlex.quote(access)} "
            f"{shlex.quote(secret)} >/dev/null\n"
        )
        if policy_value["Statement"]:
            script += (
                f"mc admin policy attach root {shlex.quote(policy_name)} "
                f"--user {shlex.quote(access)} >/dev/null\n"
            )
        mc_script(script)
    sentinels = (
        "g02/scenarios/deny-sentinel",
        "g02/trials/deny-sentinel",
        "g02/ground-truth/deny-sentinel",
        "g02/locked-tests/deny-sentinel",
        "g02/evidence/deny-sentinel",
    )
    for key in sentinels:
        mc_script(
            f"printf safe-control | mc pipe root/faultwitness-eval/{shlex.quote(key)} >/dev/null\n"
        )


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def provision_postgres(login_values: dict[str, str]) -> None:
    statements = ["BEGIN;"]
    for principal, login_value in login_values.items():
        role = "fw_g02_" + principal.replace("-", "_")
        statements.extend(
            [
                (
                    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = "
                    + sql_literal(role)
                    + ") THEN EXECUTE 'CREATE ROLE "
                    + role
                    + " LOGIN'; END IF; END $$;"
                ),
                f"ALTER ROLE {role} LOGIN PASSWORD {sql_literal(login_value)};",
                f"REVOKE ALL ON SCHEMA incident_owner, runtime_shared, graph_owner, "
                f"action_owner, trace_buffer_owner FROM {role};",
            ]
        )
    statements.append("COMMIT;")
    sql = "\n".join(statements) + "\n"
    command = (
        "PGPASSWORD=\"$POSTGRES_PASSWORD\" psql -q -v ON_ERROR_STOP=1 "
        '-U "$POSTGRES_USER" -d "$POSTGRES_DB"'
    )
    kubectl(
        ["-n", "fw-data", "exec", "-i", "postgres-0", "--", "sh", "-ec", command],
        input_text=sql,
        check=True,
    )


def ensure_probe_pods(request: dict[str, Any]) -> None:
    image = request["probe_config"]["images"]["busybox"]
    pods = request["probe_config"]["probe_pods"]
    for probe, specification in pods.items():
        namespace = specification["namespace"]
        name = "g02-probe-" + probe
        principal_label = (
            "baseline-agent"
            if probe == "baseline-agent"
            else (
                "sealed-evaluator"
                if probe in {"ordinary-developer", "cross-boundary"}
                else "canonical-owner"
            )
        )
        manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {
                    "faultwitness.dev/principal": principal_label,
                    "faultwitness.dev/eval-only": "g02-probe",
                },
            },
            "spec": {
                "serviceAccountName": specification["service_account"],
                "automountServiceAccountToken": False,
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "probe",
                        "image": image,
                        "command": ["/bin/sh", "-c", "sleep 2147483647"],
                    }
                ],
            },
        }
        existing = kubectl(["-n", namespace, "get", "pod", name, "-o", "json"])
        if existing.returncode == 0:
            current = json.loads(existing.stdout)
            spec = current.get("spec", {})
            labels = current.get("metadata", {}).get("labels", {})
            valid = (
                spec.get("containers", [{}])[0].get("image") == image
                and spec.get("serviceAccountName") == specification["service_account"]
                and spec.get("automountServiceAccountToken") is False
                and labels.get("faultwitness.dev/principal") == principal_label
                and labels.get("faultwitness.dev/eval-only") == "g02-probe"
            )
            if not valid:
                kubectl(["-n", namespace, "delete", "pod", name, "--wait=true"], check=True)
                existing = subprocess.CompletedProcess([], 1, "", "")
        if existing.returncode:
            kubectl(["apply", "-f", "-"], input_text=json.dumps(manifest), check=True)
        while True:
            result = kubectl(["-n", namespace, "get", "pod", name, "-o", "json"], check=True)
            pod = json.loads(result.stdout)
            phase = pod.get("status", {}).get("phase")
            statuses = pod.get("status", {}).get("containerStatuses", [])
            if phase == "Running" and statuses and all(
                item.get("ready") for item in statuses
            ):
                break
            if phase in {"Failed", "Succeeded"}:
                raise BlockedFailure("probe_pod_terminal")
            reject_terminal_pod_wait(pod, "probe_pod")
            time.sleep(2)


def reject_terminal_pod_wait(pod: dict[str, Any], prefix: str) -> None:
    deterministic = {
        "CreateContainerConfigError",
        "CreateContainerError",
        "CrashLoopBackOff",
        "ErrImageNeverPull",
        "ErrImagePull",
        "ImageInspectError",
        "ImagePullBackOff",
        "InvalidImageName",
        "RunContainerError",
    }
    reasons = {
        str(state.get("state", {}).get("waiting", {}).get("reason"))
        for state in pod.get("status", {}).get("containerStatuses", [])
    }
    if reasons & deterministic:
        raise BlockedFailure(prefix + "_deterministic_wait")
    conditions = pod.get("status", {}).get("conditions", [])
    if any(
        condition.get("reason") == "Unschedulable" and condition.get("status") == "False"
        for condition in conditions
    ):
        raise InfraFailure(prefix + "_unschedulable")


def provision(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("plan_digest") != digest(plan_resources(request)):
        raise BlockedFailure("provisioning_plan_digest_drift")
    apply_isolation(request)
    ensure_mc_pod(request)
    credentials: dict[str, tuple[str, str]] = {}
    postgres_logins: dict[str, str] = {}
    for principal in PRINCIPALS:
        _, access, secret, postgres_login = ensure_principal_secret(request, principal)
        credentials[principal] = (access, secret)
        postgres_logins[principal] = postgres_login
    provision_minio(request, credentials)
    provision_postgres(postgres_logins)
    ensure_probe_pods(request)
    binding = {
        "candidate_sha": request["candidate_sha"],
        "environment_fingerprint": request["environment_fingerprint"],
        "plan_digest": request.get("plan_digest"),
    }
    arguments = [
        "-n",
        "fw-eval",
        "create",
        "configmap",
        "g02-probe-binding",
        "--from-literal",
        f"candidate_sha={binding['candidate_sha']}",
        "--from-literal",
        f"environment_fingerprint={binding['environment_fingerprint']}",
        "--from-literal",
        f"plan_digest={binding['plan_digest']}",
        "--dry-run=client",
        "-o",
        "yaml",
    ]
    rendered = kubectl(arguments, check=True).stdout
    kubectl(["apply", "-f", "-"], input_text=rendered, check=True)
    return {
        "status": "pass",
        "candidate_sha": request["candidate_sha"],
        "environment_fingerprint": request["environment_fingerprint"],
        "plan_digest": request.get("plan_digest"),
        "principal_count": 4,
        "prefix_count": 5,
        "credential_secret_count": 4,
        "artifact_ref": artifact(request, "provisioning", "binding", binding),
    }


def assert_provisioned(request: dict[str, Any]) -> None:
    result = kubectl(
        ["-n", "fw-eval", "get", "configmap", "g02-probe-binding", "-o", "json"],
        check=True,
    )
    data = json.loads(result.stdout).get("data", {})
    if (
        data.get("candidate_sha") != request["candidate_sha"]
        or data.get("environment_fingerprint") != request["environment_fingerprint"]
        or data.get("plan_digest") != digest(plan_resources(request))
    ):
        raise BlockedFailure("probe_binding_drifted")


def command_outcome(result: subprocess.CompletedProcess[str]) -> tuple[bool, str]:
    if result.returncode == 0:
        return True, "allowed"
    lowered = (result.stdout + result.stderr).casefold()
    if any(
        marker in lowered
        for marker in (
            "connection refused",
            "connection reset",
            "i/o timeout",
            "no route to host",
            "service unavailable",
            "temporary failure",
            "unable to resolve host",
            "bad address",
        )
    ):
        return False, "infrastructure"
    return False, "denied"


def database_access(
    request: dict[str, Any], cell: dict[str, Any]
) -> tuple[bool, str]:
    name = cell["target"].split(":", 1)[1]
    target = request["probe_config"]["schema_targets"][name]
    relation = f"{target['schema']}.{target['relation']}"
    if cell["probe"] == "canonical-owner":
        role = target["owner_role"]
        role_statement = "" if role == "__database_owner__" else f"SET ROLE {role}; "
        sql = role_statement + f"SELECT 1 FROM {relation} LIMIT 1;"
        command = (
            "PGPASSWORD=\"$POSTGRES_PASSWORD\" psql -qAt -v ON_ERROR_STOP=1 "
            '-U "$POSTGRES_USER" -d "$POSTGRES_DB"'
        )
        result = kubectl(
            ["-n", "fw-data", "exec", "-i", "postgres-0", "--", "sh", "-ec", command],
            input_text=sql,
        )
        return command_outcome(result)
    principal = {
        "baseline-agent": "baseline-agent",
        "ordinary-developer": "ordinary-developer",
        "cross-boundary": "sealed-evaluator",
    }[cell["probe"]]
    namespace = "fw-baseline" if principal == "baseline-agent" else "fw-eval"
    secret = f"g02-{principal}-probe"
    role = secret_value(namespace, secret, "POSTGRES_USER")
    postgres_login = secret_value(namespace, secret, "POSTGRES_PASSWORD")
    db = secret_value("fw-data", "fw-postgres-env", "POSTGRES_DB")
    script = (
        f"export PGPASSWORD={shlex.quote(postgres_login)}\n"
        f"psql -qAt -v ON_ERROR_STOP=1 -h 127.0.0.1 -U {shlex.quote(role)} "
        f"-d {shlex.quote(db)} -c {shlex.quote('SELECT 1 FROM ' + relation + ' LIMIT 1;')}\n"
    )
    result = kubectl(
        ["-n", "fw-data", "exec", "-i", "postgres-0", "--", "sh", "-s"],
        input_text=script,
    )
    return command_outcome(result)


def object_operation(target: str, probe: str) -> tuple[str, str]:
    prefix = target.split("s3:g02/", 1)[1]
    if probe == "canonical-owner":
        principal = {
            "scenarios/": "scenario-controller",
            "trials/": "sealed-evaluator",
            "ground-truth/": "sealed-evaluator",
            "locked-tests/": "sealed-evaluator",
            "evidence/": "sealed-evaluator",
        }[prefix]
        action = "write" if prefix == "evidence/" else "read"
    elif probe == "baseline-agent":
        principal, action = "baseline-agent", "read"
    elif probe == "ordinary-developer":
        principal, action = "ordinary-developer", "read"
    else:
        cross_boundary = {
            "scenarios/": ("sealed-evaluator", "read"),
            "trials/": ("scenario-controller", "write"),
            "ground-truth/": ("scenario-controller", "read"),
            "locked-tests/": ("scenario-controller", "read"),
            "evidence/": ("scenario-controller", "read"),
        }
        principal, action = cross_boundary[prefix]
    return principal, action


def object_access(request: dict[str, Any], cell: dict[str, Any]) -> tuple[bool, str]:
    principal, action = object_operation(cell["target"], cell["probe"])
    namespace = {
        "scenario-controller": "fw-sut",
        "baseline-agent": "fw-baseline",
        "sealed-evaluator": "fw-eval",
        "ordinary-developer": "fw-eval",
    }[principal]
    name = f"g02-{principal}-probe"
    access = secret_value(namespace, name, "MINIO_ACCESS_KEY")
    secret = secret_value(namespace, name, "MINIO_SECRET_KEY")
    prefix = cell["target"].split("s3:g02/", 1)[1]
    path = "probe-" + digest(cell)[0:16]
    command = (
        "set -eu\n"
        f"mc alias set probe http://minio.fw-data.svc.cluster.local:9000 {shlex.quote(access)} "
        f"{shlex.quote(secret)} >/dev/null\n"
    )
    if action == "write":
        command += (
            f"printf safe-control | mc pipe probe/faultwitness-eval/g02/{prefix}{path} >/dev/null\n"
        )
    else:
        command += (
            f"mc cat probe/faultwitness-eval/g02/{prefix}deny-sentinel >/dev/null\n"
        )
    return command_outcome(mc_script(command, check=False))


def observability_access(
    request: dict[str, Any], cell: dict[str, Any]
) -> tuple[bool, str]:
    target = cell["target"].split(":", 1)[1]
    target_config = request["probe_config"]["observability_targets"][target]
    url = target_config["url"]
    probe = cell["probe"]
    pod = "g02-probe-" + probe
    namespace = request["probe_config"]["probe_pods"][probe]["namespace"]
    if target == "langsmith":
        host = urlsplit(url).hostname
        port = target_config.get("port")
        if not host or not isinstance(port, int):
            raise BlockedFailure("observability_target_invalid")
        operation = ["nc", "-z", host, str(port)]
    else:
        operation = ["wget", "-q", "-O", "/dev/null", url]
    result = kubectl(
        [
            "-n",
            namespace,
            "exec",
            pod,
            "--",
            *operation,
        ]
    )
    return command_outcome(result)


def access(request: dict[str, Any]) -> dict[str, Any]:
    assert_provisioned(request)
    cell = request.get("cell")
    if not isinstance(cell, dict) or not cell.get("cell_id"):
        raise BlockedFailure("access_cell_invalid")
    target = str(cell["target"])
    if target.startswith("schema:"):
        allowed, outcome = database_access(request, cell)
    elif target.startswith("s3:g02/"):
        allowed, outcome = object_access(request, cell)
    elif target.startswith("obs:"):
        allowed, outcome = observability_access(request, cell)
    else:
        raise BlockedFailure("access_target_unknown")
    if not allowed and cell.get("expected_allow") is True and outcome == "infrastructure":
        raise InfraFailure("access_target_unavailable")
    evidence = {
        "cell_id": cell["cell_id"],
        "actual_allow": allowed,
        "outcome": outcome,
        "candidate_sha": request["candidate_sha"],
        "environment_fingerprint": request["environment_fingerprint"],
    }
    return {
        "status": "pass",
        "cell_id": cell["cell_id"],
        "actual_allow": allowed,
        "outcome": outcome,
        "artifact_ref": artifact(request, "access", str(cell["cell_id"]), evidence),
    }


def crockford(value: bytes) -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    number = int.from_bytes(value, "big")
    result = ""
    for _ in range(26):
        result = alphabet[number & 31] + result
        number >>= 5
    return result


def trace_envelope(request: dict[str, Any], *, canary: str | None = None) -> dict[str, Any]:
    try:
        candidate_timestamp = datetime.fromisoformat(
            str(request.get("candidate_timestamp", "")).replace("Z", "+00:00")
        )
    except ValueError as error:
        raise BlockedFailure("candidate_timestamp_invalid") from error
    if candidate_timestamp.tzinfo is None:
        raise BlockedFailure("candidate_timestamp_invalid")
    seed = hashlib.sha256(
        (
            request["candidate_sha"]
            + request["environment_fingerprint"]
            + (canary or "trace")
        ).encode()
    ).digest()
    suffix = crockford(seed[:17])
    base = candidate_timestamp.astimezone(UTC).isoformat()
    stages = (
        ("api.g02-probe", "api"),
        ("state.persistence", "state_transition"),
        ("state.outbox", "state_transition"),
        ("checkpoint.g02-probe", "checkpoint"),
        ("model.stub", "model"),
        ("export.g02-probe", "export"),
    )
    spans = []
    root_span_id = "span_" + crockford(hashlib.sha256(seed + b"\x00").digest()[:17])
    for index, (name, stage) in enumerate(stages):
        attributes: dict[str, Any] = {"sequence": index}
        if canary is not None and index == 0:
            attributes["outcome"] = canary
        spans.append(
            {
                "span_id": "span_"
                + crockford(hashlib.sha256(seed + bytes([index])).digest()[:17]),
                "parent_span_id": None if index == 0 else root_span_id,
                "name": name,
                "stage": stage,
                "started_at": base,
                "ended_at": base,
                "status": "ok",
                "attributes": attributes,
            }
        )
    return {
        "trace_id": "trace_" + suffix,
        "tenant_id": "ten_" + suffix,
        "correlation_id": "corr_" + suffix,
        "causation_id": None,
        "incident_id": None,
        "task_id": None,
        "action_id": None,
        "contracts_version": "1.1.0",
        "candidate_sha": request["candidate_sha"],
        "spans": spans,
        "emitted_at": base,
    }


def submit_trace(envelope: dict[str, Any]) -> tuple[int, dict[str, Any], str, str]:
    encoded = base64.b64encode(json.dumps(envelope).encode()).decode()
    code = f"""import base64,json,os,httpx
body=base64.b64decode({encoded!r})
headers={{'x-faultwitness-ingest-token':os.environ['TRACE_INGEST_TOKEN']}}
r=httpx.post('http://127.0.0.1:8001/internal/v1/traces',headers=headers,content=body,timeout=None)
print(json.dumps({{'status':r.status_code,'body':r.json()}}))
"""
    result = kubectl(
        ["-n", "fw-control", "exec", "-i", "deployment/trace-service", "--", "python", "-"],
        input_text=code,
        check=True,
    )
    document = json.loads(result.stdout)
    return int(document["status"]), dict(document["body"]), result.stdout, result.stderr


def drain_trace_service() -> dict[str, Any]:
    code = """import json,os,httpx
h={'x-faultwitness-ingest-token':os.environ['TRACE_INGEST_TOKEN']}
r=httpx.post('http://127.0.0.1:8001/internal/v1/drain',headers=h,timeout=None)
print(json.dumps(r.json()))
"""
    result = kubectl(
        ["-n", "fw-control", "exec", "-i", "deployment/trace-service", "--", "python", "-"],
        input_text=code,
        check=True,
    )
    return json.loads(result.stdout)


def fetch_tempo(trace_id: str) -> dict[str, Any]:
    url = "http://tempo.fw-observability.svc.cluster.local:3200/api/traces/" + quote(trace_id)
    while True:
        result = kubectl(
            [
                "-n",
                "fw-observability",
                "exec",
                "g02-probe-canonical-owner",
                "--",
                "wget",
                "-q",
                "-O",
                "-",
                url,
            ]
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as error:
                raise BlockedFailure("tempo_trace_invalid_json") from error
        time.sleep(2)


def all_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in all_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in all_strings(child)]
    return [value] if isinstance(value, str) else []


def trace(request: dict[str, Any]) -> dict[str, Any]:
    assert_provisioned(request)
    status, accepted, _, _ = submit_trace(trace_envelope(request))
    if status != 202:
        raise BlockedFailure("trace_ingest_rejected")
    drained = drain_trace_service()
    pending = drained.get("status", {})
    if pending.get("pending_otlp") != 0 or pending.get("pending_archive") != 0:
        raise InfraFailure("trace_export_pending")
    tempo = fetch_tempo(str(accepted["otlp_trace_id"]))
    strings = set(all_strings(tempo))
    expected_names = {
        "api": "api.g02-probe",
        "persistence": "state.persistence",
        "outbox": "state.outbox",
        "checkpoint": "checkpoint.g02-probe",
        "model-stub": "model.stub",
        "export": "export.g02-probe",
    }
    stages = []
    for stage in TRACE_STAGES:
        observed = expected_names[stage] in strings
        summary = {"trace_id": accepted["otlp_trace_id"], "stage": stage, "observed": observed}
        stages.append(
            {
                **summary,
                "artifact_ref": artifact(request, "trace", stage, summary),
            }
        )
    return {"status": "pass", "stages": stages}


def scan_tokens(payload: str | bytes, tokens: tuple[str, str]) -> int:
    encoded = payload.encode() if isinstance(payload, str) else payload
    return sum(encoded.count(token.encode()) for token in tokens)


def kubernetes_logs(arguments: list[str]) -> str:
    result = kubectl(arguments)
    if result.returncode and "not found" not in result.stderr.casefold():
        raise BlockedFailure("log_surface_unreadable")
    return result.stdout + result.stderr


def namespace_logs(namespace: str) -> str:
    result = kubectl(
        ["-n", namespace, "get", "pods", "-o", "jsonpath={.items[*].metadata.name}"],
        check=True,
    )
    payload = ""
    for pod in result.stdout.split():
        payload += kubernetes_logs(
            ["-n", namespace, "logs", pod, "--all-containers=true", "--prefix=true"]
        )
    return payload


def grep_pod_data(namespace: str, pod: str, path: str, tokens: tuple[str, str]) -> int:
    script = "\n".join(
        f"grep -aR -F -- {shlex.quote(token)} {shlex.quote(path)} 2>/dev/null || test $? -eq 1"
        for token in tokens
    )
    result = kubectl(["-n", namespace, "exec", pod, "--", "sh", "-ec", script])
    if result.returncode:
        raise BlockedFailure("telemetry_surface_unreadable")
    return scan_tokens(result.stdout + result.stderr, tokens)


def persistent_volume_hits(
    namespace: str, pod: str, mount_path: str, tokens: tuple[str, str]
) -> int:
    pod_document = json.loads(
        kubectl(["-n", namespace, "get", "pod", pod, "-o", "json"], check=True).stdout
    )
    volume_name = None
    for container in pod_document.get("spec", {}).get("containers", []):
        for mount in container.get("volumeMounts", []):
            if mount.get("mountPath") == mount_path:
                volume_name = mount.get("name")
                break
    if not volume_name:
        raise BlockedFailure("telemetry_volume_missing")
    claim_name = None
    for volume in pod_document.get("spec", {}).get("volumes", []):
        if volume.get("name") == volume_name:
            claim_name = volume.get("persistentVolumeClaim", {}).get("claimName")
            break
    if not claim_name:
        raise BlockedFailure("telemetry_claim_missing")
    claim = json.loads(
        kubectl(
            ["-n", namespace, "get", "pvc", str(claim_name), "-o", "json"],
            check=True,
        ).stdout
    )
    volume_id = claim.get("spec", {}).get("volumeName")
    if not volume_id:
        raise BlockedFailure("telemetry_volume_unbound")
    volume = json.loads(kubectl(["get", "pv", str(volume_id), "-o", "json"], check=True).stdout)
    spec = volume.get("spec", {})
    host_path = spec.get("local", {}).get("path") or spec.get("hostPath", {}).get("path")
    if not isinstance(host_path, str):
        raise BlockedFailure("telemetry_host_path_missing")
    resolved = Path(host_path).resolve()
    storage_root = Path("/var/lib/rancher/k3s/storage").resolve()
    if storage_root not in resolved.parents:
        raise BlockedFailure("telemetry_host_path_unsafe")
    hits = 0
    token_bytes = tuple(token.encode() for token in tokens)
    for candidate in sorted(resolved.rglob("*")):
        if candidate.is_file() and not candidate.is_symlink():
            overlaps = {token: b"" for token in token_bytes}
            with candidate.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    for token in token_bytes:
                        window = overlaps[token] + chunk
                        hits += window.count(token)
                        overlaps[token] = window[-len(token) + 1 :]
    return hits


def kubernetes_object_payload() -> bytes:
    raw = kubectl(
        [
            "get",
            "configmap,secret,serviceaccount,job,pod,deployment,statefulset",
            "-A",
            "-o",
            "json",
        ],
        check=True,
    ).stdout
    document = json.loads(raw)
    decoded = bytearray(raw.encode())
    for item in document.get("items", []):
        if item.get("kind") != "Secret":
            continue
        for value in item.get("data", {}).values():
            if isinstance(value, str):
                try:
                    decoded.extend(base64.b64decode(value, validate=True))
                except ValueError as error:
                    raise BlockedFailure("kubernetes_secret_invalid_base64") from error
    return bytes(decoded)


def minio_contents(prefix: str = "") -> str:
    path = "root/faultwitness-eval" + ("/" + prefix.strip("/") if prefix else "")
    script = (
        f"mc find {shlex.quote(path)} --type f --exec 'mc cat {{}}' 2>/dev/null || true\n"
    )
    return mc_script(script, check=False).stdout


def canary(request: dict[str, Any]) -> dict[str, Any]:
    assert_provisioned(request)
    tokens = canaries(request)
    before = drain_trace_service().get("status", {})
    child_stdout = ""
    child_stderr = ""
    http_responses = ""
    for token in tokens:
        status, body, stdout, stderr = submit_trace(trace_envelope(request, canary=token))
        child_stdout += stdout
        child_stderr += stderr
        http_responses += json.dumps(body, sort_keys=True)
        if status != 422:
            raise BlockedFailure("canary_ingest_not_rejected")
    after = drain_trace_service().get("status", {})
    if before != after:
        raise BlockedFailure("rejected_canary_changed_trace_backlog")
    control_logs = kubernetes_logs(
        ["-n", "fw-control", "logs", "deployment/control-api", "--all-containers=true"]
    )
    model_logs = kubernetes_logs(
        ["-n", "fw-control", "logs", "deployment/model-gateway", "--all-containers=true"]
    )
    all_logs = ""
    for namespace in (
        "fw-control",
        "fw-data",
        "fw-observability",
        "fw-sut",
        "fw-baseline",
        "fw-eval",
    ):
        all_logs += namespace_logs(namespace)
    postgres_dump = kubectl(
        [
            "-n",
            "fw-data",
            "exec",
            "postgres-0",
            "--",
            "sh",
            "-ec",
            'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        ],
        check=True,
    ).stdout
    redis_hits = persistent_volume_hits("fw-data", "redis-0", "/data", tokens)
    postgres_hits = persistent_volume_hits(
        "fw-data", "postgres-0", "/var/lib/postgresql/data", tokens
    )
    objects = minio_contents()
    kube_objects = kubernetes_object_payload()
    telemetry = {
        "otlp-trace": persistent_volume_hits(
            "fw-observability", "tempo-0", "/data", tokens
        ),
        "otlp-metric": persistent_volume_hits(
            "fw-observability",
            "prometheus-0",
            "/data",
            tokens,
        ),
        "otlp-log": persistent_volume_hits(
            "fw-observability", "loki-0", "/data", tokens
        ),
        "redis-stream": redis_hits,
        "postgresql-state": scan_tokens(postgres_dump, tokens) + postgres_hits,
    }
    scan_inputs = {
        "process-stdout": child_stdout,
        "process-stderr": child_stderr,
        "control-http": http_responses,
        "control-sse": control_logs,
        "model-prompt": model_logs,
        "application-log": all_logs,
        "trace-buffer": postgres_dump,
        "redis-stream": "",
        "postgresql-state": "",
        "minio-archive": objects,
        "kubernetes-object": kube_objects,
        "langsmith-export": json.dumps({"before": before, "after": after}, sort_keys=True),
        "g02-scenario-object": minio_contents("g02/scenarios"),
        "g02-trial-object": minio_contents("g02/trials"),
        "g02-evidence-object": minio_contents("g02/evidence"),
    }
    canary_digest = digest(tokens)
    surfaces = []
    for surface in CANARY_SURFACES:
        hits = telemetry.get(surface, scan_tokens(scan_inputs.get(surface, ""), tokens))
        evidence = {"surface": surface, "hit_count": hits, "canary_digest": canary_digest}
        surfaces.append(
            {
                **evidence,
                "artifact_ref": artifact(request, "canary", surface, evidence),
            }
        )
    return {"status": "pass", "surfaces": surfaces}


def main() -> None:
    if len(sys.argv) != 3:
        emit({"status": "blocked", "reason_code": "arguments_invalid"})
        return
    action = sys.argv[1]
    try:
        request = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        validate_request(request)
        if action == "plan":
            emit({"status": "pass", "resources": plan_resources(request)})
        elif action == "provision":
            emit(provision(request))
        elif action == "access":
            emit(access(request))
        elif action == "trace":
            emit(trace(request))
        elif action == "canary":
            emit(canary(request))
        else:
            raise BlockedFailure("action_unknown")
    except InfraFailure as error:
        emit({"status": "infra_failed", "reason_code": str(error)})
    except (BlockedFailure, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        reason = str(error) if isinstance(error, BlockedFailure) else "probe_contract_invalid"
        emit({"status": "blocked", "reason_code": reason})
    except OSError:
        emit({"status": "infra_failed", "reason_code": "probe_io_failure"})
    except Exception:
        emit({"status": "blocked", "reason_code": "unexpected_probe_failure"})


if __name__ == "__main__":
    main()
