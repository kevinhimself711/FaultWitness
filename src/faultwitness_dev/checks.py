from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from shutil import which
from typing import Any

import yaml

from faultwitness_dev.changes import changed_paths, validate_changed_assets
from faultwitness_dev.documents import check_local_links, check_markdown_basics, check_utf8
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data, validate_repository_schemas

LIFECYCLE_FIELDS = (
    "active_gate",
    "active_gate_status",
    "active_iteration",
    "next_iteration",
    "last_closed_gate",
)
LIFECYCLE_MARKDOWN_PATHS = (
    "AGENTS.md",
    "README.md",
    "docs/roadmap/PHASES.md",
)
ITERATION_POLICY_PATH = "governance/policies/iteration-lifecycle-v1.yaml"
ITERATION_RECORD_PREFIX = "governance/iterations/"
ITERATION_TERMINAL_STATUSES = {"completed", "failed"}
ITERATION_ALLOWED_TRANSITIONS = {
    "planned": {"planned", "in_progress", "failed"},
    "in_progress": {"in_progress", "completed", "failed"},
    "completed": {"completed"},
    "failed": {"failed"},
}


def repository_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [root / line for line in result.stdout.splitlines() if line and (root / line).is_file()]


def run(command: list[str], root: Path) -> None:
    executable = which(command[0])
    if executable is None:
        raise GovernanceError(f"required executable not found: {command[0]}")
    result = subprocess.run([executable, *command[1:]], cwd=root)
    if result.returncode:
        raise GovernanceError(f"command failed ({result.returncode}): {' '.join(command)}")


def _markdown_front_matter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise GovernanceError(f"lifecycle document lacks YAML front matter: {path.name}")
    parts = content.split("---", 2)
    if len(parts) != 3:
        raise GovernanceError(f"lifecycle document has invalid YAML front matter: {path.name}")
    document = yaml.safe_load(parts[1])
    if not isinstance(document, dict):
        raise GovernanceError(f"lifecycle front matter must be an object: {path.name}")
    return document


def validate_lifecycle_records(state: dict[str, Any], records: dict[str, dict[str, Any]]) -> None:
    expected = {field: state.get(field) for field in LIFECYCLE_FIELDS}
    for path, record in records.items():
        drift = {
            field: {"expected": value, "observed": record.get(field)}
            for field, value in expected.items()
            if record.get(field) != value
        }
        if drift:
            raise GovernanceError(f"lifecycle state drift in {path}: {drift}")


def validate_lifecycle_documents(root: Path) -> None:
    state = load_data(root / "PROJECT_STATE.yaml")
    records = {path: _markdown_front_matter(root / path) for path in LIFECYCLE_MARKDOWN_PATHS}
    validate_lifecycle_records(state, records)


def validate_active_governance_state(root: Path) -> None:
    state = load_data(root / "PROJECT_STATE.yaml")
    gate = load_data(root / "governance" / "gates" / f"{state['active_gate']}.yaml")
    compatible_gate_status = {
        "not_started": "planned",
        "planned": "planned",
        "in_progress": "in_progress",
        "passed": "passed",
        "failed": "failed",
        "blocked": "blocked",
    }
    expected = compatible_gate_status[state["active_gate_status"]]
    if gate["status"] != expected:
        raise GovernanceError(
            "active Gate status drift: "
            f"PROJECT_STATE={state['active_gate_status']}, gate_record={gate['status']}"
        )

    iterations = {
        iteration_id: load_data(root / "governance" / "iterations" / f"{iteration_id}.yaml")
        for iteration_id in gate["iterations"]
    }
    active = state.get("active_iteration")
    if active is not None:
        record = iterations.get(active)
        if record is None or record["gate"] != gate["id"] or record["status"] != "in_progress":
            raise GovernanceError(f"active Iteration state drift: {active}")

    next_iteration = state.get("next_iteration")
    if next_iteration is not None:
        record = iterations.get(next_iteration)
        if record is None or record["gate"] != gate["id"] or record["status"] != "planned":
            raise GovernanceError(f"next Iteration state drift: {next_iteration}")
        first_planned = next(
            (
                iteration_id
                for iteration_id in gate["iterations"]
                if iterations[iteration_id]["status"] == "planned"
            ),
            None,
        )
        if next_iteration != first_planned:
            raise GovernanceError(
                "next Iteration is not the first planned record: "
                f"{next_iteration} != {first_planned}"
            )


