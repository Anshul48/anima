"""PEP 544 Protocol for Model Gateway integration."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from sst.gateway.contracts import GatewayRequest, GatewayResponse, ProviderProfile, RouteTarget


@runtime_checkable
class ModelGatewayProtocol(Protocol):
    """Protocol defining the standard interface for model invocation and routing."""

    profiles: dict[str, Any]
    routes: dict[str, Any]

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        """Synchronously invokes a model provider endpoint."""
        ...

    def get_route(self, role: str) -> RouteTarget | None:
        """Retrieves assigned route for a functional role."""
        ...

    def set_route(self, role: str, profile_name: str, model: str) -> None:
        """Assigns a role to a provider profile and model."""
        ...

    def register_profile(self, profile: ProviderProfile) -> None:
        """Registers a provider profile."""
        ...
