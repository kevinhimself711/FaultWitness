from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    default_sops_executable,
    load_secret_bundle,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.experiment import semantic_cache_key
from faultwitness_dev.g02_isolation import (
    CANARY_SURFACES,
    PRINCIPALS,
    TRACE_STAGES,
    access_cell_contract,
    load_isolation_config,
    validate_all_surface_canary,
    validate_live_access_matrix,
    validate_stage_matrix,
)
from faultwitness_dev.infra import run_remote_script
from faultwitness_dev.schemas import load_data


class ContextLike(Protocol):
    producer_sha: str
    environment_fingerprint: str


@dataclass(frozen=True)
class ProbeContext:
    """Minimal runtime provenance used by the retained G02 collector contracts."""

    producer_sha: str
    environment_fingerprint: str

class JournalLike(Protocol):
    root: Path

    def read(self, trial_id: str) -> dict[str, Any] | None: ...

    def begin(
        self,
        trial_id: str,
        *,
        producer_sha: str,
        cache_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def finish(
        self, trial_id: str, status: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]: ...


class ProbeBackend(Protocol):
    def provision(self, context: ContextLike) -> Mapping[str, Any]: ...

    def access_cell(
        self, context: ContextLike, contract: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def trace_matrix(self, context: ContextLike) -> Mapping[str, Any]: ...

    def canary_matrix(self, context: ContextLike) -> Mapping[str, Any]: ...


class ProbeInfrastructureError(RuntimeError):
    """A transport or external-service failure that may resume the same unit."""


class ProbeBlockedError(RuntimeError):
    """A deterministic runner or provisioning failure needing a semantic change."""


LANGSMITH_CREDENTIAL_INFO_URL = (
    "https://api.smith.langchain.com/api/v1/orgs/current/info"
)


def langsmith_access_probe(
    credential: str, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Prove the read-only credential seam without retaining response content."""
    if not credential:
        raise ProbeBlockedError("langsmith_credential_missing")
    owned = client is None
    active_client = client or httpx.Client(timeout=None)
    try:
        response = active_client.get(
            LANGSMITH_CREDENTIAL_INFO_URL,
            headers={"x-api-key": credential},
        )
    except httpx.TransportError as error:
        raise ProbeInfrastructureError("langsmith_transport") from error
    finally:
        if owned:
            active_client.close()
    status = int(response.status_code)
    if status == 200:
        return {
            "credential_allow": True,
            "response_class": "success",
            "http_status": status,
        }
    if status in {408, 425, 429} or status >= 500:
        raise ProbeInfrastructureError("langsmith_service_unavailable")
    if status in {401, 403}:
        return {
            "credential_allow": False,
            "response_class": "credential_denied",
            "http_status": status,
        }
    raise ProbeBlockedError(f"langsmith_request_rejected_{status}")


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _artifact_ref(context: ContextLike, phase: str, unit: str, value: Any) -> str:
    return (
        f"private://faultwitness/isolation/{context.producer_sha}/{phase}/{unit}/"
        f"{_digest(value)}"
    )


def _bound_payload(
    context: ContextLike, unit_id: str, result: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "producer_sha": context.producer_sha,
        "environment_fingerprint": context.environment_fingerprint,
        "unit_id": unit_id,
        "result": dict(result),
    }


def _unit_cache_key(context: ContextLike, unit_id: str) -> str:
    return semantic_cache_key(
        {"environment": context.environment_fingerprint},
        ("environment",),
        input_digest=_digest(unit_id),
    )


def _begin(
    journal: JournalLike,
    context: ContextLike,
    trial_id: str,
    unit_id: str,
) -> dict[str, Any]:
    return journal.begin(
        trial_id,
        producer_sha=context.producer_sha,
        cache_key=_unit_cache_key(context, unit_id),
        payload={"unit_id": unit_id},
    )


def _finish(
    journal: JournalLike,
    context: ContextLike,
    trial_id: str,
    unit_id: str,
    status: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    running = journal.read(trial_id)
    if running is None or running.get("status") != "running":
        _begin(journal, context, trial_id, unit_id)
    return journal.finish(trial_id, status, payload)


def _reusable(
    record: Mapping[str, Any] | None, context: ContextLike, unit_id: str
) -> Mapping[str, Any] | None:
    if (
        not record
        or record.get("status") != "pass"
        or record.get("cache_key") != _unit_cache_key(context, unit_id)
    ):
        return None
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        return None
    if (
        payload.get("environment_fingerprint") != context.environment_fingerprint
        or payload.get("unit_id") != unit_id
        or not isinstance(payload.get("result"), Mapping)
    ):
        return None
    return payload["result"]


def _terminal_result(
    record: Mapping[str, Any] | None,
    context: ContextLike,
    unit_id: str,
) -> tuple[str, Mapping[str, Any]] | None:
    """Return an exact-bound non-resumable result without executing it again."""
    if (
        not record
        or record.get("status") not in {"metric_fail", "blocked"}
        or record.get("cache_key") != _unit_cache_key(context, unit_id)
    ):
        return None
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        return None
    result = payload.get("result")
    if (
        payload.get("environment_fingerprint") != context.environment_fingerprint
        or payload.get("unit_id") != unit_id
        or not isinstance(result, Mapping)
    ):
        return None
    return str(record["status"]), result


def build_provisioning_plan(root: Path, context: ContextLike) -> dict[str, Any]:
    isolation = load_isolation_config(root)
    probes = load_data(root / "config/g02/gate-probes.yaml")
    plan = {
        "schema_version": "1.0.0",
        "producer_sha": context.producer_sha,
        "environment_fingerprint": context.environment_fingerprint,
        "principals": list(isolation["principals"]),
        "prefixes": list(isolation["prefixes"]),
        "namespaces": list(isolation["trust_zones"]),
        "credential_refs": [
            f"secret://{isolation['principals'][name]['zone']}/g02-{name}-probe"
            for name in PRINCIPALS[:3]
        ]
        + ["secret://fw-eval/g02-ordinary-developer-probe"],
        "schema_targets": probes["schema_targets"],
        "observability_targets": probes["observability_targets"],
        "probe_pods": probes["probe_pods"],
        "images": probes["images"],
        "secret_values": [],
    }
    validate_provisioning_plan(plan)
    return plan


def validate_provisioning_plan(document: Mapping[str, Any]) -> None:
    if list(document.get("principals", ())) != list(PRINCIPALS):
        raise GovernanceError("G02 provisioning plan principal registry drifted")
    if list(document.get("prefixes", ())) != [
        "g02/scenarios/",
        "g02/trials/",
        "g02/ground-truth/",
        "g02/locked-tests/",
        "g02/evidence/",
    ]:
        raise GovernanceError("G02 provisioning plan prefix registry drifted")
    if list(document.get("namespaces", ())) != ["fw-sut", "fw-baseline", "fw-eval"]:
        raise GovernanceError("G02 provisioning plan namespace registry drifted")
    refs = document.get("credential_refs")
    expected_refs = [
        "secret://fw-sut/g02-scenario-controller-probe",
        "secret://fw-baseline/g02-baseline-agent-probe",
        "secret://fw-eval/g02-sealed-evaluator-probe",
        "secret://fw-eval/g02-ordinary-developer-probe",
    ]
    if refs != expected_refs:
        raise GovernanceError("G02 provisioning credential references drifted")
    if document.get("secret_values") != []:
        raise GovernanceError("G02 provisioning plan must not contain credential values")
    images = document.get("images")
    if not isinstance(images, Mapping) or set(images) != {"busybox", "minio_mc"}:
        raise GovernanceError("G02 probe image registry drifted")
    if any("@sha256:" not in str(image) for image in images.values()):
        raise GovernanceError("G02 probe image is not digest pinned")
    if set(document.get("schema_targets", {})) != {
        "incident",
        "runtime",
        "checkpoint",
        "action",
        "delivery",
        "trace_buffer",
    }:
        raise GovernanceError("G02 provisioning schema target registry drifted")
    if set(document.get("observability_targets", {})) != {
        "prometheus",
        "loki",
        "tempo",
        "langsmith",
    }:
        raise GovernanceError("G02 provisioning observability target registry drifted")
    if set(document.get("probe_pods", {})) != {
        "canonical-owner",
        "baseline-agent",
        "ordinary-developer",
        "cross-boundary",
    }:
        raise GovernanceError("G02 provisioning probe registry drifted")


def _ensure_provisioned(
    context: ContextLike, journal: JournalLike, backend: ProbeBackend
) -> Mapping[str, Any]:
    unit_id = "isolation-provisioning"
    existing = journal.read("g02-provisioning")
    reusable = _reusable(existing, context, unit_id)
    if reusable is not None:
        return reusable
    terminal = _terminal_result(existing, context, unit_id)
    if terminal is not None:
        raise ProbeBlockedError(str(terminal[1].get("reason_code", "provisioning_blocked")))
    _begin(journal, context, "g02-provisioning", unit_id)
    try:
        result = dict(backend.provision(context))
    except ProbeInfrastructureError as error:
        payload = _bound_payload(context, unit_id, {"reason_code": str(error)})
        _finish(
            journal, context, "g02-provisioning", unit_id, "infra_failed", payload
        )
        raise
    except ProbeBlockedError as error:
        payload = _bound_payload(context, unit_id, {"reason_code": str(error)})
        _finish(journal, context, "g02-provisioning", unit_id, "blocked", payload)
        raise
    if (
        result.get("status") != "pass"
        or result.get("producer_sha") != context.producer_sha
        or result.get("environment_fingerprint") != context.environment_fingerprint
        or not result.get("artifact_ref")
    ):
        _finish(
            journal,
            context,
            "g02-provisioning",
            unit_id,
            "blocked",
            _bound_payload(context, unit_id, result),
        )
        raise ProbeBlockedError("provisioning_result_invalid")
    _finish(
        journal,
        context,
        "g02-provisioning",
        unit_id,
        "pass",
        _bound_payload(context, unit_id, result),
    )
    return result


def run_access_matrix(
    context: ContextLike, journal: JournalLike, backend: ProbeBackend
) -> dict[str, Any]:
    try:
        _ensure_provisioned(context, journal, backend)
    except ProbeInfrastructureError:
        return _matrix_document(context, "infra_failed", "cells", [])
    except ProbeBlockedError:
        return _matrix_document(context, "blocked", "cells", [])
    cells: list[dict[str, Any]] = []
    for index, contract in enumerate(access_cell_contract(), 1):
        unit_id = str(contract["cell_id"])
        trial_id = f"access-{index:02d}"
        existing = journal.read(trial_id)
        result = _reusable(existing, context, unit_id)
        terminal = _terminal_result(existing, context, unit_id)
        if terminal is not None:
            terminal_status, terminal_result = terminal
            if terminal_status == "metric_fail":
                cells.append({**contract, **dict(terminal_result)})
            return _matrix_document(context, terminal_status, "cells", cells)
        if result is None:
            _begin(journal, context, trial_id, unit_id)
            try:
                result = dict(backend.access_cell(context, contract))
            except ProbeInfrastructureError as error:
                _finish(
                    journal,
                    context,
                    trial_id,
                    unit_id,
                    "infra_failed",
                    _bound_payload(context, unit_id, {"reason_code": str(error)}),
                )
                return _matrix_document(context, "infra_failed", "cells", cells)
            except ProbeBlockedError as error:
                _finish(
                    journal,
                    context,
                    trial_id,
                    unit_id,
                    "blocked",
                    _bound_payload(context, unit_id, {"reason_code": str(error)}),
                )
                return _matrix_document(context, "blocked", "cells", cells)
            if (
                result.get("cell_id") != unit_id
                or not isinstance(result.get("actual_allow"), bool)
                or not result.get("artifact_ref")
            ):
                _finish(
                    journal,
                    context,
                    trial_id,
                    unit_id,
                    "blocked",
                    _bound_payload(context, unit_id, result),
                )
                return _matrix_document(context, "blocked", "cells", cells)
            status = (
                "pass"
                if result["actual_allow"] is contract["expected_allow"]
                else "metric_fail"
            )
            _finish(
                journal,
                context,
                trial_id,
                unit_id,
                status,
                _bound_payload(context, unit_id, result),
            )
            if status != "pass":
                cells.append({**contract, **result})
                return _matrix_document(context, status, "cells", cells)
        cells.append({**contract, **dict(result)})
    document = _matrix_document(context, "pass", "cells", cells)
    validate_live_access_matrix(document, context.producer_sha, context.environment_fingerprint)
    return document


def run_trace_matrix(
    context: ContextLike, journal: JournalLike, backend: ProbeBackend
) -> dict[str, Any]:
    try:
        _ensure_provisioned(context, journal, backend)
    except ProbeInfrastructureError:
        return _matrix_document(context, "infra_failed", "stages", [])
    except ProbeBlockedError:
        return _matrix_document(context, "blocked", "stages", [])
    reusable_stages: list[dict[str, Any]] = []
    for index, stage in enumerate(TRACE_STAGES, 1):
        record = journal.read(f"trace-{index:02d}")
        terminal = _terminal_result(record, context, stage)
        if terminal is not None:
            return _matrix_document(context, terminal[0], "stages", reusable_stages)
        result = _reusable(record, context, stage)
        if result is None:
            reusable_stages = []
            break
        reusable_stages.append(dict(result))
    if reusable_stages:
        document = _matrix_document(context, "pass", "stages", reusable_stages)
        validate_stage_matrix(document, context.producer_sha, context.environment_fingerprint)
        return document
    collection_unit = "six-stage-collection"
    terminal_collection = _terminal_result(
        journal.read("trace-collection"), context, collection_unit
    )
    if terminal_collection is not None:
        return _matrix_document(context, terminal_collection[0], "stages", [])
    _begin(journal, context, "trace-collection", collection_unit)
    try:
        result = dict(backend.trace_matrix(context))
    except ProbeInfrastructureError as error:
        _finish(
            journal,
            context,
            "trace-collection",
            collection_unit,
            "infra_failed",
            _bound_payload(context, collection_unit, {"reason_code": str(error)}),
        )
        return _matrix_document(context, "infra_failed", "stages", [])
    except ProbeBlockedError as error:
        _finish(
            journal,
            context,
            "trace-collection",
            collection_unit,
            "blocked",
            _bound_payload(context, collection_unit, {"reason_code": str(error)}),
        )
        return _matrix_document(context, "blocked", "stages", [])
    stages = result.get("stages")
    if not isinstance(stages, list):
        _finish(
            journal,
            context,
            "trace-collection",
            collection_unit,
            "blocked",
            _bound_payload(context, collection_unit, result),
        )
        return _matrix_document(context, "blocked", "stages", [])
    _finish(
        journal,
        context,
        "trace-collection",
        collection_unit,
        "pass",
        _bound_payload(context, collection_unit, result),
    )
    by_stage = {item.get("stage"): item for item in stages if isinstance(item, Mapping)}
    status = (
        "pass"
        if len(stages) == len(TRACE_STAGES) and list(by_stage) == list(TRACE_STAGES)
        else "metric_fail"
    )
    ordered: list[dict[str, Any]] = []
    for index, stage in enumerate(TRACE_STAGES, 1):
        item = dict(by_stage.get(stage, {"stage": stage, "observed": False}))
        unit_status = (
            "pass"
            if item.get("observed") is True
            and item.get("trace_id")
            and item.get("artifact_ref")
            else "metric_fail"
        )
        _finish(
            journal,
            context,
            f"trace-{index:02d}",
            stage,
            unit_status,
            _bound_payload(context, stage, item),
        )
        ordered.append(item)
        if unit_status != "pass":
            status = "metric_fail"
    document = _matrix_document(context, status, "stages", ordered)
    if status == "pass":
        validate_stage_matrix(document, context.producer_sha, context.environment_fingerprint)
    return document


def run_canary_matrix(
    context: ContextLike, journal: JournalLike, backend: ProbeBackend
) -> dict[str, Any]:
    try:
        _ensure_provisioned(context, journal, backend)
    except ProbeInfrastructureError:
        return _matrix_document(context, "infra_failed", "surfaces", [])
    except ProbeBlockedError:
        return _matrix_document(context, "blocked", "surfaces", [])
    reusable_surfaces: list[dict[str, Any]] = []
    for index, surface in enumerate(CANARY_SURFACES, 1):
        record = journal.read(f"canary-{index:02d}")
        terminal = _terminal_result(record, context, surface)
        if terminal is not None:
            return _matrix_document(context, terminal[0], "surfaces", reusable_surfaces)
        result = _reusable(record, context, surface)
        if result is None:
            reusable_surfaces = []
            break
        reusable_surfaces.append(dict(result))
    if reusable_surfaces:
        document = _matrix_document(context, "pass", "surfaces", reusable_surfaces)
        validate_all_surface_canary(
            document, context.producer_sha, context.environment_fingerprint
        )
        return document
    collection_unit = "all-surface-collection"
    terminal_collection = _terminal_result(
        journal.read("canary-collection"), context, collection_unit
    )
    if terminal_collection is not None:
        return _matrix_document(context, terminal_collection[0], "surfaces", [])
    _begin(journal, context, "canary-collection", collection_unit)
    try:
        result = dict(backend.canary_matrix(context))
    except ProbeInfrastructureError as error:
        _finish(
            journal,
            context,
            "canary-collection",
            collection_unit,
            "infra_failed",
            _bound_payload(context, collection_unit, {"reason_code": str(error)}),
        )
        return _matrix_document(context, "infra_failed", "surfaces", [])
    except ProbeBlockedError as error:
        _finish(
            journal,
            context,
            "canary-collection",
            collection_unit,
            "blocked",
            _bound_payload(context, collection_unit, {"reason_code": str(error)}),
        )
        return _matrix_document(context, "blocked", "surfaces", [])
    surfaces = result.get("surfaces")
    if not isinstance(surfaces, list):
        _finish(
            journal,
            context,
            "canary-collection",
            collection_unit,
            "blocked",
            _bound_payload(context, collection_unit, result),
        )
        return _matrix_document(context, "blocked", "surfaces", [])
    _finish(
        journal,
        context,
        "canary-collection",
        collection_unit,
        "pass",
        _bound_payload(context, collection_unit, result),
    )
    by_surface = {
        item.get("surface"): item for item in surfaces if isinstance(item, Mapping)
    }
    status = (
        "pass"
        if len(surfaces) == len(CANARY_SURFACES)
        and list(by_surface) == list(CANARY_SURFACES)
        else "metric_fail"
    )
    ordered: list[dict[str, Any]] = []
    for index, surface in enumerate(CANARY_SURFACES, 1):
        item = dict(by_surface.get(surface, {"surface": surface, "hit_count": -1}))
        unit_status = (
            "pass"
            if item.get("hit_count") == 0
            and item.get("artifact_ref")
            and item.get("canary_digest")
            else "metric_fail"
        )
        _finish(
            journal,
            context,
            f"canary-{index:02d}",
            surface,
            unit_status,
            _bound_payload(context, surface, item),
        )
        ordered.append(item)
        if unit_status != "pass":
            status = "metric_fail"
    document = _matrix_document(context, status, "surfaces", ordered)
    if status == "pass":
        validate_all_surface_canary(
            document, context.producer_sha, context.environment_fingerprint
        )
    return document


def _matrix_document(
    context: ContextLike, status: str, field_name: str, values: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "producer_sha": context.producer_sha,
        "environment_fingerprint": context.environment_fingerprint,
        field_name: [dict(value) for value in values],
        "status": status,
    }


def canary_values(context: ContextLike) -> tuple[str, str]:
    seed = hashlib.sha256(
        f"{context.environment_fingerprint}|g02-canary-v1".encode()
    ).hexdigest()[:24]
    return f"FW_SECRET_CANARY_{seed}", f"fw_pii_canary_{seed}@example.invalid"


@dataclass
class MemoryProbeBackend:
    root: Path
    access_overrides: dict[str, bool] = field(default_factory=dict)
    missing_stage: str | None = None
    canary_hit_surface: str | None = None
    calls: dict[str, int] = field(default_factory=dict)

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def provision(self, context: ContextLike) -> Mapping[str, Any]:
        self._called("provision")
        plan = build_provisioning_plan(self.root, context)
        return {
            "status": "pass",
            "producer_sha": context.producer_sha,
            "environment_fingerprint": context.environment_fingerprint,
            "plan_digest": _digest(plan),
            "artifact_ref": _artifact_ref(context, "provisioning", "plan", plan),
        }

    def access_cell(
        self, context: ContextLike, contract: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self._called("access")
        cell_id = str(contract["cell_id"])
        actual = self.access_overrides.get(cell_id, bool(contract["expected_allow"]))
        return {
            "cell_id": cell_id,
            "actual_allow": actual,
            "artifact_ref": _artifact_ref(context, "access", cell_id, actual),
        }

    def trace_matrix(self, context: ContextLike) -> Mapping[str, Any]:
        self._called("trace")
        trace_id = hashlib.sha256(context.environment_fingerprint.encode()).hexdigest()[:32]
        stages = [
            {
                "stage": stage,
                "trace_id": trace_id,
                "observed": True,
                "artifact_ref": _artifact_ref(context, "trace", stage, trace_id),
            }
            for stage in TRACE_STAGES
            if stage != self.missing_stage
        ]
        return {"status": "pass", "stages": stages}

    def canary_matrix(self, context: ContextLike) -> Mapping[str, Any]:
        self._called("canary")
        digest = _digest(canary_values(context))
        return {
            "status": "pass",
            "surfaces": [
                {
                    "surface": surface,
                    "hit_count": 1 if surface == self.canary_hit_surface else 0,
                    "artifact_ref": _artifact_ref(context, "canary", surface, digest),
                    "canary_digest": digest,
                }
                for surface in CANARY_SURFACES
            ],
        }


class RemoteProbeBackend:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.program = root / "deploy/g02/gate_probe.py"
        if not self.program.is_file():
            raise GovernanceError("G02 remote probe program is missing")

    def _request(
        self, context: ContextLike, extra: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        plan_digest = _digest(build_provisioning_plan(self.root, context))
        return {
            "producer_sha": context.producer_sha,
            "environment_fingerprint": context.environment_fingerprint,
            "plan_digest": plan_digest,
            "probe_config": load_data(self.root / "config/g02/gate-probes.yaml"),
            "isolation_manifest": (
                self.root / "deploy/g02/isolation-policy.yaml"
            ).read_text(encoding="utf-8"),
            **dict(extra or {}),
        }

    def _producer_timestamp(self, context: ContextLike) -> str:
        timestamp = subprocess.run(
            ["git", "show", "-s", "--format=%cI", context.producer_sha],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if timestamp.returncode or not timestamp.stdout.strip():
            raise ProbeBlockedError("producer_timestamp_unavailable")
        try:
            parsed = datetime.fromisoformat(timestamp.stdout.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ProbeBlockedError("producer_timestamp_invalid") from error
        if parsed.tzinfo is None:
            raise ProbeBlockedError("producer_timestamp_invalid")
        return parsed.astimezone(UTC).isoformat()

    def _invoke(
        self, action: str, context: ContextLike, extra: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        program = base64.b64encode(self.program.read_bytes()).decode()
        request = base64.b64encode(
            json.dumps(self._request(context, extra), sort_keys=True).encode()
        ).decode()
        shell = f"""set -eu
work=$(mktemp -d /tmp/faultwitness-g02-probe.XXXXXX)
cleanup() {{ rm -rf "$work"; }}
trap cleanup EXIT HUP INT TERM
printf %s {program} | base64 -d >"$work/gate_probe.py"
printf %s {request} | base64 -d >"$work/request.json"
python3 "$work/gate_probe.py" {action} "$work/request.json"
"""
        try:
            output = run_remote_script(shell, privileged=True)
        except GovernanceError as error:
            raise ProbeInfrastructureError("remote_probe_transport") from error
        secret_canary, pii_canary = canary_values(context)
        if secret_canary in output or pii_canary in output:
            raise ProbeBlockedError("probe_output_contains_raw_canary")
        try:
            document = json.loads(output)
        except json.JSONDecodeError as error:
            raise ProbeBlockedError("probe_output_invalid_json") from error
        if not isinstance(document, dict):
            raise ProbeBlockedError("probe_output_invalid_shape")
        if document.get("status") == "infra_failed":
            raise ProbeInfrastructureError(str(document.get("reason_code", "remote_infra")))
        if document.get("status") == "blocked":
            raise ProbeBlockedError(str(document.get("reason_code", "remote_blocked")))
        return document

    def provision(self, context: ContextLike) -> Mapping[str, Any]:
        plan = build_provisioning_plan(self.root, context)
        document = self._invoke("provision", context, {"plan_digest": _digest(plan)})
        if document.get("plan_digest") != _digest(plan):
            raise ProbeBlockedError("remote_provisioning_plan_drift")
        return document

    def access_cell(
        self, context: ContextLike, contract: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if contract.get("target") == "obs:langsmith":
            return self._langsmith_access(context, contract)
        return self._invoke("access", context, {"cell": dict(contract)})

    def _langsmith_access(
        self, context: ContextLike, contract: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        probe = str(contract["probe"])
        if probe == "canonical-owner":
            network_allow = True
        else:
            network = self._invoke("access", context, {"cell": dict(contract)})
            network_allow = network.get("actual_allow") is True
        credential = {
            "credential_allow": False,
            "response_class": "not_invoked",
            "http_status": None,
        }
        if probe in {"canonical-owner", "baseline-agent"}:
            bundle = load_secret_bundle(
                BootstrapPaths.defaults(), default_sops_executable()
            )
            credential = langsmith_access_probe(bundle.langsmith_api_key)
        credential_allow = credential["credential_allow"]
        actual = network_allow and (
            credential_allow if probe in {"canonical-owner", "baseline-agent"} else True
        )
        summary = {
            "cell_id": contract["cell_id"],
            "probe": probe,
            "network_allow": network_allow,
            "credential_allow": credential_allow,
            "credential_response_class": credential["response_class"],
            "credential_http_status": credential["http_status"],
            "actual_allow": actual,
        }
        return {
            "cell_id": contract["cell_id"],
            "actual_allow": actual,
            "credential_response_class": credential["response_class"],
            "credential_http_status": credential["http_status"],
            "artifact_ref": _artifact_ref(context, "access", str(contract["cell_id"]), summary),
        }

    def trace_matrix(self, context: ContextLike) -> Mapping[str, Any]:
        document = self._invoke(
            "trace", context, {"producer_timestamp": self._producer_timestamp(context)}
        )
        from faultwitness_dev.observability_deploy import relay_langsmith

        relay = relay_langsmith()
        if relay.get("pending_traces") != 0 or relay.get("pending_langsmith") != 0:
            raise ProbeBlockedError("trace_relay_backlog")
        stages = document.get("stages")
        if isinstance(stages, list):
            for item in stages:
                if item.get("stage") == "export" and relay.get("langsmith_trace_ids"):
                    item["artifact_ref"] = (
                        "private://faultwitness/g02/langsmith/"
                        + str(relay["langsmith_trace_ids"][0])
                    )
        return document

    def canary_matrix(self, context: ContextLike) -> Mapping[str, Any]:
        document = self._invoke(
            "canary", context, {"producer_timestamp": self._producer_timestamp(context)}
        )
        surfaces = document.get("surfaces")
        if not isinstance(surfaces, list):
            return document
        replacements = self._local_canary_surfaces(context)
        by_surface = {
            item.get("surface"): item for item in surfaces if isinstance(item, dict)
        }
        by_surface.update({item["surface"]: item for item in replacements})
        document["surfaces"] = [
            by_surface.get(surface, {"surface": surface}) for surface in CANARY_SURFACES
        ]
        return document

    def _local_canary_surfaces(self, context: ContextLike) -> list[dict[str, Any]]:
        tokens = canary_values(context)
        digest = _digest(tokens)
        checks: dict[str, bytes] = {}
        worktree_payload = b""
        for token in tokens:
            tracked = subprocess.run(
                ["git", "grep", "-I", "-n", "-F", token, "--", "."],
                cwd=self.root,
                capture_output=True,
            )
            if tracked.returncode not in {0, 1}:
                raise ProbeBlockedError("git_worktree_scan_failed")
            worktree_payload += tracked.stdout + tracked.stderr
        checks["git-worktree"] = worktree_payload
        history = subprocess.run(
            ["git", "log", "-p", "--all", "--format="],
            cwd=self.root,
            check=True,
            capture_output=True,
        ).stdout
        checks["git-history"] = history
        checks["eval-artifact"] = b"".join(
            path.read_bytes()
            for path in sorted((self.root / "docs/evals").rglob("*"))
            if path.is_file()
        )
        preregistry = self.root / "data/g02/core-case-preregistration.yaml"
        checks["g02-preregistry-publication"] = (
            preregistry.read_bytes() if preregistry.is_file() else b""
        )
        results = []
        for surface, payload in checks.items():
            hits = sum(payload.count(token.encode()) for token in tokens)
            results.append(
                {
                    "surface": surface,
                    "hit_count": hits,
                    "artifact_ref": _artifact_ref(
                        context, "canary", surface, _digest(payload.hex())
                    ),
                    "canary_digest": digest,
                }
            )
        return results
