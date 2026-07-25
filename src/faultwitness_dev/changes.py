from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data

GOVERNED_PREFIXES = (
    "src/",
    "schemas/",
    "governance/",
    ".github/",
    "pyproject.toml",
    "package.json",
)

GATE_CLOSURE_STATUS_PATHS = {
    "AGENTS.md",
    "CHANGELOG.md",
    "PROJECT_STATE.yaml",
    "README.md",
    "docs/adr/INDEX.yaml",
    "docs/claims/CLAIMS.yaml",
    "docs/roadmap/PHASES.md",
}


def gate_closure_paths(closing_gate: str, next_gate: str) -> set[str]:
    """Return the exact forward closure boundary for two consecutive Gates."""
    if not (
        len(closing_gate) == 3
        and len(next_gate) == 3
        and closing_gate.startswith("G")
        and next_gate.startswith("G")
        and closing_gate[1:].isdigit()
        and next_gate[1:].isdigit()
        and int(next_gate[1:]) == int(closing_gate[1:]) + 1
    ):
        raise GovernanceError("Gate closure requires consecutive Gxx identifiers")
    return GATE_CLOSURE_STATUS_PATHS | {
        f"docs/gates/{closing_gate}/REPORT.md",
        f"docs/gates/{next_gate}/PLAN.md",
        f"docs/gates/{next_gate}/REPORT.md",
        f"governance/gates/{closing_gate}.yaml",
        f"governance/gates/{next_gate}.yaml",
    }


G00_CLOSURE_PATHS = gate_closure_paths("G00", "G01")
G01_CLOSURE_PATHS = gate_closure_paths("G01", "G02")


def validate_change_record(record: dict[str, Any], root: Path | None = None) -> None:
    if record.get("behavior_change") and not record.get("docs_updated"):
        raise GovernanceError("behavior change must update documentation assets")
    for change in record.get("threshold_changes", []):
        if change.get("direction") == "decrease" or change.get("to", 0) < change.get("from", 0):
            raise GovernanceError(
                f"gate threshold decrease is forbidden: {change.get('id', '<unknown>')}"
            )
    if root is not None:
        missing = [path for path in record.get("docs_updated", []) if not (root / path).is_file()]
        if missing:
            raise GovernanceError(f"declared documentation assets do not exist: {missing}")


def changed_paths(root: Path) -> list[str]:
    base = os.environ.get("FW_BASE_REF")
    if base and set(base) != {"0"}:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return sorted(path for path in result.stdout.splitlines() if path)
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    return sorted(set(tracked + untracked))


def validate_changed_assets(root: Path, paths: list[str]) -> str:
    if not paths:
        return "no changed files"
    state = load_data(root / "PROJECT_STATE.yaml")
    iteration_id = os.environ.get("FW_ITERATION") or state.get("active_iteration")
    if iteration_id is None:
        iteration_id = infer_iteration_id(root, paths)
    if iteration_id is None:
        closing_gate = state.get("last_closed_gate")
        next_gate = state.get("active_gate")
        if isinstance(closing_gate, str) and isinstance(next_gate, str):
            validate_gate_closure_change(
                state,
                load_data(root / "governance" / "gates" / f"{closing_gate}.yaml"),
                load_data(root / "governance" / "gates" / f"{next_gate}.yaml"),
                paths,
            )
            return f"validated asset-only {closing_gate} closure for {len(paths)} changed files"
        if any(path.startswith(GOVERNED_PREFIXES) for path in paths):
            raise GovernanceError("governed change is missing a work-item record")
        return "documentation-only change without governed behavior"
    record_path = root / "governance" / "iterations" / f"{iteration_id}.yaml"
    if not record_path.is_file():
        raise GovernanceError(f"work-item record does not exist: {iteration_id}")
    record = load_data(record_path)
    validate_change_record(record, root)
    return f"validated {iteration_id} for {len(paths)} changed files"


def infer_iteration_id(root: Path, paths: list[str]) -> str | None:
    candidates: list[str] = []
    for path in paths:
        if not path.startswith("governance/iterations/") or not path.endswith(".yaml"):
            continue
        record = load_data(root / path)
        if record.get("status") in {"in_progress", "completed", "failed"} and record.get(
            "docs_updated"
        ):
            candidates.append(record["id"])
    return max(candidates) if candidates else None


def validate_g00_closure_change(
    state: dict[str, Any],
    g00: dict[str, Any],
    g01: dict[str, Any],
    paths: list[str],
) -> None:
    validate_gate_closure_change(state, g00, g01, paths)


def validate_g01_closure_change(
    state: dict[str, Any],
    g01: dict[str, Any],
    g02: dict[str, Any],
    paths: list[str],
) -> None:
    validate_gate_closure_change(state, g01, g02, paths)


def validate_gate_closure_change(
    state: dict[str, Any],
    closing_gate: dict[str, Any],
    next_gate: dict[str, Any],
    paths: list[str],
) -> None:
    closing_id = closing_gate.get("id")
    next_id = next_gate.get("id")
    if not isinstance(closing_id, str) or not isinstance(next_id, str):
        raise GovernanceError("Gate closure records require string identifiers")
    expected_paths = gate_closure_paths(closing_id, next_id)
    actual = set(paths)
    if actual != expected_paths:
        missing = sorted(expected_paths - actual)
        unexpected = sorted(actual - expected_paths)
        raise GovernanceError(
            f"{closing_id} closure asset boundary drifted: "
            f"missing={missing}, unexpected={unexpected}"
        )
    expected_state = {
        "active_gate": next_id,
        "active_gate_status": "not_started",
        "active_iteration": None,
        "next_iteration": None,
        "last_closed_gate": closing_id,
        "active_gate_plan": f"docs/gates/{next_id}/PLAN.md",
        "active_gate_report": f"docs/gates/{next_id}/REPORT.md",
    }
    drift = {
        key: state.get(key)
        for key, expected_value in expected_state.items()
        if state.get(key) != expected_value
    }
    if drift:
        raise GovernanceError(f"{closing_id} closure project-state drift: {drift}")
    if closing_gate.get("status") != "passed" or closing_gate.get("waivers"):
        raise GovernanceError(
            f"{closing_id} closure requires a passed waiver-free {closing_id} record"
        )
    if next_gate.get("status") != "planned":
        raise GovernanceError(f"{closing_id} closure requires a planned {next_id} handoff record")