def validate_iteration_status_transition(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
    label: str,
) -> None:
    if previous is None:
        if current is None:
            return
        if current.get("status") != "planned":
            raise GovernanceError(
                f"new Iteration must start planned: {label}={current.get('status')}"
            )
        if current.get("iteration_type") not in {"standard", "corrective"}:
            raise GovernanceError(f"new Iteration lacks iteration_type: {label}")
        if current.get("iteration_type") == "corrective" and not current.get("corrects"):
            raise GovernanceError(f"new corrective Iteration lacks corrects links: {label}")
        return
    if current is None:
        raise GovernanceError(f"Iteration record deletion is forbidden: {label}")
    if previous.get("id") != current.get("id"):
        raise GovernanceError(f"Iteration record identity changed: {label}")
    previous_type = previous.get("iteration_type")
    if previous_type is not None and current.get("iteration_type") != previous_type:
        raise GovernanceError(f"Iteration type changed after policy binding: {label}")
    previous_corrects = previous.get("corrects")
    if previous_corrects is not None and current.get("corrects") != previous_corrects:
        raise GovernanceError(f"Iteration corrects links changed after policy binding: {label}")
    previous_status = previous.get("status")
    current_status = current.get("status")
    allowed = ITERATION_ALLOWED_TRANSITIONS.get(str(previous_status), set())
    if current_status not in allowed:
        raise GovernanceError(
            "Iteration status regression is forbidden: "
            f"{label} {previous_status} -> {current_status}"
        )


def validate_iteration_status_sequence(records: list[dict[str, Any] | None], label: str) -> None:
    for index, (previous, current) in enumerate(zip(records, records[1:], strict=False)):
        validate_iteration_status_transition(previous, current, f"{label}@{index + 1}")


