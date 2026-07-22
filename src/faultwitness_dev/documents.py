from __future__ import annotations

import re
from pathlib import Path

from faultwitness_dev.errors import GovernanceError

LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
TEXT_SUFFIXES = {".cmd", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}


def check_utf8(paths: list[Path], root: Path) -> None:
    for path in paths:
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            "Makefile",
            ".nvmrc",
            ".python-version",
        }:
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise GovernanceError(f"not UTF-8: {path.relative_to(root)}") from error


def check_local_links(paths: list[Path], root: Path) -> None:
    for path in paths:
        if path.suffix.lower() != ".md":
            continue
        content = path.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(content):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "/")):
                continue
            if not (path.parent / target).resolve().exists():
                relative = path.relative_to(root)
                raise GovernanceError(f"broken local link in {relative}: {raw_target}")


def check_markdown_basics(paths: list[Path], root: Path) -> None:
    for path in paths:
        if path.suffix.lower() != ".md":
            continue
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            raise GovernanceError(f"empty Markdown file: {path.relative_to(root)}")
        if "\t" in content:
            raise GovernanceError(f"tab character in Markdown: {path.relative_to(root)}")
