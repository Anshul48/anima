"""Context capsules and architecture evidence providers for SST."""

from .capsule import CapsuleCompileReport, ContextCapsuleCompiler, memory_tree_payload_fragment
from .memory_adapter import (
    NullMemoryProvider,
    StaticMemoryProvider,
    TraceLiteDbAdapter,
    wrap_trace_lite_db,
)
from .provider import ArchitectureEvidence, ContextProvider

__all__ = [
    "ContextCapsuleCompiler",
    "CapsuleCompileReport",
    "memory_tree_payload_fragment",
    "NullMemoryProvider",
    "StaticMemoryProvider",
    "TraceLiteDbAdapter",
    "wrap_trace_lite_db",
    "ArchitectureEvidence",
    "ContextProvider",
]
