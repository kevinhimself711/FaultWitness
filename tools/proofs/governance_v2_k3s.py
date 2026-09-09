# ruff: noqa: E501
"""One-time private K3s side-effect/resume proof for governance v2.

The proof is deliberately not a CLI command, lifecycle, or CI test. It uses the existing private
SSH transport and :mod:`faultwitness_dev.experiment` journal. There is no orchestration timeout;
the remote observers stop only on Ready, a terminal Pod state, or a deterministic image/config
failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.experiment import (
    ExperimentBlockedError,
    ExperimentInfrastructureError,
    ExperimentRunner,
    ExperimentUnit,
    TrialJournal,
    UnitExecution,
)
from faultwitness_dev.infra import run_remote_script
from faultwitness_dev.provenance import producer_provenance
from faultwitness_dev.schemas import load_data

ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = "fw-governance-v2-proof"
POD = "side-effect-proof"
UNIT_ID = "k3s-side-effect"
READY_LOG = "governance-v2-ready"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _private_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise GovernanceError("APPDATA is required for private platform proof evidence")
    return Path(appdata) / "FaultWitness" / "evidence" / "platform" / "governance-v2-k3s"


def _tracked_tree_fingerprint() -> str:
    payload = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "."],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(payload).hexdigest()


def _remote_observation(script: str) -> dict[str, str]:
    try:
        output = run_remote_script(script, privileged=True)
    except GovernanceError as error:
        if "FW_P6_BLOCKED" in str(error):
            raise ExperimentBlockedError(str(error)) from error
        raise ExperimentInfrastructureError(str(error)) from error
    observation = dict(
        line.split("=", 1) for line in output.splitlines() if "=" in line
    )
    if not observation:
        raise ExperimentBlockedError("remote K3s proof returned no structured observation")
    return observation


def _checkpointed(
    execution: UnitExecution,
    name: str,
    operation: Callable[[], dict[str, str]],
) -> dict[str, str]:
    previous = execution.resume_checkpoints.get(name)
    if isinstance(previous, dict):
        return {str(key): str(value) for key, value in previous.items()}
    observation = operation()
    execution.checkpoint(name, observation)
    return observation


def _namespace_create_script() -> str:
    return f"""set -eu
step=namespace
on_exit() {{ status=$?; if test "$status" -ne 0; then printf 'FW_P6_BLOCKED step=%s status=%s\\n' "$step" "$status" >&2; fi; }}
trap on_exit EXIT
k='/usr/local/bin/k3s kubectl'
if $k get namespace {NAMESPACE} >/dev/null 2>&1; then
  owner=$($k get namespace {NAMESPACE} -o jsonpath='{{.metadata.labels.faultwitness\\.io/proof}}')
  test "$owner" = governance-v2
  action=existing
else
  $k create namespace {NAMESPACE} >/dev/null
  $k label namespace {NAMESPACE} faultwitness.io/proof=governance-v2 --overwrite >/dev/null
  action=created
fi
printf 'namespace={NAMESPACE}\\nnamespace_action=%s\\nowner=governance-v2\\n' "$action"
"""


def _failing_pod_script(image: str) -> str:
    return f"""set -eu
step=failing-pod
on_exit() {{ status=$?; if test "$status" -ne 0; then printf 'FW_P6_BLOCKED step=%s status=%s\\n' "$step" "$status" >&2; fi; }}
trap on_exit EXIT
k='/usr/local/bin/k3s kubectl'
if $k -n {NAMESPACE} get pod {POD} >/dev/null 2>&1; then
  command_id=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.metadata.annotations.faultwitness\\.io/proof-command}}')
  test "$command_id" = exit-7
  action=existing
else
  $k apply -f - >/dev/null <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: {POD}
  namespace: {NAMESPACE}
  annotations:
    faultwitness.io/proof-command: exit-7
spec:
  restartPolicy: Never
  containers:
    - name: proof
      image: {image}
      imagePullPolicy: IfNotPresent
      command: ["/bin/sh", "-c", "exit 7"]
EOF
  action=created
fi
printf 'pod={POD}\\npod_action=%s\\ncommand=exit-7\\n' "$action"
"""


def _failed_observation_script() -> str:
    return f"""set -eu
k='/usr/local/bin/k3s kubectl'
while :; do
  phase=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.phase}}' 2>/dev/null || true)
  waiting=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.containerStatuses[0].state.waiting.reason}}' 2>/dev/null || true)
  case "$phase" in Failed|Succeeded) break;; esac
  case "$waiting" in ErrImagePull|ImagePullBackOff|CreateContainerConfigError|InvalidImageName) break;; esac
  test -n "$phase" || {{ printf 'FW_P6_BLOCKED step=observe-failed status=missing-pod\\n' >&2; exit 42; }}
  sleep 1
done
exit_code=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.containerStatuses[0].state.terminated.exitCode}}' 2>/dev/null || true)
printf 'phase=%s\\nexit_code=%s\\nwaiting_reason=%s\\n' "$phase" "$exit_code" "$waiting"
"""


def _namespace_readback_script() -> str:
    return f"""set -eu
