from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from faultwitness_dev.cli import parser
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_lab import (
    ADAPTERS,
    FAMILIES,
    MemoryFlagClient,
    OracleState,
    base_flag_document,
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
    assert "candidate_sha=" + "1" * 40 in script
    assert "base64.b64decode" in script
    malformed_proxy = (
        "@sha256:a72cd48ad9ef7fda7607813c57383d1ca6154d860916473976942d3ac24e473c-proxy"
    )
    assert malformed_proxy not in script
    transform = script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    compile(transform, "g02-manifest-transform", "exec")


def test_lab_start_cli_is_explicitly_private_server_scoped() -> None:
    args = parser().parse_args(["lab-g02", "start", "--profile", "private-server"])
    assert args.command == "lab-g02"
    assert args.lab_action == "start"
