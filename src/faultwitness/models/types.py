from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from faultwitness.contracts.models import ModelFamily, ModelUsage


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ChannelName(StrEnum):
    BAILIAN = "bailian"
    NEWAPI = "newapi"


class ModelCapability(StrEnum):
    COMPLETE = "complete"
    STRUCTURED = "structured"
    FORCED_TOOL = "forced_tool"
    STREAM = "stream"


class ModelFailureCode(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    INVALID_RESPONSE = "invalid_response"
    INVALID_STRUCTURED_OUTPUT = "invalid_structured_output"
    INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"
    INTERRUPTED_STREAM = "interrupted_stream"
    POLICY_REJECTED = "policy_rejected"


class ModelFailure(RuntimeError):
    def __init__(
        self,
        code: ModelFailureCode,
        *,
        retryable: bool,
        pre_output: bool = True,
        status_code: int | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable
        self.pre_output = pre_output
        self.status_code = status_code


class PartialModelFailure(ModelFailure):
    def __init__(self, code: ModelFailureCode, *, visible_chunks: int) -> None:
        super().__init__(code, retryable=False, pre_output=False)
        self.visible_chunks = visible_chunks


class ToolInvocation(StrictModel):
    call_id: str = Field(min_length=1, max_length=256)
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
    arguments: dict[str, Any]


class RouteMetadata(StrictModel):
    channel: ChannelName
    model_family: ModelFamily
    requested_model: str = Field(min_length=1)
    resolved_model: str = Field(min_length=1)
    route_policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    catalog_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    attempt: int = Field(ge=1)
    fallback_count: int = Field(ge=0)
    repair_count: int = Field(ge=0, le=1)
    trace_id: str = Field(min_length=1)


class GatewayResponse(StrictModel):
    request_id: str
    response_id: str
    content: str
    structured_output: dict[str, Any] | None = None
    tool_calls: tuple[ToolInvocation, ...] = ()
    finish_reason: str
    usage: ModelUsage | None
    usage_unavailable_reason: str | None = None
    route: RouteMetadata

    @model_validator(mode="after")
    def usage_is_attributed_or_typed_unavailable(self) -> GatewayResponse:
        if (self.usage is None) == (self.usage_unavailable_reason is None):
            raise ValueError("exactly one of usage or usage_unavailable_reason is required")
        return self


class GatewayChunk(StrictModel):
    request_id: str
    sequence: int = Field(ge=0)
    delta: str = ""
    tool_call_delta: str = ""
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    route: RouteMetadata