k='/usr/local/bin/k3s kubectl'
if $k get namespace {NAMESPACE} >/dev/null 2>&1; then
  owner=$($k get namespace {NAMESPACE} -o jsonpath='{{.metadata.labels.faultwitness\\.io/proof}}')
  printf 'namespace={NAMESPACE}\\nnamespace_action=existing\\nowner=%s\\n' "$owner"
else
  printf 'namespace={NAMESPACE}\\nnamespace_action=missing\\nowner=none\\n'
fi
"""


def _recreate_pod_script(image: str) -> str:
    return f"""set -eu
step=recreate-pod
on_exit() {{ status=$?; if test "$status" -ne 0; then printf 'FW_P6_BLOCKED step=%s status=%s\\n' "$step" "$status" >&2; fi; }}
trap on_exit EXIT
k='/usr/local/bin/k3s kubectl'
command_id=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.metadata.annotations.faultwitness\\.io/proof-command}}')
phase=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.phase}}')
exit_code=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.containerStatuses[0].state.terminated.exitCode}}')
test "$command_id" = exit-7
test "$phase" = Failed
test "$exit_code" = 7
$k -n {NAMESPACE} delete pod {POD} --wait=true >/dev/null
$k apply -f - >/dev/null <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: {POD}
  namespace: {NAMESPACE}
  annotations:
    faultwitness.io/proof-command: ready-log
spec:
  restartPolicy: Never
  containers:
    - name: proof
      image: {image}
      imagePullPolicy: IfNotPresent
      command: ["/bin/sh", "-c", "echo {READY_LOG}; while true; do sleep 3600; done"]
EOF
printf 'pod={POD}\\npod_action=recreated\\ncommand=ready-log\\n'
"""


def _ready_observation_script() -> str:
    return f"""set -eu
k='/usr/local/bin/k3s kubectl'
while :; do
  phase=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.phase}}' 2>/dev/null || true)
  ready=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.containerStatuses[0].ready}}' 2>/dev/null || true)
  waiting=$($k -n {NAMESPACE} get pod {POD} -o jsonpath='{{.status.containerStatuses[0].state.waiting.reason}}' 2>/dev/null || true)
  test "$ready" = true && break
  case "$phase" in Failed|Succeeded) break;; esac
  case "$waiting" in ErrImagePull|ImagePullBackOff|CreateContainerConfigError|InvalidImageName) break;; esac
  test -n "$phase" || {{ printf 'FW_P6_BLOCKED step=observe-ready status=missing-pod\\n' >&2; exit 42; }}
  sleep 1
done
log=$($k -n {NAMESPACE} logs {POD} 2>/dev/null || true)
printf 'phase=%s\\nready=%s\\nwaiting_reason=%s\\nlog=%s\\n' "$phase" "$ready" "$waiting" "$log"
"""


def _cleanup_script() -> str:
    return f"""set -eu
step=cleanup
on_exit() {{ status=$?; if test "$status" -ne 0; then printf 'FW_P6_BLOCKED step=%s status=%s\\n' "$step" "$status" >&2; fi; }}
trap on_exit EXIT
k='/usr/local/bin/k3s kubectl'
if $k get namespace {NAMESPACE} >/dev/null 2>&1; then
  $k delete namespace {NAMESPACE} --wait=true >/dev/null
fi
if $k get namespace {NAMESPACE} >/dev/null 2>&1; then
  printf 'namespace={NAMESPACE}\\nreadback=exists\\n'
else
  printf 'namespace={NAMESPACE}\\nreadback=not_found\\n'
