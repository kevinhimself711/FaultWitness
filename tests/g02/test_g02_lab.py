from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import faultwitness_dev.g02_lab as g02_lab
from faultwitness_dev.errors import GovernanceError, InfrastructureFailure
from faultwitness_dev.g02_lab import (
    ADAPTERS,
    FAMILIES,
    TRACE_QUERY_SERVICES,
    V3_FAULT_SAMPLE_INTERVAL_SECONDS,
    V3_READINESS_COLLECTOR_CHECKPOINT,
    V3_READINESS_COLLECTOR_SOURCE_SHA256,
    V3_READINESS_OBSERVER_SOURCE_SHA256,
    LiveReadinessObserverV3,
    LiveScenarioObserver,
    MemoryFlagClient,
    OracleState,
    base_flag_document,
    build_offline_staging_inventory,
    containerd_normalized_reference,
    containerd_registry_aliases,
    fault_state,
    image_set_digest,
    live_readiness_observer_source_digest,
    load_gate_probe_images,
    load_lab_config,
    offline_staging_inventory,
    render_k3s_bootstrap_script,
    render_live_readiness_observer_v3_script,
    replay_resource_scenarios,
    run_gate_scenario_matrix,
    run_scenario,
    seed_catalog,
    select_containerd_import_source,
    validate_lab_bootstrap,
    validate_live_readiness_collector_checkpoint,
    validate_seed_catalog,
)
from faultwitness_dev.schemas import load_data

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "a" * 64


def test_v3_collector_script_shape_is_identical_for_all_six_labels() -> None:
    since = g02_lab.datetime(2026, 7, 29, 0, 0, tzinfo=g02_lab.UTC)
    scripts = []
    for fault_class in ADAPTERS:
        observer = LiveReadinessObserverV3("a" * 40, fault_class)
        scripts.append(
            render_live_readiness_observer_v3_script(observer.producer_sha, since)
        )
    assert len(scripts) == 6
    assert len(set(scripts)) == 1
    assert "request[\"fault_class\"]" not in scripts[0]


def test_v3_collector_pins_exact_email_and_ad_pods_fail_closed() -> None:
    script = render_live_readiness_observer_v3_script(
        "a" * 40,
        g02_lab.datetime(2026, 7, 29, 0, 0, tzinfo=g02_lab.UTC),
    )
    assert 'pod=~"email-.*"' not in script
    assert 'pod=~"ad-.*"' not in script
    assert "'max(container_memory_working_set_bytes" in script
    assert "+ email_pod" in script
    assert "'sum(rate(container_cpu_usage_seconds_total" in script
    assert "+ ad_pod" in script
    assert 'current_pod("email-")' in script
    assert 'current_pod("ad-")' in script
    assert "FW_G03_COLLECTOR_POD_CARDINALITY" in script


def test_dead_series_wildcard_masks_email_oracle_but_pinned_series_does_not() -> None:
    mib = 1024 * 1024
    wildcard = [
        {
            "baseline_working_set": 54.4 * mib,
            "working_set": 54.4 * mib,
        },
        {
            "baseline_working_set": 54.4 * mib,
            "working_set": 54.4 * mib,
        },
    ]
    pinned = [
        {
            "baseline_working_set": 20 * mib,
            "working_set": 20 * mib,
        },
        {
            "baseline_working_set": 20 * mib,
            "working_set": 47 * mib,
        },
    ]
    assert fault_state("emailMemoryLeak", wildcard) == OracleState.HEALTHY
    assert fault_state("emailMemoryLeak", pinned) == OracleState.FAULT_ACTIVE


def test_v3_collector_checkpoint_is_source_bound_and_interval_is_preregistered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = validate_live_readiness_collector_checkpoint()
    assert V3_READINESS_COLLECTOR_CHECKPOINT.startswith(
        "g03-readiness-v3-label-blind-six-group-collector-"
    )
    assert contract["source_sha256"] == V3_READINESS_COLLECTOR_SOURCE_SHA256
    assert (
        contract["observer_source_sha256"]
        == V3_READINESS_OBSERVER_SOURCE_SHA256
        == live_readiness_observer_source_digest()
    )
    assert contract["fault_sample_interval_seconds"] == 65
    assert V3_FAULT_SAMPLE_INTERVAL_SECONDS == 65
    assert LiveScenarioObserver.fault_sample_interval_seconds == 30
    assert LiveScenarioObserver.retain_terminal_fault_sample is False
    assert LiveReadinessObserverV3.fault_sample_interval_seconds == 65
    assert LiveReadinessObserverV3.retain_terminal_fault_sample is True
    # AMD-0007 appendix 3: the activation deadline stays frozen at 90s while the
    # recovery observation deadline and spacing become pre-registered constants.
    assert contract["fault_activation_deadline_seconds"] == 90
    assert contract["poll_interval_seconds"] == 5
    assert contract["restimulate_each_poll"] is True
    assert contract["recovery_observation_deadline_seconds"] == 240
    assert contract["recovery_sample_interval_seconds"] == 65
    assert LiveScenarioObserver.restimulate_each_poll is False
    assert LiveReadinessObserverV3.restimulate_each_poll is True
    assert LiveScenarioObserver.recovery_deadline_seconds == 90
    assert LiveScenarioObserver.recovery_sample_interval_seconds == 30
    assert LiveReadinessObserverV3.recovery_deadline_seconds == 240
    assert LiveReadinessObserverV3.recovery_sample_interval_seconds == 65
    # AMD-0007 appendix 4: the ad baseline must be measured on a quiesced pod so a
    # previous case's burn cannot inflate it through the 2-minute rate() lookback.
    assert contract["ad_cpu_quiescent_max_cores"] == 0.25
    assert contract["ad_cpu_quiescence_deadline_seconds"] == 240
    assert LiveScenarioObserver.require_ad_cpu_quiescent_baseline is False
    assert LiveReadinessObserverV3.require_ad_cpu_quiescent_baseline is True
    # The frozen predicate thresholds are untouched by that wait.
    assert g02_lab.AD_CPU_ACTIVE_MIN_CORES == 0.5
    assert g02_lab.AD_CPU_ACTIVE_MULTIPLIER == 5.0

    monkeypatch.setattr(
        g02_lab,
        "live_readiness_collector_source_digest",
        lambda: "0" * 64,
    )
    with pytest.raises(GovernanceError, match="checkpoint digest"):
        validate_live_readiness_collector_checkpoint()


