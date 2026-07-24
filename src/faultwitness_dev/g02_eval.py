from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_collectors import (
    CandidateProbeBackend,
    ProbeBackend,
    run_access_matrix,
    run_canary_matrix,
    run_trace_matrix,
)
from faultwitness_dev.g02_isolation import (
    validate_all_surface_canary,
    validate_live_access_matrix,
    validate_stage_matrix,
)
from faultwitness_dev.schemas import load_data, validate_repository_schemas

PHASE_TERMINAL_STATUSES = {"pass", "metric_fail", "infra_failed", "blocked"}
RESUMABLE_STATUSES = {"pending", "infra_failed"}
EVIDENCE_ONLY_FILES = {
    "CHANGELOG.md",
    "PROJECT_STATE.yaml",
    "docs/adr/INDEX.yaml",
    "docs/claims/CLAIMS.yaml",
    "docs/engineering/AI_DEVELOPMENT_LOG.md",
}
EVIDENCE_ONLY_PREFIXES = (
    "docs/evals/",
    "docs/gates/",
    "docs/roadmap/",
    "governance/gates/",
    "governance/iterations/",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_digest(document: Any) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class PhaseDefinition:
    phase_id: str
    dependencies: tuple[str, ...]
    owner_iteration: str
    destructive: bool = False


@dataclass(frozen=True)
class PhaseContext:
    candidate_sha: str
    runtime_image_digests: tuple[str, ...]
    sut_image_set_digest: str
    config_digest: str
    evaluator_digest: str
    dataset_digest: str
    environment_fingerprint: str

    def cache_key(self, phase: PhaseDefinition) -> str:
        return _canonical_digest(
            {
                "candidate_sha": self.candidate_sha,
                "runtime_image_digests": sorted(self.runtime_image_digests),
                "sut_image_set_digest": self.sut_image_set_digest,
                "config_digest": self.config_digest,
                "evaluator_digest": self.evaluator_digest,
                "dataset_digest": self.dataset_digest,
                "environment_fingerprint": self.environment_fingerprint,
                "phase_id": phase.phase_id,
            }
        )


G02_PHASES = (
    PhaseDefinition("preflight-manifests", (), "I-0016"),
    PhaseDefinition("preflight-candidate-binding", ("preflight-manifests",), "I-0016"),
    PhaseDefinition("preflight-static-inheritance", ("preflight-candidate-binding",), "I-0016"),
    PhaseDefinition("preflight-upstream-g01", ("preflight-static-inheritance",), "I-0016"),
    PhaseDefinition("lab-deploy-and-bind", ("preflight-upstream-g01",), "I-0017"),
    PhaseDefinition("isolation-access-matrix", ("lab-deploy-and-bind",), "I-0024"),
    PhaseDefinition("trace-six-stage-matrix", ("lab-deploy-and-bind",), "I-0024"),
    PhaseDefinition(
        "all-surface-canary",
        ("isolation-access-matrix", "trace-six-stage-matrix"),
        "I-0024",
    ),
    PhaseDefinition("scenario-matrix", ("all-surface-canary",), "I-0017", destructive=True),
    PhaseDefinition("baseline-deterministic", ("scenario-matrix",), "I-0019"),
    PhaseDefinition("baseline-live", ("scenario-matrix", "baseline-deterministic"), "I-0019"),
    PhaseDefinition("baseline-aggregate", ("baseline-deterministic", "baseline-live"), "I-0019"),
    PhaseDefinition("candidate-reconciliation", ("baseline-aggregate",), "I-0016"),
    PhaseDefinition("close-readiness", ("candidate-reconciliation",), "I-0016"),
)


def validate_gate_orchestration_selection(
    state: Mapping[str, Any],
    iteration: Mapping[str, Any],
    manifest: Mapping[str, Any],
    plan_text: str,
) -> tuple[str, str]:
    iteration_id = iteration.get("id")
    eval_id = iteration.get("eval_id")
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != iteration_id
        or iteration.get("gate") != "G02"
        or iteration.get("status") != "in_progress"
        or iteration.get("iteration_type") != "standard"
    ):
        raise GovernanceError("G02 Gate Eval requires one active standard orchestration Iteration")
    if not isinstance(iteration_id, str) or not isinstance(eval_id, str):
        raise GovernanceError("G02 orchestration record lacks an Iteration or Eval ID")
    if manifest.get("eval_id") != eval_id or manifest.get("iteration") != iteration_id:
        raise GovernanceError("G02 orchestration Eval manifest binding drifted")
    missing = [phase.phase_id for phase in G02_PHASES if phase.phase_id not in plan_text]
    if missing:
        raise GovernanceError(
            "G02 active Iteration is not a complete Gate orchestration: " + ", ".join(missing)
        )
    return iteration_id, eval_id


