"""Candidate-bound G01 audit and close-readiness checks.

The evaluator deliberately separates evidence collection from Gate closure.  It never
changes Gate thresholds and it never edits manifests; the evidence-sync commit remains
an explicit operator action after a candidate has been evaluated.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultwitness_dev.audit import audit_repository, scan_publication_boundary
from faultwitness_dev.control_api_deploy import (
    inspect_control_api,
    inspect_keycloak_realm,
    run_control_api_smoke,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g01_recovery import run_postgres_restore_rehearsal
from faultwitness_dev.infra import (
    audit_runtime_coexistence,
    run_network_matrix,
    run_remote_script,
    run_runtime_smokes,
)
from faultwitness_dev.model_deploy import inspect_model_gateway, run_model_gateway_smoke
from faultwitness_dev.observability_deploy import (
    inspect_trace_service,
    run_trace_service_smoke,
)
from faultwitness_dev.platform import inspect_platform_readiness
from faultwitness_dev.runtime_deploy import inspect_runtime_schema
from faultwitness_dev.schemas import load_data, validate_repository_schemas

FULL_SHA_LEN = 40
ITERATIONS = [f"I-{number:04d}" for number in range(7, 16)]
EVALS = [f"EVAL-G01-{number:03d}" for number in range(1, 10)]
STABILITY_SECONDS = 900


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "-c", "safe.directory=" + str(root), "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _require_candidate(root: Path, candidate_sha: str) -> None:
    if len(candidate_sha) != FULL_SHA_LEN or any(
        c not in "0123456789abcdef" for c in candidate_sha
    ):
        raise GovernanceError("candidate SHA must be a full lowercase 40-character SHA")
    if _head(root) != candidate_sha:
        raise GovernanceError("G01 candidate SHA must equal checked-out HEAD")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    if state.get("active_gate") != "G01" or state.get("active_gate_status") != "in_progress":
        raise GovernanceError("G01 must remain in progress during candidate audit")


def _run(root: Path, args: list[str], *, timeout: int = 180) -> str:
    result = subprocess.run(
        args,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise GovernanceError(
            "candidate command failed: "
            f"{' '.join(args)}\n{result.stdout[-1200:]}\n{result.stderr[-1200:]}"
        )
    return result.stdout


def _test_group(root: Path, *paths: str) -> dict[str, Any]:
    output = _run(root, ["uv", "run", "pytest", *paths, "-q"], timeout=240)
    return {"status": "pass", "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def _eval_manifest_debt(root: Path, candidate_sha: str, *, include_final: bool) -> list[str]:
    stop = 10 if include_final else 9
    debt: list[str] = []
    for number in range(1, stop):
        path = root / "docs" / "evals" / f"EVAL-G01-{number:03d}" / "manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        if (
            document.get("status") != "pass"
            or document.get("evaluated_revision") != candidate_sha
            or document.get("open_evidence")
        ):
            debt.append(document["eval_id"])
    return debt


def _platform_stability(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Apply the operator's narrow post-window generic-error adjudication."""
    started = time.monotonic()
    try:
        return inspect_platform_readiness(
            root,
            candidate_sha,
            stability_seconds=STABILITY_SECONDS,
        )
    except GovernanceError as error:
        elapsed = time.monotonic() - started
        generic = "remote_command_or_transport_failed" in str(error)
        if elapsed < STABILITY_SECONDS or not generic:
            raise
        return {
            "status": "operator_adjudicated_pass",
            "candidate_sha": candidate_sha,
            "stability_seconds": STABILITY_SECONDS,
            "reason": "generic remote error occurred only after the full clean window",
        }


