from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from faultwitness.contracts.models import ModelRequest, ModelUsage
from faultwitness.models.catalog import ModelProfile
from faultwitness.models.types import (
    GatewayChunk,
    ModelFailure,
    ModelFailureCode,
    PartialModelFailure,
    RouteMetadata,
    ToolInvocation,
)


@dataclass(frozen=True)
class ChannelResult:
    response_id: str
    resolved_model: str
    content: str
    tool_calls: tuple[ToolInvocation, ...]
    finish_reason: str
    usage: ModelUsage | None


class ModelChannel(Protocol):
    async def complete(
        self, request: ModelRequest, profile: ModelProfile, route: RouteMetadata
    ) -> ChannelResult: ...

    def stream(
        self, request: ModelRequest, profile: ModelProfile, route: RouteMetadata
    ) -> AsyncIterator[GatewayChunk]: ...


class OpenAICompatibleChannel:
    """Strict Chat Completions adapter shared by Bailian and NewAPI."""

    def __init__(
        self,
        *,
        base_url: str,
        credential: str,
        timeout_seconds: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout = timeout_seconds
        self._transport = transport

    def _payload(
        self, request: ModelRequest, profile: ModelProfile, *, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": profile.model_id,
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "stream": stream,
            **profile.request_overrides,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if request.target_json_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        if request.tool_schemas:
            payload["tools"] = list(request.tool_schemas)
            try:
                forced_name = request.tool_schemas[0]["function"]["name"]
            except (KeyError, TypeError) as error:
                raise ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False) from error
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": forced_name},
            }
        return payload

    async def _request(self, payload: dict[str, Any], *, stream: bool) -> httpx.Response:
        try:
            client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self._credential}"},
            )
            response = await client.post(self._base_url + "/chat/completions", json=payload)
        except httpx.TimeoutException as error:
            raise ModelFailure(ModelFailureCode.TIMEOUT, retryable=True) from error
        except httpx.TransportError as error:
            raise ModelFailure(ModelFailureCode.UPSTREAM_UNAVAILABLE, retryable=True) from error
        finally:
            if "client" in locals():
                await client.aclose()
        if response.status_code >= 400:
            self._raise_status(response.status_code)
        return response

    @staticmethod
    def _raise_status(status: int) -> None:
        if status == 429:
            raise ModelFailure(ModelFailureCode.RATE_LIMITED, retryable=True, status_code=status)
        if status in {408, 500, 502, 503, 504}:
            raise ModelFailure(
                ModelFailureCode.UPSTREAM_UNAVAILABLE, retryable=True, status_code=status
            )
        if status in {401, 403}:
            raise ModelFailure(ModelFailureCode.AUTHENTICATION, retryable=False, status_code=status)
        raise ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False, status_code=status)

    @staticmethod
    def _usage(value: Any) -> ModelUsage | None:
        if not isinstance(value, dict):
            return None
        try:
            prompt = int(value["prompt_tokens"])
            completion = int(value["completion_tokens"])
            return ModelUsage(
                input_tokens=prompt,
                output_tokens=completion,
                total_tokens=prompt + completion,
                cost_usd=None,
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _tool_calls(message: dict[str, Any]) -> tuple[ToolInvocation, ...]:
        calls = []
        for raw in message.get("tool_calls") or ():
            try:
                function = raw["function"]
                arguments = json.loads(function["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError
                calls.append(
                    ToolInvocation(call_id=raw["id"], name=function["name"], arguments=arguments)
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ModelFailure(
                    ModelFailureCode.INVALID_TOOL_ARGUMENTS, retryable=False
                ) from error
        return tuple(calls)

    async def complete(
        self, request: ModelRequest, profile: ModelProfile, route: RouteMetadata
    ) -> ChannelResult:
        response = await self._request(self._payload(request, profile, stream=False), stream=False)
        try:
            document = response.json()
            choice = document["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""
            return ChannelResult(
                response_id=str(document["id"]),
                resolved_model=str(document.get("model") or profile.model_id),
                content=content,
                tool_calls=self._tool_calls(message),
                finish_reason=str(choice.get("finish_reason") or "unknown"),
                usage=self._usage(document.get("usage")),
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            if isinstance(error, ModelFailure):
                raise
            raise ModelFailure(ModelFailureCode.INVALID_RESPONSE, retryable=False) from error

    async def stream(
        self, request: ModelRequest, profile: ModelProfile, route: RouteMetadata
    ) -> AsyncIterator[GatewayChunk]:
        payload = self._payload(request, profile, stream=True)
        visible = 0
        sequence = 0
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self._timeout,
                    transport=self._transport,
                    headers={"Authorization": f"Bearer {self._credential}"},
                ) as client,
                client.stream(
                    "POST", self._base_url + "/chat/completions", json=payload
                ) as response,
            ):
                if response.status_code >= 400:
                    self._raise_status(response.status_code)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        document = json.loads(data)
                        choices = document.get("choices") or []
                        usage = self._usage(document.get("usage"))
                        if not choices and usage is not None:
                            yield GatewayChunk(
                                request_id=request.request_id,
                                sequence=sequence,
                                usage=usage,
                                route=route,
                            )
                            sequence += 1
                            continue
                        choice = choices[0]
                        delta = choice.get("delta") or {}
                        content = delta.get("content") or ""
                        tool_delta = "".join(
                            str(item.get("function", {}).get("arguments") or "")
                            for item in (delta.get("tool_calls") or ())
                        )
                        if content or tool_delta:
                            visible += 1
                        yield GatewayChunk(
                            request_id=request.request_id,
                            sequence=sequence,
                            delta=content,
                            tool_call_delta=tool_delta,
                            finish_reason=choice.get("finish_reason"),
                            usage=usage,
                            route=route,
                        )
                        sequence += 1
                    except (
                        KeyError,
                        IndexError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as error:
                        if visible:
                            raise PartialModelFailure(
                                ModelFailureCode.INTERRUPTED_STREAM, visible_chunks=visible
                            ) from error
                        raise ModelFailure(
                            ModelFailureCode.INVALID_RESPONSE, retryable=False
                        ) from error
        except PartialModelFailure:
            raise
        except ModelFailure as error:
            if visible:
                raise PartialModelFailure(error.code, visible_chunks=visible) from error
            raise
        except httpx.TimeoutException as error:
            if visible:
                raise PartialModelFailure(
                    ModelFailureCode.INTERRUPTED_STREAM, visible_chunks=visible
                ) from error
            raise ModelFailure(ModelFailureCode.TIMEOUT, retryable=True) from error
        except httpx.TransportError as error:
            if visible:
                raise PartialModelFailure(
                    ModelFailureCode.INTERRUPTED_STREAM, visible_chunks=visible
                ) from error
            raise ModelFailure(ModelFailureCode.UPSTREAM_UNAVAILABLE, retryable=True) from error
