from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import faultwitness_dev.g02_lab as g02_lab
from faultwitness_dev.cli import parser
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_lab import (
    ADAPTERS,
    FAMILIES,
    TRACE_QUERY_SERVICES,
    LiveScenarioObserver,
    MemoryFlagClient,
    OracleState,
    base_flag_document,
    build_offline_staging_inventory,
    containerd_normalized_reference,
    containerd_registry_aliases,
    fault_state,
    image_set_digest,
    load_gate_probe_images,
    load_lab_config,
    offline_staging_inventory,
    render_k3s_bootstrap_script,
    run_gate_scenario_matrix,
    run_scenario,
    seed_catalog,
    select_containerd_import_source,
    validate_lab_bootstrap,
    validate_seed_catalog,
)
from faultwitness_dev.schemas import load_data

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "a" * 64


def _observer() -> Any:
    memory_sample = iter((2.0, 3.0))

    def observe(phase: str, fault_class: str) -> Mapping[str, Any]:
        if phase == "control":
            return {"state": OracleState.HEALTHY}
        if phase == "recovery":
            return {"ready": True, "journey_healthy": True, "signal_not_worsening": True}
        if fault_class == "emailMemoryLeak":
            return {"working_set": next(memory_sample)}
        return {
            "productCatalogFailure": {"journey_failed": True, "correlated_error": True},
            "adHighCpu": {
                "cpu_rate": 2.0,
                "baseline_cpu_max": 1.0,
                "correlated_span": True,
            },
            "paymentFailure": {"checkout_failed": True, "payment_error": True},
            "paymentUnreachable": {"checkout_failed": True, "connection_error": True},
            "kafkaQueueProblems": {
                "consumer_lag": 2.0,
                "baseline_lag": 1.0,
                "kafka_error": True,
            },
        }[fault_class]

    return observe


def test_seed_catalog_is_exact_complete_and_opaque() -> None:
    seeds = seed_catalog(DIGEST)
    validate_seed_catalog(seeds, DIGEST)
    assert len(seeds) == 32
    assert {seed["family"] for seed in seeds} == set(FAMILIES)
    assert {seed["fault_action"]["class"] for seed in seeds} == set(ADAPTERS)
    assert all(seed["fault_action"]["class"] not in seed["scenario_id"] for seed in seeds)


def test_unknown_action_fixture_is_rejected() -> None:
    scenario = load_data(ROOT / "tests/fixtures/g02/scenario_unknown_action.yaml")
    with pytest.raises(GovernanceError, match="unknown fault action"):
        run_scenario(scenario, MemoryFlagClient(base_flag_document()), _observer())


def test_six_fault_adapters_reach_fault_and_exact_recovery() -> None:
    by_fault = {seed["fault_action"]["class"]: seed for seed in seed_catalog(DIGEST)}
    for fault_class in ADAPTERS:
        client = MemoryFlagClient(base_flag_document())
        result = run_scenario(by_fault[fault_class], client, _observer())
        assert result["state_sequence"] == ["HEALTHY", "FAULT_ACTIVE", "HEALTHY"]
        assert result["original_digest"] == result["restored_digest"]


def test_prior_recovery_proves_next_precondition_without_control_resample() -> None:
    scenario = next(
        seed
        for seed in seed_catalog(DIGEST)
        if seed["fault_action"]["class"] == "productCatalogFailure"
    )
    delegate = _observer()

    def no_control_observer(phase: str, fault_class: str) -> Mapping[str, Any]:
        if phase == "control":
            raise AssertionError("prior recovery must replace the redundant control sample")
        return delegate(phase, fault_class)

    healthy_recovery = [
        {"ready": True, "journey_healthy": True, "signal_not_worsening": True},
        {"ready": True, "journey_healthy": True, "signal_not_worsening": True},
    ]
    result = run_scenario(
        scenario,
        MemoryFlagClient(base_flag_document()),
        no_control_observer,
        precondition_recovery=healthy_recovery,
    )
    assert result["precondition_source"] == "prior-scenario-recovery"
    assert result["state_sequence"] == ["HEALTHY", "FAULT_ACTIVE", "HEALTHY"]