def test_v3_terminal_fault_sample_preserves_interval_and_cleanup_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveReadinessObserverV3("1" * 40, "adHighCpu")
    observer.baseline_cpu = 0.01
    sleeps: list[float] = []
    monotonic = iter((0.0, 91.0, 100.0, 191.0, 200.0))
    sample = {
        "cpu_rate": 0.01,
        "trace_count": 1,
        "descriptions": [],
        "ready": True,
        "journey_status": 200,
        "absent_series": [],
    }
    monkeypatch.setattr(
        observer,
        "_stimulate_ad_request",
        lambda: {"status": "pass", "request_count": 1, "response_status": 200},
    )
    monkeypatch.setattr(observer, "_sample", lambda _since: dict(sample))
    monkeypatch.setattr(g02_lab.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(g02_lab.time, "sleep", sleeps.append)

    first = observer("fault", "adHighCpu")
    second = observer("fault", "adHighCpu")
    recovery = observer("recovery", "adHighCpu")

    assert len(observer.fault_samples) == 2
    assert observer.fault_samples == [first, second]
    assert sleeps == [65]
    assert recovery["signal_not_worsening"] is True


def _observer() -> Any:
    memory_sample = iter((3 * 1024 * 1024, 5 * 1024 * 1024))

    def observe(phase: str, fault_class: str) -> Mapping[str, Any]:
        if phase == "control":
            return {"state": OracleState.HEALTHY}
        if phase == "recovery":
            return {"ready": True, "journey_healthy": True, "signal_not_worsening": True}
        if fault_class == "emailMemoryLeak":
            return {
                "working_set": next(memory_sample),
                "baseline_working_set": 1 * 1024 * 1024,
            }
        return {
            "productCatalogFailure": {"journey_failed": True, "correlated_error": True},
            "adHighCpu": {
                "cpu_rate": 6.0,
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


@pytest.mark.parametrize("operation", ["read", "write"])
def test_remote_flag_transport_failure_is_retryable_infrastructure(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    def fail_remote(*_args: Any, **_kwargs: Any) -> str:
        raise GovernanceError("remote_command_or_transport_failed")

    monkeypatch.setattr(g02_lab, "run_remote_script", fail_remote)
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)
    client = g02_lab.RemoteFlagClient("1" * 40)
    with pytest.raises(InfrastructureFailure, match=f"remote flag {operation}"):
        if operation == "read":
            client.read()
        else:
            client.write(base_flag_document())


def test_remote_flag_read_retries_transport_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient transport failure must not discard an already-valid scenario.

    The first flag read happens before any measurement, so failing it outright
    costs a whole case that then has to be re-measured. AMD-0003 classifies a
    transport failure as attributable infrastructure, so it is retried.
    """
    attempts = 0

    def flaky_remote(*_args: Any, **_kwargs: Any) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise GovernanceError("SOPS operation failed without emitting secret material")
        return json.dumps(base_flag_document())

    monkeypatch.setattr(g02_lab, "run_remote_script", flaky_remote)
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)
    document = g02_lab.RemoteFlagClient("1" * 40).read()
    assert attempts == 3
    assert document == base_flag_document()


def test_remote_flag_write_is_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A write may have landed before the transport error, so retrying could double-apply it."""
    attempts = 0

    def fail_remote(*_args: Any, **_kwargs: Any) -> str:
        nonlocal attempts
        attempts += 1
        raise GovernanceError("remote_command_or_transport_failed")

    monkeypatch.setattr(g02_lab, "run_remote_script", fail_remote)
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)
    with pytest.raises(InfrastructureFailure, match="remote flag write"):
        g02_lab.RemoteFlagClient("1" * 40).write(base_flag_document())
    assert attempts == 1


def test_flag_transport_retry_does_not_touch_pinned_metric_digests() -> None:
    """The retry is transport-only, so both checkpoint-pinned sources must be unchanged."""
    assert (
        g02_lab.live_readiness_collector_source_digest()
        == g02_lab.V3_READINESS_COLLECTOR_SOURCE_SHA256
    )
    assert (
        g02_lab.live_readiness_observer_source_digest()
        == g02_lab.V3_READINESS_OBSERVER_SOURCE_SHA256
    )


def test_remote_flag_client_uses_a_valid_kubectl_jsonpath() -> None:
    prelude = g02_lab.RemoteFlagClient("1" * 40)._prelude()
    assert "jsonpath='{.spec.clusterIP}'" in prelude
    assert "{{.spec.clusterIP}}" not in prelude


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


def test_kafka_stimulus_uses_observed_sut_and_exactly_one_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "kafkaQueueProblems")
    captured: dict[str, Any] = {}

    def remote(script: str, *, privileged: bool) -> str:
        captured["script"] = script
        captured["privileged"] = privileged
        return '{"cart_status":200,"checkout_count":1,"checkout_status":200,"status":"pass"}'

    monkeypatch.setattr(g02_lab, "run_remote_script", remote)
    result = observer._stimulate_kafka_fault()

    assert result["checkout_count"] == 1
    assert captured["privileged"] is True
    assert "fw-g02-candidate-binding" not in captured["script"]
    assert captured["script"].count('"/api/checkout", checkout') == 1
    assert captured["script"].count('post("/api/cart"') == 1


def test_ad_stimulus_uses_the_pinned_locust_route_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "adHighCpu")
    captured: dict[str, Any] = {}

    def remote(script: str, *, privileged: bool) -> str:
        captured["script"] = script
        captured["privileged"] = privileged
        return '{"request_count":1,"response_status":200,"status":"pass"}'

    monkeypatch.setattr(g02_lab, "run_remote_script", remote)
    result = observer._stimulate_ad_request()

    assert result == {"request_count": 1, "response_status": 200, "status": "pass"}
    assert captured["privileged"] is True
    assert captured["script"].count('"contextKeys": "binoculars"') == 1
    assert captured["script"].count("urllib.request.urlopen(endpoint)") == 1


