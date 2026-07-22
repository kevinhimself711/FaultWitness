"""I-0001 bootstrap checks, replaced by faultwitness_dev in I-0002."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".nvmrc",
    ".python-version",
    "AGENTS.md",
    "CHANGELOG.md",
    "LICENSE",
    "Makefile",
    "PROJECT_STATE.yaml",
    "README.md",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "uv.lock",
)
TEXT_SUFFIXES = {".cmd", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise RuntimeError(message)


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def check_required_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")


def check_utf8(files: list[Path]) -> None:
    for path in files:
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Makefile", ".nvmrc", ".python-version"}:
            try:
                path.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                fail(f"not UTF-8: {path.relative_to(ROOT)} ({error})")


def check_local_links(files: list[Path]) -> None:
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        for raw_target in LINK_PATTERN.findall(path.read_text(encoding="utf-8")):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "/")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                fail(f"broken local link in {path.relative_to(ROOT)}: {raw_target}")


def check_repository_boundary(files: list[Path]) -> None:
    forbidden_names = {"agent开发岗位", "agent开发面经", "小红书", "牛客"}
    for path in files:
        relative = path.relative_to(ROOT)
        if ".." in relative.parts:
            fail(f"path escapes repository: {relative}")
        lowered = relative.as_posix().lower()
        if any(name in lowered for name in forbidden_names):
            fail(f"raw research material must not be tracked: {relative}")


def check_git_diff() -> None:
    result = subprocess.run(["git", "diff", "--check"], cwd=ROOT)
    if result.returncode:
        fail("git diff --check failed")


def run_checks(target: str) -> None:
    if target not in {"verify-fast", "eval-changed"}:
        fail(f"unknown target: {target}")
    files = repository_files()
    check_required_files()
    check_utf8(files)
    check_local_links(files)
    check_repository_boundary(files)
    check_git_diff()
    print(f"PASS {target}: {len(files)} repository files checked")


def main() -> int:
    try:
        if len(sys.argv) != 2:
            fail("usage: bootstrap_check.py <verify-fast|eval-changed>")
        run_checks(sys.argv[1])
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
