from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from faultwitness.contracts.compiler import (
    ContractCompilationError,
    assert_generated_resource_current,
    load_generated_resource,
    write_generated_resource,
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
    parse_endpoint_handoff,
    rotate_server_endpoint,
    run_capability_probe,
    validate_migration,
)
from faultwitness_dev.checks import verify_docs, verify_fast
from faultwitness_dev.control_api_deploy import (
    deploy_control_api,
    diagnose_control_api,
    inspect_control_api,
    inspect_keycloak_realm,
    provision_keycloak_realm,
    run_control_api_smoke,
    run_keycloak_outage_smoke,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.experiment import TrialJournal
from faultwitness_dev.external_links import check_external_links
from faultwitness_dev.g02_baselines import (
    METRIC_VERSION,
    LiveConfigurationError,
    aggregate_gate_baselines,
    metric_v2_dataset_digest,
    run_gate_deterministic_matrix,
    run_gate_live_matrix,
    write_json_artifact,
)
from faultwitness_dev.g02_lab import deploy_g02_lab, replay_resource_scenarios
from faultwitness_dev.g03_readiness import run_retest_baselines_v3
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
    install_nvidia_container_toolkit,
    install_nvidia_runtime,
    prepare_offline_base_images,
    recover_cluster_dns,
    resolve_public_image_digest,
    run_network_matrix,
    run_runtime_smokes,
)
from faultwitness_dev.model_deploy import (
    deploy_model_gateway,
    inspect_model_gateway,
    run_model_gateway_smoke,
)
from faultwitness_dev.observability_deploy import (
    deploy_trace_service,
    diagnose_trace_service,
    inspect_trace_service,
    run_trace_service_smoke,
)
from faultwitness_dev.platform import deploy_platform, inspect_platform_readiness
from faultwitness_dev.provenance import producer_provenance
from faultwitness_dev.runtime_deploy import deploy_runtime_schema, inspect_runtime_schema
from faultwitness_dev.schemas import load_data, validate_repository_schemas


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
        "verify-docs",
        "validate",
        "external-links",
    ):
        subparsers.add_parser(command)

    baseline_retest = subparsers.add_parser("retest-baselines-v2")
    baseline_retest.add_argument(
        "--scenario-artifact",
        type=Path,
        default=Path("docs/evals/EVAL-G02-046/artifacts/phases/scenario-matrix/summary.json"),
    )
    baseline_retest.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".audit/g03-readiness/baseline-v2"),
    )
    baseline_retest.add_argument("--skip-live", action="store_true")

    baseline_retest_v3 = subparsers.add_parser("retest-baselines-v3")
    baseline_retest_v3.add_argument("--output-dir", type=Path, required=True)
    baseline_retest_v3.add_argument("--skip-live", action="store_true")
    baseline_retest_v3.add_argument("--resume", action="store_true")
    baseline_retest_v3.add_argument("--repetitions", type=int, choices=(3, 5))
    baseline_retest_v3.add_argument(
        "--inherit-passing-trials-from",
        type=Path,
        help=(
            "preflight only: seed this run with the passing scenario records of an earlier "
            "run so an attributable infrastructure failure does not force re-measuring "
            "cases that already passed. Each record is reused only if its recomputed "
            "semantic cache key still matches; the inheritance is recorded in the manifest."
        ),
    )
    baseline_retest_v3.add_argument(
        "--continue-on-case-failure",
        action="store_true",
        help=(
            "diagnostic scan only: replay every scenario instead of aborting on the "
            "first failure. Products are diagnostic_only and never gate evidence."
        ),
    )

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
    probe_host.add_argument("--output", type=Path, required=True)
    probe_host.add_argument("--config-root", type=Path)
    probe_host.add_argument("--sops", type=Path)
    probe_host.add_argument("--probe-script", type=Path)

    rotate_endpoint = subparsers.add_parser("rotate-server-endpoint")
    rotate_endpoint.add_argument("--handoff", type=Path, required=True)
    rotate_endpoint.add_argument("--reason", required=True)
    rotate_endpoint.add_argument("--config-root", type=Path)
    rotate_endpoint.add_argument("--sops", type=Path)
    rotate_endpoint.add_argument("--age-keygen", type=Path)

    accept_credentials = subparsers.add_parser("accept-existing-credentials")
    accept_credentials.add_argument(
        "--operator-confirmed-long-lived", action="store_true", required=True
    )
    accept_credentials.add_argument("--config-root", type=Path)
    accept_credentials.add_argument("--sops", type=Path)

    subparsers.add_parser("capture-infra-baseline")
    subparsers.add_parser("install-k3s-core")
    subparsers.add_parser("install-gvisor-runtime")
    subparsers.add_parser("install-nvidia-container-toolkit")
    subparsers.add_parser("install-nvidia-runtime")
    subparsers.add_parser("install-kata-runtime")
    subparsers.add_parser("prepare-offline-images")
    subparsers.add_parser("deploy-g02-lab")
    subparsers.add_parser("runtime-smokes")
    subparsers.add_parser("network-matrix")
    subparsers.add_parser("audit-runtime-coexistence")
    subparsers.add_parser("harden-runtime-listeners")
    subparsers.add_parser("recover-cluster-dns")
    inspect_infra = subparsers.add_parser("inspect-infra")
    inspect_infra.add_argument("--unprivileged", action="store_true")
    resolve_image = subparsers.add_parser("resolve-public-image")
    resolve_image.add_argument("--image", required=True)
    deploy_services = subparsers.add_parser("deploy-platform")
    deploy_services.add_argument("--chart", type=Path)
    deploy_services.add_argument("--values", type=Path)
    inspect_services = subparsers.add_parser("inspect-platform")
    inspect_services.add_argument("--stability-seconds", type=int, default=0)
    subparsers.add_parser("deploy-runtime-schema")
    subparsers.add_parser("inspect-runtime-schema")
    subparsers.add_parser("deploy-control-api")
    subparsers.add_parser("inspect-control-api")
    subparsers.add_parser("diagnose-control-api")
    subparsers.add_parser("provision-keycloak-realm")
    subparsers.add_parser("inspect-keycloak-realm")
    subparsers.add_parser("smoke-control-api")
    subparsers.add_parser("smoke-keycloak-outage")
    subparsers.add_parser("deploy-trace-service")
    subparsers.add_parser("inspect-trace-service")
    subparsers.add_parser("diagnose-trace-service")
    subparsers.add_parser("smoke-trace-service")
    subparsers.add_parser("deploy-model-gateway")
    subparsers.add_parser("inspect-model-gateway")
    subparsers.add_parser("smoke-model-gateway")
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
        elif args.command == "verify-docs":
            verify_docs(root)
            message = "documentation checks passed"
        elif args.command == "validate":
            loaded = validate_repository_schemas(root)
            message = f"validated {len(loaded)} governed assets"
        elif args.command == "retest-baselines-v2":
            scenario_path = (
                args.scenario_artifact
                if args.scenario_artifact.is_absolute()
                else root / args.scenario_artifact
            )
            output_dir = (
                args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
            )
            frozen_scenarios = load_data(scenario_path)
            provenance = producer_provenance(
                root,
                [
                    root / "src/faultwitness_dev/g02_baselines.py",
                    root / "src/faultwitness_dev/g02_lab.py",
                    root / "config/g02/baselines.yaml",
                    root / "config/g02/lab.yaml",
                ],
            )
            state = load_data(root / "PROJECT_STATE.yaml")
            sut_producer_sha = str(state["latest_release"]["producer_commit"])
            gate_report = root / "docs/gates/G02/REPORT.md"
            historical_report_digest = hashlib.sha256(gate_report.read_bytes()).hexdigest()
            corrected_scenarios = replay_resource_scenarios(
                root,
                provenance.producer_sha,
                frozen_scenarios,
                TrialJournal(output_dir / "journals/resource-scenarios"),
                sut_producer_sha=sut_producer_sha,
            )
            artifact_digests = {
                "corrected_scenarios.json": write_json_artifact(
                    output_dir / "corrected-scenarios.json",
                    corrected_scenarios,
                )
            }
            dataset_digest = metric_v2_dataset_digest(corrected_scenarios)
            deterministic = run_gate_deterministic_matrix(
                provenance.producer_sha,
                corrected_scenarios,
                metric_version=METRIC_VERSION,
            )
            artifact_digests["deterministic.json"] = write_json_artifact(
                output_dir / "deterministic.json",
                deterministic,
            )
            if args.skip_live:
                summary = {
                    "status": "deterministic_only",
                    "non_gate_evidence": True,
                    "metric_version": METRIC_VERSION,
                    "producer_sha": provenance.producer_sha,
                    "source_digest": provenance.source_digest,
                    "dirty_worktree": provenance.dirty,
                    "sut_producer_sha": sut_producer_sha,
                    "dataset_digest": dataset_digest,
                    "artifact_digests": artifact_digests,
                    "historical_g02_report_sha256": historical_report_digest,
                }
            else:
                live = run_gate_live_matrix(
                    root,
                    provenance.producer_sha,
                    dataset_digest,
                    corrected_scenarios,
                    output_dir / "journals/live-baselines",
                    metric_version=METRIC_VERSION,
                )
                artifact_digests["live.json"] = write_json_artifact(
                    output_dir / "live.json",
                    live,
                )
                if live["status"] != "pass":
                    raise GovernanceError(
                        "metric v2 live baseline has resumable infrastructure failures"
                    )
                aggregate = aggregate_gate_baselines(
                    corrected_scenarios,
                    deterministic,
                    live,
                    dataset_digest,
                    metric_version=METRIC_VERSION,
                )
                artifact_digests["aggregate.json"] = write_json_artifact(
                    output_dir / "aggregate.json",
                    aggregate,
                )
                summary = {
                    "status": "pass",
                    "non_gate_evidence": True,
                    "purpose": "G03 readiness baseline correction; not G02 Gate evidence",
                    "metric_version": METRIC_VERSION,
                    "producer_sha": provenance.producer_sha,
                    "source_digest": provenance.source_digest,
                    "dirty_worktree": provenance.dirty,
                    "sut_producer_sha": sut_producer_sha,
                    "dataset_digest": dataset_digest,
                    "best_baseline": aggregate["best_baseline"],
                    "g03_comparison": aggregate["g03_comparison"],
                    "artifact_digests": artifact_digests,
                    "historical_g02_report_sha256": historical_report_digest,
                }
            if hashlib.sha256(gate_report.read_bytes()).hexdigest() != historical_report_digest:
                raise GovernanceError("baseline retest modified the immutable G02 report")
            write_json_artifact(output_dir / "summary.json", summary)
            message = (
                f"recorded metric v2 baseline readiness in {output_dir} "
                f"with dataset digest {dataset_digest}"
            )
        elif args.command == "retest-baselines-v3":
            output_dir = (
                args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
            )
            summary = run_retest_baselines_v3(
                root,
                output_dir,
                skip_live=bool(args.skip_live),
                resume=bool(args.resume),
                repetitions=args.repetitions,
                continue_on_case_failure=bool(args.continue_on_case_failure),
                inherit_from=args.inherit_passing_trials_from,
            )
            message = (
                f"recorded metric v3 baseline readiness in {output_dir} "
                f"with execution {summary['execution_status']} and "
                f"readiness {summary['readiness_status']}"
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
                producer_provenance(root).producer_sha,
                args.output,
            )
            message = (
                "captured two matching sanitized capability probes with normalized digest "
                f"{report['normalized_sha256']}"
            )
        elif args.command == "rotate-server-endpoint":
            paths = (
                BootstrapPaths.under(args.config_root)
                if args.config_root
                else BootstrapPaths.defaults()
            )
            if not args.handoff.is_file():
                raise GovernanceError("endpoint handoff file is missing")
            endpoints = parse_endpoint_handoff(args.handoff.read_text(encoding="utf-8"))
            preferred = endpoints[0]
            metadata = rotate_server_endpoint(
                paths,
                args.sops or default_sops_executable(),
                args.age_keygen or default_age_keygen_executable(),
                host=preferred.host,
                port=preferred.port,
                username=preferred.username,
                password=preferred.password,
                reason=args.reason,
            )
            alternates = ", ".join(item.label for item in endpoints[1:]) or "none"
            message = (
                f"re-pointed the secret store at the {preferred.label} endpoint and cleared the "
                f"host pin, dedicated-key, and capability-reprobe evidence for re-verification "
                f"(rotations={len(metadata['server_endpoint_rotations'])}, "
                f"alternate endpoints available: {alternates})"
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
        elif args.command == "capture-infra-baseline":
            summary = capture_preinstall_baseline(root)
            message = (
                "captured private preinstall baseline for "
                f"{summary['container_count']} Docker containers with digest "
                f"{summary['baseline_sha256']}"
            )
        elif args.command == "install-k3s-core":
            summary = install_k3s_core(root)
            message = (
                "installed pinned K3s core while preserving "
                f"{summary['container_count']} Docker containers with zero regression"
            )
        elif args.command == "install-gvisor-runtime":
            summary = install_gvisor_runtime(root)
            message = f"installed gVisor {summary['gvisor_version']} and registered " + ", ".join(
                summary["runtime_classes"]
            )
        elif args.command == "install-nvidia-container-toolkit":
            summary = install_nvidia_container_toolkit(root)
            message = (
                f"installed NVIDIA container toolkit {summary['toolkit_version']} and "
                f"registered the containerd {summary['containerd_handler']} handler"
            )
        elif args.command == "install-nvidia-runtime":
            summary = install_nvidia_runtime(root)
            message = (
                f"installed NVIDIA device plugin {summary['device_plugin_version']} "
                "with at least one allocatable GPU"
            )
        elif args.command == "install-kata-runtime":
            summary = install_kata_runtime(root)
            message = (
                f"installed Kata {summary['kata_version']} and registered "
                f"RuntimeClass {summary['runtime_class']}"
            )
        elif args.command == "prepare-offline-images":
            summary = prepare_offline_base_images(root)
            message = "imported pinned offline images: " + ", ".join(summary["images"])
        elif args.command == "deploy-g02-lab":
            summary = deploy_g02_lab(root)
            message = (
                f"deployed the G02 SUT into namespace {summary['namespace']} with "
                f"{len(summary['ready_deployments'])} ready workloads"
            )
        elif args.command == "runtime-smokes":
            summary = run_runtime_smokes(root)
            message = "passed real workload smokes for " + ", ".join(summary["runtimes"])
        elif args.command == "network-matrix":
            summary = run_network_matrix(root)
            message = f"passed all {len(summary['passed_cases'])} NetworkPolicy cases"
        elif args.command == "audit-runtime-coexistence":
            summary = audit_runtime_coexistence(root)
            message = (
                "preserved Docker baseline with zero regression and "
                f"{summary['new_nonpublic_listener_count']} non-public listeners"
            )
        elif args.command == "harden-runtime-listeners":
            summary = harden_runtime_listeners(root)
            message = (
                f"selected single-node Flannel {summary['flannel_backend']} and removed "
                "the wildcard VXLAN listener"
            )
        elif args.command == "recover-cluster-dns":
            summary = recover_cluster_dns(root)
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
                chart=args.chart,
                values=args.values,
            )
            message = (
                f"deployed {summary['release']} in {summary['namespace']} from producer "
                f"{summary['producer_sha']} with bundle digest "
                f"{summary['deployment_bundle_sha256']}"
            )
        elif args.command == "inspect-platform":
            summary = inspect_platform_readiness(
                root,
                stability_seconds=args.stability_seconds,
            )
            message = (
                f"observed {summary['workload_count']} sanitized Ready workloads for "
                f"{summary['stability_seconds']} seconds using observed workload images"
            )
        elif args.command == "deploy-runtime-schema":
            summary = deploy_runtime_schema(root)
            message = (
                f"deployed runtime schema from {summary['producer_sha']} with migration digest "
                f"{summary['migration_sha256']}"
            )
        elif args.command == "inspect-runtime-schema":
            summary = inspect_runtime_schema()
            message = (
                f"observed runtime migrations {','.join(summary['migrations'])} with "
                f"{summary['table_count']} owner-isolated tables"
            )
        elif args.command == "deploy-control-api":
            summary = deploy_control_api(root)
            message = (
                f"deployed private Control API from {summary['producer_sha']} with bundle "
                f"digest {summary['bundle_sha256']}"
            )
        elif args.command == "inspect-control-api":
            summary = inspect_control_api()
            message = (
                f"observed Control API {summary['ready']}/{summary['available']} Ready as "
                f"{summary['service_type']} from observed image {summary['image']}"
            )
        elif args.command == "diagnose-control-api":
            message = diagnose_control_api().strip()
        elif args.command == "provision-keycloak-realm":
            summary = provision_keycloak_realm(root)
            message = (
                f"provisioned Keycloak realm for {summary['tenant_count']} synthetic tenants, "
                f"{summary['role_count']} roles, and {summary['user_count']} users on "
                f"producer {summary['producer_sha']}"
            )
        elif args.command == "inspect-keycloak-realm":
            summary = inspect_keycloak_realm()
            message = (
                f"observed Keycloak realm with {summary['tenant_count']} tenants, "
                f"{summary['role_count']} roles, and {summary['user_count']} users on "
                f"source {summary['source_digest']}"
            )
        elif args.command == "smoke-control-api":
            summary = run_control_api_smoke()
            message = (
                f"passed live OIDC Control API smoke on observed image {summary['image']} with "
                "create/read/SSE success and cross-tenant/injection/false-approval denial"
            )
        elif args.command == "smoke-keycloak-outage":
            summary = run_keycloak_outage_smoke()
            message = (
                f"passed cold-JWKS Keycloak outage smoke on observed image {summary['image']} "
                "with fail-closed 401 before state mutation"
            )
        elif args.command == "deploy-trace-service":
            summary = deploy_trace_service(root)
            message = (
                f"deployed private trace service from {summary['producer_sha']} with bundle "
                f"digest {summary['bundle_sha256']}"
            )
        elif args.command == "inspect-trace-service":
            summary = inspect_trace_service()
            message = (
                f"observed trace service {summary['ready']}/{summary['available']} Ready as "
                f"{summary['service_type']} from observed image {summary['image']}"
            )
        elif args.command == "diagnose-trace-service":
            message = diagnose_trace_service().strip()
        elif args.command == "smoke-trace-service":
            summary = run_trace_service_smoke()
            message = (
                f"passed sanitized LangSmith/OTLP/archive trace smoke on "
                f"{summary['image']} with zero pending delivery"
            )
        elif args.command == "deploy-model-gateway":
            summary = deploy_model_gateway(root)
            message = (
                f"deployed private Model Gateway {summary['image']} with bundle "
                f"{summary['bundle_sha256']}"
            )
        elif args.command == "inspect-model-gateway":
            summary = inspect_model_gateway()
            message = (
                f"observed Model Gateway {summary['ready']}/1 Ready as {summary['service_type']}"
            )
        elif args.command == "smoke-model-gateway":
            summary = run_model_gateway_smoke()
            message = (
                f"passed authenticated Model Gateway smoke for {summary['family']} "
                f"on observed image {summary['image']}"
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
    except (
        ContractCompilationError,
        GovernanceError,
        LiveConfigurationError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"FAIL {args.command}: {error}")
        return 1