def test_product_stimulus_uses_the_pinned_failure_product_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "productCatalogFailure")
    captured: dict[str, Any] = {}

    def remote(script: str, *, privileged: bool) -> str:
        captured["script"] = script
        captured["privileged"] = privileged
        return '{"request_count":1,"response_status":500,"status":"pass"}'

    monkeypatch.setattr(g02_lab, "run_remote_script", remote)
    result = observer._stimulate_product_fault()

    assert result == {"request_count": 1, "response_status": 500, "status": "pass"}
    assert captured["privileged"] is True
    assert captured["script"].count("/api/products/OLJCESPC7Z") == 1
    assert captured["script"].count("urllib.request.urlopen(endpoint)") == 1


def test_product_observer_stimulates_once_before_two_frozen_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "productCatalogFailure")
    stimuli: list[str] = []
    sleeps: list[float] = []
    sample = {
        "descriptions": ["Error: Product Catalog Fail Feature Flag Enabled"],
        "trace_count": 1,
    }
    monkeypatch.setattr(
        observer,
        "_stimulate_product_fault",
        lambda: stimuli.append("product")
        or {"status": "pass", "request_count": 1, "response_status": 500},
    )
    monkeypatch.setattr(observer, "_sample", lambda _since: sample)
    monkeypatch.setattr(g02_lab.time, "sleep", sleeps.append)

    first = observer("fault", "productCatalogFailure")
    second = observer("fault", "productCatalogFailure")

    assert stimuli == ["product"]
    assert sleeps == [30]
    assert first["product_stimulus"]["request_count"] == 1
    assert second["product_stimulus"]["request_count"] == 1
    assert fault_state("productCatalogFailure", [first, second]) is OracleState.FAULT_ACTIVE


def test_email_stimulus_calls_the_synchronous_service_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "emailMemoryLeak")
    captured: dict[str, Any] = {}

    def remote(script: str, *, privileged: bool) -> str:
        captured["script"] = script
        captured["privileged"] = privileged
        return '{"request_count":1,"response_status":200,"status":"pass"}'

    monkeypatch.setattr(g02_lab, "run_remote_script", remote)
    result = observer._stimulate_email_request()

    assert result == {"request_count": 1, "response_status": 200, "status": "pass"}
    assert captured["privileged"] is True
    assert captured["script"].count("/send_order_confirmation") == 1
    assert captured["script"].count("urllib.request.urlopen(request)") == 1


def test_email_runtime_reset_replaces_exactly_one_ready_pod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "emailMemoryLeak")
    captured: dict[str, Any] = {}

    def remote(script: str, *, privileged: bool) -> str:
        captured["script"] = script
        captured["privileged"] = privileged
        return json.dumps(
            {
                "status": "pass",
                "reset_count": 1,
                "old_pod_uid": "old",
                "new_pod_uid": "new",
                "new_pod_name": "email-new",
                "ready": True,
            }
        )

    monkeypatch.setattr(g02_lab, "run_remote_script", remote)
    result = observer._reset_email_runtime()

    assert result["reset_count"] == 1
    assert result["ready"] is True
    assert result["new_pod_name"] == "email-new"
    assert captured["privileged"] is True
    assert '"delete", "pod", old_name, "--wait=true"' in captured["script"]
    assert "time.sleep(2)" in captured["script"]


def test_email_control_resets_then_records_nonzero_same_pod_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "emailMemoryLeak")
    resets: list[str] = []
    monkeypatch.setattr(
        observer,
        "_reset_email_runtime",
        lambda: resets.append("reset")
        or {
            "status": "pass",
            "reset_count": 1,
            "old_pod_uid": "old",
            "new_pod_uid": "new",
            "new_pod_name": "email-new",
            "ready": True,
        },
    )
    monkeypatch.setattr(
        observer,
        "_sample",
        lambda _since: {
            "working_set": 40 * 1024 * 1024,
            "cpu_rate": 0.01,
            "consumer_lag": 0.0,
            "ready": True,
            "journey_status": 200,
        },
    )

    assert observer("control", "emailMemoryLeak") == {"state": OracleState.HEALTHY}
    assert resets == ["reset"]
    assert observer.baseline_working_set == 40 * 1024 * 1024
    assert observer.email_runtime_reset["new_pod_name"] == "email-new"


