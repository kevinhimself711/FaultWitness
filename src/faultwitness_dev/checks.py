from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

from faultwitness_dev.documents import check_local_links, check_markdown_basics, check_utf8
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data, validate_repository_schemas


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


def validate_current_state(root: Path) -> None:
    """Validate only the current pointer and its directly referenced assets."""
    state = load_data(root / "PROJECT_STATE.yaml")
    for field in ("active_plan", "active_report"):
        target = root / state[field]
        if not target.is_file():
            raise GovernanceError(f"current state references a missing {field}: {state[field]}")
    release = state["latest_release"]
    manifest = root / release["evidence_manifest"]
    if not manifest.is_file():
        raise GovernanceError(
            "current state references a missing release manifest: "
            f"{release['evidence_manifest']}"
        )


def run_repository_audit(root: Path) -> None:
    # Local import avoids a module cycle: audit reuses repository_files from this module.
    from faultwitness_dev.audit import audit_repository

    audit_repository(root)


def check_release_evidence(root: Path) -> None:
    """Require tracked artifacts for the current release; report historical gaps."""
    state = load_data(root / "PROJECT_STATE.yaml")
    manifest_path = root / state["latest_release"]["evidence_manifest"]
    eval_root = manifest_path.parent
    artifacts = eval_root / "artifacts"
    if not artifacts.is_dir():
        raise GovernanceError(f"release evidence artifacts directory is missing: {artifacts}")
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--", f"{artifacts.relative_to(root).as_posix()}/"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    if not any((root / path).is_file() for path in tracked):
        raise GovernanceError(f"release evidence has no tracked artifacts: {eval_root}")

    missing: list[str] = []
    for candidate in sorted((root / "docs/evals").glob("EVAL-*/")):
        candidate_artifacts = candidate / "artifacts"
        if not candidate_artifacts.is_dir() or not any(candidate_artifacts.rglob("*")):
            missing.append(candidate.relative_to(root).as_posix())
    if missing:
        print("historical EVAL directories missing artifacts: " + ", ".join(missing))


def verify_fast(root: Path) -> None:
    files = repository_files(root)
    check_utf8(files, root)
    check_release_evidence(root)
    run(["ruff", "check", "src", "tests"], root)
    run(["pytest", "-q"], root)
    run(["git", "diff", "--check"], root)


def verify_docs(root: Path) -> None:
    files = repository_files(root)
    check_markdown_basics(files, root)
    check_local_links(files, root)
    validate_repository_schemas(root)
    validate_current_state(root)
    run_repository_audit(root)
    run(["pnpm", "exec", "markdownlint-cli2"], root)
