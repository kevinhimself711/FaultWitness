from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data

TERMINAL_STATUSES = {"pass", "metric_fail", "infra_failed", "blocked"}
RESUMABLE_STATUSES = {"running", "infra_failed"}


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def semantic_cache_key(
    checkpoint_values: Mapping[str, str],
    required_checkpoints: Sequence[str],
    *,
    input_digest: str,
    dependency_artifacts: Mapping[str, str] | None = None,
) -> str:
    """Key one unit by semantic inputs, never by governance HEAD or producer SHA."""
    missing = sorted(set(required_checkpoints) - set(checkpoint_values))
    if missing:
        raise GovernanceError(f"missing semantic checkpoints: {missing}")
    subject = {
        "checkpoints": {name: checkpoint_values[name] for name in sorted(required_checkpoints)},
        "dependencies": dict(sorted((dependency_artifacts or {}).items())),
        "input_digest": input_digest,
    }
    return _digest(subject)


def affected_units(
    checkpoint_dependencies: Mapping[str, Sequence[str]],
    changed_checkpoints: Sequence[str],
    unit_dependencies: Mapping[str, Sequence[str]] | None = None,
) -> set[str]:
    """Return direct consumers and their real downstream dependency closure."""
    changed = set(changed_checkpoints)
    affected = {
        unit
        for unit, required in checkpoint_dependencies.items()
        if changed.intersection(required)
    }
    graph = unit_dependencies or {}
    while True:
        downstream = {
            unit for unit, required in graph.items() if affected.intersection(required)
        }
        expanded = affected | downstream
        if expanded == affected:
            return affected
        affected = expanded


@dataclass(frozen=True)
class ExperimentUnit:
    unit_id: str
    required_checkpoints: tuple[str, ...]
    depends_on: tuple[str, ...]
    input_digest: str
    destructive: bool = False

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise GovernanceError("experiment unit ID cannot be empty")
        if len(set(self.required_checkpoints)) != len(self.required_checkpoints):
            raise GovernanceError(f"duplicate checkpoint on unit {self.unit_id}")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise GovernanceError(f"duplicate dependency on unit {self.unit_id}")
        if not self.input_digest:
            raise GovernanceError(f"experiment unit {self.unit_id} lacks an input digest")


class ExperimentInfrastructureError(RuntimeError):
    """A trial-local external failure that may resume from its journal checkpoints."""


class ExperimentBlockedError(RuntimeError):
    """A deterministic external precondition failure requiring a semantic change."""