def inspect_g01_reconciliation(candidate_sha: str) -> dict[str, Any]:
    """Fail closed on candidate drift and unresolved durable runtime work."""
    if len(candidate_sha) != FULL_SHA_LEN or any(
        character not in "0123456789abcdef" for character in candidate_sha
    ):
        raise GovernanceError("candidate SHA must be a full lowercase 40-character SHA")
    query = """SELECT count(*) FROM runtime_shared.dead_letter;
SELECT sum(pending) FROM (
  SELECT count(*) AS pending FROM incident_owner.outbox WHERE state <> 'PUBLISHED'
  UNION ALL SELECT count(*) FROM task_owner.outbox WHERE state <> 'PUBLISHED'
  UNION ALL SELECT count(*) FROM graph_owner.outbox WHERE state <> 'PUBLISHED'
  UNION ALL SELECT count(*) FROM action_owner.outbox WHERE state <> 'PUBLISHED'
) AS outbox_counts;
SELECT count(*) FROM task_owner.lease WHERE expires_at <= now();
SELECT count(*) FROM trace_buffer_owner.delivery WHERE state <> 'ACKED';
SELECT count(*) FROM runtime_shared.schema_version
WHERE version IN ('001_i0011','002_i0012','003_i0013');
"""
    encoded_query = base64.b64encode(query.encode()).decode()
    bindings = (
        ("fw-system", "fw-platform-candidate-binding"),
        ("fw-system", "fw-runtime-candidate-binding"),
        ("fw-system", "fw-keycloak-realm-candidate"),
        ("fw-control", "fw-control-api-candidate"),
        ("fw-control", "fw-trace-candidate"),
        ("fw-control", "fw-model-candidate"),
    )
    binding_checks = "\n".join(
        "/usr/local/bin/k3s kubectl -n "
        f"{namespace} get configmap {name} "
        "-o jsonpath='{.data.candidate_sha}'; printf '\\n'"
        for namespace, name in bindings
    )
    script = f"""set -eu
{binding_checks}
printf %s {encoded_query} | base64 -d | \
  /usr/local/bin/k3s kubectl -n fw-data exec -i postgres-0 -- sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -At -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
"""
    lines = [
        line.strip()
        for line in run_remote_script(script, privileged=True).splitlines()
        if line.strip()
    ]
    if len(lines) != len(bindings) + 5:
        raise GovernanceError("G01 reconciliation returned an incomplete sanitized result")
    observed_bindings = lines[: len(bindings)]
    if any(binding != candidate_sha for binding in observed_bindings):
        raise GovernanceError("G01 reconciliation detected candidate binding drift")
    try:
        dead_letters, outbox_pending, stale_leases, trace_pending, migration_count = map(
            int, lines[len(bindings) :]
        )
    except ValueError as error:
        raise GovernanceError("G01 reconciliation returned invalid counters") from error
    unresolved = {
        "dead_letters": dead_letters,
        "outbox_pending": outbox_pending,
        "stale_leases": stale_leases,
        "trace_pending": trace_pending,
    }
    if migration_count != 3 or any(unresolved.values()):
        raise GovernanceError(
            f"G01 reconciliation found unresolved durable work: {unresolved}, "
            f"migration_count={migration_count}"
        )
    return {
        "candidate_sha": candidate_sha,
        "status": "pass",
        "binding_count": len(bindings),
        "migration_count": migration_count,
        **unresolved,
    }


def _fourteen_walkthroughs(root: Path, candidate_sha: str, *, run_private: bool) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    records.append(
        {
            "id": "W-G01-001",
            "status": "pass",
            "evidence": "secure-bootstrap manifest and publication scan",
        }
    )
    if run_private:
        runtime = run_runtime_smokes(root, candidate_sha)
        network = run_network_matrix(root, candidate_sha)
        coexistence = audit_runtime_coexistence(root, candidate_sha)
        records.append({"id": "W-G01-002", "status": "pass", "evidence": coexistence})
        records.append(
            {
                "id": "W-G01-003",
                "status": "pass",
                "evidence": {"runtime": runtime, "network": network},
            }
        )
    else:
        records.extend(
            [
                {"id": "W-G01-002", "status": "pending", "evidence": "private runtime required"},
                {"id": "W-G01-003", "status": "pending", "evidence": "private runtime required"},
            ]
        )
    records.extend(
        [
            {
                "id": "W-G01-004",
                "status": "pass",
                "evidence": _test_group(root, "tests/api/test_control_api.py"),
            },
            {
                "id": "W-G01-005",
                "status": "pass",
                "evidence": _test_group(root, "tests/persistence", "tests/runtime"),
            },
            {
                "id": "W-G01-006",
                "status": "pass",
                "evidence": _test_group(root, "tests/runtime/test_streams.py"),
            },
            {
                "id": "W-G01-007",
                "status": "pass",
                "evidence": _test_group(root, "tests/runtime/test_checkpoint.py"),
            },
        ]
    )
    if run_private:
        api = run_control_api_smoke(candidate_sha)
        trace = run_trace_service_smoke(candidate_sha)
        model = run_model_gateway_smoke(candidate_sha)
        records.extend(
            [
                {"id": "W-G01-008", "status": "pass", "evidence": api},
                {"id": "W-G01-009", "status": "pass", "evidence": api},
                {"id": "W-G01-010", "status": "pass", "evidence": trace},
                {"id": "W-G01-012", "status": "pass", "evidence": model},
            ]
        )
    else:
        records.extend(
            {"id": identifier, "status": "pending", "evidence": "private service evidence required"}
            for identifier in ("W-G01-008", "W-G01-009", "W-G01-010", "W-G01-012")
        )
    records.extend(
        [
            {
                "id": "W-G01-011",
                "status": "pass",
                "evidence": _test_group(root, "tests/observability", "tests/security"),
            },
            {"id": "W-G01-013", "status": "pass", "evidence": _test_group(root, "tests/models")},
            {
                "id": "W-G01-014",
                "status": "pass",
                "evidence": _test_group(root, "tests/audit", "tests/governance"),
            },
        ]
    )
    return {
        "count": len(records),
        "records": records,
        "pass_count": sum(r["status"] == "pass" for r in records),
    }


