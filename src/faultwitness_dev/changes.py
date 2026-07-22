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
        candidates = [
            Path(path).stem
            for path in paths
            if path.startswith("governance/iterations/I-") and path.endswith(".yaml")
        ]
        if len(candidates) == 1:
            iteration_id = candidates[0]
    if any(path.startswith(GOVERNED_PREFIXES) for path in paths) and iteration_id is None:
        raise GovernanceError("governed change is missing an Iteration record")
    if iteration_id is None:
        return "documentation-only change without governed behavior"
    record_path = root / "governance" / "iterations" / f"{iteration_id}.yaml"
    if not record_path.is_file():
        raise GovernanceError(f"Iteration record does not exist: {iteration_id}")
    record = load_data(record_path)
    validate_change_record(record, root)
    return f"validated {iteration_id} for {len(paths)} changed files"