fi
"""


def _first_handler(image: str) -> Callable[[UnitExecution], dict[str, Any]]:
    def execute(execution: UnitExecution) -> dict[str, Any]:
        namespace = _checkpointed(
            execution,
            "namespace",
            lambda: _remote_observation(_namespace_create_script()),
        )
        pod = _checkpointed(
            execution,
            "failed-pod",
            lambda: _remote_observation(_failing_pod_script(image)),
        )
        terminal = _checkpointed(
            execution,
            "terminal-observation",
            lambda: _remote_observation(_failed_observation_script()),
        )
        if terminal.get("phase") != "Failed" or terminal.get("exit_code") != "7":
            raise ExperimentBlockedError(
                "controlled Pod did not reach exact Failed/exit-7 observation"
            )
        return {
            "status": "metric_fail",
            "payload": {
                "root_cause": "controlled command checkpoint exit-7",
                "namespace": namespace,
                "pod": pod,
                "terminal": terminal,
            },
        }

    return execute


def _fixed_handler(image: str) -> Callable[[UnitExecution], dict[str, Any]]:
    def execute(execution: UnitExecution) -> dict[str, Any]:
        namespace = _checkpointed(
            execution,
            "namespace-readback",
            lambda: _remote_observation(_namespace_readback_script()),
        )
        if namespace.get("namespace_action") != "existing" or namespace.get("owner") != "governance-v2":
            raise ExperimentBlockedError("owned disposable namespace was not preserved")
        pod = _checkpointed(
            execution,
            "pod-recreated",
            lambda: _remote_observation(_recreate_pod_script(image)),
        )
        ready = _checkpointed(
            execution,
            "ready-observation",
            lambda: _remote_observation(_ready_observation_script()),
        )
        if (
            ready.get("phase") != "Running"
            or ready.get("ready") != "true"
            or ready.get("log") != READY_LOG
        ):
            raise ExperimentBlockedError("corrected Pod did not reach exact Ready/log observation")
        cleanup = _checkpointed(
            execution,
            "cleanup",
            lambda: _remote_observation(_cleanup_script()),
        )
        if cleanup.get("readback") != "not_found":
            raise ExperimentBlockedError("namespace cleanup did not read back NotFound")
        return {
            "status": "pass",
            "payload": {
                "namespace": namespace,
                "pod": pod,
                "ready": ready,
                "cleanup": cleanup,
                "model_calls": 0,
                "authorization_requests": 0,
            },
        }

    return execute


def _write_private_summary(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def main() -> int:
    config = load_data(ROOT / "config/g02/gate-probes.yaml")
    image = str(config["images"]["busybox"])
    private_root = _private_root()
    journal = TrialJournal(private_root / "journal")
    summary_path = private_root / "proof-summary.json"
    provenance = producer_provenance(
        ROOT,
        [
            ROOT / "src/faultwitness_dev/experiment.py",
            ROOT / "src/faultwitness_dev/infra.py",
            ROOT / "config/g02/gate-probes.yaml",
            Path(__file__),
        ],
    )
    tracked_before = _tracked_tree_fingerprint()
    unit = ExperimentUnit(
        unit_id=UNIT_ID,
        required_checkpoints=("platform", "pod_command"),
        depends_on=(),
        input_digest=_digest({"namespace": NAMESPACE, "pod": POD, "image": image}),
        destructive=True,
    )
    first_checkpoints = {"platform": image, "pod_command": _digest("exit 7")}
    fixed_checkpoints = {"platform": image, "pod_command": _digest("ready-log")}
    first_runner = ExperimentRunner(
        (unit,), journal, first_checkpoints, producer_sha=provenance.producer_sha
    )
    fixed_runner = ExperimentRunner(
        (unit,), journal, fixed_checkpoints, producer_sha=provenance.producer_sha
    )
    first_key = first_runner.cache_key(unit)
    fixed_key = fixed_runner.cache_key(unit)
    current = journal.read(UNIT_ID)

    if current and current.get("cache_key") == fixed_key and current.get("status") == "pass":
        final = current
    else:
        if current and current.get("cache_key") == fixed_key:
            first = next(
                (
                    row
                    for row in reversed(current.get("history", []))
                    if row.get("cache_key") == first_key and row.get("status") == "metric_fail"
                ),
                None,
            )
        elif current and current.get("cache_key") == first_key and current.get("status") == "metric_fail":
            first = current
        else:
            first_run = first_runner.run({UNIT_ID: _first_handler(image)})
            first = first_run.records[0]
        if first is None or first.get("status") != "metric_fail":
            status = "infra_failed" if first is None else str(first.get("status"))
            result = {"proof": "P6-private-k3s", "status": status, "record": first}
            _write_private_summary(summary_path, result)
            print(json.dumps(result, indent=2))
            return 2
        fixed_run = fixed_runner.run({UNIT_ID: _fixed_handler(image)})
        final = fixed_run.records[0]

    failed = next(
        (
            row
            for row in reversed(final.get("history", []))
            if row.get("cache_key") == first_key and row.get("status") == "metric_fail"
        ),
        None,
    )
    tracked_after = _tracked_tree_fingerprint()
    passed = (
        final.get("status") == "pass"
        and final.get("cache_key") == fixed_key
        and failed is not None
        and failed.get("runtime_checkpoints", {})
        .get("terminal-observation", {})
        .get("exit_code")
        == "7"
        and final.get("runtime_checkpoints", {}).get("pod-recreated", {}).get("pod_action")
        == "recreated"
        and final.get("runtime_checkpoints", {}).get("ready-observation", {}).get("log")
        == READY_LOG
        and final.get("runtime_checkpoints", {}).get("cleanup", {}).get("readback")
        == "not_found"
        and tracked_before == tracked_after
    )
    result = {
        "proof": "P6-private-k3s",
        "status": "pass" if passed else "blocked",
        "producer_sha": provenance.producer_sha,
        "source_digest": provenance.source_digest,
        "dirty": provenance.dirty,
        "image": image,
        "namespace": NAMESPACE,
        "trial_path": str(journal.path(UNIT_ID)),
        "execution_attempt": final.get("execution_attempt"),
        "record_version": final.get("record_version"),
        "failed_observation_preserved": failed is not None,
        "pod_replay_scope": "failed-pod-only",
        "cleanup_readback": final.get("runtime_checkpoints", {}).get("cleanup"),
        "tracked_tree_unchanged": tracked_before == tracked_after,
        "authorization_requests": 0,
        "model_calls": 0,
        "model_tokens": 0,
        "model_cost": 0,
    }
    _write_private_summary(summary_path, result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