def test_unhealthy_prior_recovery_cannot_bypass_precondition() -> None:
    scenario = next(
        seed
        for seed in seed_catalog(DIGEST)
        if seed["fault_action"]["class"] == "productCatalogFailure"
    )
    unhealthy_recovery = [
        {"ready": True, "journey_healthy": False, "signal_not_worsening": True},
        {"ready": True, "journey_healthy": True, "signal_not_worsening": True},
    ]
    with pytest.raises(GovernanceError, match="prior scenario recovery"):
        run_scenario(
            scenario,
            MemoryFlagClient(base_flag_document()),
            _observer(),
            precondition_recovery=unhealthy_recovery,
        )


def test_false_green_oracle_fixture_is_not_fault_active() -> None:
    fixture = load_data(ROOT / "tests/fixtures/g02/oracle_false_green.yaml")
    assert fault_state(fixture["fault_class"], fixture["observations"]) is OracleState.HEALTHY


def test_kafka_observer_uses_exported_poll_lag_and_exact_fault_log() -> None:
    observer = LiveScenarioObserver("1" * 40, "kafkaQueueProblems")
    observer.baseline_lag = 0.0
    sample = {
        "descriptions": [],
        "consumer_lag": 12.0,
        "kafka_log_error": False,
        "kafka_fault_log": True,
        "error_spans": 0,
    }
    observation = observer._active_observation(sample)
    assert observation["consumer_lag"] > observation["baseline_lag"]
    assert observation["kafka_error"] is True


def test_payment_unreachable_trace_query_uses_checkout_caller() -> None:
    assert TRACE_QUERY_SERVICES["paymentUnreachable"] == "checkout"
    assert TRACE_QUERY_SERVICES["paymentFailure"] == "payment"


def test_payment_unreachable_observer_requires_correlated_caller_signals() -> None:
    observer = LiveScenarioObserver("1" * 40, "paymentUnreachable")
    observation = observer._active_observation(
        {
            "descriptions": [],
            "error_spans": 2,
            "checkout_error_spans": 1,
            "payment_connection_errors": 1,
        }
    )
    assert observation["checkout_failed"] is True
    assert observation["connection_error"] is True


def test_payment_unreachable_observer_rejects_uncorrelated_checkout_error() -> None:
    observer = LiveScenarioObserver("1" * 40, "paymentUnreachable")
    observation = observer._active_observation(
        {
            "descriptions": ["unavailable"],
            "error_spans": 1,
            "checkout_error_spans": 1,
            "payment_connection_errors": 0,
        }
    )
    assert observation["checkout_failed"] is True
    assert observation["connection_error"] is False
    assert fault_state("paymentUnreachable", [observation, observation]) is OracleState.HEALTHY


def test_payment_unreachable_change_preserves_payment_failure_branch() -> None:
    observer = LiveScenarioObserver("1" * 40, "paymentFailure")
    observation = observer._active_observation(
        {"descriptions": ["Payment rejected"], "error_spans": 1}
    )
    assert observation["checkout_failed"] is True
    assert observation["payment_error"] is True


def test_memory_observer_uses_working_set_signal() -> None:
    observer = LiveScenarioObserver("1" * 40, "emailMemoryLeak")
    observation = observer._active_observation(
        {"working_set": 42.0, "descriptions": [], "trace_count": 0}
    )
    assert observation["working_set"] == 42.0


def test_restore_noop_fixture_blocks_and_quarantines() -> None:
    fixture = load_data(ROOT / "tests/fixtures/g02/fault_restore_noop.yaml")
    scenario = next(
        seed
        for seed in seed_catalog(DIGEST)
        if seed["fault_action"]["class"] == fixture["fault_class"]
    )
    client = MemoryFlagClient(base_flag_document(), ignore_restore=fixture["ignore_restore"])
    with pytest.raises(GovernanceError, match="cleanup blocked and quarantined"):
        run_scenario(scenario, client, _observer())


def test_lab_bootstrap_rejects_unpinned_image_fixture() -> None:
    fixture = load_data(ROOT / "tests/fixtures/g02/lab_unpinned_image.yaml")
    with pytest.raises(GovernanceError, match="not digest-pinned"):
        validate_lab_bootstrap(fixture)


