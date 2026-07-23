"""Channel-neutral model gateway with explicit routing and failure semantics."""

from faultwitness.models.catalog import CapabilityCatalog, ModelProfile, RoutePolicy
from faultwitness.models.channel import OpenAICompatibleChannel
from faultwitness.models.gateway import ModelGateway
from faultwitness.models.types import (
    ChannelName,
    GatewayChunk,
    GatewayResponse,
    ModelCapability,
    ModelFailure,
    ModelFailureCode,
    PartialModelFailure,
    RouteMetadata,
    ToolInvocation,
)

__all__ = [
    "CapabilityCatalog",
    "ChannelName",
    "GatewayChunk",
    "GatewayResponse",
    "ModelCapability",
    "ModelFailure",
    "ModelFailureCode",
    "ModelGateway",
    "ModelProfile",
    "OpenAICompatibleChannel",
    "PartialModelFailure",
    "RouteMetadata",
    "RoutePolicy",
    "ToolInvocation",
]
