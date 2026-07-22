from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from faultwitness_dev.audit import (
    audit_repository,
    check_external_links,
    validate_g00_closure_readiness,
)
from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    accept_host_key_candidate,
    capture_host_key_candidate,
    default_age_keygen_executable,
    default_sops_executable,
    finalize_handoff,
    install_and_verify_ssh_key,
    migrate_handoff,
    record_api_rotation_from_clipboard,
    rotate_and_verify_server_password,
    run_capability_probe,
    validate_migration,
)
from faultwitness_dev.checks import eval_changed, run, verify_fast
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.evals import evaluate_iteration
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
    subparsers = command_parser.add_subparsers(dest="command", required=True)
    for command in (
        "verify-fast",
        "eval-changed",
        "validate",
        "audit-g00",
        "eval-g00",
        "eval-g00-close",
        "external-links",
    ):
        subparsers.add_parser(command)

    bootstrap = subparsers.add_parser("bootstrap-secrets")
    bootstrap.add_argument("--handoff", type=Path, default=Path("envs.txt"))
    bootstrap.add_argument("--config-root", type=Path)
    bootstrap.add_argument("--sops", type=Path)
    bootstrap.add_argument("--age-keygen", type=Path)

    verify_bootstrap = subparsers.add_parser("verify-bootstrap")
    verify_bootstrap.add_argument("--config-root", type=Path)
    verify_bootstrap.add_argument("--sops", type=Path)

    finalize_bootstrap = subparsers.add_parser("finalize-bootstrap")
    finalize_bootstrap.add_argument("--handoff", type=Path, default=Path("envs.txt"))
    finalize_bootstrap.add_argument("--config-root", type=Path)
    finalize_bootstrap.add_argument("--sops", type=Path)

    capture_host_key = subparsers.add_parser("capture-host-key")
    capture_host_key.add_argument("--config-root", type=Path)
    capture_host_key.add_argument("--sops", type=Path)

    accept_host_key = subparsers.add_parser("accept-host-key")
    accept_host_key.add_argument("--fingerprint", required=True)
    accept_host_key.add_argument("--config-root", type=Path)

    install_ssh_key = subparsers.add_parser("install-ssh-key")
    install_ssh_key.add_argument("--config-root", type=Path)
    install_ssh_key.add_argument("--sops", type=Path)
    install_ssh_key.add_argument("--askpass", type=Path)

    probe_host = subparsers.add_parser("probe-host")
    probe_host.add_argument("--candidate-sha", required=True)
    probe_host.add_argument("--output", type=Path, required=True)
    probe_host.add_argument("--config-root", type=Path)
    probe_host.add_argument("--sops", type=Path)
    probe_host.add_argument("--probe-script", type=Path)

    rotate_server = subparsers.add_parser("rotate-server-password")
    rotate_server.add_argument("--config-root", type=Path)
    rotate_server.add_argument("--sops", type=Path)
    rotate_server.add_argument("--age-keygen", type=Path)
    rotate_server.add_argument("--askpass", type=Path)

    rotate_api = subparsers.add_parser("record-api-rotation")
    rotate_api.add_argument(
        "--name", choices=("bailian.api_key", "langsmith.api_key"), required=True
    )
    rotate_api.add_argument("--from-clipboard", action="store_true", required=True)
    rotate_api.add_argument("--provider-ui-confirmed", action="store_true", required=True)
    rotate_api.add_argument("--config-root", type=Path)
    rotate_api.add_argument("--sops", type=Path)
    rotate_api.add_argument("--age-keygen", type=Path)

    eval_iteration = subparsers.add_parser("eval-iteration")
    eval_iteration.add_argument("iteration")
    eval_iteration.add_argument("--candidate-sha", required=True)
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
        elif args.command == "bootstrap-secrets":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            metadata = migrate_handoff(
                args.handoff,
                paths,
                args.sops or default_sops_executable(),
                args.age_keygen or default_age_keygen_executable(),
            )
            message = (
                f"migrated {len(metadata['secret_names'])} named secrets to the encrypted "
                "private store; plaintext handoff retained pending rotation evidence"
            )
        elif args.command == "verify-bootstrap":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            metadata = validate_migration(paths, args.sops or default_sops_executable())
            message = (
                f"verified encrypted round-trip and {len(metadata['secret_names'])} required "
                "secret names without exposing values"
            )
        elif args.command == "finalize-bootstrap":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            finalize_handoff(
                args.handoff,
                paths,
                args.sops or default_sops_executable(),
            )
            message = "deleted plaintext handoff after all rotation and capability evidence passed"
        elif args.command == "capture-host-key":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            fingerprint = capture_host_key_candidate(
                paths, args.sops or default_sops_executable()
            )
            message = (
                "captured an untrusted host-key candidate; verify this fingerprint through an "
                f"independent channel before acceptance: {fingerprint}"
            )
        elif args.command == "accept-host-key":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            accept_host_key_candidate(paths, args.fingerprint)
            message = "accepted the host key after exact out-of-band fingerprint comparison"
        elif args.command == "install-ssh-key":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            askpass = args.askpass or root / "deploy" / "bootstrap" / "ssh-askpass.cmd"
            install_and_verify_ssh_key(
                paths,
                args.sops or default_sops_executable(),
                askpass,
            )
            message = "installed and verified the dedicated SSH key without exposing the password"
        elif args.command == "probe-host":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            report = run_capability_probe(
                paths,
                args.sops or default_sops_executable(),
                args.probe_script or root / "deploy" / "bootstrap" / "probe_host.py",
                args.candidate_sha,
                args.output,
            )
            message = (
                "captured two matching sanitized capability probes with normalized digest "
                f"{report['normalized_sha256']}"
            )
        elif args.command == "rotate-server-password":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            rotate_and_verify_server_password(
                paths,
                args.sops or default_sops_executable(),
                args.age_keygen or default_age_keygen_executable(),
                args.askpass or root / "deploy" / "bootstrap" / "ssh-askpass.cmd",
            )
            message = "rotated and verified the server password without emitting either value"
        elif args.command == "record-api-rotation":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            record_api_rotation_from_clipboard(
                args.name,
                paths,
                args.sops or default_sops_executable(),
                args.age_keygen or default_age_keygen_executable(),
                args.provider_ui_confirmed,
            )
            message = (
                "stored the provider-UI replacement directly from clipboard and marked its "
                "rotation verified"
            )
        elif args.command == "eval-iteration":
            summary = evaluate_iteration(root, args.iteration, args.candidate_sha)
            message = (
                f"{summary['eval_id']} passed on {summary['candidate_sha']} with "
                f"{len(summary['checks'])} blocking checks"
            )
        else:
            report = check_external_links(root)
            message = f"recorded {report['checked']} external link results (non-blocking)"
        print(f"PASS {args.command}: {message}")
        return 0
    except (GovernanceError, subprocess.CalledProcessError) as error:
        print(f"FAIL {args.command}: {error}")
        return 1