def test_gate_scenario_runner_executes_and_reuses_exact_32_trials(tmp_path: Path) -> None:
    from faultwitness_dev.g02_eval import TrialJournal

    journal = TrialJournal(tmp_path)

    def client_factory(_candidate_sha: str) -> MemoryFlagClient:
        return MemoryFlagClient(base_flag_document())

    def observer_factory(_candidate_sha: str, _fault_class: str) -> Any:
        return g02_lab.scripted_sequence_observer()

    first = run_gate_scenario_matrix(
        ROOT,
        "1" * 40,
        journal,
        client_factory=client_factory,
        observer_factory=observer_factory,
    )
    second = run_gate_scenario_matrix(
        ROOT,
        "1" * 40,
        journal,
        client_factory=client_factory,
        observer_factory=observer_factory,
    )
    assert first["status"] == "pass"
    assert first["scenario_count"] == 32
    assert len(first["observation_packets"]) == 32
    assert [item["trial_id"] for item in second["trials"]] == [
        item["trial_id"] for item in first["trials"]
    ]
    assert all(item["attempt"] == 2 for item in second["trials"])


def test_image_set_digest_is_order_independent() -> None:
    config = {
        "images": [
            {"name": "b", "platform": "linux/amd64", "reference": f"example/b@sha256:{'b' * 64}"},
            {"name": "a", "platform": "linux/amd64", "reference": f"example/a@sha256:{'a' * 64}"},
        ]
    }
    reversed_config = {"images": list(reversed(config["images"]))}
    assert image_set_digest(config) == image_set_digest(reversed_config)


def test_containerd_normalization_preserves_repository_and_digest() -> None:
    digest = "a" * 64
    source = f"index.docker.io/library/busybox@sha256:{digest}"
    assert containerd_normalized_reference(source) == (f"docker.io/library/busybox@sha256:{digest}")
    quay = f"quay.io/example/image@sha256:{digest}"
    assert containerd_normalized_reference(quay) == quay


def test_offline_staging_inventory_contains_exact_probe_images_without_sut_digest_drift() -> None:
    config = load_lab_config(ROOT)
    probes = load_gate_probe_images(ROOT)
    inventory = offline_staging_inventory(ROOT, config)
    assert image_set_digest(config) == (
        "3df502956e9c4ab2311501a9e867a40bdc1afae79ebcf3de284a95611e52610e"
    )
    assert {key: value for key, value in inventory.items() if key.startswith("probe-")} == {
        "probe-busybox": probes["busybox"],
        "probe-minio-mc": probes["minio_mc"],
    }
    assert inventory["busybox"] != inventory["probe-busybox"]


def test_offline_staging_inventory_deduplicates_normalized_exact_reference() -> None:
    digest = "a" * 64
    config = {
        "images": [
            {
                "name": "existing",
                "platform": "linux/amd64",
                "reference": f"index.docker.io/example/image@sha256:{digest}",
            }
        ]
    }
    inventory = build_offline_staging_inventory(
        config,
        {
            "busybox": f"docker.io/example/image@sha256:{digest}",
            "minio_mc": f"docker.io/example/other@sha256:{'b' * 64}",
        },
    )
    assert set(inventory) == {"existing", "probe-minio-mc"}


def test_offline_staging_inventory_rejects_repository_digest_drift() -> None:
    config = {
        "images": [
            {
                "name": "existing",
                "platform": "linux/amd64",
                "reference": f"index.docker.io/example/image@sha256:{'a' * 64}",
            }
        ]
    }
    with pytest.raises(GovernanceError, match="digest drift"):
        build_offline_staging_inventory(
            config,
            {
                "busybox": f"docker.io/example/image@sha256:{'b' * 64}",
                "minio_mc": f"docker.io/example/other@sha256:{'c' * 64}",
            },
        )


def test_containerd_import_source_prefers_requested_exact_digest() -> None:
    digest = "sha256:" + "a" * 64
    requested = f"docker.io/example/image@{digest}"
    alias = f"index.docker.io/example/image@{digest}"
    assert select_containerd_import_source(
        requested, {requested: digest, alias: digest}
    ) == requested


def test_containerd_import_source_accepts_only_exact_digest_alias() -> None:
    digest = "sha256:" + "a" * 64
    requested = f"docker.io/example/image@{digest}"
    alias = f"index.docker.io/example/image@{digest}"
    assert containerd_registry_aliases(requested) == (requested, alias)
    assert select_containerd_import_source(requested, {alias: digest}) == alias


def test_containerd_import_source_rejects_wrong_digest_alias() -> None:
    digest = "sha256:" + "a" * 64
    requested = f"docker.io/example/image@{digest}"
    alias = f"index.docker.io/example/image@{digest}"
    with pytest.raises(GovernanceError, match="exact repository-and-digest"):
        select_containerd_import_source(requested, {alias: "sha256:" + "b" * 64})