class TrialJournal:
    """Atomic journal separating executions, record writes, and side-effect checkpoints."""

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

    def begin(
        self,
        trial_id: str,
        *,
        producer_sha: str,
        cache_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = self.read(trial_id)
        same_semantics = previous is not None and previous.get("cache_key") == cache_key
        history = [] if previous is None else list(previous.get("history", []))
        if previous is not None:
            history.append({key: value for key, value in previous.items() if key != "history"})
        document = {
            "trial_id": trial_id,
            "status": "running",
            "execution_attempt": 1
            if previous is None
            else int(previous["execution_attempt"]) + 1,
            "record_version": 1
            if previous is None
            else int(previous["record_version"]) + 1,
            "producer_sha": producer_sha,
            "cache_key": cache_key,
            "recorded_at": datetime.now(UTC).isoformat(),
            "runtime_checkpoints": dict(previous.get("runtime_checkpoints", {}))
            if same_semantics
            else {},
            "history": history,
            "payload": dict(payload or {}),
        }
        return self._write(trial_id, document)

    def checkpoint(
        self,
        trial_id: str,
        checkpoint_name: str,
        observation: Any,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a completed side effect or last usable observation without a new execution."""
        if not checkpoint_name:
            raise GovernanceError("runtime checkpoint name cannot be empty")
        previous = self.read(trial_id)
        if previous is None or previous.get("status") != "running":
            raise GovernanceError("trial must be running before it can checkpoint")
        checkpoints = dict(previous.get("runtime_checkpoints", {}))
        checkpoints[checkpoint_name] = observation
        document = {
            **previous,
            "record_version": int(previous["record_version"]) + 1,
            "recorded_at": datetime.now(UTC).isoformat(),
            "runtime_checkpoints": checkpoints,
            "payload": dict(previous.get("payload", {}))
            if payload is None
            else dict(payload),
        }
        return self._write(trial_id, document)

    def finish(
        self,
        trial_id: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if status not in TERMINAL_STATUSES:
            raise GovernanceError(f"invalid terminal trial status: {status}")
        previous = self.read(trial_id)
        if previous is None or previous.get("status") != "running":
            raise GovernanceError("trial must be running before it can finish")
        stable_payload = dict(payload)
        return self._write(
            trial_id,
            {
                **previous,
                "status": status,
                "record_version": int(previous["record_version"]) + 1,
                "recorded_at": datetime.now(UTC).isoformat(),
                "payload": stable_payload,
                "artifact_digest": _digest(stable_payload),
            },
        )

    def _write(self, trial_id: str, document: Mapping[str, Any]) -> dict[str, Any]:
        path = self.path(trial_id)
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
        return dict(document)


@dataclass
class UnitExecution:
    unit: ExperimentUnit
    journal: TrialJournal
    record: dict[str, Any]

    @property
    def resume_checkpoints(self) -> dict[str, Any]:
        return dict(self.record.get("runtime_checkpoints", {}))

    def checkpoint(
        self,
        name: str,
        observation: Any,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.record = self.journal.checkpoint(
            self.unit.unit_id, name, observation, payload=payload
        )
        return self.record


ExperimentHandler = Callable[[UnitExecution], Mapping[str, Any]]


@dataclass(frozen=True)
class ExperimentRun:
    records: tuple[dict[str, Any], ...]
    executed_units: tuple[str, ...]
    reused_units: tuple[str, ...]
    skipped_units: tuple[str, ...]


class ExperimentRunner:
    """Execute a semantic unit DAG with local resume and dependency-scoped invalidation."""

    def __init__(
        self,
        units: Iterable[ExperimentUnit],
        journal: TrialJournal,
        checkpoint_values: Mapping[str, str],
        *,
        producer_sha: str,
    ) -> None:
        self.units = tuple(units)
        self.journal = journal
        self.checkpoint_values = dict(checkpoint_values)
        self.producer_sha = producer_sha
        self._by_id = {unit.unit_id: unit for unit in self.units}
        if len(self._by_id) != len(self.units):
            raise GovernanceError("experiment unit registry contains duplicate IDs")
        seen: set[str] = set()
        for unit in self.units:
            missing = sorted(set(unit.depends_on) - seen)
            if missing:
                raise GovernanceError(
                    f"experiment DAG is not topologically ordered: {unit.unit_id} {missing}"
                )
            seen.add(unit.unit_id)

    def cache_key(self, unit: ExperimentUnit) -> str:
        dependency_artifacts: dict[str, str] = {}
        for dependency_id in unit.depends_on:
            dependency = self._by_id[dependency_id]
            record = self.journal.read(dependency_id)
            if (
                record is None
                or record.get("status") != "pass"
                or record.get("cache_key") != self.cache_key(dependency)
                or not isinstance(record.get("artifact_digest"), str)
            ):
                raise GovernanceError(
                    f"unit dependency lacks an exact semantic pass: "
                    f"{unit.unit_id} <- {dependency_id}"
                )
            dependency_artifacts[dependency_id] = _digest(
                {
                    "semantic_key": record["cache_key"],
                    "artifact_digest": record["artifact_digest"],
                }
            )
        return semantic_cache_key(
            self.checkpoint_values,
            unit.required_checkpoints,
            input_digest=unit.input_digest,
            dependency_artifacts=dependency_artifacts,
        )

    def run(
        self,
        handlers: Mapping[str, ExperimentHandler],
        *,
        unit_ids: Iterable[str] | None = None,
    ) -> ExperimentRun:
        selected = set(unit_ids) if unit_ids is not None else set(self._by_id)
        unknown = sorted(selected - set(self._by_id))
        if unknown:
            raise GovernanceError(f"unknown experiment units: {unknown}")
        records: list[dict[str, Any]] = []
        executed: list[str] = []
        reused: list[str] = []
        skipped: list[str] = []
        failed: set[str] = set()

        for unit in self.units:
            if unit.unit_id not in selected:
                continue
            if failed.intersection(unit.depends_on):
                skipped.append(unit.unit_id)
                failed.add(unit.unit_id)
                continue
            try:
                cache_key = self.cache_key(unit)
            except GovernanceError:
                if any(
                    (self.journal.read(dependency) or {}).get("status") != "pass"
                    for dependency in unit.depends_on
                ):
                    skipped.append(unit.unit_id)
                    failed.add(unit.unit_id)
                    continue
                raise
            previous = self.journal.read(unit.unit_id)
            if previous and previous.get("cache_key") == cache_key:
                status = previous.get("status")
                if status == "pass":
                    records.append(previous)
                    reused.append(unit.unit_id)
                    continue
                if status in {"metric_fail", "blocked"}:
                    raise GovernanceError(
                        f"unit {unit.unit_id} cannot retry unchanged semantic inputs after {status}"
                    )
                if status not in RESUMABLE_STATUSES:
                    raise GovernanceError(
                        f"unit {unit.unit_id} has invalid resumable status: {status}"
                    )

            handler = handlers.get(unit.unit_id)
            if handler is None:
                raise GovernanceError(f"experiment handler is not implemented: {unit.unit_id}")
            running = self.journal.begin(
                unit.unit_id,
                producer_sha=self.producer_sha,
                cache_key=cache_key,
                payload={"resuming": bool(previous and previous.get("cache_key") == cache_key)},
            )
            execution = UnitExecution(unit, self.journal, running)
            executed.append(unit.unit_id)
            try:
                outcome = dict(handler(execution))
                status = str(outcome.pop("status", "pass"))
                payload = outcome.pop("payload", outcome)
                if not isinstance(payload, Mapping):
                    raise GovernanceError(
                        f"experiment handler payload is not an object: {unit.unit_id}"
                    )
                record = self.journal.finish(unit.unit_id, status, payload)
            except ExperimentInfrastructureError as error:
                record = self.journal.finish(
                    unit.unit_id, "infra_failed", {"reason": str(error)}
                )
            except ExperimentBlockedError as error:
                record = self.journal.finish(
                    unit.unit_id, "blocked", {"reason": str(error)}
                )
            records.append(record)
            if record["status"] != "pass":
                failed.add(unit.unit_id)

        return ExperimentRun(
            records=tuple(records),
            executed_units=tuple(executed),
            reused_units=tuple(reused),
            skipped_units=tuple(skipped),
        )
