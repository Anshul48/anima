"""Model gateway contracts, backends, and multi-provider router."""

from .backends import SSTLLMClient
from .contracts import (
    AuthenticationError,
    GatewayRequest,
    GatewayResponse,
    MalformedResponseError,
    MissingModelError,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderGatewayError,
    ProviderKind,
    ProviderProfile,
    RateLimitError,
    RouteTarget,
    SecretRef,
    TimeoutError,
    UnreachableEndpointError,
    UnsupportedModelError,
    redact_text,
)
from .gateway import ModelGateway, SSTModelGateway

__all__ = [
    "ModelGateway",
    "SSTModelGateway",
    "SSTLLMClient",
    "GatewayRequest",
    "GatewayResponse",
    "ProviderProfile",
    "ProviderKind",
    "RouteTarget",
    "SecretRef",
    "ModelCatalog",
    "ModelCatalogEntry",
    "ProviderGatewayError",
    "UnreachableEndpointError",
    "AuthenticationError",
    "MissingModelError",
    "UnsupportedModelError",
    "RateLimitError",
    "MalformedResponseError",
    "TimeoutError",
    "redact_text",
]
