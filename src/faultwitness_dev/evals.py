from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
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
from faultwitness_dev.errors import GovernanceError
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
    if askpass_source_marker.read_text(encoding="utf-8").strip() != expected[
        "ssh_askpass_source"
    ]:
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
    expected_deferred = {
        "bailian.api_key": "deferred_to_I-0013_live_eval",
        "langsmith.api_key": "deferred_to_I-0014_live_eval",
    }
    if any(verification.get(name) != status for name, status in expected_deferred.items()):
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
    actual_recipient = derive_age_recipient(
        default_age_keygen_executable(), paths.identity_file
    )
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

    commands = {
        command["id"]: command for command in documents["commands_events"]["commands"]
    }
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
                facts={name: True for name in transition["preconditions"]},
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


def evaluate_iteration(root: Path, iteration: str, candidate_sha: str) -> dict[str, Any]:
    if iteration == "I-0007":
        if os.name != "nt":
            raise GovernanceError(
                "EVAL-G01-001 private bootstrap Eval must run on its Windows owner host"
            )
        return evaluate_i0007(root, candidate_sha)
    if iteration == "I-0010":
        return evaluate_i0010(root, candidate_sha)
    raise GovernanceError(f"no private Eval implementation is registered for {iteration}")
