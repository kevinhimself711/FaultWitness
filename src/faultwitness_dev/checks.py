from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

from faultwitness_dev.changes import changed_paths, validate_changed_assets
from faultwitness_dev.documents import check_local_links, check_markdown_basics, check_utf8
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import validate_repository_schemas


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


def verify_fast(root: Path) -> None:
    files = repository_files(root)
    check_utf8(files, root)
    check_markdown_basics(files, root)
    check_local_links(files, root)
    validate_repository_schemas(root)
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
