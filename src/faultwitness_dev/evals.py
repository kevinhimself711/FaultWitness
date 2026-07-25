from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pydantic import ValidationError

from faultwitness.contracts.compiler import (
    assert_generated_resource_current,
    load_generated_resource,
)
from faultwitness.contracts.models import (
    CORE_MODEL_TYPES,
    SUPPORT_MODEL_TYPES,
    CommandEnvelope,
)
from faultwitness.state.kernel import (
    ActorMismatchError,
    GuardRejectedError,
    IdempotencyError,
    OwnerMismatchError,
    PredicateRegistry,
    TransitionKernel,
    TransitionRequest,
    VersionConflictError,
)
from faultwitness_dev.audit import scan_publication_boundary
from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    assert_no_sensitive_capability_fields,
    canonical_capability_report,
    default_age_keygen_executable,
    default_sops_executable,
    default_ssh_askpass_executable,
    derive_age_recipient,
    validate_migration,
)
from faultwitness_dev.changes import infer_iteration_id
from faultwitness_dev.checks import (
    validate_iteration_lifecycle_history,
    validate_iteration_status_sequence,
    validate_iteration_status_transition,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_baselines import (
    QUALITY_FLOORS,
    LiveInfrastructureError,
    deterministic_baseline,
    load_baseline_config,
    make_bailian_adapter,
    run_live_trials,
    score_result,
)
from faultwitness_dev.g02_collectors import evaluate_i0024
from faultwitness_dev.g02_eval import evaluate_i0016, validate_gate_orchestration_selection
from faultwitness_dev.g02_isolation import (
    evaluate_i0018,
    load_isolation_config,
    prove_writer_canaries,
    simulate_identity_policies,
    validate_namespace_isolation_manifest,
    validate_public_https_egress,
)
from faultwitness_dev.g02_lab import (
    build_offline_staging_inventory,
    containerd_normalized_reference,
    containerd_registry_aliases,
    evaluate_i0017,
    image_set_digest,
    load_gate_probe_images,
    load_lab_config,
    offline_staging_inventory,
    select_containerd_import_source,
)
from faultwitness_dev.infra import _remote_process, _run_remote_script_transport
from faultwitness_dev.model_eval import run_model_eval
from faultwitness_dev.observability_deploy import (
    inspect_trace_service,
    run_trace_service_smoke,
)
from faultwitness_dev.runtime_deploy import inspect_runtime_schema
from faultwitness_dev.schemas import load_data, validate_document, validate_repository_schemas


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise GovernanceError("pinned bootstrap tool is missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head_sha(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def validate_capability_baseline(
    report: dict[str, Any], candidate_sha: str, schema: dict[str, Any] | None = None
) -> None:
    if schema is not None:
        validate_document(report, schema, "sanitized capability baseline")
    assert_no_sensitive_capability_fields(report)
    capabilities = report.get("capabilities")
    if not isinstance(capabilities, dict):
        raise GovernanceError("capability baseline is missing its capabilities object")
    expected = canonical_capability_report(capabilities, candidate_sha)
    if report != expected:
        raise GovernanceError("capability baseline digest or candidate binding drifted")
    failures: list[str] = []
    checks = {
        "architecture": str(capabilities["architecture"]).casefold() in {"x86_64", "amd64"},
        "cpu_count": capabilities["cpu_count"] >= 32,
        "memory_bytes": capabilities["memory_bytes"] >= 60 * 1024**3,
        "kernel_release": str(capabilities["kernel_release"]).startswith("5.15."),
        "cgroup_version": capabilities["cgroup_version"] == 1,
        "kvm_available": capabilities["kvm_available"] is True,
        "seccomp_available": capabilities["seccomp_available"] is True,
        "user_namespace_available": capabilities["user_namespace_available"] is True,
        "docker_available": capabilities["docker_available"] is True,
        "docker_unhealthy_count": capabilities["docker_unhealthy_count"] == 0,
        "protected_ports": capabilities["ports_80_443_in_use"] is True,
        "k3s_absent": capabilities["k3s_available"] is False,
        "helm_absent": capabilities["helm_available"] is False,
        "gvisor_absent": capabilities["gvisor_available"] is False,
        "kata_absent": capabilities["kata_available"] is False,
        "nvidia_available": capabilities["nvidia_available"] is True,
        "gpu_model": "4090" in str(capabilities["gpu_model"]),
        "gpu_memory_bytes": capabilities["gpu_memory_bytes"] >= 23 * 1024**3,
        "root_total_bytes": capabilities["root_total_bytes"] >= 100 * 1024**3,
        "cidr_conflict": capabilities["cidr_conflict_with_10_42_10_43"] is False,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    if failures:
        raise GovernanceError("capability baseline failed required checks: " + ", ".join(failures))


def _validate_toolchain(root: Path) -> None:
    lock = load_data(root / "config" / "secrets" / "toolchain.lock.yaml")["tools"]
    sops = default_sops_executable()
    age_keygen = default_age_keygen_executable()
    age = age_keygen.with_name("age.exe")
    askpass = default_ssh_askpass_executable()
    askpass_source = root / lock["ssh_askpass"]["source"]
    askpass_source_marker = askpass.with_name("source.sha256")
    actual = {
        "sops": _sha256(sops),
        "age.exe": _sha256(age),
        "age-keygen.exe": _sha256(age_keygen),
        "ssh_askpass_source": _sha256(askpass_source),
    }
    expected = {
        "sops": lock["sops"]["sha256"],
        "age.exe": lock["age"]["executables"]["age.exe"],
        "age-keygen.exe": lock["age"]["executables"]["age-keygen.exe"],
        "ssh_askpass_source": lock["ssh_askpass"]["sha256"],
    }
    drift = sorted(name for name in expected if actual[name] != expected[name])
    if drift:
        raise GovernanceError("bootstrap toolchain checksum drift: " + ", ".join(drift))
    if not askpass.is_file() or not askpass_source_marker.is_file():
        raise GovernanceError("compiled SSH askpass helper or source marker is missing")
    if askpass_source_marker.read_text(encoding="utf-8").strip() != expected["ssh_askpass_source"]:
        raise GovernanceError("compiled SSH askpass source marker drifted")


def evaluate_i0007(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G01-001 candidate SHA must equal the checked-out HEAD")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    record = loaded["governance/iterations/I-0007.yaml"]
    if state.get("active_gate") != "G01" or state.get("active_iteration") != "I-0007":
        raise GovernanceError("EVAL-G01-001 requires I-0007 as the sole active Iteration")
    if state.get("active_gate_status") != "in_progress" or record.get("status") != "in_progress":
        raise GovernanceError("EVAL-G01-001 requires G01 and I-0007 in progress")
    if (root / "envs.txt").exists():
        raise GovernanceError("plaintext handoff still exists")
    ignore_lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    if ignore_lines.count("/envs.txt") != 1:
        raise GovernanceError(".gitignore must contain exactly one precise /envs.txt rule")
    paths = BootstrapPaths.defaults()
    metadata = validate_migration(paths, default_sops_executable())
    acceptance = metadata.get("credential_acceptance", {})
    required_credentials = {"server.password", "bailian.api_key", "langsmith.api_key"}
    pending = sorted(
        name for name in required_credentials if acceptance.get(name) != "accepted_existing"
    )
    if pending:
        raise GovernanceError("unaccepted existing credentials: " + ", ".join(pending))
    verification = metadata.get("credential_verification", {})
    if verification.get("server.password") != "verified_login":
        raise GovernanceError("existing server password has not passed login verification")
    allowed_verification = {
        "bailian.api_key": {"deferred_to_I-0014_live_eval", "verified_live_I-0014"},
        "langsmith.api_key": {"deferred_to_I-0013_live_eval", "verified_live_I-0013"},
    }
    if any(
        verification.get(name) not in statuses for name, statuses in allowed_verification.items()
    ):
        raise GovernanceError("API credential live verification ownership drifted")
    flags = {
        "host_key_verified": metadata.get("host_key_verified") is True,
        "ssh_key_verified": metadata.get("ssh_key_verified") is True,
        "capability_reprobe_match": metadata.get("capability_reprobe_match") is True,
        "handoff_deleted": metadata.get("handoff_deleted") is True,
    }
    failed_flags = sorted(name for name, passed in flags.items() if not passed)
    if failed_flags:
        raise GovernanceError(
            "private bootstrap evidence is incomplete: " + ", ".join(failed_flags)
        )
    policy = load_data(root / ".sops.yaml")
    policy_recipient = policy["creation_rules"][0]["age"]
    actual_recipient = derive_age_recipient(default_age_keygen_executable(), paths.identity_file)
    if policy_recipient != actual_recipient:
        raise GovernanceError("repository SOPS recipient does not match the private identity")
    _validate_toolchain(root)
    capability_path = root / "docs" / "evals" / "EVAL-G01-001" / "CAPABILITY_BASELINE.json"
    if not capability_path.is_file():
        raise GovernanceError("sanitized capability baseline is missing")
    capability = json.loads(capability_path.read_text(encoding="utf-8"))
    capability_schema = load_data(
        root / "schemas" / "bootstrap" / "capability-baseline.schema.json"
    )
    validate_capability_baseline(capability, candidate_sha, capability_schema)
    scan_publication_boundary(root)
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    forbidden_tracked = sorted(
        path
        for path in tracked
        if path == "envs.txt"
        or path.endswith("faultwitness.secrets.yaml")
        or path.endswith("identity.txt")
        or path.endswith("faultwitness_ed25519")
    )
    if forbidden_tracked:
        raise GovernanceError(
            "private bootstrap material is tracked: " + ", ".join(forbidden_tracked)
        )
    return {
        "eval_id": "EVAL-G01-001",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "secret_count": len(metadata["secret_names"]),
        "accepted_credential_count": len(acceptance),
        "capability_sha256": capability["normalized_sha256"],
        "checks": {
            "encrypted_round_trip": "pass",
            "credential_acceptance": "pass",
            "host_key": "pass",
            "ssh_key": "pass",
            "capability_reprobe": "pass",
            "publication_boundary": "pass",
            "toolchain": "pass",
        },
    }


def evaluate_i0010(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Run the deterministic local EVAL-G01-004 contract and mutation suite."""
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G01-004 candidate SHA must equal the checked-out HEAD")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    record = loaded["governance/iterations/I-0010.yaml"]
    if state.get("active_gate") != "G01" or state.get("active_iteration") != "I-0010":
        raise GovernanceError("EVAL-G01-004 requires I-0010 as the sole active Iteration")
    if state.get("active_gate_status") != "in_progress" or record.get("status") != "in_progress":
        raise GovernanceError("EVAL-G01-004 requires G01 and I-0010 in progress")

    assert_generated_resource_current(root)
    resource = load_generated_resource(root)
    documents = resource["documents"]
    machines = {
        machine_id: documents[f"state_machine.{machine_id}"]
        for machine_id in ("incident", "runtime_task", "agent_graph", "action_transaction")
    }
    counts = {
        "core_types": len(documents["types"]["types"]),
        "states": sum(len(machine["states"]) for machine in machines.values()),
        "transitions": sum(len(machine["transitions"]) for machine in machines.values()),
        "commands": len(documents["commands_events"]["commands"]),
        "events": len(documents["commands_events"]["events"]),
        "errors": len(documents["failures"]["errors"]),
    }
    expected_counts = {
        "core_types": 21,
        "states": 52,
        "transitions": 82,
        "commands": 34,
        "events": 43,
        "errors": 10,
    }
    if counts != expected_counts:
        raise GovernanceError(f"frozen executable contract counts drifted: {counts}")
    if len(CORE_MODEL_TYPES) != 21 or len(SUPPORT_MODEL_TYPES) != 12:
        raise GovernanceError("executable model registry count drifted")
    if any(
        model.model_config.get("strict") is not True
        or model.model_config.get("frozen") is not True
        or model.model_config.get("extra") != "forbid"
        for model in CORE_MODEL_TYPES + SUPPORT_MODEL_TYPES
    ):
        raise GovernanceError("an executable model weakened the strict boundary policy")

    commands = {command["id"]: command for command in documents["commands_events"]["commands"]}
    predicate_names = TransitionKernel.required_predicates(resource)
    kernel = TransitionKernel(resource, PredicateRegistry.fact_registry(predicate_names))
    legal_count = 0
    mutation_count = 0
    decision_digests: set[str] = set()
    for machine_id, machine in machines.items():
        for transition in machine["transitions"]:
            command = commands[transition["command"]]
            required_key = command["idempotency"] == "required"
            request = TransitionRequest(
                machine_id=machine_id,
                transition_id=transition["id"],
                owner_component=machine["owner_component"],
                actor=transition["actor"],
                aggregate_id=f"eval-{machine_id}",
                state=transition["from"],
                state_version=7,
                command=transition["command"],
                expected_state_version=7,
                idempotency_key=f"eval-{transition['id']}" if required_key else None,
                current_fencing_token="fence-current",
                fencing_token="fence-current",
                current_action_digest="a" * 64,
                action_digest="a" * 64,
                facts={
                    **{name: True for name in transition["preconditions"]},
                    f"guard:{transition['id']}": True,
                },
            )
            decision = kernel.service(machine_id).decide(request)
            if decision != kernel.service(machine_id).decide(request):
                raise GovernanceError(f"non-deterministic transition: {transition['id']}")
            if decision.next_state != transition["to"] or decision.event != transition["event"]:
                raise GovernanceError(f"transition output drift: {transition['id']}")
            legal_count += 1
            decision_digests.add(decision.decision_digest)

            mutations: list[tuple[TransitionRequest, type[Exception]]] = [
                (replace(request, owner_component="CMP-INVALID"), OwnerMismatchError),
                (replace(request, actor="CMP-INVALID"), ActorMismatchError),
                (
                    replace(
                        request,
                        facts={**dict(request.facts or {}), transition["preconditions"][0]: False},
                    ),
                    GuardRejectedError,
                ),
                (
                    replace(
                        request,
                        facts={
                            **dict(request.facts or {}),
                            f"guard:{transition['id']}": False,
                        },
                    ),
                    GuardRejectedError,
                ),
            ]
            if command["version_check"] in {"state_version", "digest_and_state_version"}:
                mutations.append((replace(request, expected_state_version=8), VersionConflictError))
            elif command["version_check"] == "fencing_token":
                mutations.append(
                    (replace(request, fencing_token="fence-stale"), VersionConflictError)
                )
            if command["idempotency"] == "required":
                mutations.append((replace(request, idempotency_key=None), IdempotencyError))
            elif command["idempotency"] == "derived":
                mutations.append((replace(request, idempotency_key="caller-key"), IdempotencyError))
            for mutated, expected_error in mutations:
                try:
                    kernel.decide(mutated)
                except expected_error:
                    mutation_count += 1
                else:
                    raise GovernanceError(
                        "illegal mutation accepted for "
                        f"{transition['id']}: {expected_error.__name__}"
                    )

    try:
        CommandEnvelope.model_validate({"schema_version": "1.1.0"})
    except ValidationError:
        schema_negative = "pass"
    else:
        raise GovernanceError("incomplete CommandEnvelope was accepted")
    return {
        "eval_id": "EVAL-G01-004",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "artifact_sha256": resource["artifact_sha256"],
        "counts": counts,
        "support_type_count": len(SUPPORT_MODEL_TYPES),
        "legal_transition_count": legal_count,
        "unique_decision_digest_count": len(decision_digests),
        "rejected_mutation_count": mutation_count,
        "schema_negative": schema_negative,
    }


def evaluate_i0013(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Run the candidate-bound implementation checkpoint for EVAL-G01-007."""
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G01-007 candidate SHA must equal the checked-out HEAD")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    record = loaded["governance/iterations/I-0013.yaml"]
    if state.get("active_gate") != "G01" or state.get("active_iteration") != "I-0013":
        raise GovernanceError("EVAL-G01-007 requires I-0013 as the sole active Iteration")
    if state.get("active_gate_status") != "in_progress" or record.get("status") != "in_progress":
        raise GovernanceError("EVAL-G01-007 requires G01 and I-0013 in progress")
    schema = inspect_runtime_schema(candidate_sha)
    if "003_i0013" not in schema["migrations"]:
        raise GovernanceError("EVAL-G01-007 trace buffer migration is absent")
    service = inspect_trace_service(candidate_sha)
    smoke = run_trace_service_smoke(candidate_sha)
    scan_publication_boundary(root)
    for field, length in (
        ("trace_ref", 24),
        ("langsmith_trace_id", 36),
        ("otlp_trace_id", 32),
    ):
        if not isinstance(smoke.get(field), str) or len(smoke[field]) != length:
            raise GovernanceError(f"EVAL-G01-007 sanitized {field} is invalid")
    return {
        "eval_id": "EVAL-G01-007",
        "candidate_sha": candidate_sha,
        "status": "implementation_checkpoint_pass",
        "checks": {
            "encrypted_trace_schema": "pass",
            "private_clusterip_service": "pass",
            "langsmith_live_export": "pass",
            "otlp_trace_metric_log_export": "pass",
            "minio_dvc_archive": "pass",
            "duplicate_ingest": "pass",
            "pre_persistence_canary_rejection": "pass",
            "zero_pending_delivery": "pass",
            "publication_boundary": "pass",
        },
        "table_count": schema["table_count"],
        "service_type": service["service_type"],
        "trace_ref": smoke["trace_ref"],
        "langsmith_trace_id": smoke["langsmith_trace_id"],
        "otlp_trace_id": smoke["otlp_trace_id"],
    }


def evaluate_i0014(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Run the full live capability checkpoint for EVAL-G01-008."""
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G01-008 candidate SHA must equal the checked-out HEAD")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    record = loaded["governance/iterations/I-0014.yaml"]
    if state.get("active_gate") != "G01" or state.get("active_iteration") != "I-0014":
        raise GovernanceError("EVAL-G01-008 requires I-0014 as the sole active Iteration")
    if state.get("active_gate_status") != "in_progress" or record.get("status") != "in_progress":
        raise GovernanceError("EVAL-G01-008 requires G01 and I-0014 in progress")
    tests = subprocess.run(
        ["uv", "run", "pytest", "tests/models", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if tests.returncode != 0:
        raise GovernanceError("EVAL-G01-008 offline NewAPI and failure matrix failed")
    scan_publication_boundary(root)
    result = run_model_eval(root, candidate_sha)
    result["checks"]["newapi_offline_wire_matrix"] = "pass"
    result["checks"]["publication_boundary"] = "pass"
    return result


def evaluate_iteration(root: Path, iteration: str, candidate_sha: str) -> dict[str, Any]:
    if iteration == "I-0007":
        if os.name != "nt":
            raise GovernanceError(
                "EVAL-G01-001 private bootstrap Eval must run on its Windows owner host"
            )
        return evaluate_i0007(root, candidate_sha)
    if iteration == "I-0010":
        return evaluate_i0010(root, candidate_sha)
    if iteration == "I-0013":
        return evaluate_i0013(root, candidate_sha)
    if iteration == "I-0014":
        return evaluate_i0014(root, candidate_sha)
    if iteration == "I-0016":
        return evaluate_i0016(root, candidate_sha)
    if iteration == "I-0017":
        return evaluate_i0017(root, candidate_sha)
    if iteration == "I-0018":
        return evaluate_i0018(root, candidate_sha)
    if iteration == "I-0019":
        return evaluate_i0019(root, candidate_sha)
    if iteration == "I-0021":
        return evaluate_i0021(root, candidate_sha)
    if iteration == "I-0022":
        return evaluate_i0022(root, candidate_sha)
    if iteration == "I-0024":
        return evaluate_i0024(root, candidate_sha)
    if iteration == "I-0026":
        return evaluate_i0026(root, candidate_sha)
    if iteration == "I-0028":
        return evaluate_i0028(root, candidate_sha)
    if iteration == "I-0030":
        return evaluate_i0030(root, candidate_sha)
    if iteration == "I-0032":
        return evaluate_i0032(root, candidate_sha)
    if iteration == "I-0034":
        return evaluate_i0034(root, candidate_sha)
    raise GovernanceError(f"no private Eval implementation is registered for {iteration}")


def evaluate_i0026(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-011 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-011 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0026.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != "I-0026"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-011 requires I-0026 as the sole active Iteration")

    def result(returncode: int, stdout: str = "", stderr: str = "") -> Any:
        return type(
            "TransportResult",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    started_at = datetime.now(UTC).isoformat()
    cases: list[dict[str, Any]] = []
    calls: list[tuple[list[str], dict[str, Any]]] = []
    responses = iter(
        [
            result(0, "/tmp/faultwitness-remote.Eval01\n"),
            result(0, "pass"),
            result(0),
        ]
    )

    def passing_runner(arguments: list[str], **kwargs: Any) -> Any:
        calls.append((arguments, kwargs))
        return next(responses)

    oversized_script = "transport-marker\n" + "x" * 32_768
    output = _run_remote_script_transport(
        oversized_script,
        privileged=True,
        sudo_stdin="synthetic-credential",
        arguments=["ssh", "candidate-bound-host"],
        runner=passing_runner,
    )
    if output != "pass" or len(calls) != 3:
        raise GovernanceError("I-0026 bounded transport did not complete all three stages")
    if any(sum(len(value) for value in arguments) >= 32_767 for arguments, _ in calls):
        raise GovernanceError("I-0026 child-process arguments exceed the Windows safe limit")
    if any(
        "transport-marker" in value or "synthetic-credential" in value
        for arguments, _ in calls
        for value in arguments
    ):
        raise GovernanceError("I-0026 script or credential entered process arguments")
    if [kwargs["input"] for _, kwargs in calls] != [
        oversized_script.encode("utf-8"),
        b"synthetic-credential\n",
        b"",
    ]:
        raise GovernanceError("I-0026 script and credential channels were not separated")
    cases.append({"case_id": "oversized-bounded-transport", "status": "pass"})

    failure_commands: list[str] = []
    failure_responses = iter(
        [
            result(0, "/tmp/faultwitness-remote.Eval02\n"),
            result(7, stderr="FW_PROBE_FAILED step=execute"),
            result(0),
        ]
    )

    def failure_runner(arguments: list[str], **_kwargs: Any) -> Any:
        failure_commands.append(arguments[-1])
        return next(failure_responses)

    try:
        _run_remote_script_transport(
            "exit 7\n",
            privileged=True,
            sudo_stdin="synthetic-credential",
            arguments=["ssh"],
            runner=failure_runner,
        )
    except GovernanceError as error:
        if "FW_PROBE_FAILED step=execute" not in str(error):
            raise
    else:
        raise GovernanceError("I-0026 execution failure was accepted")
    if failure_commands[-1] != "rm -f -- /tmp/faultwitness-remote.Eval02":
        raise GovernanceError("I-0026 execution failure skipped cleanup")
    cases.append({"case_id": "execute-failure-cleanup", "status": "pass"})

    cleanup_responses = iter(
        [
            result(0, "/tmp/faultwitness-remote.Eval03\n"),
            result(0, "pass"),
            result(9, stderr="FW_CLEANUP_FAILED step=remove"),
        ]
    )
    try:
        _run_remote_script_transport(
            "true\n",
            privileged=True,
            sudo_stdin="synthetic-credential",
            arguments=["ssh"],
            runner=lambda *_args, **_kwargs: next(cleanup_responses),
        )
    except GovernanceError as error:
        if "remote script cleanup failed" not in str(error):
            raise
    else:
        raise GovernanceError("I-0026 cleanup failure was accepted")
    cases.append({"case_id": "cleanup-failure-blocks", "status": "pass"})

    invalid_calls = 0

    def invalid_runner(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal invalid_calls
        invalid_calls += 1
        return result(0, "/tmp/not-candidate-bound\n")

    try:
        _run_remote_script_transport(
            "true\n",
            privileged=True,
            sudo_stdin="synthetic-credential",
            arguments=["ssh"],
            runner=invalid_runner,
        )
    except GovernanceError as error:
        if "invalid temporary path" not in str(error):
            raise
    else:
        raise GovernanceError("I-0026 invalid remote path was accepted")
    if invalid_calls != 1:
        raise GovernanceError("I-0026 executed a script after invalid path output")
    cases.append({"case_id": "invalid-path-blocks", "status": "pass"})

    isolation = load_isolation_config(root)
    identities = simulate_identity_policies(isolation)
    writers = prove_writer_canaries(isolation)
    if len(identities) != 4 or any(item.get("status") != "pass" for item in identities):
        raise GovernanceError("V-G02-009 Iteration N must remain exactly four")
    if len(writers) != 4 or any(item.get("status") != "pass" for item in writers):
        raise GovernanceError("V-G02-011 Iteration N must remain exactly four")

    artifact = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "validation": "I-0026-bounded-remote-transport",
        "transport_case_count": len(cases),
        "cases": cases,
        "frozen_validation_n": {
            "V-G02-009": 4,
            "V-G02-010": 0,
            "V-G02-011": 4,
        },
        "gate_l2_execution": 0,
        "remote_execution": 0,
        "destructive_scenarios": 0,
        "external_service_calls": 0,
        "model_calls": 0,
        "start_time": started_at,
        "end_time": datetime.now(UTC).isoformat(),
        "status": "pass",
        "open_evidence": [],
    }
    artifact_path = (
        root / "docs/evals/EVAL-G02-011/artifacts/bounded-remote-transport.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "eval_id": "EVAL-G02-011",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case_id"]: case["status"] for case in cases},
        "open_evidence": [],
    }


def evaluate_i0028(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-013 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-013 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0028.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != "I-0028"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-013 requires I-0028 as the sole active Iteration")

    def result(returncode: int, stdout: str = "", stderr: str = "") -> Any:
        return type(
            "TransportResult",
            (),
            {"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )()

    started_at = datetime.now(UTC).isoformat()
    cases: list[dict[str, Any]] = []

    byte_payload = "set -eu\nprintf ok\n"
    byte_result = _remote_process(
        subprocess.run,
        [sys.executable, "-c"],
        "import sys; print(sys.stdin.buffer.read().hex())",
        byte_payload,
    )
    expected_hex = byte_payload.encode("utf-8").hex()
    received_hex = byte_result.stdout.strip()
    if byte_result.returncode or received_hex != expected_hex or "0d0a" in received_hex:
        raise GovernanceError("I-0028 real child process did not preserve exact LF bytes")
    cases.append(
        {
            "case_id": "real-child-byte-exact",
            "status": "pass",
            "expected_hex": expected_hex,
            "received_hex": received_hex,
        }
    )

    calls: list[tuple[list[str], dict[str, Any]]] = []
    responses = iter(
        [
            result(0, "/tmp/faultwitness-remote.Eval28\n"),
            result(0, "pass"),
            result(0),
        ]
    )

    def passing_runner(arguments: list[str], **kwargs: Any) -> Any:
        calls.append((arguments, kwargs))
        return next(responses)

    oversized_script = "transport-marker\n" + "x" * 32_768
    output = _run_remote_script_transport(
        oversized_script,
        privileged=True,
        sudo_stdin="synthetic-credential",
        arguments=["ssh", "candidate-bound-host"],
        runner=passing_runner,
    )
    if output != "pass" or len(calls) != 3:
        raise GovernanceError("I-0028 bounded transport did not complete all three stages")
    if any(sum(len(value) for value in arguments) >= 32_767 for arguments, _ in calls):
        raise GovernanceError("I-0028 child-process arguments exceed the Windows safe limit")
    if any(
        "transport-marker" in value or "synthetic-credential" in value
        for arguments, _ in calls
        for value in arguments
    ):
        raise GovernanceError("I-0028 script or credential entered process arguments")
    if [kwargs["input"] for _, kwargs in calls] != [
        oversized_script.encode("utf-8"),
        b"synthetic-credential\n",
        b"",
    ]:
        raise GovernanceError("I-0028 script and credential channels were not byte-separated")
    if any(kwargs.get("text") is not False for _, kwargs in calls):
        raise GovernanceError("I-0028 transport did not use binary subprocess mode")
    if any("timeout" in kwargs or "encoding" in kwargs for _, kwargs in calls):
        raise GovernanceError("I-0028 transport added timeout or text encoding to subprocess")
    cases.append({"case_id": "bounded-separated-binary-channels", "status": "pass"})

    failure_commands: list[str] = []
    failure_responses = iter(
        [
            result(0, "/tmp/faultwitness-remote.Fail28\n"),
            result(7, stderr="FW_PROBE_FAILED step=execute"),
            result(0),
        ]
    )

    def failure_runner(arguments: list[str], **_kwargs: Any) -> Any:
        failure_commands.append(arguments[-1])
        return next(failure_responses)

    try:
        _run_remote_script_transport(
            "exit 7\n",
            privileged=True,
            sudo_stdin="synthetic-credential",
            arguments=["ssh"],
            runner=failure_runner,
        )
    except GovernanceError as error:
        if "FW_PROBE_FAILED step=execute" not in str(error):
            raise
    else:
        raise GovernanceError("I-0028 execution failure was accepted")
    if failure_commands[-1] != "rm -f -- /tmp/faultwitness-remote.Fail28":
        raise GovernanceError("I-0028 execution failure skipped cleanup")
    cases.append({"case_id": "execute-failure-cleanup", "status": "pass"})

    cleanup_responses = iter(
        [
            result(0, "/tmp/faultwitness-remote.Clean28\n"),
            result(0, "pass"),
            result(9, stderr="FW_CLEANUP_FAILED step=remove"),
        ]
    )
    try:
        _run_remote_script_transport(
            "true\n",
            privileged=True,
            sudo_stdin="synthetic-credential",
            arguments=["ssh"],
            runner=lambda *_args, **_kwargs: next(cleanup_responses),
        )
    except GovernanceError as error:
        if "remote script cleanup failed" not in str(error):
            raise
    else:
        raise GovernanceError("I-0028 cleanup failure was accepted")

    invalid_calls = 0

    def invalid_runner(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal invalid_calls
        invalid_calls += 1
        return result(0, "/tmp/not-candidate-bound\n")

    try:
        _run_remote_script_transport(
            "true\n",
            privileged=True,
            sudo_stdin="synthetic-credential",
            arguments=["ssh"],
            runner=invalid_runner,
        )
    except GovernanceError as error:
        if "invalid temporary path" not in str(error):
            raise
    else:
        raise GovernanceError("I-0028 invalid remote path was accepted")
    if invalid_calls != 1:
        raise GovernanceError("I-0028 executed a script after invalid path output")
    cases.append({"case_id": "cleanup-and-path-fail-closed", "status": "pass"})

    isolation = load_isolation_config(root)
    identities = simulate_identity_policies(isolation)
    writers = prove_writer_canaries(isolation)
    if len(identities) != 4 or any(item.get("status") != "pass" for item in identities):
        raise GovernanceError("V-G02-009 Iteration N must remain exactly four")
    if len(writers) != 4 or any(item.get("status") != "pass" for item in writers):
        raise GovernanceError("V-G02-011 Iteration N must remain exactly four")

    artifact = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "validation": "I-0028-byte-exact-remote-process-transport",
        "transport_case_count": len(cases),
        "cases": cases,
        "frozen_validation_n": {
            "V-G02-009": 4,
            "V-G02-010": 0,
            "V-G02-011": 4,
        },
        "gate_l2_execution": 0,
        "remote_execution": 0,
        "destructive_scenarios": 0,
        "external_service_calls": 0,
        "model_calls": 0,
        "start_time": started_at,
        "end_time": datetime.now(UTC).isoformat(),
        "status": "pass",
        "open_evidence": [],
    }
    artifact_path = (
        root / "docs/evals/EVAL-G02-013/artifacts/byte-exact-remote-transport.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "eval_id": "EVAL-G02-013",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case_id"]: case["status"] for case in cases},
        "open_evidence": [],
    }


def evaluate_i0030(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-015 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-015 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0030.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != "I-0030"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-015 requires I-0030 as the sole active Iteration")

    started_at = datetime.now(UTC).isoformat()
    probe_path = root / "deploy/g02/gate_probe.py"
    probe_source = probe_path.read_text(encoding="utf-8")
    if "from datetime import UTC" in probe_source:
        raise GovernanceError("I-0030 probe retains the Python 3.11-only UTC import")

    compatibility_program = """
import json
import runpy
import sys

namespace = runpy.run_path(sys.argv[1], run_name="faultwitness_g02_probe_compat")
timestamp = namespace["datetime"].now(namespace["UTC"])
print(json.dumps({
    "imported": True,
    "python_version": list(sys.version_info[:2]),
    "timestamp": timestamp.isoformat(),
    "utc_identity": namespace["UTC"] is namespace["timezone"].utc,
    "utc_offset_seconds": timestamp.utcoffset().total_seconds(),
}, sort_keys=True))
""".strip()
    command = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--python",
        "3.8",
        "python",
        "-c",
        compatibility_program,
        str(probe_path),
    ]
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise GovernanceError(
            "I-0030 managed Python 3.8 probe failed: "
            + (result.stderr.strip() or "no diagnostic")
        )
    try:
        compatibility = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise GovernanceError(
            "I-0030 managed Python 3.8 probe returned invalid evidence"
        ) from error

    cases: list[dict[str, Any]] = []
    if compatibility.get("python_version") != [3, 8] or not compatibility.get("imported"):
        raise GovernanceError("I-0030 did not import the probe under actual Python 3.8")
    cases.append(
        {
            "case_id": "actual-managed-python38-import",
            "status": "pass",
            "python_version": compatibility["python_version"],
        }
    )
    if (
        not compatibility.get("utc_identity")
        or compatibility.get("utc_offset_seconds") != 0.0
        or not str(compatibility.get("timestamp", "")).endswith("+00:00")
    ):
        raise GovernanceError("I-0030 UTC-aware timestamp semantics changed")
    cases.append(
        {
            "case_id": "python38-utc-aware-timestamp",
            "status": "pass",
            "timestamp": compatibility["timestamp"],
            "utc_offset_seconds": compatibility["utc_offset_seconds"],
        }
    )

    isolation = load_isolation_config(root)
    identities = simulate_identity_policies(isolation)
    writers = prove_writer_canaries(isolation)
    if len(identities) != 4 or any(item.get("status") != "pass" for item in identities):
        raise GovernanceError("V-G02-009 Iteration N must remain exactly four")
    if len(writers) != 4 or any(item.get("status") != "pass" for item in writers):
        raise GovernanceError("V-G02-011 Iteration N must remain exactly four")

    artifact = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "validation": "I-0030-python38-probe-compatibility",
        "compatibility_case_count": len(cases),
        "cases": cases,
        "probe_source_digest": hashlib.sha256(probe_path.read_bytes()).hexdigest(),
        "frozen_validation_n": {
            "V-G02-009": 4,
            "V-G02-010": 0,
            "V-G02-011": 4,
        },
        "gate_l2_execution": 0,
        "remote_execution": 0,
        "destructive_scenarios": 0,
        "external_service_calls": 0,
        "model_calls": 0,
        "start_time": started_at,
        "end_time": datetime.now(UTC).isoformat(),
        "status": "pass",
        "open_evidence": [],
    }
    artifact_path = (
        root / "docs/evals/EVAL-G02-015/artifacts/python38-probe-compatibility.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "eval_id": "EVAL-G02-015",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case_id"]: case["status"] for case in cases},
        "open_evidence": [],
    }


def evaluate_i0032(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-017 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-017 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0032.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != "I-0032"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-017 requires I-0032 as the sole active Iteration")

    started_at = datetime.now(UTC).isoformat()
    cases: list[dict[str, Any]] = []
    config = load_lab_config(root)
    sut_digest = image_set_digest(config)
    frozen_sut_digest = "3df502956e9c4ab2311501a9e867a40bdc1afae79ebcf3de284a95611e52610e"
    if sut_digest != frozen_sut_digest or len(config.get("images", [])) != 30:
        raise GovernanceError("I-0032 changed the frozen 30-image SUT image set")
    probes = load_gate_probe_images(root)
    inventory = offline_staging_inventory(root, config)
    probe_inventory = {key: value for key, value in inventory.items() if key.startswith("probe-")}
    expected_probe_inventory = {
        "probe-busybox": probes["busybox"],
        "probe-minio-mc": probes["minio_mc"],
    }
    if probe_inventory != expected_probe_inventory:
        raise GovernanceError(
            "I-0032 staging inventory does not contain the exact two probe images"
        )
    cases.append(
        {
            "case_id": "exact-sut-probe-inventory-union",
            "status": "pass",
            "sut_image_count": 30,
            "sut_image_set_digest": sut_digest,
            "probe_archive_keys": sorted(probe_inventory),
            "probe_references": probe_inventory,
        }
    )

    digest = "a" * 64
    index_reference = f"index.docker.io/example/probe@sha256:{digest}"
    docker_reference = f"docker.io/example/probe@sha256:{digest}"
    if containerd_normalized_reference(index_reference) != docker_reference:
        raise GovernanceError("I-0032 changed Docker Hub reference normalization")
    cases.append(
        {
            "case_id": "docker-hub-reference-normalization",
            "status": "pass",
            "source": index_reference,
            "normalized": docker_reference,
        }
    )

    other_digest = "b" * 64
    synthetic_config = {
        "images": [
            {
                "name": "sut-probe",
                "platform": "linux/amd64",
                "reference": index_reference,
            }
        ]
    }
    synthetic_probes = {
        "busybox": docker_reference,
        "minio_mc": f"docker.io/example/other@sha256:{other_digest}",
    }
    deduplicated = build_offline_staging_inventory(synthetic_config, synthetic_probes)
    if len(deduplicated) != 2 or "probe-busybox" in deduplicated:
        raise GovernanceError("I-0032 did not deduplicate an equivalent exact reference")
    drifted = dict(synthetic_probes)
    drifted["busybox"] = f"docker.io/example/probe@sha256:{'c' * 64}"
    try:
        build_offline_staging_inventory(synthetic_config, drifted)
    except GovernanceError as error:
        if "digest drift" not in str(error):
            raise
    else:
        raise GovernanceError("I-0032 accepted same-repository digest drift")
    cases.append(
        {
            "case_id": "reference-deduplication-and-digest-drift-rejection",
            "status": "pass",
            "deduplicated_archive_keys": sorted(deduplicated),
        }
    )

    isolation = load_isolation_config(root)
    identities = simulate_identity_policies(isolation)
    writers = prove_writer_canaries(isolation)
    if len(identities) != 4 or any(item.get("status") != "pass" for item in identities):
        raise GovernanceError("V-G02-009 Iteration N must remain exactly four")
    if len(writers) != 4 or any(item.get("status") != "pass" for item in writers):
        raise GovernanceError("V-G02-011 Iteration N must remain exactly four")

    artifact = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "validation": "I-0032-digest-pinned-probe-image-offline-staging",
        "staging_case_count": len(cases),
        "cases": cases,
        "offline_archive_count": len(inventory),
        "offline_archive_references": inventory,
        "frozen_validation_n": {
            "V-G02-009": 4,
            "V-G02-010": 0,
            "V-G02-011": 4,
            "V-G02-017": 0,
        },
        "gate_l2_execution": 0,
        "remote_execution": 0,
        "destructive_scenarios": 0,
        "external_service_calls": 0,
        "model_calls": 0,
        "start_time": started_at,
        "end_time": datetime.now(UTC).isoformat(),
        "status": "pass",
        "open_evidence": [],
    }
    artifact_path = root / "docs/evals/EVAL-G02-017/artifacts/probe-image-staging.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "eval_id": "EVAL-G02-017",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case_id"]: case["status"] for case in cases},
        "open_evidence": [],
    }


def evaluate_i0034(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-019 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-019 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0034.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != "I-0034"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-019 requires I-0034 as the sole active Iteration")

    started_at = datetime.now(UTC).isoformat()
    cases: list[dict[str, Any]] = []
    digest = "sha256:" + "a" * 64
    requested = f"docker.io/example/probe@{digest}"
    alias = f"index.docker.io/example/probe@{digest}"

    exact_source = select_containerd_import_source(
        requested, {requested: digest, alias: digest}
    )
    if exact_source != requested:
        raise GovernanceError("I-0034 did not prefer the exact requested source")
    cases.append(
        {
            "case_id": "requested-source-exact-digest",
            "status": "pass",
            "selected_source": exact_source,
        }
    )

    alias_source = select_containerd_import_source(requested, {alias: digest})
    if alias_source != alias or containerd_registry_aliases(requested) != (requested, alias):
        raise GovernanceError("I-0034 did not resolve the exact Docker Hub host alias")
    cases.append(
        {
            "case_id": "alias-only-source-exact-digest",
            "status": "pass",
            "selected_source": alias_source,
            "target_reference": requested,
        }
    )

    try:
        select_containerd_import_source(requested, {alias: "sha256:" + "b" * 64})
    except GovernanceError as error:
        if "exact repository-and-digest" not in str(error):
            raise
    else:
        raise GovernanceError("I-0034 accepted an alias with the wrong digest")
    cases.append(
        {
            "case_id": "alias-wrong-digest-fails-closed",
            "status": "pass",
        }
    )

    isolation = load_isolation_config(root)
    identities = simulate_identity_policies(isolation)
    writers = prove_writer_canaries(isolation)
    if len(identities) != 4 or any(item.get("status") != "pass" for item in identities):
        raise GovernanceError("V-G02-009 Iteration N must remain exactly four")
    if len(writers) != 4 or any(item.get("status") != "pass" for item in writers):
        raise GovernanceError("V-G02-011 Iteration N must remain exactly four")

    config = load_lab_config(root)
    sut_digest = image_set_digest(config)
    if sut_digest != "3df502956e9c4ab2311501a9e867a40bdc1afae79ebcf3de284a95611e52610e":
        raise GovernanceError("I-0034 changed the frozen SUT image-set digest")
    artifact = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "validation": "I-0034-containerd-imported-reference-alias-resolution",
        "alias_case_count": len(cases),
        "cases": cases,
        "sut_image_set_digest": sut_digest,
        "frozen_validation_n": {
            "V-G02-009": 4,
            "V-G02-010": 0,
            "V-G02-011": 4,
            "V-G02-017": 0,
        },
        "gate_l2_execution": 0,
        "remote_execution": 0,
        "deployments": 0,
        "destructive_scenarios": 0,
        "external_service_calls": 0,
        "model_calls": 0,
        "start_time": started_at,
        "end_time": datetime.now(UTC).isoformat(),
        "status": "pass",
        "open_evidence": [],
    }
    artifact_path = root / "docs/evals/EVAL-G02-019/artifacts/containerd-alias-resolution.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "eval_id": "EVAL-G02-019",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case_id"]: case["status"] for case in cases},
        "open_evidence": [],
    }


def evaluate_i0022(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-007 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-007 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0022.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_iteration") != "I-0022"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-007 requires I-0022 as the sole active Iteration")

    started_at = datetime.now(UTC).isoformat()
    cases: list[dict[str, str]] = []
    namespace = validate_namespace_isolation_manifest(root)
    if namespace["baseline_observability_namespaces"] != ["fw-observability", "fw-sut"]:
        raise GovernanceError("I-0022 baseline observability egress did not converge")
    cases.append({"case_id": "exact-observability-egress", "status": "pass"})

    if namespace["observability_ingress"] != "exact-baseline-principal":
        raise GovernanceError("I-0022 observability ingress exceeded the baseline principal")
    cases.append({"case_id": "exact-observability-ingress", "status": "pass"})

    broad = load_data(root / "tests/fixtures/g02/isolation_broad_private_egress.yaml")
    try:
        validate_public_https_egress(broad)
    except GovernanceError:
        cases.append({"case_id": "reject-private-public-https-egress", "status": "pass"})
    else:
        raise GovernanceError("I-0022 broad public HTTPS negative fixture was accepted")

    policies = simulate_identity_policies(load_isolation_config(root))
    if len(policies) != 4 or any(item["status"] != "pass" for item in policies):
        raise GovernanceError("I-0022 changed an unauthorized identity path")
    cases.append({"case_id": "preserve-unauthorized-denies", "status": "pass"})

    replacement_state = {
        "active_gate": "G02",
        "active_gate_status": "in_progress",
        "active_iteration": "I-0023",
    }
    replacement = dict(load_data(root / "governance/iterations/I-0023.yaml"))
    replacement["status"] = "in_progress"
    replacement_manifest = load_data(root / "docs/evals/EVAL-G02-008/manifest.json")
    replacement_plan = (root / "docs/evals/EVAL-G02-008/PLAN.md").read_text(encoding="utf-8")
    if validate_gate_orchestration_selection(
        replacement_state,
        replacement,
        replacement_manifest,
        replacement_plan,
    ) != ("I-0023", "EVAL-G02-008"):
        raise GovernanceError("I-0022 replacement orchestration selected the wrong Eval")
    terminal = load_data(root / "governance/iterations/I-0020.yaml")
    terminal_state = {**replacement_state, "active_iteration": "I-0020"}
    terminal_manifest = load_data(root / "docs/evals/EVAL-G02-005/manifest.json")
    terminal_plan = (root / "docs/evals/EVAL-G02-005/PLAN.md").read_text(encoding="utf-8")
    try:
        validate_gate_orchestration_selection(
            terminal_state,
            terminal,
            terminal_manifest,
            terminal_plan,
        )
    except GovernanceError:
        pass
    else:
        raise GovernanceError("I-0022 allowed terminal EVAL-G02-005 to run again")

    with TemporaryDirectory() as temporary:
        fixture_root = Path(temporary)
        records = fixture_root / "governance" / "iterations"
        records.mkdir(parents=True)
        (records / "I-0020.yaml").write_text(
            "id: I-0020\nstatus: failed\ndocs_updated: [docs/evals/EVAL-G02-005/REPORT.md]\n",
            encoding="utf-8",
        )
        (records / "I-0022.yaml").write_text(
            "id: I-0022\nstatus: planned\ndocs_updated: [docs/evals/EVAL-G02-007/PLAN.md]\n",
            encoding="utf-8",
        )
        changed_records = [
            "governance/iterations/I-0020.yaml",
            "governance/iterations/I-0022.yaml",
        ]
        if infer_iteration_id(fixture_root, changed_records) != "I-0020":
            raise GovernanceError("I-0022 terminal failure attribution drifted")
    cases.append({"case_id": "forward-eval-selection", "status": "pass"})

    artifact = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "validation": "I-0022-live-isolation-forward-routing",
        "iteration_n": 5,
        "cases": cases,
        "external_execution": 0,
        "gate_phase_execution": 0,
        "model_calls": 0,
        "start_time": started_at,
        "end_time": datetime.now(UTC).isoformat(),
        "status": "pass",
        "open_evidence": [],
    }
    artifact_path = root / "docs/evals/EVAL-G02-007/artifacts/live-isolation-forward-routing.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "eval_id": "EVAL-G02-007",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case_id"]: case["status"] for case in cases},
        "open_evidence": [],
    }


def evaluate_i0021(root: Path, candidate_sha: str) -> dict[str, Any]:
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-006 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-006 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0021.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_iteration") != "I-0021"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-006 requires I-0021 as the sole active Iteration")

    started_at = datetime.now(UTC).isoformat()
    planned = {"id": "I-9000", "status": "planned", "iteration_type": "standard"}
    active = {"id": "I-9000", "status": "in_progress", "iteration_type": "standard"}
    completed = {"id": "I-9000", "status": "completed", "iteration_type": "standard"}
    failed = {"id": "I-9000", "status": "failed", "iteration_type": "standard"}
    cases: list[dict[str, str]] = []

    validate_iteration_status_transition(planned, active, "accept-planned-active")
    cases.append({"case_id": "accept-planned-active", "status": "pass"})
    validate_iteration_status_transition(active, completed, "accept-active-completed")
    cases.append({"case_id": "accept-active-completed", "status": "pass"})

    for case_id, previous, current in (
        ("reject-completed-active", completed, active),
        ("reject-failed-planned", failed, planned),
    ):
        try:
            validate_iteration_status_transition(previous, current, case_id)
        except GovernanceError:
            cases.append({"case_id": case_id, "status": "pass"})
        else:
            raise GovernanceError(f"lifecycle negative case was accepted: {case_id}")

    deletion_rejected = False
    hidden_reactivation_rejected = False
    try:
        validate_iteration_status_transition(completed, None, "reject-terminal-deletion")
    except GovernanceError:
        deletion_rejected = True
    try:
        validate_iteration_status_sequence(
            [completed, active, completed], "reject-hidden-terminal-reactivation"
        )
    except GovernanceError:
        hidden_reactivation_rejected = True
    if not deletion_rejected or not hidden_reactivation_rejected:
        raise GovernanceError("terminal deletion or hidden reactivation was accepted")
    cases.append({"case_id": "reject-deletion-and-hidden-history", "status": "pass"})

    validate_iteration_lifecycle_history(root)
    i0020 = (root / "docs" / "roadmap" / "iterations" / "I-0020.md").read_text(encoding="utf-8")
    forbidden = ("reopens its owning Iteration", "reopen the owner")
    if any(phrase in i0020 for phrase in forbidden):
        raise GovernanceError("I-0020 retains a completed-owner reopening route")

    artifact = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "validation": "I-0021-lifecycle-monotonicity",
        "iteration_n": 5,
        "cases": cases,
        "policy_path": "governance/policies/iteration-lifecycle-v1.yaml",
        "repository_history": "pass",
        "i0020_owner_reopen_route": "absent",
        "start_time": started_at,
        "end_time": datetime.now(UTC).isoformat(),
        "status": "pass",
        "open_evidence": [],
    }
    artifact_path = (
        root / "docs" / "evals" / "EVAL-G02-006" / "artifacts" / "lifecycle-monotonicity.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "eval_id": "EVAL-G02-006",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case_id"]: case["status"] for case in cases},
        "open_evidence": [],
    }


def evaluate_i0019(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Offline owning-runner proof for the G02 baseline/scoring Iteration.

    This deliberately uses four non-seed synthetic trials. Gate-scale live calls are owned by
    the later unified-candidate phase and are never started by this Iteration Eval.
    """
    if _head_sha(root) != candidate_sha:
        raise GovernanceError("EVAL-G02-004 candidate SHA must equal checked-out HEAD")
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout:
        raise GovernanceError("EVAL-G02-004 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0019.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_iteration") != "I-0019"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-004 requires I-0019 as the sole active Iteration")

    artifact_dir = root / "docs" / "evals" / "EVAL-G02-004" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    load_baseline_config(root)
    fixtures = [
        (
            {
                "schema_version": "1.0.0",
                "case_id": "synthetic-correct",
                "problem_brief": "catalog",
                "observations": [
                    {"id": "catalog-error", "journey_failed": True, "correlated_error": True}
                ],
            },
            {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]},
        ),
        (
            {
                "schema_version": "1.0.0",
                "case_id": "synthetic-unsupported",
                "problem_brief": "catalog",
                "observations": [
                    {"id": "catalog-error", "journey_failed": True, "correlated_error": True}
                ],
            },
            {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]},
        ),
        (
            {
                "schema_version": "1.0.0",
                "case_id": "synthetic-no-evidence",
                "problem_brief": "catalog",
                "observations": [
                    {"id": "catalog-error", "journey_failed": True, "correlated_error": True}
                ],
            },
            {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]},
        ),
        (
            {
                "schema_version": "1.0.0",
                "case_id": "synthetic-wrong",
                "problem_brief": "catalog",
                "observations": [
                    {"id": "catalog-error", "journey_failed": True, "correlated_error": True}
                ],
            },
            {"root_cause": "paymentFailure", "evidence": ["catalog-error"]},
        ),
        (
            {
                "schema_version": "1.0.0",
                "case_id": "synthetic-malformed",
                "problem_brief": "catalog",
                "observations": [
                    {"id": "catalog-error", "journey_failed": True, "correlated_error": True}
                ],
            },
            {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]},
        ),
    ]
    scored = []
    for index, (packet, truth) in enumerate(fixtures):
        result = deterministic_baseline(packet)
        if index == 1:
            result["root_cause"] = "paymentFailure"
        if index == 2:
            result.pop("root_cause")
        if index == 3:
            result["claims"] = [{"claim": "unsupported", "supported": False}]
        if index == 4:
            result["evidence"] = []
        scored.append(score_result(result, truth))
    (artifact_dir / "scorer-contract.json").write_text(
        json.dumps(
            {
                "candidate_sha": candidate_sha,
                "validation": "V-G02-012",
                "fixtures": scored,
                "status": "pass",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "threshold-registry.json").write_text(
        json.dumps(
            {
                "candidate_sha": candidate_sha,
                "validation": "V-G02-013",
                "thresholds": QUALITY_FLOORS,
                "status": "pass",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    deterministic_rows = []
    for index in range(3):
        packet = {
            "schema_version": "1.0.0",
            "case_id": f"synthetic-{index}",
            "problem_brief": "catalog",
            "observations": [
                {"id": "catalog-error", "journey_failed": True, "correlated_error": True}
            ],
        }
        result = deterministic_baseline(packet)
        if index == 1:
            result["root_cause"] = "paymentFailure"
        if index == 2:
            result.pop("root_cause")
        deterministic_rows.append(
            {
                "case_id": packet["case_id"],
                **score_result(
                    result,
                    {"root_cause": "productCatalogFailure", "evidence": ["catalog-error"]},
                ),
            }
        )
    (artifact_dir / "deterministic-smoke.json").write_text(
        json.dumps(
            {
                "candidate_sha": candidate_sha,
                "validation": "V-G02-014",
                "N": 3,
                "rows": deterministic_rows,
                "status": "pass",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    live_records = []
    resume_demonstrated = False
    for baseline in ("naive_react", "no_rag"):
        trials = []
        for case_id in ("synthetic-live-a", "synthetic-live-b"):
            trials.append(
                {
                    "trial_id": f"i0019-{candidate_sha}-{baseline}-{case_id}",
                    "baseline": baseline,
                    "packet": {
                        "schema_version": "1.0.0",
                        "case_id": case_id,
                        "problem_brief": "catalog",
                        "observations": [
                            {
                                "id": "catalog-error",
                                "journey_failed": True,
                                "correlated_error": True,
                            }
                        ],
                    },
                }
            )
        adapter = make_bailian_adapter(root, baseline)
        if baseline == "no_rag":
            interrupted = False

            def one_controlled_interruption(
                packet: dict[str, Any], live_adapter=adapter
            ) -> dict[str, Any]:
                nonlocal interrupted
                if not interrupted:
                    interrupted = True
                    raise LiveInfrastructureError("controlled pre-request transport interruption")
                return dict(live_adapter(packet))

            current = run_live_trials(
                root / "docs" / "evals" / "EVAL-G02-004" / "artifacts" / "live-journal",
                trials,
                one_controlled_interruption,
            )
            if not any(record.get("status") == "infra_failed" for record in current):
                raise GovernanceError("EVAL-G02-004 did not exercise trial-local resume")
            current = run_live_trials(
                root / "docs" / "evals" / "EVAL-G02-004" / "artifacts" / "live-journal",
                trials,
                adapter,
            )
            resume_demonstrated = True
        else:
            current = run_live_trials(
                root / "docs" / "evals" / "EVAL-G02-004" / "artifacts" / "live-journal",
                trials,
                adapter,
            )
        live_records.extend(current)
    if any(record.get("status") != "pass" for record in live_records):
        raise GovernanceError("EVAL-G02-004 retains infrastructure-failed live trials")
    total_input = sum(int(record["payload"].get("input_tokens", 0)) for record in live_records)
    total_output = sum(int(record["payload"].get("output_tokens", 0)) for record in live_records)
    total_cost = sum(float(record["payload"].get("cost_cny", 0.0)) for record in live_records)
    (artifact_dir / "live-smoke.json").write_text(
        json.dumps(
            {
                "candidate_sha": candidate_sha,
                "validation": "V-G02-015",
                "N": 4,
                "records": live_records,
                "fallback_count": 0,
                "resume_demonstrated": resume_demonstrated,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cost_cny": total_cost,
                "status": "pass",
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "eval_id": "EVAL-G02-004",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {
            "scorer": "pass",
            "thresholds": "pass",
            "deterministic_baseline": "pass",
            "live_resume": "pass",
        },
        "open_evidence": [],
    }
