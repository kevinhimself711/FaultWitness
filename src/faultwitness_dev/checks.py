from __future__ import annotations

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
    "last_closed_gate",
)
LIFECYCLE_MARKDOWN_PATHS = (
    "AGENTS.md",
    "README.md",
    "docs/roadmap/PHASES.md",
)


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


def validate_lifecycle_records(
    state: dict[str, Any], records: dict[str, dict[str, Any]]
) -> None:
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
    records = {
        path: _markdown_front_matter(root / path) for path in LIFECYCLE_MARKDOWN_PATHS
    }
    validate_lifecycle_records(state, records)


def verify_fast(root: Path) -> None:
    files = repository_files(root)
    check_utf8(files, root)
    check_markdown_basics(files, root)
    check_local_links(files, root)
    validate_repository_schemas(root)
    validate_lifecycle_documents(root)
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