def test_ad_observer_stimulates_each_fault_sample_and_once_after_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "adHighCpu")
    observer.baseline_cpu = 0.01
    stimuli: list[str] = []
    sleeps: list[float] = []
    samples = iter(
        (
            {"cpu_rate": 1.0, "trace_count": 1, "descriptions": []},
            {"cpu_rate": 1.0, "trace_count": 1, "descriptions": []},
            {
                "cpu_rate": 0.01,
                "trace_count": 1,
                "ready": True,
                "journey_status": 200,
                "descriptions": [],
            },
            {
                "cpu_rate": 0.01,
                "trace_count": 1,
                "ready": True,
                "journey_status": 200,
                "descriptions": [],
            },
        )
    )

    def stimulate() -> dict[str, Any]:
        phase = "fault" if not stimuli else "recovery"
        stimuli.append(phase)
        return {"status": "pass", "request_count": 1, "response_status": 200}

    monkeypatch.setattr(observer, "_stimulate_ad_request", stimulate)
    monkeypatch.setattr(observer, "_sample", lambda _since: next(samples))
    monkeypatch.setattr(g02_lab.time, "sleep", sleeps.append)

    first = observer("fault", "adHighCpu")
    second = observer("fault", "adHighCpu")
    first_recovery = observer("recovery", "adHighCpu")
    second_recovery = observer("recovery", "adHighCpu")

    assert stimuli == ["fault", "recovery", "recovery"]
    assert sleeps == [30, 30]
    assert first["ad_stimulus"]["request_count"] == 1
    assert second["ad_stimulus"]["request_count"] == 1
    assert first_recovery["ad_recovery_stimulus"]["request_count"] == 1
    assert second_recovery["ad_recovery_stimulus"]["request_count"] == 1
    assert fault_state("adHighCpu", [first, second]) is OracleState.FAULT_ACTIVE


def test_payment_stimulus_accepts_fault_response_but_sends_one_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "paymentUnreachable")
    captured: dict[str, Any] = {}

    def remote(script: str, *, privileged: bool) -> str:
        captured["script"] = script
        captured["privileged"] = privileged
        return '{"cart_status":200,"checkout_count":1,"checkout_status":500,"status":"pass"}'

    monkeypatch.setattr(g02_lab, "run_remote_script", remote)
    result = observer._stimulate_payment_fault()

    assert result["checkout_count"] == 1
    assert result["checkout_status"] == 500
    assert captured["privileged"] is True
    assert "fw-g02-candidate-binding" not in captured["script"]
    assert captured["script"].count('"/api/checkout", checkout') == 1
    assert captured["script"].count('post("/api/cart"') == 1
    assert 'allow_checkout_http_error = request["allow_checkout_http_error"]' in captured["script"]


@pytest.mark.parametrize("fault_class", ["paymentFailure", "paymentUnreachable"])
def test_payment_observer_stimulates_once_before_two_frozen_samples(
    fault_class: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer = LiveScenarioObserver("1" * 40, fault_class)
    stimuli: list[str] = []
    sleeps: list[float] = []
    sample = {
        "descriptions": ["Payment rejected"],
        "error_spans": 2,
        "checkout_error_spans": 1,
        "payment_connection_errors": 1,
    }
    monkeypatch.setattr(
        observer,
        "_stimulate_payment_fault",
        lambda: stimuli.append("checkout") or {"status": "pass", "checkout_count": 1},
    )
    monkeypatch.setattr(observer, "_sample", lambda _since: sample)
    monkeypatch.setattr(g02_lab.time, "sleep", sleeps.append)

    first = observer("fault", fault_class)
    second = observer("fault", fault_class)

    assert stimuli == ["checkout"]
    assert sleeps == [30]
    assert observer.payment_stimulus == {"status": "pass", "checkout_count": 1}
    assert fault_state(fault_class, [first, second]) is OracleState.FAULT_ACTIVE


def test_kafka_observer_stimulates_once_before_two_frozen_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "kafkaQueueProblems")
    stimuli: list[str] = []
    sleeps: list[float] = []
    sample = {
        "descriptions": [],
        "consumer_lag": 12.0,
        "kafka_log_error": False,
        "kafka_fault_log": True,
        "error_spans": 0,
    }
    monkeypatch.setattr(
        observer,
        "_stimulate_kafka_fault",
        lambda: stimuli.append("checkout") or {"status": "pass", "checkout_count": 1},
    )
    monkeypatch.setattr(observer, "_sample", lambda _since: sample)
    monkeypatch.setattr(g02_lab.time, "sleep", sleeps.append)

    first = observer("fault", "kafkaQueueProblems")
    second = observer("fault", "kafkaQueueProblems")

    assert stimuli == ["checkout"]
    assert sleeps == [30]
    assert first["kafka_stimulus"]["checkout_count"] == 1
    assert second["kafka_stimulus"]["checkout_count"] == 1
    assert fault_state("kafkaQueueProblems", [first, second]) is OracleState.FAULT_ACTIVE


def test_live_observation_without_result_is_infrastructure_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "kafkaQueueProblems")
    monkeypatch.setattr(
        g02_lab,
        "run_remote_script",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(GovernanceError("transport lost")),
    )

    with pytest.raises(InfrastructureFailure, match="produced no result"):
        observer._sample(g02_lab.datetime.now(g02_lab.UTC))


