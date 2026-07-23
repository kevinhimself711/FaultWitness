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

G00_CLOSURE_PATHS = {
    "CHANGELOG.md",
    "PROJECT_STATE.yaml",
    "docs/adr/INDEX.yaml",
    "docs/claims/CLAIMS.yaml",
    "docs/gates/G00/REPORT.md",
    "docs/gates/G01/PLAN.md",
    "docs/gates/G01/REPORT.md",
    "governance/gates/G00.yaml",
    "governance/gates/G01.yaml",
}

G01_CLOSURE_PATHS = {
    "CHANGELOG.md",
    "PROJECT_STATE.yaml",
    "docs/adr/INDEX.yaml",
    "docs/claims/CLAIMS.yaml",
    "docs/gates/G01/REPORT.md",
    "docs/gates/G02/PLAN.md",
    "docs/gates/G02/REPORT.md",
    "governance/gates/G01.yaml",
    "governance/gates/G02.yaml",
}


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
        if state.get("last_closed_gate") == "G01":
            validate_g01_closure_change(
                state,
                load_data(root / "governance" / "gates" / "G01.yaml"),
                load_data(root / "governance" / "gates" / "G02.yaml"),
                paths,
            )
            return f"validated asset-only G01 closure for {len(paths)} changed files"
        if state.get("last_closed_gate") == "G00":
            validate_g00_closure_change(
                state,
                load_data(root / "governance" / "gates" / "G00.yaml"),
                load_data(root / "governance" / "gates" / "G01.yaml"),
                paths,
            )
            return f"validated asset-only G00 closure for {len(paths)} changed files"
        if any(path.startswith(GOVERNED_PREFIXES) for path in paths):
            raise GovernanceError("governed change is missing an Iteration record")
        return "documentation-only change without governed behavior"
    record_path = root / "governance" / "iterations" / f"{iteration_id}.yaml"
    if not record_path.is_file():
        raise GovernanceError(f"Iteration record does not exist: {iteration_id}")
    record = load_data(record_path)
    validate_change_record(record, root)
    return f"validated {iteration_id} for {len(paths)} changed files"


def infer_iteration_id(root: Path, paths: list[str]) -> str | None:
    candidates: list[str] = []
    for path in paths:
        if not path.startswith("governance/iterations/I-") or not path.endswith(".yaml"):
            continue
        record = load_data(root / path)
        if record.get("status") in {"in_progress", "completed"} and record.get("docs_updated"):
            candidates.append(record["id"])
    return max(candidates) if candidates else None


def validate_g00_closure_change(
    state: dict[str, Any],
    g00: dict[str, Any],
    g01: dict[str, Any],
    paths: list[str],
) -> None:
    actual = set(paths)
    if actual != G00_CLOSURE_PATHS:
        missing = sorted(G00_CLOSURE_PATHS - actual)
        unexpected = sorted(actual - G00_CLOSURE_PATHS)
        raise GovernanceError(
            f"G00 closure asset boundary drifted: missing={missing}, unexpected={unexpected}"
        )
    expected_state = {
        "active_gate": "G01",
        "active_gate_status": "not_started",
        "active_iteration": None,
        "next_iteration": None,
        "last_closed_gate": "G00",
        "active_gate_plan": "docs/gates/G01/PLAN.md",
        "active_gate_report": "docs/gates/G01/REPORT.md",
    }
    drift = {
        key: state.get(key)
        for key, expected_value in expected_state.items()
        if state.get(key) != expected_value
    }
    if drift:
        raise GovernanceError(f"G00 closure project-state drift: {drift}")
    if g00.get("id") != "G00" or g00.get("status") != "passed" or g00.get("waivers"):
        raise GovernanceError("G00 closure requires a passed waiver-free G00 record")
    if g01.get("id") != "G01" or g01.get("status") != "planned":
        raise GovernanceError("G00 closure requires a planned G01 handoff record")


def validate_g01_closure_change(
    state: dict[str, Any],
    g01: dict[str, Any],
    g02: dict[str, Any],
    paths: list[str],
) -> None:
    actual = set(paths)
    if actual != G01_CLOSURE_PATHS:
        missing = sorted(G01_CLOSURE_PATHS - actual)
        unexpected = sorted(actual - G01_CLOSURE_PATHS)
        raise GovernanceError(
            f"G01 closure asset boundary drifted: missing={missing}, unexpected={unexpected}"
        )
    expected_state = {
        "active_gate": "G02",
        "active_gate_status": "not_started",
        "active_iteration": None,
        "next_iteration": None,
        "last_closed_gate": "G01",
        "active_gate_plan": "docs/gates/G02/PLAN.md",
        "active_gate_report": "docs/gates/G02/REPORT.md",
    }
    drift = {
        key: state.get(key)
        for key, expected_value in expected_state.items()
        if state.get(key) != expected_value
    }
    if drift:
        raise GovernanceError(f"G01 closure project-state drift: {drift}")
    if g01.get("id") != "G01" or g01.get("status") != "passed" or g01.get("waivers"):
        raise GovernanceError("G01 closure requires a passed waiver-free G01 record")
    if g02.get("id") != "G02" or g02.get("status") != "planned":
        raise GovernanceError("G01 closure requires a planned G02 handoff record")
