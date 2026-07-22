from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from faultwitness.contracts.compiler import (
    ContractCompilationError,
    assert_generated_resource_current,
    load_generated_resource,
    write_generated_resource,
)
from faultwitness_dev.audit import (
    audit_repository,
    check_external_links,
    validate_g00_closure_readiness,
)
from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    accept_existing_credentials,
    accept_host_key_candidate,
    capture_host_key_candidate,
    default_age_keygen_executable,
    default_sops_executable,
    default_ssh_askpass_executable,
    finalize_handoff,
    install_and_verify_ssh_key,
    migrate_handoff,
    run_capability_probe,
    validate_migration,
)
from faultwitness_dev.checks import eval_changed, run, verify_fast
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.evals import evaluate_iteration
from faultwitness_dev.infra import (
    audit_runtime_coexistence,
    capture_preinstall_baseline,
    diagnose_k3s_failure,
    diagnose_network_matrix,
    diagnose_nvidia_failure,
    diagnose_runtime_smokes,
    harden_runtime_listeners,
    inspect_infra_prerequisites,
    install_gvisor_runtime,
    install_k3s_core,
    install_kata_runtime,
    install_nvidia_runtime,
    prepare_offline_base_images,
    recover_cluster_dns,
    resolve_public_image_digest,
    run_network_matrix,
    run_runtime_smokes,
)
from faultwitness_dev.platform import deploy_platform, inspect_platform_readiness
from faultwitness_dev.runtime_deploy import deploy_runtime_schema, inspect_runtime_schema
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

    accept_credentials = subparsers.add_parser("accept-existing-credentials")
    accept_credentials.add_argument(
        "--operator-confirmed-long-lived", action="store_true", required=True
    )
    accept_credentials.add_argument("--config-root", type=Path)
    accept_credentials.add_argument("--sops", type=Path)

    eval_iteration = subparsers.add_parser("eval-iteration")
    eval_iteration.add_argument("iteration")
    eval_iteration.add_argument("--candidate-sha", required=True)
    infra_baseline = subparsers.add_parser("capture-infra-baseline")
    infra_baseline.add_argument("--candidate-sha", required=True)
    install_core = subparsers.add_parser("install-k3s-core")
    install_core.add_argument("--candidate-sha", required=True)
    install_gvisor = subparsers.add_parser("install-gvisor-runtime")
    install_gvisor.add_argument("--candidate-sha", required=True)
    install_nvidia = subparsers.add_parser("install-nvidia-runtime")
    install_nvidia.add_argument("--candidate-sha", required=True)
    install_kata = subparsers.add_parser("install-kata-runtime")
    install_kata.add_argument("--candidate-sha", required=True)
    prepare_images = subparsers.add_parser("prepare-offline-images")
    prepare_images.add_argument("--candidate-sha", required=True)
    runtime_smokes = subparsers.add_parser("runtime-smokes")
    runtime_smokes.add_argument("--candidate-sha", required=True)
    network_matrix = subparsers.add_parser("network-matrix")
    network_matrix.add_argument("--candidate-sha", required=True)
    coexistence = subparsers.add_parser("audit-runtime-coexistence")
    coexistence.add_argument("--candidate-sha", required=True)
    harden_listeners = subparsers.add_parser("harden-runtime-listeners")
    harden_listeners.add_argument("--candidate-sha", required=True)
    recover_dns = subparsers.add_parser("recover-cluster-dns")
    recover_dns.add_argument("--candidate-sha", required=True)
    inspect_infra = subparsers.add_parser("inspect-infra")
    inspect_infra.add_argument("--unprivileged", action="store_true")
    resolve_image = subparsers.add_parser("resolve-public-image")
    resolve_image.add_argument("--image", required=True)
    deploy_services = subparsers.add_parser("deploy-platform")
    deploy_services.add_argument("--candidate-sha", required=True)
    deploy_services.add_argument("--chart", type=Path)
    deploy_services.add_argument("--values", type=Path)
    inspect_services = subparsers.add_parser("inspect-platform")
    inspect_services.add_argument("--candidate-sha", required=True)
    inspect_services.add_argument("--stability-seconds", type=int, default=0)
    deploy_runtime = subparsers.add_parser("deploy-runtime-schema")
    deploy_runtime.add_argument("--candidate-sha", required=True)
    inspect_runtime = subparsers.add_parser("inspect-runtime-schema")
    inspect_runtime.add_argument("--candidate-sha", required=True)
    subparsers.add_parser("compile-contracts")
    subparsers.add_parser("check-contracts")
    subparsers.add_parser("diagnose-k3s")
    subparsers.add_parser("diagnose-nvidia")
    subparsers.add_parser("diagnose-runtime-smokes")
    subparsers.add_parser("diagnose-network-matrix")
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
                "private store; plaintext handoff retained pending acceptance and host evidence"
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
            message = (
                "deleted plaintext handoff after existing-credential, host-pin, and dedicated-"
                "key evidence passed"
            )
        elif args.command == "capture-host-key":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            fingerprint = capture_host_key_candidate(paths, args.sops or default_sops_executable())
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
            askpass = args.askpass or default_ssh_askpass_executable()
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
        elif args.command == "accept-existing-credentials":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            if not args.operator_confirmed_long_lived:
                raise GovernanceError("operator confirmation is required")
            accept_existing_credentials(paths, args.sops or default_sops_executable())
            message = "accepted the three existing long-lived credentials without changing values"
        elif args.command == "eval-iteration":
            summary = evaluate_iteration(root, args.iteration, args.candidate_sha)
            evidence_count = len(summary.get("checks", {})) or summary.get(
                "legal_transition_count", 0
            )
            message = (
                f"{summary['eval_id']} passed on {summary['candidate_sha']} with "
                f"{evidence_count} primary checks"
            )
        elif args.command == "capture-infra-baseline":
            summary = capture_preinstall_baseline(root, args.candidate_sha)
            message = (
                "captured private preinstall baseline for "
                f"{summary['container_count']} Docker containers with digest "
                f"{summary['baseline_sha256']}"
            )
        elif args.command == "install-k3s-core":
            summary = install_k3s_core(root, args.candidate_sha)
            message = (
                "installed pinned K3s core while preserving "
                f"{summary['container_count']} Docker containers with zero regression"
            )
        elif args.command == "install-gvisor-runtime":
            summary = install_gvisor_runtime(root, args.candidate_sha)
            message = f"installed gVisor {summary['gvisor_version']} and registered " + ", ".join(
                summary["runtime_classes"]
            )
        elif args.command == "install-nvidia-runtime":
            summary = install_nvidia_runtime(root, args.candidate_sha)
            message = (
                f"installed NVIDIA device plugin {summary['device_plugin_version']} "
                "with at least one allocatable GPU"
            )
        elif args.command == "install-kata-runtime":
            summary = install_kata_runtime(root, args.candidate_sha)
            message = (
                f"installed Kata {summary['kata_version']} and registered "
                f"RuntimeClass {summary['runtime_class']}"
            )
        elif args.command == "prepare-offline-images":
            summary = prepare_offline_base_images(root, args.candidate_sha)
            message = "imported pinned offline images: " + ", ".join(summary["images"])
        elif args.command == "runtime-smokes":
            summary = run_runtime_smokes(root, args.candidate_sha)
            message = "passed real workload smokes for " + ", ".join(summary["runtimes"])
        elif args.command == "network-matrix":
            summary = run_network_matrix(root, args.candidate_sha)
            message = f"passed all {len(summary['passed_cases'])} NetworkPolicy cases"
        elif args.command == "audit-runtime-coexistence":
            summary = audit_runtime_coexistence(root, args.candidate_sha)
            message = (
                "preserved Docker baseline with zero regression and "
                f"{summary['new_nonpublic_listener_count']} non-public listeners"
            )
        elif args.command == "harden-runtime-listeners":
            summary = harden_runtime_listeners(args.candidate_sha)
            message = (
                f"selected single-node Flannel {summary['flannel_backend']} and removed "
                "the wildcard VXLAN listener"
            )
        elif args.command == "recover-cluster-dns":
            summary = recover_cluster_dns(args.candidate_sha)
            message = (
                "recovered CoreDNS with "
                f"{summary['ready_replicas_minimum']} ready replica and an endpoint"
            )
        elif args.command == "inspect-infra":
            values = inspect_infra_prerequisites(privileged=not args.unprivileged)
            message = (
                "privileged remote prerequisites passed; current state is "
                f"k3s={values['k3s']}, helm={values['helm']}, config={values['config']}, "
                f"service={values['k3s_service']}, runsc={values['runsc']}, "
                f"containerd={values['containerd_config']}, "
                f"runsc_config={values['runsc_config']}, "
                f"nvidia={values['nvidia_runtime']}, "
                f"nvidia_config={values['nvidia_config']}, zstd={values['zstd']}, "
                f"zstd_candidate={values['zstd_candidate']}, pause={values['pause_image']}"
                f", kata_stage_bytes={values['kata_stage_bytes']}, "
                f"gcc={values['gcc']}, make={values['make']}, "
                f"image_stage={values['image_stage_dir']}/"
                f"{values['image_stage_writable']}, pause_refs={values['pause_refs']}, "
                f"kata_runtime_rs={values['kata_runtime_rs']}, "
                f"coredns={values['coredns_ready']}/{values['dns_endpoint']}"
            )
        elif args.command == "resolve-public-image":
            digest = resolve_public_image_digest(args.image)
            message = f"resolved linux/amd64 digest {digest} for {args.image}"
        elif args.command == "deploy-platform":
            summary = deploy_platform(
                root,
                args.candidate_sha,
                chart=args.chart,
                values=args.values,
            )
            message = (
                f"deployed {summary['release']} in {summary['namespace']} from candidate "
                f"{summary['candidate_sha']} with bundle digest "
                f"{summary['deployment_bundle_sha256']}"
            )
        elif args.command == "inspect-platform":
            summary = inspect_platform_readiness(
                root,
                args.candidate_sha,
                stability_seconds=args.stability_seconds,
            )
            message = (
                f"observed {summary['workload_count']} sanitized Ready workloads for "
                f"{summary['stability_seconds']} seconds on {summary['candidate_sha']}"
            )
        elif args.command == "deploy-runtime-schema":
            summary = deploy_runtime_schema(root, args.candidate_sha)
            message = (
                f"deployed runtime schema from {summary['candidate_sha']} with migration digest "
                f"{summary['migration_sha256']}"
            )
        elif args.command == "inspect-runtime-schema":
            summary = inspect_runtime_schema(args.candidate_sha)
            message = (
                f"observed runtime migration {summary['migration']} with "
                f"{summary['table_count']} owner-isolated tables"
            )
        elif args.command == "compile-contracts":
            target = write_generated_resource(root)
            bundle = load_generated_resource(root)
            message = (
                f"wrote {target.relative_to(root).as_posix()} for contract version "
                f"{bundle['contracts_version']} with digest {bundle['artifact_sha256']}"
            )
        elif args.command == "check-contracts":
            assert_generated_resource_current(root)
            bundle = load_generated_resource(root)
            message = (
                f"generated contract version {bundle['contracts_version']} is current with "
                f"digest {bundle['artifact_sha256']}"
            )
        elif args.command == "diagnose-k3s":
            diagnosis = diagnose_k3s_failure()
            message = (
                "stored private K3s journal with digest "
                f"{diagnosis['sha256']}; categories=" + ",".join(diagnosis["categories"])
            )
        elif args.command == "diagnose-nvidia":
            diagnosis = diagnose_nvidia_failure()
            message = (
                "stored private NVIDIA diagnostics with digest "
                f"{diagnosis['sha256']}; categories=" + ",".join(diagnosis["categories"])
            )
        elif args.command == "diagnose-runtime-smokes":
            diagnosis = diagnose_runtime_smokes()
            message = (
                "stored private runtime-smoke diagnostics with digest "
                f"{diagnosis['sha256']}; categories=" + ",".join(diagnosis["categories"])
            )
        elif args.command == "diagnose-network-matrix":
            diagnosis = diagnose_network_matrix()
            message = (
                "stored private network-matrix diagnostics with digest "
                f"{diagnosis['sha256']}; categories=" + ",".join(diagnosis["categories"])
            )
        else:
            report = check_external_links(root)
            message = f"recorded {report['checked']} external link results (non-blocking)"
        print(f"PASS {args.command}: {message}")
        return 0
    except (ContractCompilationError, GovernanceError, subprocess.CalledProcessError) as error:
        print(f"FAIL {args.command}: {error}")
        return 1