def test_gate_scenario_runner_preserves_collection_infra_failure(
    tmp_path: Path,
) -> None:
    from faultwitness_dev.experiment import TrialJournal

    journal = TrialJournal(tmp_path)
    clients: list[MemoryFlagClient] = []

    def client_factory(_producer_sha: str) -> MemoryFlagClient:
        client = MemoryFlagClient(base_flag_document())
        clients.append(client)
        return client

    def observer_factory(_producer_sha: str, _fault_class: str) -> Any:
        def observe(phase: str, _fault: str) -> Mapping[str, Any]:
            if phase == "control":
                return {"state": OracleState.HEALTHY}
            if phase == "recovery":
                return {"ready": True, "journey_healthy": True, "signal_not_worsening": True}
            raise InfrastructureFailure("fixture source collection failed")

        return observe

    result = run_gate_scenario_matrix(
        ROOT,
        "1" * 40,
        journal,
        client_factory=client_factory,
        observer_factory=observer_factory,
    )

    assert result["status"] == "infra_failed"
    assert result["scenario_count"] == 0
    assert result["trials"][-1]["status"] == "infra_failed"
    assert clients[0].read() == base_flag_document()


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
    observer.baseline_working_set = 40.0
    observation = observer._active_observation(
        {"working_set": 42.0, "descriptions": [], "trace_count": 0}
    )
    assert observation["working_set"] == 42.0
    assert observation["baseline_working_set"] == 40.0
    assert observation["metric_service"] == "emailservice"
    assert observation["working_set_unit"] == "bytes"


def _live_memory_sample(working_set: float) -> dict[str, Any]:
    return {
        "working_set": working_set,
        "descriptions": [],
        "ready": True,
        "journey_status": 200,
        "trace_count": 0,
    }


def test_memory_observer_retains_first_sample_and_uses_second_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "emailMemoryLeak")
    mib = 1024 * 1024
    observer.baseline_working_set = 100 * mib
    observer.email_runtime_reset = {
        "status": "pass",
        "reset_count": 1,
        "old_pod_uid": "old",
        "new_pod_uid": "new",
        "new_pod_name": "email-new",
        "ready": True,
    }
    samples = iter(
        (
            _live_memory_sample(110 * mib),
            _live_memory_sample(120 * mib),
            _live_memory_sample(110 * mib),
            _live_memory_sample(100 * mib),
        )
    )
    sleeps: list[float] = []
    stimuli: list[bool] = []
    monkeypatch.setattr(
        observer,
        "_stimulate_email_request",
        lambda: stimuli.append(False)
        or {"status": "pass", "request_count": 1},
    )
    monkeypatch.setattr(observer, "_sample", lambda _since: next(samples))
    monkeypatch.setattr(g02_lab.time, "sleep", sleeps.append)

    first = observer("fault", "emailMemoryLeak")
    second = observer("fault", "emailMemoryLeak")
    first_recovery = observer("recovery", "emailMemoryLeak")
    second_recovery = observer("recovery", "emailMemoryLeak")

    assert observer.fault_samples == [first, second]
    assert fault_state("emailMemoryLeak", [first, second]) is OracleState.FAULT_ACTIVE
    assert first_recovery["signal_not_worsening"] is True
    assert second_recovery["signal_not_worsening"] is True
    assert first["email_stimulus_count"] == 1
    assert second["email_stimulus_count"] == 2
    assert first_recovery["email_recovery_stimulus"]["request_count"] == 1
    assert first["email_runtime_reset"]["reset_count"] == 1
    assert stimuli == [False, False, False]
    assert sleeps == [30, 30]


def test_memory_oracle_allows_first_scrape_lag_but_requires_material_growth() -> None:
    mib = 1024 * 1024
    observations = [
        {
            "working_set": 100 * mib,
            "baseline_working_set": 100 * mib,
        },
        {
            "working_set": 106 * mib,
            "baseline_working_set": 100 * mib,
        },
    ]
    assert (
        fault_state("emailMemoryLeak", observations)
        is OracleState.FAULT_ACTIVE
    )


def test_memory_recovery_ignores_subthreshold_runtime_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mib = 1024 * 1024
    observer = LiveScenarioObserver("1" * 40, "emailMemoryLeak")
    observer.baseline_working_set = 100 * mib
    observer.fault_samples = [{"working_set": 106 * mib}]
    monkeypatch.setattr(
        observer,
        "_stimulate_email_request",
        lambda: {"status": "pass", "request_count": 1},
    )
    monkeypatch.setattr(
        observer,
        "_sample",
        lambda _since: _live_memory_sample(106.5 * mib),
    )
    recovery = observer("recovery", "emailMemoryLeak")
    assert recovery["signal_not_worsening"] is True


def test_memory_non_growth_keeps_cleanup_comparator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = LiveScenarioObserver("1" * 40, "emailMemoryLeak")
    mib = 1024 * 1024
    observer.baseline_working_set = 100 * mib
    observer.email_runtime_reset = {
        "status": "pass",
        "reset_count": 1,
        "old_pod_uid": "old",
        "new_pod_uid": "new",
        "new_pod_name": "email-new",
        "ready": True,
    }
    samples = iter(
        (
            _live_memory_sample(110 * mib),
            _live_memory_sample(109 * mib),
            _live_memory_sample(100 * mib),
        )
    )
    clock = iter((0.0, 0.0, 91.0, 0.0))
    monkeypatch.setattr(
        observer,
        "_stimulate_email_request",
        lambda: {
            "status": "pass",
            "request_count": 1,
        },
    )
    monkeypatch.setattr(observer, "_sample", lambda _since: next(samples))
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(g02_lab.time, "monotonic", lambda: next(clock))

    first = observer("fault", "emailMemoryLeak")
    second = observer("fault", "emailMemoryLeak")
    recovery = observer("recovery", "emailMemoryLeak")

    assert observer.fault_samples == [first]
    assert fault_state("emailMemoryLeak", [first, second]) is OracleState.HEALTHY
    assert recovery["signal_not_worsening"] is True


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


def test_cleanup_failure_dominates_a_primary_fault_oracle_failure() -> None:
    scenario = next(
        seed
        for seed in seed_catalog(DIGEST)
        if seed["fault_action"]["class"] == "productCatalogFailure"
    )
    client = MemoryFlagClient(base_flag_document(), ignore_restore=True)

    def never_active(phase: str, _fault_class: str) -> Mapping[str, Any]:
        if phase == "control":
            return {"state": OracleState.HEALTHY}
        if phase == "fault":
            return {"journey_failed": False, "correlated_error": False}
        return {"ready": True, "journey_healthy": True, "signal_not_worsening": True}

    with pytest.raises(GovernanceError, match="cleanup blocked and quarantined"):
        run_scenario(scenario, client, never_active)


def test_lab_bootstrap_rejects_unpinned_image_fixture() -> None:
    fixture = load_data(ROOT / "tests/fixtures/g02/lab_unpinned_image.yaml")
    with pytest.raises(GovernanceError, match="not digest-pinned"):
        validate_lab_bootstrap(fixture)


def test_gate_scenario_runner_executes_and_reuses_exact_32_trials(tmp_path: Path) -> None:
    from faultwitness_dev.experiment import TrialJournal

    journal = TrialJournal(tmp_path)

    def client_factory(_producer_sha: str) -> MemoryFlagClient:
        return MemoryFlagClient(base_flag_document())

    def observer_factory(_producer_sha: str, _fault_class: str) -> Any:
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
    assert all(item["execution_attempt"] == 1 for item in second["trials"])
    assert all(item["record_version"] == 2 for item in second["trials"])


def test_resource_replay_reuses_24_cases_and_reexecutes_exactly_8(tmp_path: Path) -> None:
    from faultwitness_dev.experiment import TrialJournal

    def client_factory(_producer_sha: str) -> MemoryFlagClient:
        return MemoryFlagClient(base_flag_document())

    def observer_factory(_producer_sha: str, _fault_class: str) -> Any:
        return g02_lab.scripted_sequence_observer()

    frozen = run_gate_scenario_matrix(
        ROOT,
        "1" * 40,
        TrialJournal(tmp_path / "frozen"),
        client_factory=client_factory,
        observer_factory=observer_factory,
    )
    journal = TrialJournal(tmp_path / "resource-v2")
    replayed = replay_resource_scenarios(
        ROOT,
        "2" * 40,
        frozen,
        journal,
        client_factory=client_factory,
        observer_factory=observer_factory,
    )
    repeated = replay_resource_scenarios(
        ROOT,
        "2" * 40,
        frozen,
        journal,
        client_factory=client_factory,
        observer_factory=observer_factory,
    )

    assert replayed["scenario_count"] == 32
    assert replayed["inherited_case_count"] == 24
    assert replayed["replayed_case_count"] == 8
    assert len(list((tmp_path / "resource-v2" / "trials").glob("*.json"))) == 8
    assert [item["artifact_digest"] for item in repeated["trials"]] == [
        item["artifact_digest"] for item in replayed["trials"]
    ]
    assert all(
        item["execution_attempt"] == 1
        for item in repeated["trials"]
        if item["trial_id"].startswith("g02-v2-resource-")
    )


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


def test_fault_lab_runner_is_pinned_and_records_observed_provenance() -> None:
    config = load_lab_config(ROOT)
    summary = validate_lab_bootstrap(config)
    script = render_k3s_bootstrap_script(config, "1" * 40)
    assert summary["image_count"] == 30
    assert summary["profile"] == "k3s"
    assert all(not image["reference"].startswith("docker.io/") for image in config["images"])
    assert "sha256sum -c" in script
    assert "namespace: fw-sut" in script
    assert "delete namespace fw-sut --ignore-not-found --wait=true" in script
    assert "create namespace fw-sut" in script
    assert "kubectl apply -n fw-sut" in script
    assert "readyReplicas" in script
    assert "grep -q '\"emailMemoryLeak\"'" in script
    assert "rollout restart deployment/flagd" in script
    assert "FW_G02_LOAD_USERS_ANCHOR_DRIFT" in script
    assert "load_users_minimum" in script
    assert 'value: "1"' in script
    assert "sleep 5" in script
    assert "rollout status" not in script
    assert "--timeout" not in script
    assert "printf 'producer_sha=%s" in script
    assert "1" * 40 in script
    assert "faultwitness.io/producer-sha=" + "1" * 40 in script
    assert "candidate-binding" not in script
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


