from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from faultwitness.contracts.models import AgentBudget, ModelFamily, ModelMessage, ModelRequest
from faultwitness.models.catalog import CapabilityCatalog
from faultwitness.models.channel import OpenAICompatibleChannel
from faultwitness.models.types import ChannelName, ModelFailure, ModelFailureCode, RouteMetadata

ROOT = Path(__file__).resolve().parents[2]
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def request(*, stream: bool = False, tools: bool = False) -> ModelRequest:
    return ModelRequest(
        request_id="mreq_" + ULID,
        tenant_id="ten_" + ULID,
        correlation_id="corr_" + ULID,
        model_family=ModelFamily.QWEN,
        model_id="qwen3.7-plus-2026-05-26",
        messages=(ModelMessage(role="user", content="reply briefly"),),
        tool_schemas=(
            (
                {
                    "type": "function",
                    "function": {"name": "lookup", "parameters": {"type": "object"}},
                },
            )
            if tools
            else ()
        ),
        stream=stream,
        budget=AgentBudget(
            deadline=datetime.now(UTC) + timedelta(minutes=1),
            max_steps=1,
            max_model_calls=2,
            max_tokens=100,
            max_cost_usd=1,
        ),
    )


def profile():
    return CapabilityCatalog.load(ROOT / "config/models/catalog.yaml").profiles["qwen_primary"]


def route() -> RouteMetadata:
    return RouteMetadata(
        channel=ChannelName.BAILIAN,
        model_family=ModelFamily.QWEN,
        requested_model="qwen3.7-plus-2026-05-26",
        resolved_model="qwen3.7-plus-2026-05-26",
        route_policy_version="1.0.0",
        catalog_version="1.0.0",
        attempt=1,
        fallback_count=0,
        repair_count=0,
        trace_id="trace-safe",
    )


@pytest.mark.asyncio
async def test_complete_parses_usage_and_forced_tool() -> None:
    def handler(incoming: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(incoming.content)
        assert body["tool_choice"] == "required"
        return httpx.Response(
            200,
            json={
                "id": "response-1",
                "model": "qwen3.7-plus-2026-05-26",
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {"name": "lookup", "arguments": '{"key":"v"}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            },
        )

    channel = OpenAICompatibleChannel(
        base_url="https://fake.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(handler),
    )
    result = await channel.complete(request(tools=True), profile(), route())
    assert result.tool_calls[0].arguments == {"key": "v"}
    assert result.usage and result.usage.total_tokens == 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (429, ModelFailureCode.RATE_LIMITED, True),
        (503, ModelFailureCode.UPSTREAM_UNAVAILABLE, True),
        (401, ModelFailureCode.AUTHENTICATION, False),
        (400, ModelFailureCode.CONFIGURATION, False),
    ],
)
async def test_statuses_have_typed_retry_semantics(
    status: int, code: ModelFailureCode, retryable: bool
) -> None:
    channel = OpenAICompatibleChannel(
        base_url="https://fake.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(lambda _: httpx.Response(status)),
    )
    with pytest.raises(ModelFailure) as captured:
        await channel.complete(request(), profile(), route())
    assert captured.value.code is code
    assert captured.value.retryable is retryable


@pytest.mark.asyncio
async def test_stream_reconstructs_content_and_usage() -> None:
    data = (
        'data: {"choices":[{"delta":{"content":"hel"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":2,'
        '"completion_tokens":1,"total_tokens":3}}\n\n'
        "data: [DONE]\n\n"
    )
    channel = OpenAICompatibleChannel(
        base_url="https://fake.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=data)),
    )
    chunks = [item async for item in channel.stream(request(stream=True), profile(), route())]
    assert "".join(item.delta for item in chunks) == "hello"
    assert chunks[-1].usage and chunks[-1].usage.total_tokens == 3


@pytest.mark.asyncio
async def test_transport_timeout_is_typed_transient() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    channel = OpenAICompatibleChannel(
        base_url="https://newapi.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(ModelFailure) as captured:
        await channel.complete(request(), profile(), route())
    assert captured.value.code is ModelFailureCode.TIMEOUT
    assert captured.value.retryable


@pytest.mark.asyncio
async def test_invalid_json_is_typed_invalid_response() -> None:
    channel = OpenAICompatibleChannel(
        base_url="https://newapi.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="not-json")),
    )
    with pytest.raises(ModelFailure) as captured:
        await channel.complete(request(), profile(), route())
    assert captured.value.code is ModelFailureCode.INVALID_RESPONSE
    assert not captured.value.retryable


@pytest.mark.asyncio
async def test_invalid_tool_arguments_fail_closed() -> None:
    response = {
        "id": "response-1",
        "model": "qwen3.7-plus-2026-05-26",
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {"name": "lookup", "arguments": "not-json"},
                        }
                    ]
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    channel = OpenAICompatibleChannel(
        base_url="https://newapi.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)),
    )
    with pytest.raises(ModelFailure) as captured:
        await channel.complete(request(tools=True), profile(), route())
    assert captured.value.code is ModelFailureCode.INVALID_TOOL_ARGUMENTS


@pytest.mark.asyncio
async def test_malformed_chunk_before_output_is_invalid_response() -> None:
    channel = OpenAICompatibleChannel(
        base_url="https://newapi.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text="data: {not-json}\n\ndata: [DONE]\n\n")
        ),
    )
    with pytest.raises(ModelFailure) as captured:
        _ = [item async for item in channel.stream(request(stream=True), profile(), route())]
    assert captured.value.code is ModelFailureCode.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_malformed_chunk_after_output_is_partial_failure() -> None:
    data = (
        'data: {"choices":[{"delta":{"content":"visible"},"finish_reason":null}]}\n\n'
        "data: {not-json}\n\n"
    )
    channel = OpenAICompatibleChannel(
        base_url="https://newapi.invalid/v1",
        credential="synthetic",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=data)),
    )
    from faultwitness.models.types import PartialModelFailure

    with pytest.raises(PartialModelFailure) as captured:
        _ = [item async for item in channel.stream(request(stream=True), profile(), route())]
    assert captured.value.visible_chunks == 1
