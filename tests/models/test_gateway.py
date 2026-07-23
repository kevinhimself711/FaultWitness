from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from faultwitness.contracts.models import (
    AgentBudget,
    ModelFamily,
    ModelMessage,
    ModelRequest,
    ModelUsage,
)
from faultwitness.models.catalog import CapabilityCatalog
from faultwitness.models.channel import ChannelResult
from faultwitness.models.gateway import ModelGateway
from faultwitness.models.types import (
    GatewayChunk,
    ModelFailure,
    ModelFailureCode,
    PartialModelFailure,
)

ROOT = Path(__file__).resolve().parents[2]
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def request(
    *, structured: bool = False, stream: bool = False, content: str = "return result"
) -> ModelRequest:
    return ModelRequest(
        request_id="mreq_" + ULID,
        tenant_id="ten_" + ULID,
        correlation_id="corr_" + ULID,
        model_family=ModelFamily.QWEN,
        model_id="qwen3.7-plus-2026-05-26",
        messages=(ModelMessage(role="user", content=content),),
        target_json_schema=(
            {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            }
            if structured
            else None
        ),
        stream=stream,
        budget=AgentBudget(
            deadline=datetime.now(UTC) + timedelta(minutes=1),
            max_steps=1,
            max_model_calls=3,
            max_tokens=100,
            max_cost_usd=1,
        ),
    )


class FakeChannel:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def complete(self, request, profile, route):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return ChannelResult(
            response_id=f"response-{self.calls}",
            resolved_model=profile.model_id,
            content=outcome,
            tool_calls=(),
            finish_reason="stop",
            usage=ModelUsage(input_tokens=2, output_tokens=1, total_tokens=3),
        )

    async def stream(self, request, profile, route) -> AsyncIterator[GatewayChunk]:
        self.calls += 1
        for outcome in self.outcomes:
            if isinstance(outcome, Exception):
                raise outcome
            yield GatewayChunk(
                request_id=request.request_id, sequence=self.calls - 1, delta=outcome, route=route
            )


def gateway(channel: FakeChannel) -> ModelGateway:
    catalog = CapabilityCatalog.load(ROOT / "config/models/catalog.yaml")
    return ModelGateway(
        catalog=catalog, channels={"bailian": channel}, trace_id_factory=lambda: "trace-fixed"
    )


@pytest.mark.asyncio
async def test_transient_failure_retries_once() -> None:
    channel = FakeChannel([ModelFailure(ModelFailureCode.RATE_LIMITED, retryable=True), "ok"])
    response = await gateway(channel).complete(request())
    assert response.content == "ok"
    assert response.route.attempt == 2
    assert channel.calls == 2


@pytest.mark.asyncio
async def test_authentication_failure_does_not_retry() -> None:
    channel = FakeChannel([ModelFailure(ModelFailureCode.AUTHENTICATION, retryable=False)])
    with pytest.raises(ModelFailure) as captured:
        await gateway(channel).complete(request())
    assert captured.value.code is ModelFailureCode.AUTHENTICATION
    assert channel.calls == 1


@pytest.mark.asyncio
async def test_exhausted_transient_failure_falls_back_before_output() -> None:
    channel = FakeChannel(
        [
            ModelFailure(ModelFailureCode.UPSTREAM_UNAVAILABLE, retryable=True),
            ModelFailure(ModelFailureCode.UPSTREAM_UNAVAILABLE, retryable=True),
            "fallback-ok",
        ]
    )
    response = await gateway(channel).complete(request())
    assert response.content == "fallback-ok"
    assert response.route.fallback_count == 1
    assert response.route.model_family is ModelFamily.DEEPSEEK


@pytest.mark.asyncio
async def test_invalid_structured_output_repairs_once() -> None:
    channel = FakeChannel(["not-json", '{"ok":true}'])
    response = await gateway(channel).complete(request(structured=True))
    assert response.structured_output == {"ok": True}
    assert response.route.repair_count == 1
    assert channel.calls == 2


@pytest.mark.asyncio
async def test_missing_usage_is_explicitly_typed() -> None:
    channel = FakeChannel(["ok"])
    original = channel.complete

    async def without_usage(request, profile, route):
        result = await original(request, profile, route)
        return ChannelResult(
            response_id=result.response_id,
            resolved_model=result.resolved_model,
            content=result.content,
            tool_calls=result.tool_calls,
            finish_reason=result.finish_reason,
            usage=None,
        )

    channel.complete = without_usage
    response = await gateway(channel).complete(request())
    assert response.usage is None
    assert response.usage_unavailable_reason == "upstream_omitted_usage"


@pytest.mark.asyncio
async def test_canary_is_rejected_before_channel() -> None:
    channel = FakeChannel(["never"])
    with pytest.raises(ModelFailure) as captured:
        await gateway(channel).complete(request(content="FW_SECRET_CANARY-do-not-send"))
    assert captured.value.code is ModelFailureCode.POLICY_REJECTED
    assert channel.calls == 0


@pytest.mark.asyncio
async def test_stream_failure_after_visible_chunk_is_partial_and_never_retried() -> None:
    channel = FakeChannel(
        ["visible", ModelFailure(ModelFailureCode.UPSTREAM_UNAVAILABLE, retryable=True)]
    )
    with pytest.raises(PartialModelFailure) as captured:
        _ = [chunk async for chunk in gateway(channel).stream(request(stream=True))]
    assert captured.value.visible_chunks == 1
    assert channel.calls == 1
