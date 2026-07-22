from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from faultwitness_dev.checks import eval_changed, verify_fast
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import validate_repository_schemas


def repository_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return Path(result.stdout.strip())


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(prog="faultwitness_dev")
    command_parser.add_argument("command", choices=("verify-fast", "eval-changed", "validate"))
    return command_parser


def main() -> int:
    args = parser().parse_args()
    try:
        root = repository_root()
        if args.command == "verify-fast":
            verify_fast(root)
            message = "repository checks, tests, and Markdown passed"
        elif args.command == "eval-changed":
            message = eval_changed(root)
        else:
            loaded = validate_repository_schemas(root)
            message = f"validated {len(loaded)} governed assets"
        print(f"PASS {args.command}: {message}")
        return 0
    except (GovernanceError, subprocess.CalledProcessError) as error:
        print(f"FAIL {args.command}: {error}")
        return 1