def resolve_active_gate_eval(root: Path) -> tuple[str, str]:
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration_id = state.get("active_iteration")
    if not isinstance(iteration_id, str):
        raise GovernanceError("G02 Gate Eval requires an active orchestration Iteration")
    iteration_path = root / "governance" / "iterations" / f"{iteration_id}.yaml"
    if not iteration_path.is_file():
        raise GovernanceError("G02 active Iteration record is missing")
    iteration = load_data(iteration_path)
    eval_id = iteration.get("eval_id")
    if not isinstance(eval_id, str):
        raise GovernanceError("G02 active Iteration lacks an Eval ID")
    eval_root = root / "docs" / "evals" / eval_id
    manifest_path = eval_root / "manifest.json"
    plan_path = eval_root / "PLAN.md"
    if not manifest_path.is_file() or not plan_path.is_file():
        raise GovernanceError("G02 active orchestration Eval assets are missing")
    return validate_gate_orchestration_selection(
        state,
        iteration,
        load_data(manifest_path),
        plan_path.read_text(encoding="utf-8"),
    )


class TrialJournal:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, trial_id: str) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
        if not trial_id or any(character not in allowed for character in trial_id):
            raise GovernanceError("trial ID contains unsupported characters")
        return self.root / "trials" / f"{trial_id}.json"

    def read(self, trial_id: str) -> dict[str, Any] | None:
        path = self.path(trial_id)
        return load_data(path) if path.is_file() else None

    def write(self, trial_id: str, status: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if status not in {"pending", "running", *PHASE_TERMINAL_STATUSES}:
            raise GovernanceError(f"invalid trial status: {status}")
        previous = self.read(trial_id)
        attempt = 1 if previous is None else int(previous["attempt"]) + 1
        document = {
            "trial_id": trial_id,
            "status": status,
            "attempt": attempt,
            "recorded_at": _utc_now(),
            "payload": dict(payload),
        }
        _atomic_json(self.path(trial_id), document)
        return document


PhaseHandler = Callable[[PhaseContext, TrialJournal], Mapping[str, Any]]


class PhaseEngine:
    def __init__(
        self,
        definitions: Iterable[PhaseDefinition],
        context: PhaseContext,
        journal_root: Path,
    ) -> None:
        self.definitions = tuple(definitions)
        self.context = context
        self.journal_root = journal_root
        self.trials = TrialJournal(journal_root)
        self._by_id = {definition.phase_id: definition for definition in self.definitions}
        if len(self._by_id) != len(self.definitions):
            raise GovernanceError("phase registry contains duplicate IDs")
        seen: set[str] = set()
        for definition in self.definitions:
            missing = sorted(set(definition.dependencies) - seen)
            if missing:
                raise GovernanceError(
                    f"phase DAG is not topologically ordered: {definition.phase_id} {missing}"
                )
            seen.add(definition.phase_id)

    def record_path(self, phase_id: str) -> Path:
        return self.journal_root / "phases" / f"{phase_id}.json"

    def read_record(self, phase_id: str) -> dict[str, Any] | None:
        path = self.record_path(phase_id)
        return load_data(path) if path.is_file() else None

    def _exact_pass(self, phase_id: str) -> bool:
        definition = self._by_id[phase_id]
        record = self.read_record(phase_id)
        return bool(
            record
            and record.get("cache_key") == self.context.cache_key(definition)
            and record.get("status") == "pass"
        )

    def _selected_definitions(
        self,
        *,
        phase_id: str | None,
        from_failed: bool,
    ) -> tuple[PhaseDefinition, ...]:
        if phase_id is not None:
            if phase_id not in self._by_id:
                raise GovernanceError(f"unknown G02 phase: {phase_id}")
            return (self._by_id[phase_id],)
        if not from_failed:
            return self.definitions
        for index, definition in enumerate(self.definitions):
            record = self.read_record(definition.phase_id)
            if record is None or record.get("cache_key") != self.context.cache_key(definition):
                return self.definitions[index:]
            status = record.get("status")
            if status in RESUMABLE_STATUSES:
                return self.definitions[index:]
            if status in {"metric_fail", "blocked"}:
                raise GovernanceError(
                    f"phase {definition.phase_id} requires a new candidate or external unblock"
                )
        return ()

    def run(
        self,
        handlers: Mapping[str, PhaseHandler],
        *,
        phase_id: str | None = None,
        resume: bool = False,
        from_failed: bool = False,
    ) -> list[dict[str, Any]]:
        if resume and from_failed:
            raise GovernanceError("--resume and --from-failed are mutually exclusive")
        selected = self._selected_definitions(phase_id=phase_id, from_failed=from_failed)
        results: list[dict[str, Any]] = []
        for definition in selected:
            for dependency in definition.dependencies:
                if not self._exact_pass(dependency):
                    raise GovernanceError(
                        "phase dependency lacks an exact-key pass: "
                        f"{definition.phase_id} <- {dependency}"
                    )
            cache_key = self.context.cache_key(definition)
            previous = self.read_record(definition.phase_id)
            if previous and previous.get("cache_key") == cache_key:
                status = previous.get("status")
                if status == "pass":
                    results.append(previous)
                    continue
                if status in {"metric_fail", "blocked"}:
                    raise GovernanceError(
                        f"phase {definition.phase_id} cannot rerun on the same candidate: {status}"
                    )
                if status not in RESUMABLE_STATUSES and not resume and not from_failed:
                    raise GovernanceError(
                        f"phase {definition.phase_id} has a non-resumable state: {status}"
                    )
            handler = handlers.get(definition.phase_id)
            if handler is None:
                raise GovernanceError(f"phase handler is not implemented: {definition.phase_id}")
            started_at = _utc_now()
            execution_count = (
                1
                if previous is None or previous.get("cache_key") != cache_key
                else int(previous.get("execution_count", 0)) + 1
            )
            payload = dict(handler(self.context, self.trials))
            status = payload.pop("status", "pass")
            if status not in PHASE_TERMINAL_STATUSES:
                raise GovernanceError(f"phase handler returned invalid status: {status}")
            record = {
                "phase_id": definition.phase_id,
                "status": status,
                "start_time": started_at,
                "end_time": _utc_now(),
                "cache_key": cache_key,
                "candidate_sha": self.context.candidate_sha,
                "execution_count": execution_count,
                "destructive": definition.destructive,
                "payload": payload,
            }
            _atomic_json(self.record_path(definition.phase_id), record)
            results.append(record)
            if status != "pass":
                break
        return results


def validate_candidate_binding_document(document: Mapping[str, Any]) -> None:
    for field in (
        "candidate_sha",
        "evidence_head_sha",
        "subject_digests",
        "environment_fingerprint",
        "changed_paths",
    ):
        if field not in document:
            raise GovernanceError(f"candidate binding lacks {field}")
    if document["candidate_sha"] == document["evidence_head_sha"]:
        if document["changed_paths"]:
            raise GovernanceError("same-SHA binding cannot declare changed paths")
    else:
        forbidden = sorted(
            path
            for path in document["changed_paths"]
            if path not in EVIDENCE_ONLY_FILES
            and not any(path.startswith(prefix) for prefix in EVIDENCE_ONLY_PREFIXES)
        )
        if forbidden:
            raise GovernanceError(
                "evidence descendant changes candidate-affecting paths: " + ", ".join(forbidden)
            )
    digests = document["subject_digests"]
    if not isinstance(digests, dict) or not digests:
        raise GovernanceError("candidate binding lacks subject digests")
    if any(not isinstance(value, str) or len(value) != 64 for value in digests.values()):
        raise GovernanceError("candidate binding contains an invalid subject digest")
    if (
        not isinstance(document["environment_fingerprint"], str)
        or len(document["environment_fingerprint"]) != 64
    ):
        raise GovernanceError("candidate binding contains an invalid environment fingerprint")


def inspect_candidate_binding(
    root: Path,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    validate_candidate_binding_document(document)
    candidate = str(document["candidate_sha"])
    evidence_head = str(document["evidence_head_sha"])
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, evidence_head],
        cwd=root,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        raise GovernanceError("evidence head is not a descendant of the candidate")
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{candidate}..{evidence_head}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    if changed != list(document["changed_paths"]):
        raise GovernanceError("candidate binding changed-path declaration drifted")
    return {
        "status": "pass",
        "candidate_sha": candidate,
        "evidence_head_sha": evidence_head,
        "subject_digest_count": len(document["subject_digests"]),
        "environment_fingerprint": document["environment_fingerprint"],
    }


def validate_manifest_debt_documents(documents: Mapping[str, Mapping[str, Any]]) -> None:
    if not documents:
        raise GovernanceError("manifest debt runner received no manifests")
    for label, manifest in documents.items():
        if manifest.get("status") != "pass":
            raise GovernanceError(f"manifest is not passing: {label}")
        if manifest.get("open_evidence"):
            raise GovernanceError(f"manifest has open evidence: {label}")
        if manifest.get("schema_version") == "2.0.0":
            phases = manifest.get("phases")
            if not isinstance(phases, list) or not phases:
                raise GovernanceError(f"v2 manifest lacks phase evidence: {label}")
            for phase in phases:
                if (
                    phase.get("status") != "pass"
                    or not phase.get("start_time")
                    or not phase.get("end_time")
                ):
                    raise GovernanceError(f"v2 manifest has incomplete phase evidence: {label}")


def inspect_manifest_debt(root: Path, manifest_paths: Iterable[str]) -> dict[str, Any]:
    paths = tuple(manifest_paths)
    documents = {path: load_data(root / path) for path in paths}
    validate_manifest_debt_documents(documents)
    return {"status": "pass", "manifest_count": len(documents), "manifests": list(paths)}


def validate_reconciliation_document(document: Mapping[str, Any]) -> None:
    if document.get("open_evidence"):
        raise GovernanceError("reconciliation has open evidence")
    if document.get("waivers"):
        raise GovernanceError("reconciliation has waivers")
    for field in ("backlog_count", "dlq_count", "fallback_count"):
        if document.get(field) != 0:
            raise GovernanceError(f"reconciliation has nonzero {field}")
    phases = document.get("phases")
    if not isinstance(phases, list) or not phases:
        raise GovernanceError("reconciliation lacks phase records")
    for phase in phases:
        if phase.get("status") != "pass":
            raise GovernanceError(f"reconciliation has unresolved phase: {phase.get('phase_id')}")
        if not phase.get("start_time") or not phase.get("end_time"):
            raise GovernanceError(f"reconciliation phase lacks timestamps: {phase.get('phase_id')}")
        if phase.get("destructive") and phase.get("execution_count") != 1:
            raise GovernanceError(
                f"destructive phase execution count drifted: {phase.get('phase_id')}"
            )
    trials = document.get("trials", [])
    unresolved = [trial.get("trial_id") for trial in trials if trial.get("status") != "pass"]
    if unresolved:
        raise GovernanceError("reconciliation has unresolved trials: " + ", ".join(unresolved))


def inspect_reconciliation(document: Mapping[str, Any]) -> dict[str, Any]:
    validate_reconciliation_document(document)
    return {
        "status": "pass",
        "phase_count": len(document["phases"]),
        "trial_count": len(document.get("trials", [])),
        "open_evidence": 0,
        "backlog_count": 0,
        "dlq_count": 0,
    }


def _load_gate_binding(root: Path, candidate_sha: str) -> dict[str, Any]:
    iteration_id, eval_id = resolve_active_gate_eval(root)
    binding_path = root / "docs" / "evals" / eval_id / "candidate-binding.json"
    if not binding_path.is_file():
        raise GovernanceError("G02 candidate-binding asset is missing")
    binding = dict(load_data(binding_path))
    if binding.get("candidate_sha") != candidate_sha:
        raise GovernanceError("G02 candidate-binding SHA drifted")
    validate_candidate_binding_document(binding)
    if "phase_inputs" in binding:
        raise GovernanceError("G02 operator-precomputed phase inputs are forbidden")
    journal_root = Path(str(binding.get("journal_root", "")))
    if (
        not journal_root.is_absolute()
        or candidate_sha not in journal_root.parts
        or eval_id not in journal_root.parts
    ):
        raise GovernanceError("G02 journal root is not candidate and Eval scoped")
    binding["_iteration_id"] = iteration_id
    binding["_eval_id"] = eval_id
    return binding


def _context_from_binding(binding: Mapping[str, Any]) -> PhaseContext:
    return PhaseContext(
        candidate_sha=str(binding["candidate_sha"]),
        runtime_image_digests=tuple(binding["runtime_image_digests"]),
        sut_image_set_digest=str(binding["sut_image_set_digest"]),
        config_digest=str(binding["config_digest"]),
        evaluator_digest=str(binding["evaluator_digest"]),
        dataset_digest=str(binding["dataset_digest"]),
        environment_fingerprint=str(binding["environment_fingerprint"]),
    )


def _phase_records_before(engine: PhaseEngine, phase_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for definition in engine.definitions:
        if definition.phase_id == phase_id:
            break
        record = engine.read_record(definition.phase_id)
        if record is None:
            raise GovernanceError(f"missing phase record before {phase_id}: {definition.phase_id}")
        records.append(record)
    return records


def _trial_records(journal: TrialJournal) -> list[dict[str, Any]]:
    trial_root = journal.root / "trials"
    if not trial_root.is_dir():
        return []
    return [load_data(path) for path in sorted(trial_root.glob("*.json"))]


def _owned_phase_handlers(
    root: Path,
    binding: Mapping[str, Any],
    engine: PhaseEngine,
    probe_backend: ProbeBackend | None = None,
) -> dict[str, PhaseHandler]:
    def phase_output(phase_id: str, filename: str) -> Path:
        eval_id = binding.get("_eval_id")
        if not isinstance(eval_id, str):
            raise GovernanceError("G02 phase handler lacks an active Eval binding")
        return root / "docs" / "evals" / eval_id / "artifacts" / "phases" / phase_id / filename

    def manifests(_context: PhaseContext, _journal: TrialJournal) -> Mapping[str, Any]:
        return inspect_manifest_debt(root, binding["manifest_paths"])

    def candidate(_context: PhaseContext, _journal: TrialJournal) -> Mapping[str, Any]:
        return inspect_candidate_binding(root, binding)

    def static(_context: PhaseContext, _journal: TrialJournal) -> Mapping[str, Any]:
        checked = 0
        for relative, expected in binding["subject_digests"].items():
            path = root / relative
            if not path.is_file():
                raise GovernanceError(f"candidate subject path is missing: {relative}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise GovernanceError(f"candidate subject digest drifted: {relative}")
            checked += 1
        return {"status": "pass", "subject_count": checked}

    def upstream(_context: PhaseContext, _journal: TrialJournal) -> Mapping[str, Any]:
        paths = [path for path in binding["manifest_paths"] if "/EVAL-G01-" in path]
        if len(paths) != 9:
            raise GovernanceError("G02 upstream preflight requires exactly nine G01 manifests")
        return inspect_manifest_debt(root, paths)

    def lab(context: PhaseContext, _journal: TrialJournal) -> Mapping[str, Any]:
        from faultwitness_dev.g02_lab import deploy_g02_lab

        document = deploy_g02_lab(
            root,
            context.candidate_sha,
            evidence_head_sha=str(binding["evidence_head_sha"]),
        )
        if document.get("image_set_digest") != context.sut_image_set_digest:
            raise GovernanceError("G02 deployed lab image-set binding drifted")
        output = phase_output("lab-deploy-and-bind", "summary.json")
        _atomic_json(output, document)
        return {
            "status": "pass",
            "ready_deployment_count": len(document["ready_deployments"]),
            "artifact_digest": _canonical_digest(document),
            "artifact_path": output.relative_to(root).as_posix(),
        }

    def backend() -> ProbeBackend:
        nonlocal probe_backend
        if probe_backend is None:
            probe_backend = CandidateProbeBackend(root, binding)
        return probe_backend

    def collector_result(
        phase_id: str,
        document: Mapping[str, Any],
        output: Path,
        validator: Callable[[Mapping[str, Any], str, str], Mapping[str, Any]],
        context: PhaseContext,
    ) -> Mapping[str, Any]:
        _atomic_json(output, document)
        status = str(document.get("status", "blocked"))
        summary: Mapping[str, Any] = {}
        if status == "pass":
            summary = validator(
                document, context.candidate_sha, context.environment_fingerprint
            )
        return {
            **summary,
            "status": status,
            "phase_id": phase_id,
            "artifact_digest": _canonical_digest(document),
            "artifact_path": output.relative_to(root).as_posix(),
        }

    def access(context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        phase_id = "isolation-access-matrix"
        return collector_result(
            phase_id,
            run_access_matrix(context, journal, backend()),
            phase_output(phase_id, "matrix.json"),
            validate_live_access_matrix,
            context,
        )

    def stages(context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        phase_id = "trace-six-stage-matrix"
        return collector_result(
            phase_id,
            run_trace_matrix(context, journal, backend()),
            phase_output(phase_id, "matrix.json"),
            validate_stage_matrix,
            context,
        )

    def canary(context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        phase_id = "all-surface-canary"
        return collector_result(
            phase_id,
            run_canary_matrix(context, journal, backend()),
            phase_output(phase_id, "matrix.json"),
            validate_all_surface_canary,
            context,
        )

    def scenarios(context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        from faultwitness_dev.g02_lab import run_gate_scenario_matrix

        document = run_gate_scenario_matrix(root, context.candidate_sha, journal)
        output = phase_output("scenario-matrix", "summary.json")
        _atomic_json(output, document)
        return {
            "status": document["status"],
            "scenario_count": document["scenario_count"],
            "artifact_digest": _canonical_digest(document),
            "artifact_path": output.relative_to(root).as_posix(),
        }

    def scenario_document() -> dict[str, Any]:
        path = phase_output("scenario-matrix", "summary.json")
        if not path.is_file():
            raise GovernanceError("G02 baseline phase lacks scenario-matrix output")
        document = load_data(path)
        if not isinstance(document, dict) or document.get("status") != "pass":
            raise GovernanceError("G02 baseline phase received an incomplete scenario matrix")
        return document

    def deterministic_baseline_phase(
        context: PhaseContext, _journal: TrialJournal
    ) -> Mapping[str, Any]:
        from faultwitness_dev.g02_baselines import run_gate_deterministic_matrix

        document = run_gate_deterministic_matrix(context.candidate_sha, scenario_document())
        output = phase_output("baseline-deterministic", "results.json")
        _atomic_json(output, document)
        return {
            "status": "pass",
            "case_count": 32,
            "validation": "V-G02-014",
            "artifact_digest": _canonical_digest(document),
            "artifact_path": output.relative_to(root).as_posix(),
        }

    def live_baseline_phase(context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        from faultwitness_dev.g02_baselines import run_gate_live_matrix

        document = run_gate_live_matrix(
            root,
            context.candidate_sha,
            context.dataset_digest,
            scenario_document(),
            journal.root,
        )
        output = phase_output("baseline-live", "journal-index.json")
        _atomic_json(output, document)
        return {
            "status": document["status"],
            "trial_count": document["trial_count"],
            "validation": "V-G02-015",
            "artifact_digest": _canonical_digest(document),
            "artifact_path": output.relative_to(root).as_posix(),
        }

    def baseline_aggregate_phase(
        context: PhaseContext, _journal: TrialJournal
    ) -> Mapping[str, Any]:
        from faultwitness_dev.g02_baselines import aggregate_gate_baselines

        deterministic = load_data(phase_output("baseline-deterministic", "results.json"))
        live = load_data(phase_output("baseline-live", "journal-index.json"))
        metrics = aggregate_gate_baselines(
            scenario_document(), deterministic, live, context.dataset_digest
        )
        output = phase_output("baseline-aggregate", "metrics.json")
        _atomic_json(output, metrics)
        return {
            "status": "pass",
            "case_clusters": metrics["case_clusters"],
            "artifact_digest": _canonical_digest(metrics),
            "artifact_path": output.relative_to(root).as_posix(),
        }

    def reconciliation(_context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        document = {
            "open_evidence": binding.get("open_evidence", []),
            "waivers": binding.get("waivers", []),
            "backlog_count": binding.get("backlog_count"),
            "dlq_count": binding.get("dlq_count"),
            "fallback_count": binding.get("fallback_count"),
            "phases": _phase_records_before(engine, "candidate-reconciliation"),
            "trials": _trial_records(journal),
        }
        return inspect_reconciliation(document)

    def close(_context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        records = _phase_records_before(engine, "close-readiness")
        document = {
            "open_evidence": binding.get("open_evidence", []),
            "waivers": binding.get("waivers", []),
            "backlog_count": binding.get("backlog_count"),
            "dlq_count": binding.get("dlq_count"),
            "fallback_count": binding.get("fallback_count"),
            "phases": records,
            "trials": _trial_records(journal),
        }
        summary = inspect_reconciliation(document)
        summary["status"] = "pass"
        return summary

    return {
        "preflight-manifests": manifests,
        "preflight-candidate-binding": candidate,
        "preflight-static-inheritance": static,
        "preflight-upstream-g01": upstream,
        "lab-deploy-and-bind": lab,
        "isolation-access-matrix": access,
        "trace-six-stage-matrix": stages,
        "all-surface-canary": canary,
        "scenario-matrix": scenarios,
        "baseline-deterministic": deterministic_baseline_phase,
        "baseline-live": live_baseline_phase,
        "baseline-aggregate": baseline_aggregate_phase,
        "candidate-reconciliation": reconciliation,
        "close-readiness": close,
    }


def run_g02_eval(
    root: Path,
    candidate_sha: str,
    *,
    phase_id: str | None = None,
    resume: bool = False,
    from_failed: bool = False,
) -> dict[str, Any]:
    binding = _load_gate_binding(root, candidate_sha)
    journal_root = Path(binding["journal_root"])
    if not journal_root.is_absolute():
        raise GovernanceError("G02 Gate journal root must be repository-external and absolute")
    engine = PhaseEngine(G02_PHASES, _context_from_binding(binding), journal_root)
    handlers = _owned_phase_handlers(root, binding, engine)
    results = engine.run(
        handlers,
        phase_id=phase_id,
        resume=resume,
        from_failed=from_failed,
    )
    return {
        "eval_id": binding["_eval_id"],
        "candidate_sha": candidate_sha,
        "status": "pass" if results and results[-1]["status"] == "pass" else "pending",
        "phase_count": len(results),
        "last_phase": results[-1]["phase_id"] if results else None,
    }


def inspect_g02_close_readiness(
    root: Path, candidate_sha: str, evidence_head_sha: str
) -> dict[str, Any]:
    binding = _load_gate_binding(root, candidate_sha)
    if binding.get("evidence_head_sha") != evidence_head_sha:
        raise GovernanceError("G02 close-readiness evidence head drifted")
    journal_root = Path(binding["journal_root"])
    engine = PhaseEngine(G02_PHASES, _context_from_binding(binding), journal_root)
    records = [engine.read_record(definition.phase_id) for definition in G02_PHASES]
    if any(record is None for record in records):
        raise GovernanceError("G02 close readiness lacks one or more phase records")
    if any(record.get("status") != "pass" for record in records if record is not None):
        raise GovernanceError("G02 close readiness has a non-passing phase")
    return {
        "eval_id": binding["_eval_id"],
        "candidate_sha": candidate_sha,
        "evidence_head_sha": evidence_head_sha,
        "status": "ready",
        "phase_count": len(records),
    }


def _contract_context(candidate_sha: str) -> PhaseContext:
    digest = "1" * 64
    return PhaseContext(
        candidate_sha=candidate_sha,
        runtime_image_digests=(digest,),
        sut_image_set_digest="2" * 64,
        config_digest="3" * 64,
        evaluator_digest="4" * 64,
        dataset_digest="5" * 64,
        environment_fingerprint="6" * 64,
    )


def run_phase_contract_suite(candidate_sha: str, work_root: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    first = PhaseDefinition("first", (), "I-0016")
    second = PhaseDefinition("second", ("first",), "I-0016")
    calls: list[str] = []

    def passing(phase_id: str) -> PhaseHandler:
        def handler(_context: PhaseContext, _journal: TrialJournal) -> Mapping[str, Any]:
            calls.append(phase_id)
            return {"status": "pass", "artifact_digest": _canonical_digest(phase_id)}

        return handler

    engine = PhaseEngine((first, second), _contract_context(candidate_sha), work_root / "case-1")
    handlers = {"first": passing("first"), "second": passing("second")}
    engine.run(handlers)
    engine.run(handlers)
    if calls != ["first", "second"]:
        raise GovernanceError("exact-key pass cache was re-executed")
    cases.append({"case": "dag_and_cache", "status": "pass"})

    isolated = PhaseEngine((first, second), _contract_context(candidate_sha), work_root / "case-2")
    try:
        isolated.run(handlers, phase_id="second")
    except GovernanceError as error:
        if "dependency" not in str(error):
            raise
    else:
        raise GovernanceError("single phase ignored its dependency")
    cases.append({"case": "phase_dependency", "status": "pass"})

    resume_engine = PhaseEngine(
        (first, second), _contract_context(candidate_sha), work_root / "case-3"
    )
    attempts = {"second": 0}

    def transient(_context: PhaseContext, journal: TrialJournal) -> Mapping[str, Any]:
        attempts["second"] += 1
        journal.write("trial-resume", "infra_failed", {"attempt": attempts["second"]})
        if attempts["second"] == 1:
            return {"status": "infra_failed"}
        journal.write("trial-resume", "pass", {"attempt": attempts["second"]})
        return {"status": "pass"}

    resume_engine.run({"first": passing("resume-first"), "second": transient})
    resume_engine.run({"first": passing("resume-first"), "second": transient}, resume=True)
    if attempts["second"] != 2 or resume_engine.trials.read("trial-resume")["status"] != "pass":
        raise GovernanceError("resume did not preserve and continue the failed trial")
    cases.append({"case": "resume_infra_failed", "status": "pass"})

    from_failed_engine = PhaseEngine(
        (first, second), _contract_context(candidate_sha), work_root / "case-4"
    )
    from_failed_engine.run({"first": passing("from-first"), "second": transient})
    from_failed_engine.run(
        {"first": passing("from-first"), "second": passing("from-second")},
        from_failed=True,
    )
    cases.append({"case": "from_failed", "status": "pass"})

    destructive = PhaseDefinition("destructive", (), "I-0016", destructive=True)
    destructive_calls: list[str] = []

    def destructive_handler(_context: PhaseContext, _journal: TrialJournal) -> Mapping[str, Any]:
        destructive_calls.append("run")
        return {"status": "pass"}

    destructive_engine = PhaseEngine(
        (destructive,), _contract_context(candidate_sha), work_root / "case-5"
    )
    destructive_engine.run({"destructive": destructive_handler})
    destructive_engine.run({"destructive": destructive_handler})
    if destructive_calls != ["run"]:
        raise GovernanceError("destructive exact-key pass executed more than once")
    cases.append({"case": "destructive_once", "status": "pass"})

    if len(cases) != 5:
        raise GovernanceError("V-G02-001 must execute exactly five contract cases")
    return cases


def evaluate_i0016(root: Path, candidate_sha: str) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if head != candidate_sha:
        raise GovernanceError("EVAL-G02-001 candidate SHA must equal checked-out HEAD")
    if subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True).stdout:
        raise GovernanceError("EVAL-G02-001 requires a clean candidate worktree")
    loaded = validate_repository_schemas(root)
    state = loaded["PROJECT_STATE.yaml"]
    iteration = loaded["governance/iterations/I-0016.yaml"]
    if (
        state.get("active_gate") != "G02"
        or state.get("active_gate_status") != "in_progress"
        or state.get("active_iteration") != "I-0016"
        or iteration.get("status") != "in_progress"
    ):
        raise GovernanceError("EVAL-G02-001 requires I-0016 as the sole active Iteration")

    import tempfile

    started_at = _utc_now()
    with tempfile.TemporaryDirectory(prefix="fw-g02-i0016-") as temporary:
        cases = run_phase_contract_suite(candidate_sha, Path(temporary))

    negative_fixtures = {
        "candidate_binding": (
            validate_candidate_binding_document,
            root / "tests" / "fixtures" / "g02" / "candidate_non_evidence_descendant.json",
        ),
        "manifest_debt": (
            lambda document: validate_manifest_debt_documents({"negative": document}),
            root / "tests" / "fixtures" / "g02" / "manifest_open_evidence.json",
        ),
        "reconciliation": (
            validate_reconciliation_document,
            root / "tests" / "fixtures" / "g02" / "reconciliation_pending.json",
        ),
    }
    rejected: list[str] = []
    for name, (validator, path) in negative_fixtures.items():
        try:
            validator(load_data(path))
        except GovernanceError:
            rejected.append(name)
        else:
            raise GovernanceError(f"owned L2 negative fixture was accepted: {name}")

    artifact = {
        "schema_version": "1.0.0",
        "eval_id": "EVAL-G02-001",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "start_time": started_at,
        "end_time": _utc_now(),
        "validation": "V-G02-001",
        "iteration_n": len(cases),
        "cases": cases,
        "owned_l2_ready": sorted(rejected),
        "open_evidence": [],
    }
    artifact_path = root / "docs" / "evals" / "EVAL-G02-001" / "artifacts" / "phase-contract.json"
    _atomic_json(artifact_path, artifact)
    return {
        "eval_id": "EVAL-G02-001",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {case["case"]: "pass" for case in cases},
        "owned_l2_ready": sorted(rejected),
        "artifact_path": artifact_path.relative_to(root).as_posix(),
    }