def evaluate_g01(root: Path, candidate_sha: str, *, profile: str) -> dict[str, Any]:
    _require_candidate(root, candidate_sha)
    if profile not in {"private-server", "local"}:
        raise GovernanceError("G01 profile must be private-server or local")
    private = profile == "private-server"
    audit = audit_repository(root)
    scan_publication_boundary(root)
    schema = inspect_runtime_schema(candidate_sha) if private else {"status": "deferred_private"}
    platform = (
        _platform_stability(root, candidate_sha) if private else {"status": "deferred_private"}
    )
    services = {
        "control_api": inspect_control_api(candidate_sha)
        if private
        else {"status": "deferred_private"},
        "keycloak": inspect_keycloak_realm(candidate_sha)
        if private
        else {"status": "deferred_private"},
        "trace": inspect_trace_service(candidate_sha)
        if private
        else {"status": "deferred_private"},
        "model": inspect_model_gateway(candidate_sha)
        if private
        else {"status": "deferred_private"},
    }
    reconciliation = (
        inspect_g01_reconciliation(candidate_sha) if private else {"status": "deferred_private"}
    )
    recovery = (
        run_postgres_restore_rehearsal(candidate_sha) if private else {"status": "deferred_private"}
    )
    walkthroughs = _fourteen_walkthroughs(root, candidate_sha, run_private=private)
    upstream_debt = _eval_manifest_debt(root, candidate_sha, include_final=False)
    passed = walkthroughs["pass_count"] == 14 and private and not upstream_debt
    return {
        "schema_version": "1.0.0",
        "eval_id": "EVAL-G01-009",
        "candidate_sha": candidate_sha,
        "profile": profile,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "status": "pass" if passed else "pending",
        "audit": {
            "status": "pass",
            "summary_sha256": hashlib.sha256(
                json.dumps(audit, sort_keys=True).encode()
            ).hexdigest(),
        },
        "runtime_schema": schema,
        "platform": platform,
        "services": services,
        "reconciliation": reconciliation,
        "recovery": recovery,
        "walkthroughs": walkthroughs,
        "upstream_eval_debt": upstream_debt,
        "readiness": "candidate evidence complete" if passed else "blocking evidence remains",
    }


def evaluate_g01_close(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Positive/negative close-readiness check; this function never closes G01."""
    _require_candidate(root, candidate_sha)
    manifests = []
    for number in range(1, 10):
        path = root / "docs" / "evals" / f"EVAL-G01-{number:03d}" / "manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        manifests.append(document)
    incomplete = _eval_manifest_debt(root, candidate_sha, include_final=True)
    iterations = [
        load_data(root / "governance" / "iterations" / f"I-{number:04d}.yaml")
        for number in range(7, 16)
    ]
    incomplete_iterations = [item["id"] for item in iterations if item.get("status") != "completed"]
    missing_commits = [
        item["id"]
        for item in iterations
        if not isinstance(item.get("commit"), str) or len(item["commit"]) != FULL_SHA_LEN
    ]
    gate = load_data(root / "governance" / "gates" / "G01.yaml")
    waivers = gate.get("waivers", [])
    if incomplete or incomplete_iterations or missing_commits or waivers:
        raise GovernanceError(
            "G01 close readiness rejected incomplete evidence: "
            f"evals={incomplete}, iterations={incomplete_iterations}, "
            f"missing_commits={missing_commits}, waivers={len(waivers)}"
        )
    return {
        "eval_id": "EVAL-G01-009-CLOSE",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "gate_closed": False,
        "manifest_count": len(manifests),
        "iteration_count": len(iterations),
    }
