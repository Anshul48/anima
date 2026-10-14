"""Contracts and schemas for the SST provider model gateway."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"Bearer\s+([a-zA-Z0-9_\.\-]{20,})", re.IGNORECASE),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*([^\s,;]+)"),
]


def redact_text(text: str, known_secrets: list[str] | None = None) -> str:
    """Redacts secrets, API keys, and sensitive tokens from text."""
    if not text:
        return text
    result = text
    if known_secrets:
        for secret in known_secrets:
            if secret and len(secret) >= 4:
                result = result.replace(secret, "***REDACTED***")
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("***REDACTED***", result)
    return result


class ProviderKind(StrEnum):
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"
    TEST = "test"


class SecretRef(BaseModel):
    """Reference naming an entry in the OS secret store. Never contains raw secret data."""

    name: str = Field(description="Name/Key of the secret in the OS credential store")

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"SecretRef(name={self.name!r})"


class ModelCatalogEntry(BaseModel):
    """Entry describing a discovered or custom configured model."""

    id: str
    display_label: str = ""
    capabilities: list[str] = Field(default_factory=list)
    context_window: int | None = None
    custom: bool = False
    refreshed_at: str | None = None


class ModelCatalog(BaseModel):
    """Catalog of available models for a provider profile."""

    models: list[ModelCatalogEntry] = Field(default_factory=list)
    custom_ids: list[str] = Field(default_factory=list)
    fingerprint: str | None = None
    refreshed_at: str | None = None
    last_attempt_at: str | None = None
    last_error: str | None = None


class ProviderProfile(BaseModel):
    """Metadata profile for a local or remote model provider without raw secrets."""

    name: str
    kind: ProviderKind
    api_base: str
    credential_ref: str | None = None
    catalog_source: str = "discovered"
    selected_model: str | None = None
    timeout_seconds: int = 60
    token_cap: int | None = None
    cost_cap_usd: float | None = None
    # Optional USD rates for valid cost accounting. A profile is priced only
    # when BOTH are set; otherwise response costs are unknown (cost_known
    # False) and any USD cap is rejected rather than silently unenforced.
    input_usd_per_1k_tokens: float | None = None
    output_usd_per_1k_tokens: float | None = None
    capabilities: list[str] = Field(default_factory=list)
    last_verified_at: str | None = None
    catalog: ModelCatalog = Field(default_factory=ModelCatalog)
    diagnostic_state: dict[str, Any] = Field(default_factory=dict)


class RouteTarget(BaseModel):
    """Routing target assigning a role to a provider profile and model."""

    profile: str
    model: str


class GatewayRequest(BaseModel):
    """Model invocation request."""

    role: str = ""
    profile_name: str | None = None
    model: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_seconds: int | None = None
    response_schema: dict[str, Any] | None = None


class GatewayResponse(BaseModel):
    """Model invocation response."""

    content: str
    model: str
    profile: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    # True only when cost_usd is valid accounting (priced profile or free
    # fixture). False means the dollar cost is UNKNOWN, not zero.
    cost_known: bool = False
    duration_seconds: float = 0.0
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


# --- Error Hierarchy with Categorized Remediation ---


class ProviderGatewayError(Exception):
    """Base error for all provider gateway operations with redaction and remediation."""

    def __init__(
        self,
        message: str,
        category: str = "gateway_error",
        remediation: str = "Check provider settings and connectivity.",
        status_code: int | None = None,
        profile: str | None = None,
        redacted_details: str | None = None,
    ) -> None:
        self.raw_message = message
        self.message = redact_text(message)
        self.category = category
        self.remediation = remediation
        self.status_code = status_code
        self.profile = profile
        self.redacted_details = redact_text(redacted_details) if redacted_details else None
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [f"[{self.category}] {self.message}"]
        if self.status_code:
            parts.append(f"(Status code: {self.status_code})")
        if self.profile:
            parts.append(f"(Profile: {self.profile})")
        if self.remediation:
            parts.append(f"\nRemediation: {self.remediation}")
        return " ".join(parts)


class UnreachableEndpointError(ProviderGatewayError):
    def __init__(self, message: str, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message,
            category="unreachable_endpoint",
            remediation="Verify endpoint URL is reachable and provider daemon (e.g., Ollama) is running.",
            profile=profile,
            **kwargs,
        )


class AuthenticationError(ProviderGatewayError):
    def __init__(self, message: str, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message,
            category="authentication_failure",
            remediation="Authentication failed. Verify API key or credential.",
            profile=profile,
            **kwargs,
        )


class MissingModelError(ProviderGatewayError):
    def __init__(self, message: str, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message,
            category="missing_model",
            remediation="Requested model does not exist on provider. Check model name or pull it locally.",
            profile=profile,
            **kwargs,
        )


class UnsupportedModelError(ProviderGatewayError):
    def __init__(self, message: str, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message,
            category="unsupported_model",
            remediation="Model does not support requested capability.",
            profile=profile,
            **kwargs,
        )


class RateLimitError(ProviderGatewayError):
    def __init__(self, message: str, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message,
            category="rate_limit",
            remediation="Rate limit or account quota exceeded. Wait before retrying.",
            profile=profile,
            **kwargs,
        )


class MalformedResponseError(ProviderGatewayError):
    def __init__(self, message: str, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message,
            category="malformed_response",
            remediation="Provider returned an unexpected, empty, or unparseable response payload.",
            profile=profile,
            **kwargs,
        )


class TimeoutError(ProviderGatewayError):
    def __init__(self, message: str, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message,
            category="timeout",
            remediation="Request timed out. Increase timeout_seconds or verify latency.",
            profile=profile,
            **kwargs,
        )
