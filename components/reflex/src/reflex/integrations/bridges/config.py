"""Reflex Ecosystem Bridges Configuration.

Feature flags, timeout budgets, endpoints, and buffer parameters for optional
external adapters (Entorhinal personal context and Trace episodic memory).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class EcosystemIntegrationConfig:
    """Feature flags and endpoint configuration for external ecosystem bridges."""

    # Entorhinal (Personal context layer)
    entorhinal_enabled: bool = False
    entorhinal_endpoint: str = ""
    entorhinal_snapshot_path: str = "/context/snapshot"
    entorhinal_health_path: str = "/health"
    entorhinal_timeout_ms: float = 100.0  # Strict <=100ms latency budget
    entorhinal_cache_ttl_ms: float = 60000.0  # 1 minute local TTL
    entorhinal_circuit_breaker_threshold: int = 3  # 3 consecutive timeouts/failures
    entorhinal_circuit_breaker_reset_ms: float = 30000.0  # 30s half-open cooldown

    # Trace (Episodic long-term memory)
    trace_enabled: bool = False
    trace_endpoint: str = ""
    trace_transitions_path: str = "/telemetry/transitions"
    trace_health_path: str = "/health"
    trace_batch_size: int = 50
    trace_buffer_capacity: int = 1000  # Default 1000 items in-memory ring buffer
    trace_flush_interval_ms: float = 1000.0  # 1s periodic background flush
    trace_timeout_ms: float = 2000.0
    trace_drop_oldest: bool = True

    # Security & Redaction
    auto_redact: bool = True
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entorhinal_enabled": self.entorhinal_enabled,
            "entorhinal_endpoint": self.entorhinal_endpoint,
            "entorhinal_snapshot_path": self.entorhinal_snapshot_path,
            "entorhinal_health_path": self.entorhinal_health_path,
            "entorhinal_timeout_ms": self.entorhinal_timeout_ms,
            "entorhinal_cache_ttl_ms": self.entorhinal_cache_ttl_ms,
            "entorhinal_circuit_breaker_threshold": self.entorhinal_circuit_breaker_threshold,
            "entorhinal_circuit_breaker_reset_ms": self.entorhinal_circuit_breaker_reset_ms,
            "trace_enabled": self.trace_enabled,
            "trace_endpoint": self.trace_endpoint,
            "trace_transitions_path": self.trace_transitions_path,
            "trace_health_path": self.trace_health_path,
            "trace_batch_size": self.trace_batch_size,
            "trace_buffer_capacity": self.trace_buffer_capacity,
            "trace_flush_interval_ms": self.trace_flush_interval_ms,
            "trace_timeout_ms": self.trace_timeout_ms,
            "trace_drop_oldest": self.trace_drop_oldest,
            "auto_redact": self.auto_redact,
            "extra_headers": dict(self.extra_headers),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EcosystemIntegrationConfig:
        return cls(
            entorhinal_enabled=bool(data.get("entorhinal_enabled", False)),
            entorhinal_endpoint=str(data.get("entorhinal_endpoint", "")),
            entorhinal_snapshot_path=str(data.get("entorhinal_snapshot_path", "/context/snapshot")),
            entorhinal_health_path=str(data.get("entorhinal_health_path", "/health")),
            entorhinal_timeout_ms=float(data.get("entorhinal_timeout_ms", 100.0)),
            entorhinal_cache_ttl_ms=float(data.get("entorhinal_cache_ttl_ms", 60000.0)),
            entorhinal_circuit_breaker_threshold=int(data.get("entorhinal_circuit_breaker_threshold", 3)),
            entorhinal_circuit_breaker_reset_ms=float(data.get("entorhinal_circuit_breaker_reset_ms", 30000.0)),
            trace_enabled=bool(data.get("trace_enabled", False)),
            trace_endpoint=str(data.get("trace_endpoint", "")),
            trace_transitions_path=str(data.get("trace_transitions_path", "/telemetry/transitions")),
            trace_health_path=str(data.get("trace_health_path", "/health")),
            trace_batch_size=int(data.get("trace_batch_size", 50)),
            trace_buffer_capacity=int(data.get("trace_buffer_capacity", 1000)),
            trace_flush_interval_ms=float(data.get("trace_flush_interval_ms", 1000.0)),
            trace_timeout_ms=float(data.get("trace_timeout_ms", 2000.0)),
            trace_drop_oldest=bool(data.get("trace_drop_oldest", True)),
            auto_redact=bool(data.get("auto_redact", True)),
            extra_headers=dict(data.get("extra_headers", {})),
        )
