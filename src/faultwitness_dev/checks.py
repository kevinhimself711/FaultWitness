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
    """Require tracked artifacts for the current release and report historical gaps."""
    state = load_data(root / "PROJECT_STATE.yaml")
    release = state["latest_release"]
    manifest_path = root / str(release["evidence_manifest"])
    eval_root = manifest_path.parent
    artifacts = eval_root / "artifacts"
    if not artifacts.is_dir():
        raise GovernanceError(f"release evidence artifacts directory is missing: {artifacts}")

    relative_artifacts = artifacts.relative_to(root).as_posix()
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--", f"{relative_artifacts}/"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    if not any((root / path).is_file() for path in tracked):
        raise GovernanceError(f"release evidence has no tracked artifacts: {eval_root}")

    missing: list[str] = []
    evals_root = root / "docs/evals"
    for candidate in sorted(path for path in evals_root.glob("EVAL-*") if path.is_dir()):
        if candidate == eval_root:
            continue
        candidate_artifacts = candidate / "artifacts"
        if not candidate_artifacts.is_dir() or not any(
            path.is_file() for path in candidate_artifacts.rglob("*")
        ):
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


PNPM_CHECKS = ("markdownlint-cli2", "repository-audit")


def verify_docs(root: Path) -> None:
    """Run documentation checks, degrading to the pure-Python subset without pnpm.

    The pure-Python group always runs and any failure in it fails the command. The
    pnpm group is skipped with a printed notice when pnpm is unavailable, so a missing
    optional toolchain cannot make every documentation check unrunnable.
    """
    files = repository_files(root)
    for name, check in (
        ("markdown-basics", lambda: check_markdown_basics(files, root)),
        ("local-links", lambda: check_local_links(files, root)),
        ("repository-schemas", lambda: validate_repository_schemas(root)),
        ("current-state", lambda: validate_current_state(root)),
    ):
        check()
        print(f"  ran {name}")

    if which("pnpm") is None:
        print(
            "  skipped "
            + ", ".join(PNPM_CHECKS)
            + ": pnpm not on PATH (optional toolchain; does not affect exit code)"
        )
        return

    run(["pnpm", "exec", "markdownlint-cli2"], root)
    print("  ran markdownlint-cli2")
    run_repository_audit(root)
    print("  ran repository-audit")