def test_clean_clone_runner_is_pinned_and_candidate_bound() -> None:
    config = load_lab_config(ROOT)
    summary = validate_lab_bootstrap(config)
    script = render_k3s_bootstrap_script(config, "1" * 40)
    assert summary["image_count"] == 30
    assert summary["profile"] == "k3s"
    assert all(not image["reference"].startswith("docker.io/") for image in config["images"])
    assert "sha256sum -c" in script
    assert "namespace: fw-sut" in script
    assert "kubectl apply -n fw-sut" in script
    assert "readyReplicas" in script
    assert "grep -q '\"emailMemoryLeak\"'" in script
    assert "rollout restart deployment/flagd" in script
    assert "sleep 5" in script
    assert "rollout status" not in script
    assert "--timeout" not in script
    assert "candidate_sha=" + "1" * 40 in script
    assert "base64.b64decode" in script
    malformed_proxy = (
        "@sha256:a72cd48ad9ef7fda7607813c57383d1ca6154d860916473976942d3ac24e473c-proxy"
    )
    assert malformed_proxy not in script
    transform = script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    compile(transform, "g02-manifest-transform", "exec")
    readiness_checks = script.split("python3 -c '\n")[1:]
    assert len(readiness_checks) == 2
    for index, check in enumerate(readiness_checks):
        compile(check.split("\n')", 1)[0], f"g02-readiness-{index}", "exec")


def test_lab_start_cli_is_explicitly_private_server_scoped() -> None:
    args = parser().parse_args(["lab-g02", "start", "--profile", "private-server"])
    assert args.command == "lab-g02"
    assert args.lab_action == "start"


def test_lab_checkout_accepts_only_exact_candidate_or_validated_evidence_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = "1" * 40
    evidence_head = "2" * 40

    def descendant_run(arguments: list[str], **_kwargs: Any) -> SimpleNamespace:
        if arguments[1:3] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=evidence_head, returncode=0)
        assert arguments[1:3] == ["merge-base", "--is-ancestor"]
        assert arguments[3:] == [candidate, evidence_head]
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(g02_lab.subprocess, "run", descendant_run)
    assert g02_lab._validate_lab_checkout(tmp_path, candidate, evidence_head) == evidence_head

    def non_descendant_run(arguments: list[str], **_kwargs: Any) -> SimpleNamespace:
        if arguments[1:3] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=evidence_head, returncode=0)
        return SimpleNamespace(stdout="", returncode=1)

    monkeypatch.setattr(g02_lab.subprocess, "run", non_descendant_run)
    with pytest.raises(GovernanceError, match="not a candidate descendant"):
        g02_lab._validate_lab_checkout(tmp_path, candidate, evidence_head)

    monkeypatch.setattr(
        g02_lab.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="3" * 40, returncode=0),
    )
    with pytest.raises(GovernanceError, match="validated evidence head"):
        g02_lab._validate_lab_checkout(tmp_path, candidate, evidence_head)


def test_live_inject_and_restore_are_exact_and_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = base_flag_document()

    class FakeRemoteFlagClient:
        current = document

        def __init__(self, candidate_sha: str) -> None:
            assert candidate_sha == "1" * 40

        def read(self) -> dict[str, Any]:
            return self.current

        def write(self, value: Mapping[str, Any]) -> None:
            FakeRemoteFlagClient.current = dict(value)

    monkeypatch.setattr(g02_lab, "RemoteFlagClient", FakeRemoteFlagClient)
    monkeypatch.setattr(g02_lab, "_operation_root", lambda: tmp_path)
    injected = g02_lab.inject_live_fault("1" * 40, "productCatalogFailure")
    assert FakeRemoteFlagClient.current["flags"]["productCatalogFailure"]["defaultVariant"] == "on"
    restored = g02_lab.restore_live_fault("1" * 40, injected["operation_id"])
    assert restored["restored_digest"] == injected["original_digest"]
    assert FakeRemoteFlagClient.current == document


def test_lab_inject_and_restore_cli_are_explicit() -> None:
    inject = parser().parse_args(["lab-g02", "inject", "--fault-class", "productCatalogFailure"])
    restore = parser().parse_args(
        ["lab-g02", "restore", "--operation-id", "op-20260723T000000Z-aaaaaaaaaaaa"]
    )
    assert inject.lab_action == "inject"
    assert restore.lab_action == "restore"
