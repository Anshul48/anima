"""CLI wiring for explicit memory providers.

The ``sst run`` command accepts ``--memory-provider``: ``"none"`` (default)
reports that no provider is wired, ``"static"`` serves insights passed via
``--memory-insight``, and any other spec fails closed with a clear error so
a misspelled provider can never silently degrade to none.
"""

from __future__ import annotations

from collections.abc import Sequence

import click

from sst.context.memory_adapter import StaticMemoryProvider
from sst.protocols.memory import MemoryProviderProtocol

NONE_PROVIDER_SPEC: str = "none"
STATIC_PROVIDER_SPEC: str = "static"


def build_memory_provider(
    spec: str | None,
    insights: Sequence[str] | None = None,
) -> MemoryProviderProtocol | None:
    """Builds the memory provider for a CLI spec, or None for ``"none"``.

    Raises:
        click.ClickException: If the spec names an unknown provider.
    """
    normalized = (spec or NONE_PROVIDER_SPEC).strip().lower()
    if normalized == NONE_PROVIDER_SPEC:
        return None
    if normalized == STATIC_PROVIDER_SPEC:
        return StaticMemoryProvider(insights=list(insights or ()))
    raise click.ClickException(
        f"Unknown memory provider spec: '{spec}'. Expected '{NONE_PROVIDER_SPEC}' or '{STATIC_PROVIDER_SPEC}'."
    )


def format_provider_report(provider: MemoryProviderProtocol | None) -> str:
    """Formats the one-line CLI report for the wired (or absent) provider."""
    if provider is None:
        return "Memory provider: none (status=UNAVAILABLE — proceeding without prior insights)"
    availability = provider.check_availability()
    detail = f"adapter={availability.adapter_version}"
    if availability.last_error:
        detail += f" last_error={availability.last_error}"
    return f"Memory provider: {provider.provider_name} (status={availability.status.value} {detail})"
