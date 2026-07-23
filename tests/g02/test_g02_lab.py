from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import faultwitness_dev.g02_lab as g02_lab
from faultwitness_dev.cli import parser
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_lab import (
    ADAPTERS,
    FAMILIES,
    MemoryFlagClient,
    OracleState,
    base_flag_document,
    containerd_normalized_reference,
    fault_state,
    image_set_digest,
    load_lab_config,
    render_k3s_bootstrap_script,
    run_scenario,
    seed_catalog,
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


def test_false_green_oracle_fixture_is_not_fault_active() -> None:
    fixture = load_data(ROOT / "tests/fixtures/g02/oracle_false_green.yaml")
    assert fault_state(fixture["fault_class"], fixture["observations"]) is OracleState.HEALTHY


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
    assert containerd_normalized_reference(source) == (
        f"docker.io/library/busybox@sha256:{digest}"
    )
    quay = f"quay.io/example/image@sha256:{digest}"
    assert containerd_normalized_reference(quay) == quay


def test_clean_clone_runner_is_pinned_and_candidate_bound() -> None:
    config = load_lab_config(ROOT)
    summary = validate_lab_bootstrap(config)
    script = render_k3s_bootstrap_script(config, "1" * 40)
    assert summary["image_count"] == 30
    assert summary["profile"] == "k3s"
    assert all(
        not image["reference"].startswith("docker.io/") for image in config["images"]
    )
    assert "sha256sum -c" in script
    assert "namespace: fw-sut" in script
    assert "kubectl apply -n fw-sut" in script
    assert "readyReplicas" in script
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
    assert FakeRemoteFlagClient.current["flags"]["productCatalogFailure"][
        "defaultVariant"
    ] == "on"
    restored = g02_lab.restore_live_fault("1" * 40, injected["operation_id"])
    assert restored["restored_digest"] == injected["original_digest"]
    assert FakeRemoteFlagClient.current == document


def test_lab_inject_and_restore_cli_are_explicit() -> None:
    inject = parser().parse_args(
        ["lab-g02", "inject", "--fault-class", "productCatalogFailure"]
    )
    restore = parser().parse_args(
        ["lab-g02", "restore", "--operation-id", "op-20260723T000000Z-aaaaaaaaaaaa"]
    )
    assert inject.lab_action == "inject"
    assert restore.lab_action == "restore"
