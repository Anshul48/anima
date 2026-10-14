"""PEP 544 Protocol for tree state persistence and event log storage."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sst.core.events import SSTEvent
from sst.core.models import SSTNode, SSTTree


@runtime_checkable
class TreeStoreProtocol(Protocol):
    """Protocol defining storage operations for append-only events, leases, and trees."""

    def append_event(self, event: SSTEvent) -> int:
        """Appends an event to the append-only event log."""
        ...

    def get_events(self, tree_id: str, since_sequence: int = 0) -> list[SSTEvent]:
        """Retrieves chronological events for a tree."""
        ...

    def rebuild_tree_from_events(self, tree_id: str) -> SSTTree | None:
        """Reconstructs live SSTTree DAG by replaying events."""
        ...

    def save_tree(self, tree: SSTTree) -> None:
        """Persists snapshot of SSTTree."""
        ...

    def save_node(self, node: SSTNode) -> None:
        """Saves or updates a single node."""
        ...

    def load_tree(self, tree_id: str) -> SSTTree | None:
        """Loads an entire tree and its constituent nodes."""
        ...

    def acquire_lease(self, tree_id: str, owner: str, ttl_seconds: int = 60) -> bool:
        """Attempts to acquire or extend an exclusive writer lease."""
        ...

    def release_lease(self, tree_id: str, owner: str) -> None:
        """Releases a held writer lease."""
        ...
