"""Concrete memory-provider adapters behind the versioned provider interface.

- :class:`NullMemoryProvider`: explicit "no provider" that reports
  ``UNAVAILABLE`` instead of failing or pretending.
- :class:`TraceLiteDbAdapter`: wraps a duck-typed ``trace_lite_db`` object
  (``query_quad_channel`` / ``query_negative_inhibitors`` / ``query``) so
  legacy callers keep working while gaining availability reporting.
- :class:`StaticMemoryProvider`: serves a fixed list of insight strings
  (CLI wiring, tests, scripted runs).

Channel failures are captured per channel and surfaced via
``ProviderAvailability.last_error``; a query never raises for provider
faults and never returns insights without the availability observed while
fetching them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sst.protocols.memory import (
    MEMORY_PROVIDER_PROTOCOL_VERSION,
    MemoryInsight,
    MemoryProviderProtocol,
    MemoryQueryResult,
    ProviderAvailability,
    ProviderStatus,
)


class NullMemoryProvider:
    """Explicit no-provider implementation reporting UNAVAILABLE."""

    def __init__(self, reason: str = "no memory provider configured") -> None:
        self._reason = reason

    @property
    def provider_name(self) -> str:
        return "none"

    @property
    def adapter_version(self) -> str:
        return MEMORY_PROVIDER_PROTOCOL_VERSION

    def check_availability(self) -> ProviderAvailability:
        return ProviderAvailability(
            provider_name=self.provider_name,
            status=ProviderStatus.UNAVAILABLE,
            last_error=self._reason,
        )

    def query_insights(self, goal: str, limit: int = 5) -> MemoryQueryResult:
        _ = (goal, limit)
        return MemoryQueryResult(insights=[], availability=self.check_availability())


class StaticMemoryProvider:
    """Serves a fixed list of insight strings with AVAILABLE status."""

    def __init__(
        self,
        insights: Sequence[str],
        layer: str = "static",
        evidence_ref_prefix: str = "static",
    ) -> None:
        self._insights = list(insights)
        self._layer = layer
        self._prefix = evidence_ref_prefix

    @property
    def provider_name(self) -> str:
        return "static"

    @property
    def adapter_version(self) -> str:
        return MEMORY_PROVIDER_PROTOCOL_VERSION

    def check_availability(self) -> ProviderAvailability:
        return ProviderAvailability(
            provider_name=self.provider_name,
            status=ProviderStatus.AVAILABLE,
            evidence_refs=[f"{self._prefix}:{i}" for i in range(len(self._insights))],
            insight_count=len(self._insights),
        )

    def query_insights(self, goal: str, limit: int = 5) -> MemoryQueryResult:
        _ = goal
        items = [
            MemoryInsight(
                kind="insight",
                text=text,
                layer=self._layer,
                evidence_ref=f"{self._prefix}:{i}",
            )
            for i, text in enumerate(self._insights[: max(0, limit)])
        ]
        availability = ProviderAvailability(
            provider_name=self.provider_name,
            status=ProviderStatus.AVAILABLE,
            evidence_refs=[it.evidence_ref for it in items],
            insight_count=len(items),
        )
        return MemoryQueryResult(insights=items, availability=availability)


class TraceLiteDbAdapter:
    """Wraps a duck-typed trace-lite db behind :class:`MemoryProviderProtocol`.

    Channel priority matches the legacy compiler behavior
    (``query_quad_channel`` → ``query_negative_inhibitors`` → ``query``):
    the first successful channel supplies the insights. A failing channel
    falls through to the next available one and records its error instead
    of silently yielding nothing.
    """

    def __init__(self, trace_lite_db: Any, provider_name: str = "trace-lite-db") -> None:
        self._db = trace_lite_db
        self._provider_name = provider_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def adapter_version(self) -> str:
        return MEMORY_PROVIDER_PROTOCOL_VERSION

    @property
    def wrapped(self) -> Any:
        """Returns the underlying duck-typed trace-lite db object."""
        return self._db

    def check_availability(self) -> ProviderAvailability:
        if self._db is None:
            return ProviderAvailability(
                provider_name=self.provider_name,
                status=ProviderStatus.UNAVAILABLE,
                last_error="no memory provider configured",
            )
        if not self._known_channels():
            return ProviderAvailability(
                provider_name=self.provider_name,
                status=ProviderStatus.UNAVAILABLE,
                last_error="unsupported trace_lite_db surface: no known query method",
            )
        return ProviderAvailability(
            provider_name=self.provider_name,
            status=ProviderStatus.AVAILABLE,
        )

    def query_insights(self, goal: str, limit: int = 5) -> MemoryQueryResult:
        channels = self._known_channels()
        if self._db is None or not channels:
            availability = self.check_availability()
            return MemoryQueryResult(insights=[], availability=availability)

        insights: list[MemoryInsight] = []
        errors: list[str] = []
        succeeded = False
        for channel in channels:
            try:
                if channel == "quad":
                    insights = self._query_quad_channel(goal, limit)
                elif channel == "inhibitors":
                    insights = self._query_inhibitors(goal)
                elif channel == "query":
                    insights = self._query_generic(goal, limit)
                succeeded = True
                break
            except Exception as exc:
                errors.append(f"{channel}: {exc}")

        if not succeeded:
            availability = ProviderAvailability(
                provider_name=self.provider_name,
                status=ProviderStatus.UNAVAILABLE,
                last_error="; ".join(errors) if errors else "all memory channels failed",
            )
            return MemoryQueryResult(insights=[], availability=availability)

        status = ProviderStatus.DEGRADED if errors else ProviderStatus.AVAILABLE
        availability = ProviderAvailability(
            provider_name=self.provider_name,
            status=status,
            evidence_refs=_dedupe(it.evidence_ref for it in insights if it.evidence_ref),
            last_error="; ".join(errors) if errors else None,
            insight_count=len(insights),
        )
        return MemoryQueryResult(insights=insights, availability=availability)

    def _known_channels(self) -> list[str]:
        if self._db is None:
            return []
        channels: list[str] = []
        if hasattr(self._db, "query_quad_channel"):
            channels.append("quad")
        if hasattr(self._db, "query_negative_inhibitors"):
            channels.append("inhibitors")
        if hasattr(self._db, "query"):
            channels.append("query")
        return channels

    def _query_quad_channel(self, goal: str, limit: int) -> list[MemoryInsight]:
        quad = self._db.query_quad_channel(goal, limit_per_channel=limit)
        if not hasattr(quad, "get"):
            raise TypeError("query_quad_channel must return a channel dict")
        insights: list[MemoryInsight] = []
        for ref in quad.get("ast_structural", []) or []:
            excerpt = str(getattr(ref, "excerpt", ""))
            path = str(getattr(ref, "path", ""))
            insights.append(
                MemoryInsight(
                    kind="interface",
                    text=f"{excerpt} in {path}",
                    layer="ast_structural",
                    path=path,
                    evidence_ref=f"ast_structural:{path}" if path else "ast_structural",
                )
            )
        for ref in (quad.get("raptor_summary", []) or []) + (quad.get("dense_semantic", []) or []):
            layer = str(getattr(ref, "retrieval_layer", "dense_semantic"))
            path = str(getattr(ref, "path", ""))
            excerpt = str(getattr(ref, "excerpt", ""))
            insights.append(
                MemoryInsight(
                    kind="insight",
                    text=f"[{layer}:{path}] {excerpt[:300]}",
                    layer=layer,
                    path=path,
                    evidence_ref=f"{layer}:{path}" if path else layer,
                )
            )
        return insights

    def _query_inhibitors(self, goal: str) -> list[MemoryInsight]:
        inhibitors = self._db.query_negative_inhibitors(goal)
        return [
            MemoryInsight(
                kind="insight",
                text=f"[NEGATIVE_INHIBITOR] {inh}",
                layer="negative_inhibitor",
                evidence_ref=f"negative-inhibitor:{i}",
            )
            for i, inh in enumerate(inhibitors or [])
        ]

    def _query_generic(self, goal: str, limit: int) -> list[MemoryInsight]:
        res = self._db.query(goal, top_k=limit)
        insights: list[MemoryInsight] = []
        if hasattr(res, "evidence"):
            for i, ev in enumerate(res.evidence or []):
                text = str(getattr(ev, "text", str(ev)))
                source = str(getattr(ev, "source_file", ""))
                insights.append(
                    MemoryInsight(
                        kind="insight",
                        text=f"[{source}] {text}" if source else text,
                        layer="evidence",
                        path=source,
                        evidence_ref=source or f"evidence:{i}",
                    )
                )
        elif hasattr(res, "passages"):
            for i, passage in enumerate(res.passages or []):
                insights.append(
                    MemoryInsight(
                        kind="insight",
                        text=str(passage.text),
                        layer="passage",
                        evidence_ref=f"passage:{i}",
                    )
                )
        return insights


def wrap_trace_lite_db(trace_lite_db: Any) -> MemoryProviderProtocol:
    """Wraps a duck-typed trace-lite db in a versioned provider adapter.

    Objects already satisfying :class:`MemoryProviderProtocol` are returned
    unchanged; ``None`` yields a :class:`NullMemoryProvider`.
    """
    if trace_lite_db is None:
        return NullMemoryProvider()
    if isinstance(trace_lite_db, MemoryProviderProtocol):
        return trace_lite_db
    return TraceLiteDbAdapter(trace_lite_db)


def _dedupe(refs: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered
