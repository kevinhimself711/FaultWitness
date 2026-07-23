from __future__ import annotations

import inspect

from faultwitness_dev.observability_deploy import relay_langsmith, run_trace_service_smoke


def test_trace_smoke_exposes_explicit_uncertain_ack_injection() -> None:
    smoke = inspect.signature(run_trace_service_smoke)
    relay = inspect.signature(relay_langsmith)
    assert smoke.parameters["inject_uncertain_ack"].default is False
    assert relay.parameters["inject_uncertain_ack"].default is False


def test_relay_uses_retry_before_ack_and_checks_stable_identity() -> None:
    source = inspect.getsource(relay_langsmith)
    retry_index = source.index("uncertain-ACK replay")
    ack_index = source.index('f"/internal/v1/relay/langsmith/{trace.trace_ref}/ack"')
    assert retry_index < ack_index
    assert "trace.payload_digest != expected_digest" in source
    assert 'summary["remote_trace_id"] != expected_remote' in source