def test_lab_manifest_uses_minimum_nonzero_ambient_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = render_k3s_bootstrap_script(load_lab_config(ROOT), "1" * 40)
    transform = script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    manifest = tmp_path / "lab.yaml"
    manifest.write_text(
        'marker: "emailMemoryLeak"\n'
        '            - name: LOCUST_USERS\n'
        '              value: "10"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["g02-manifest-transform", str(manifest)])

    exec(compile(transform, "g02-manifest-transform", "exec"), {})

    rendered = manifest.read_text(encoding="utf-8")
    assert 'value: "1"' in rendered
    assert 'value: "10"' not in rendered


def test_live_inject_and_restore_are_exact_and_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = base_flag_document()

    class FakeRemoteFlagClient:
        current = document

        def __init__(self, producer_sha: str) -> None:
            assert producer_sha == "1" * 40

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


def _restimulation_sample(fault_class: str) -> dict[str, Any]:
    """A benign sample: flag off, nothing failing, all instruments present."""
    return {
        "absent_series": [],
        "recorded_at": "2026-07-29T00:00:00+00:00",
        "ready": True,
        "journey_status": 200,
        "cpu_rate": 0.01,
        "working_set": 3 * 1024 * 1024,
        "consumer_lag": 0.0,
        "consumer_record_lag": 0.0,
        "consumer_poll_lag_seconds": 0.0,
        "trace_count": 1,
        "descriptions": [],
        "error_spans": 0,
        "checkout_error_spans": 0,
        "payment_connection_errors": 0,
        "kafka_log_error": False,
        "kafka_fault_log": False,
    }


@pytest.mark.parametrize("fault_class", sorted(ADAPTERS))
def test_repeated_fault_stimulus_cannot_manufacture_a_false_positive(
    fault_class: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driving the workload every poll tick removes false negatives only.

    With the fault flag off the oracle must stay non-ACTIVE no matter how many
    extra requests the runner issues. This is the machine-checkable form of the
    AMD-0007 appendix-3 claim that per-poll stimulus strengthens rather than
    relaxes the predicate.
    """
    observer = LiveReadinessObserverV3("1" * 40, fault_class)
    observer.baseline_cpu = 0.01
    observer.baseline_working_set = 3 * 1024 * 1024
    observer.baseline_lag = 0.0
    stimuli = {"count": 0}

    def stimulate() -> dict[str, Any]:
        stimuli["count"] += 1
        return {"status": "pass", "request_count": 1, "response_status": 200}

    for name in (
        "_stimulate_ad_request",
        "_stimulate_email_request",
        "_stimulate_product_fault",
        "_stimulate_kafka_fault",
        "_stimulate_payment_fault",
    ):
        monkeypatch.setattr(observer, name, stimulate)
    monkeypatch.setattr(
        observer, "_sample", lambda _since: _restimulation_sample(fault_class)
    )
    ticks = iter([0.0] + [float(step) for step in range(5, 200, 5)])
    monkeypatch.setattr(g02_lab.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)

    first = observer("fault", fault_class)
    if fault_class == "emailMemoryLeak":
        # The first email window is the "before" sample by design and returns
        # without polling; the comparison window is the one that polls.
        first = observer("fault", fault_class)
    # The window polled repeatedly and re-drove the workload each tick...
    assert stimuli["count"] > 1
    assert observer.fault_poll_stimuli > 0
    # ...and still refused to declare the fault active.
    comparison = [observer.fault_samples[0], first]
    assert fault_state(fault_class, comparison) != OracleState.FAULT_ACTIVE


def test_v3_absent_series_is_infrastructure_not_a_zero_measurement() -> None:
    """A missing instrument must never be scored as an observed 0.0.

    The wait is label-blind: the packet carries all six evidence groups for
    every label, so a window is unscoreable until every series is present,
    regardless of which one the sealed predicate reads.
    """
    observer = LiveReadinessObserverV3("1" * 40, "kafkaQueueProblems")
    sample = _restimulation_sample("kafkaQueueProblems")
    sample["absent_series"] = ["consumer_poll_lag_seconds"]
    sample["consumer_poll_lag_seconds"] = None
    assert observer._absent_series(sample) == ("consumer_poll_lag_seconds",)

    # A series this label's predicate never reads still blocks the window,
    # because the packet cannot omit that evidence group.
    unrelated = _restimulation_sample("kafkaQueueProblems")
    unrelated["absent_series"] = ["working_set"]
    assert observer._absent_series(unrelated) == ("working_set",)

    # A complete window is scoreable.
    assert observer._absent_series(_restimulation_sample("kafkaQueueProblems")) == ()

    # Only a series still absent at the deadline is an infrastructure failure,
    # which AMD-0003 authorises for unlimited attributable retries.
    failure = observer._absent_series_failure(("cpu_rate",))
    assert isinstance(failure, InfrastructureFailure)
    assert "cpu_rate" in str(failure)
    assert "deadline" in str(failure)


def test_v3_ad_baseline_waits_out_a_previous_cases_burn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduce the SEED-G02-0014 -> SEED-G02-0015 baseline collision.

    Case 14's last recovery sample read 2.2433 cores; case 15 sampled its baseline 34
    seconds later and, because the ad CPU query is a 2-minute rate(), recorded that
    same decaying value as `baseline_cpu`. Multiplied by AD_CPU_ACTIVE_MULTIPLIER the
    activation bar became 11.2 cores against a pod that saturates near 4.
    """
    observer = LiveReadinessObserverV3("1" * 40, "adHighCpu")
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)

    # The decay actually observed in the diagnostic scan, ending at rest.
    decay = [2.243332663338218, 1.402, 0.61, 0.12, 0.002]
    seen: list[float] = []

    def _sample(_since: object) -> dict[str, object]:
        sample = _restimulation_sample("adHighCpu")
        value = decay[min(len(seen), len(decay) - 1)]
        seen.append(value)
        sample["cpu_rate"] = value
        return sample

    monkeypatch.setattr(observer, "_sample", _sample)
    observer._await_ad_cpu_quiescence()

    # It refused the contaminated readings and only accepted a quiesced one.
    assert observer.ad_cpu_quiescent_cores is not None
    assert observer.ad_cpu_quiescent_cores <= g02_lab.V3_AD_CPU_QUIESCENT_MAX_CORES
    assert seen[0] == 2.243332663338218
    assert len(seen) > 1

    # With that baseline the real fault reading activates; with the contaminated one
    # it could not, which is exactly how case 15 failed.
    quiesced = observer.ad_cpu_quiescent_cores
    observed_burn = 4.001263351731677
    assert observed_burn >= max(
        g02_lab.AD_CPU_ACTIVE_MIN_CORES, quiesced * g02_lab.AD_CPU_ACTIVE_MULTIPLIER
    )
    assert observed_burn < max(
        g02_lab.AD_CPU_ACTIVE_MIN_CORES,
        2.243332663338218 * g02_lab.AD_CPU_ACTIVE_MULTIPLIER,
    )


def test_v3_ad_quiescence_failure_is_infrastructure_not_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pod that never settles is a lab condition, not a candidate verdict."""
    observer = LiveReadinessObserverV3("1" * 40, "adHighCpu")
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)

    def _sample(_since: object) -> dict[str, object]:
        sample = _restimulation_sample("adHighCpu")
        sample["cpu_rate"] = 3.9
        return sample

    monkeypatch.setattr(observer, "_sample", _sample)
    with pytest.raises(InfrastructureFailure, match="quiescent"):
        observer._await_ad_cpu_quiescence()

    # v1/v2 never wait, so their recorded behaviour is unchanged.
    legacy = LiveScenarioObserver("1" * 40, "adHighCpu")
    assert legacy.require_ad_cpu_quiescent_baseline is False


def test_v3_transient_scrape_gap_is_waited_out_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A momentary scrape gap must not abort a case that would otherwise pass.

    This is the regression guard for the false negative where a transient gap in
    ``cpu_rate`` -- a series the kafka predicate never reads -- failed the case.
    """
    observer = LiveReadinessObserverV3("1" * 40, "kafkaQueueProblems")
    observer.baseline_lag = 1.0
    monkeypatch.setattr(g02_lab.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(observer, "_drive_label_workload", lambda _phase: None)
    monkeypatch.setattr(observer, "_stimulate_kafka_fault", lambda: {"status": 200})

    samples: list[dict[str, object]] = []
    gap = _restimulation_sample("kafkaQueueProblems")
    gap["absent_series"] = ["cpu_rate"]
    gap["cpu_rate"] = None
    samples.append(gap)
    good = _restimulation_sample("kafkaQueueProblems")
    good["consumer_lag"] = 87.0
    good["consumer_record_lag"] = 87.0
    good["kafka_error"] = True
    good["error_spans"] = 3
    samples.append(good)

    calls = {"count": 0}

    def _sample(_since: object) -> dict[str, object]:
        index = min(calls["count"], len(samples) - 1)
        calls["count"] += 1
        return dict(samples[index])

    monkeypatch.setattr(observer, "_sample", _sample)
    observation = observer("fault", "kafkaQueueProblems")

    # The gap was polled through, not raised, and the following complete window
    # produced the fault verdict.
    assert calls["count"] >= 2
    assert observation["cpu_rate"] is not None
    assert fault_state("kafkaQueueProblems", [observation, observation]) == (
        OracleState.FAULT_ACTIVE
    )


def test_v3_collector_reports_absent_series_as_null() -> None:
    since = g02_lab.datetime(2026, 7, 29, 0, 0, tzinfo=g02_lab.UTC)
    script = render_live_readiness_observer_v3_script("a" * 40, since)
    # Absent series become null and are named, rather than coerced to 0.0.
    assert "return float(result[0][\"value\"][1]) if result else None" in script
    assert '"absent_series": absent_series,' in script
    # The frozen v1/v2 collector keeps its original zero-coercing behaviour.
    legacy = g02_lab.inspect.getsource(LiveScenarioObserver._sample)
    assert "else 0.0" in legacy


def test_v3_fail_closed_marker_is_not_laundered_into_infrastructure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A collector refusal is a governance verdict, not a retryable fault.

    Rewrapping it would move a deliberate fail-closed check into the AMD-0003
    unlimited-retry class, which is the opposite of what fail-closed means.
    """
    observer = LiveReadinessObserverV3("1" * 40, "adHighCpu")
    monkeypatch.setattr(
        g02_lab, "validate_live_readiness_collector_checkpoint", lambda: {}
    )

    def refuse(_script: str, **_kwargs: Any) -> str:
        raise GovernanceError(
            "remote script failed: FW_G03_COLLECTOR_POD_CARDINALITY ad- count=2"
        )

    monkeypatch.setattr(g02_lab, "run_remote_script", refuse)
    with pytest.raises(GovernanceError, match="FW_G03_COLLECTOR_POD_CARDINALITY"):
        observer._sample(g02_lab.datetime.now(g02_lab.UTC))

    def transport_failure(_script: str, **_kwargs: Any) -> str:
        raise GovernanceError("ssh transport produced no output")

    monkeypatch.setattr(g02_lab, "run_remote_script", transport_failure)
    with pytest.raises(InfrastructureFailure):
        observer._sample(g02_lab.datetime.now(g02_lab.UTC))
