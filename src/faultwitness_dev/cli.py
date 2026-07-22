from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from faultwitness_dev.audit import (
    audit_repository,
    check_external_links,
    validate_g00_closure_readiness,
)
from faultwitness_dev.checks import eval_changed, run, verify_fast
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
    command_parser.add_argument(
        "command",
        choices=(
            "verify-fast",
            "eval-changed",
            "validate",
            "audit-g00",
            "eval-g00",
            "eval-g00-close",
            "external-links",
        ),
    )
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
        elif args.command == "validate":
            loaded = validate_repository_schemas(root)
            message = f"validated {len(loaded)} governed assets"
        elif args.command == "audit-g00":
            summary = audit_repository(root)
            message = f"audited {summary['component_count']} dependency components"
        elif args.command in {"eval-g00", "eval-g00-close"}:
            verify_fast(root)
            summary = audit_repository(root)
            run(["pnpm", "run", "check:mermaid"], root)
            changed_message = eval_changed(root)
            closure_message = ""
            if args.command == "eval-g00-close":
                closure_message = "; " + validate_g00_closure_readiness(root)
            message = (
                f"full candidate passed with {summary['component_count']} components; "
                f"{changed_message}{closure_message}"
            )
        else:
            report = check_external_links(root)
            message = f"recorded {report['checked']} external link results (non-blocking)"
        print(f"PASS {args.command}: {message}")
        return 0
    except (GovernanceError, subprocess.CalledProcessError) as error:
        print(f"FAIL {args.command}: {error}")
        return 1