def _load_yaml_from_revision(root: Path, revision: str, path: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return None
    try:
        document = yaml.safe_load(result.stdout)
    except yaml.YAMLError as error:
        raise GovernanceError(f"cannot parse prior Iteration record {path}: {error}") from error
    if not isinstance(document, dict):
        raise GovernanceError(f"prior Iteration record is not an object: {path}")
    return document


def _policy_start_revision(root: Path) -> str:
    if not (root / ITERATION_POLICY_PATH).is_file():
        raise GovernanceError("forward Iteration lifecycle policy asset is missing")
    result = subprocess.run(
        ["git", "log", "--format=%H", "--diff-filter=A", "--", ITERATION_POLICY_PATH],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    commits = result.stdout.splitlines()
    if not commits:
        # The active implementation candidate introduces the policy in its worktree. History
        # enforcement begins once that candidate is committed; worktree transitions are still
        # checked below.
        return ""
    return commits[-1]


def _iteration_paths_in_commit(root: Path, commit: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
            "--",
            "governance/iterations",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return sorted(path for path in result.stdout.splitlines() if path.endswith(".yaml"))


def _validate_committed_iteration_history(root: Path, start: str) -> None:
    if not start:
        return
    result = subprocess.run(
        ["git", "rev-list", "--reverse", "--topo-order", f"{start}^..HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    for commit in result.stdout.splitlines():
        parent_result = subprocess.run(
            ["git", "rev-parse", f"{commit}^1"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        parent = parent_result.stdout.strip() if parent_result.returncode == 0 else ""
        for path in _iteration_paths_in_commit(root, commit):
            previous = _load_yaml_from_revision(root, parent, path) if parent else None
            current = _load_yaml_from_revision(root, commit, path)
            validate_iteration_status_transition(previous, current, f"{path}@{commit[:12]}")


def validate_corrective_iteration_links(root: Path) -> None:
    records = {
        path.stem: load_data(path)
        for path in sorted((root / "governance" / "iterations").glob("I-*.yaml"))
    }
    for iteration_id, record in records.items():
        iteration_type = record.get("iteration_type")
        corrects = record.get("corrects", [])
        if iteration_type is None:
            continue  # Legacy record created before the machine policy epoch.
        if iteration_type not in {"standard", "corrective"}:
            raise GovernanceError(f"Iteration has invalid iteration_type: {iteration_id}")
        if iteration_type == "standard" and corrects:
            raise GovernanceError(f"standard Iteration cannot declare corrects: {iteration_id}")
        if iteration_type == "corrective" and not corrects:
            raise GovernanceError(f"corrective Iteration lacks corrects links: {iteration_id}")
        for target_id in corrects:
            target = records.get(target_id)
            if target is None:
                raise GovernanceError(
                    f"corrective Iteration links an unknown record: {iteration_id} -> {target_id}"
                )
            if target.get("status") not in ITERATION_TERMINAL_STATUSES:
                raise GovernanceError(
                    f"corrective Iteration target is not terminal: {iteration_id} -> {target_id}"
                )
            if target.get("gate") != record.get("gate"):
                raise GovernanceError(
                    f"corrective Iteration crosses Gate ownership: {iteration_id} -> {target_id}"
                )
            if int(target_id.split("-")[1]) >= int(iteration_id.split("-")[1]):
                raise GovernanceError(
                    f"corrective Iteration does not point backward: {iteration_id} -> {target_id}"
                )


def validate_iteration_lifecycle_history(root: Path) -> None:
    policy = load_data(root / ITERATION_POLICY_PATH)
    if policy.get("terminal_statuses") != sorted(ITERATION_TERMINAL_STATUSES):
        raise GovernanceError("Iteration lifecycle policy terminal statuses drifted")
    expected_transitions = {
        status: sorted(transitions) for status, transitions in ITERATION_ALLOWED_TRANSITIONS.items()
    }
    observed_transitions = {
        str(status): sorted(str(target) for target in targets)
        for status, targets in policy.get("allowed_transitions", {}).items()
    }
    if observed_transitions != expected_transitions:
        raise GovernanceError("Iteration lifecycle policy allowed transitions drifted")
    if policy.get("new_record_initial_status") != "planned":
        raise GovernanceError("Iteration lifecycle policy initial status drifted")
    if policy.get("corrective_link_direction") != "lower_iteration_id":
        raise GovernanceError("Iteration lifecycle policy corrective direction drifted")
    validate_corrective_iteration_links(root)
    _validate_committed_iteration_history(root, _policy_start_revision(root))

    changed = set(changed_paths(root))
    paths = sorted(
        path
        for path in changed
        if path.startswith(ITERATION_RECORD_PREFIX) and path.endswith(".yaml")
    )
    base = os.environ.get("FW_BASE_REF")
    revision = base if base and set(base) != {"0"} else "HEAD"
    for path in paths:
        previous = _load_yaml_from_revision(root, revision, path)
        current_path = root / path
        current = load_data(current_path) if current_path.is_file() else None
        validate_iteration_status_transition(previous, current, f"{path}@worktree")


def validate_validation_layer_counts(items: list[dict[str, Any]]) -> None:
    for item in items:
        if item["layer"] == "L3" and item["iteration_n"] == item["gate_n"]:
            raise GovernanceError(f"L3 validation uses overlapping N: {item['id']}")


def validate_g02_validation_registry(root: Path) -> None:
    registry = load_data(root / "docs" / "gates" / "G02" / "VALIDATIONS.yaml")
    items = registry["validation_items"]
    validate_validation_layer_counts(items)
    by_id = {item["id"]: item for item in items}
    if len(by_id) != len(items):
        raise GovernanceError("G02 validation registry has duplicate IDs")

    for item in items:
        owner = root / "governance" / "iterations" / f"{item['owning_iteration']}.yaml"
        if not owner.is_file() or load_data(owner).get("gate") != "G02":
            raise GovernanceError(f"validation has an invalid owning Iteration: {item['id']}")
        if item["zero_tolerance"]:
            missing = [
                field
                for field in ("runner", "negative_fixture", "artifact_paths")
                if not item.get(field)
            ]
            if missing:
                raise GovernanceError(
                    f"zero-tolerance validation lacks review assets: {item['id']} {missing}"
                )

    carry_in = load_data(root / "docs" / "gates" / "G02" / "CARRY_IN.yaml")
    if len(carry_in["debts"]) != 4:
        raise GovernanceError("G01 carry-in registry must contain exactly four debts")
    for debt in carry_in["debts"]:
        if debt["coverage"] == "covered_by_target_gate":
            validation = by_id.get(debt["validation_id"])
            if validation is None or validation["owning_iteration"] != debt["owning_iteration"]:
                raise GovernanceError(f"covered carry-in debt has invalid ownership: {debt['id']}")
            if not debt["gate_report_label"]:
                raise GovernanceError(f"covered carry-in debt lacks a report label: {debt['id']}")
        elif any(
            debt[field] is not None
            for field in ("owning_iteration", "validation_id", "gate_report_label")
        ):
            raise GovernanceError(f"uncovered carry-in debt claims an owner: {debt['id']}")


def validate_manifest_revision_change(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    changed: set[str],
    label: str,
) -> None:
    previous_revision = None if previous is None else previous.get("evaluated_revision")
    if current.get("evaluated_revision") == previous_revision:
        return
    artifacts = set(current.get("artifacts", []))
    if not artifacts.intersection(changed):
        raise GovernanceError(
            f"evaluated_revision changed without a corresponding artifact change: {label}"
        )


def _load_manifest_from_revision(root: Path, revision: str, path: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return None
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise GovernanceError(f"cannot parse prior Eval manifest {path}: {error}") from error
    if not isinstance(document, dict):
        raise GovernanceError(f"prior Eval manifest is not an object: {path}")
    return document


def validate_changed_manifest_artifacts(root: Path) -> None:
    changed = set(changed_paths(root))
    manifest_paths = sorted(
        path
        for path in changed
        if path.startswith("docs/evals/") and path.endswith("/manifest.json")
    )
    base = os.environ.get("FW_BASE_REF")
    revision = base if base and set(base) != {"0"} else "HEAD"
    for path in manifest_paths:
        current = load_data(root / path)
        previous = _load_manifest_from_revision(root, revision, path)
        validate_manifest_revision_change(current, previous, changed, path)


def verify_fast(root: Path) -> None:
    files = repository_files(root)
    check_utf8(files, root)
    check_markdown_basics(files, root)
    check_local_links(files, root)
    validate_repository_schemas(root)
    validate_lifecycle_documents(root)
    validate_active_governance_state(root)
    validate_iteration_lifecycle_history(root)
    validate_g02_validation_registry(root)
    validate_changed_manifest_artifacts(root)
    run(["ruff", "check", "src", "tests"], root)
    run(["pytest", "-q"], root)
    run(["pnpm", "exec", "markdownlint-cli2"], root)
    run(["git", "diff", "--check"], root)


def eval_changed(root: Path) -> str:
    validate_repository_schemas(root)
    files = repository_files(root)
    check_utf8(files, root)
    check_local_links(files, root)
    return validate_changed_assets(root, changed_paths(root))
