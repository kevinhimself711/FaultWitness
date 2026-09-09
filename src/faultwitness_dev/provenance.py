from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from faultwitness_dev.errors import GovernanceError


@dataclass(frozen=True)
class ProducerProvenance:
    producer_sha: str
    source_digest: str
    dirty: bool


def content_digest(root: Path, inputs: list[Path]) -> str:
    """Digest actual input bytes and repository-relative names, including dirty worktrees."""
    resolved_root = root.resolve()
    files: list[Path] = []
    for item in inputs:
        path = item.resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError as error:
            raise GovernanceError("provenance inputs must remain inside the repository") from error
        if path.is_dir():
            files.extend(
                candidate
                for candidate in sorted(path.rglob("*"))
                if candidate.is_file() and not candidate.is_symlink()
            )
        elif path.is_file() and not path.is_symlink():
            files.append(path)
        else:
            raise GovernanceError(f"provenance input is missing or unsupported: {item}")
    digest = hashlib.sha256()
    for path in sorted(set(files)):
        relative = path.relative_to(resolved_root).as_posix().encode()
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def producer_provenance(root: Path, inputs: list[Path] | None = None) -> ProducerProvenance:
    producer_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if len(producer_sha) != 40 or any(
        character not in "0123456789abcdef" for character in producer_sha
    ):
        raise GovernanceError("producer commit is not a full lowercase Git SHA")
    selected = inputs or [root / "src", root / "deploy", root / "config", root / "migrations"]
    existing = [path for path in selected if path.exists()]
    source_digest = content_digest(root, existing) if existing else hashlib.sha256(b"").hexdigest()
    relative = [path.resolve().relative_to(root.resolve()).as_posix() for path in existing]
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--", *relative],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    )
    return ProducerProvenance(producer_sha, source_digest, dirty)
