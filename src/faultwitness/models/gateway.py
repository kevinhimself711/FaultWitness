from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from faultwitness.contracts.models import ModelRequest
from faultwitness.models.catalog import CapabilityCatalog, ModelProfile
from faultwitness.models.channel import ChannelResult, ModelChannel
from faultwitness.models.types import (
    ChannelName,
    GatewayChunk,
    GatewayResponse,
    ModelCapability,
    ModelFailure,
    ModelFailureCode,
    PartialModelFailure,
    RouteMetadata,
)

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{12,}\b", re.IGNORECASE),
    re.compile(r"FW_(?:SECRET|PII|COT)_CANARY", re.IGNORECASE),
    re.compile(r"\b(?:chain[_ -]?of[_ -]?thought|private[_ -]?reasoning)\b", re.IGNORECASE),
)


class GatewayObserver(Protocol):
    async def record(self, event: dict[str, Any]) -> None: ...


class NullObserver:
    async def record(self, event: dict[str, Any]) -> None:
        return None


class ModelGateway:
    def __init__(
        self,
        *,
        catalog: CapabilityCatalog,
        channels: dict[ChannelName, ModelChannel],
        observer: GatewayObserver | None = None,
        trace_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._catalog = catalog
        self._channels = channels
        self._observer = observer or NullObserver()
        self._trace_id_factory = trace_id_factory or (lambda: str(uuid.uuid4()))

    @staticmethod
    def _capability(request: ModelRequest) -> ModelCapability:
        if request.stream:
            return ModelCapability.STREAM
        if request.tool_schemas:
            return ModelCapability.FORCED_TOOL
        if request.target_json_schema is not None:
            return ModelCapability.STRUCTURED
        return ModelCapability.COMPLETE

    @staticmethod
    def _reject_sensitive_request(request: ModelRequest) -> None:
        values = [message.content for message in request.messages]
        document = json.dumps(
            {
                "target_json_schema": request.target_json_schema,
                "tool_schemas": request.tool_schemas,
            },
            sort_keys=True,
        )
        values.append(document)
        if any(pattern.search(value) for value in values for pattern in _SECRET_PATTERNS):
            raise ModelFailure(ModelFailureCode.POLICY_REJECTED, retryable=False)

    def _route(
        self,
        request: ModelRequest,
        profile: ModelProfile,
        *,
        attempt: int,
        fallback_count: int,
        repair_count: int,
        trace_id: str,
        resolved_model: str | None = None,
    ) -> RouteMetadata:
        return RouteMetadata(
            channel=profile.channel,
            model_family=profile.family,
            requested_model=request.model_id,
            resolved_model=resolved_model or profile.model_id,
            route_policy_version=self._catalog.route_policy.version,
            catalog_version=self._catalog.catalog_version,
            attempt=attempt,
            fallback_count=fallback_count,
            repair_count=repair_count,
            trace_id=trace_id,
        )

    @staticmethod
    def _validate_structured(result: ChannelResult, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            Draft202012Validator.check_schema(schema)
            value = json.loads(result.content)
            if not isinstance(value, dict):
                raise ValidationError("structured output root must be an object")
            Draft202012Validator(schema).validate(value)
            return value
        except (SchemaError, ValidationError, json.JSONDecodeError) as error:
            raise ModelFailure(
                ModelFailureCode.INVALID_STRUCTURED_OUTPUT, retryable=False
            ) from error

    @staticmethod
    def _validate_tool_calls(result: ChannelResult, schemas: tuple[dict[str, Any], ...]) -> None:
        if not result.tool_calls:
            raise ModelFailure(ModelFailureCode.INVALID_TOOL_ARGUMENTS, retryable=False)
        definitions: dict[str, dict[str, Any]] = {}
        try:
            for item in schemas:
                function = item["function"]
                definitions[str(function["name"])] = function["parameters"]
            for call in result.tool_calls:
                schema = definitions[call.name]
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(call.arguments)
        except (KeyError, SchemaError, ValidationError, TypeError) as error:
            raise ModelFailure(ModelFailureCode.INVALID_TOOL_ARGUMENTS, retryable=False) from error

    @staticmethod
    def _repair_request(request: ModelRequest) -> ModelRequest:
        instruction = (
            "Return only one JSON object that strictly satisfies the supplied JSON schema. "
            "Do not add markdown, commentary, or private reasoning."
        )
        messages = (
            *request.messages,
            request.messages[0].model_copy(update={"role": "user", "content": instruction}),
        )
        return request.model_copy(update={"messages": messages})

    async def complete(self, request: ModelRequest) -> GatewayResponse:
        self._reject_sensitive_request(request)
        capability = self._capability(request)
        if capability is ModelCapability.STREAM:
            raise ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False)
        profiles = self._catalog.candidates(request.model_family, capability)
        if not profiles:
            raise ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False)
        trace_id = self._trace_id_factory()
        last_error: ModelFailure | None = None
        attempt = 0
        repair_count = 0
        for fallback_count, profile in enumerate(profiles):
            channel = self._channels.get(profile.channel)
            if channel is None:
                last_error = ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False)
                continue
            retries = self._catalog.route_policy.max_transient_retries
            while True:
                attempt += 1
                route = self._route(
                    request,
                    profile,
                    attempt=attempt,
                    fallback_count=fallback_count,
                    repair_count=repair_count,
                    trace_id=trace_id,
                )
                await self._observer.record(
                    {
                        "kind": "model_attempt_started",
                        "request_id": request.request_id,
                        **route.model_dump(mode="json"),
                    }
                )
                try:
                    result = await channel.complete(request, profile, route)
                    structured = None
                    if request.tool_schemas:
                        self._validate_tool_calls(result, request.tool_schemas)
                    if request.target_json_schema is not None:
                        try:
                            structured = self._validate_structured(
                                result, request.target_json_schema
                            )
                        except ModelFailure:
                            if repair_count >= self._catalog.route_policy.max_repairs:
                                raise
                            repair_count += 1
                            request = self._repair_request(request)
                            continue
                    resolved_route = self._route(
                        request,
                        profile,
                        attempt=attempt,
                        fallback_count=fallback_count,
                        repair_count=repair_count,
                        trace_id=trace_id,
                        resolved_model=result.resolved_model,
                    )
                    response = GatewayResponse(
                        request_id=request.request_id,
                        response_id=result.response_id,
                        content=result.content,
                        structured_output=structured,
                        tool_calls=result.tool_calls,
                        finish_reason=result.finish_reason,
                        usage=result.usage,
                        usage_unavailable_reason=(
                            None if result.usage is not None else "upstream_omitted_usage"
                        ),
                        route=resolved_route,
                    )
                    await self._observer.record(
                        {
                            "kind": "model_attempt_completed",
                            "request_id": request.request_id,
                            **resolved_route.model_dump(mode="json"),
                        }
                    )
                    return response
                except ModelFailure as error:
                    last_error = error
                    await self._observer.record(
                        {
                            "kind": "model_attempt_failed",
                            "request_id": request.request_id,
                            "failure_code": error.code.value,
                            **route.model_dump(mode="json"),
                        }
                    )
                    if error.retryable and retries > 0:
                        retries -= 1
                        continue
                    if error.code in {
                        ModelFailureCode.AUTHENTICATION,
                        ModelFailureCode.CONFIGURATION,
                        ModelFailureCode.INVALID_TOOL_ARGUMENTS,
                        ModelFailureCode.POLICY_REJECTED,
                    }:
                        raise
                    break
            if last_error and not last_error.pre_output:
                raise last_error
        assert last_error is not None
        raise last_error

    async def stream(self, request: ModelRequest) -> AsyncIterator[GatewayChunk]:
        self._reject_sensitive_request(request)
        if not request.stream:
            raise ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False)
        profiles = self._catalog.candidates(request.model_family, ModelCapability.STREAM)
        if not profiles:
            raise ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False)
        trace_id = self._trace_id_factory()
        attempt = 0
        last_error: ModelFailure | None = None
        for fallback_count, profile in enumerate(profiles):
            channel = self._channels.get(profile.channel)
            if channel is None:
                continue
            retries = self._catalog.route_policy.max_transient_retries
            while True:
                attempt += 1
                route = self._route(
                    request,
                    profile,
                    attempt=attempt,
                    fallback_count=fallback_count,
                    repair_count=0,
                    trace_id=trace_id,
                )
                visible = 0
                try:
                    async for chunk in channel.stream(request, profile, route):
                        if chunk.delta or chunk.tool_call_delta:
                            visible += 1
                        yield chunk
                    return
                except PartialModelFailure:
                    raise
                except ModelFailure as error:
                    last_error = error
                    if visible:
                        raise PartialModelFailure(error.code, visible_chunks=visible) from error
                    if error.retryable and retries > 0:
                        retries -= 1
                        continue
                    if not error.retryable:
                        raise
                    break
        if last_error is None:
            last_error = ModelFailure(ModelFailureCode.CONFIGURATION, retryable=False)
        raise last_error
