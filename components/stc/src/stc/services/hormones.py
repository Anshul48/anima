"""In-memory Scoped Pub/Sub Hormone Bus implementation."""

from __future__ import annotations

from collections import defaultdict, deque

from stc.protocols.interfaces import HormoneBusProtocol
from stc.schemas.hormones import HormoneEvent


class ScopedHormoneBus(HormoneBusProtocol):
    """Deterministic in-memory scoped hormone message bus.

    Enforces cell-level isolation and explicit topic/channel addressing to
    prevent global broadcast storms across subagent populations.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, set[str]] = defaultdict(set)
        self._pending_queues: defaultdict[str, deque[HormoneEvent]] = defaultdict(deque)

    def subscribe(self, subsystem_id: str, topics: list[str] | None = None) -> None:
        """Register a subsystem receptor on specific topics."""
        if topics is None:
            self._subscriptions[subsystem_id].add("*")
        else:
            for t in topics:
                self._subscriptions[subsystem_id].add(t)

    def publish(self, event: HormoneEvent) -> str:
        """Publish a typed hormone event to its scoped target channel.

        Only delivers to subsystems that are explicitly listed in
        `event.scope.target_subsystems` AND have a matching subscribed topic.
        """
        for target in event.scope.target_subsystems:
            subscribed_topics = self._subscriptions.get(target, set())
            if "*" in subscribed_topics or event.scope.topic in subscribed_topics:
                self._pending_queues[target].append(event)
        return event.event_id

    def poll_events(self, subsystem_id: str, max_events: int = 10) -> list[HormoneEvent]:
        """Retrieve pending scoped events addressed to this subsystem."""
        queue = self._pending_queues[subsystem_id]
        events: list[HormoneEvent] = []
        while queue and len(events) < max_events:
            events.append(queue.popleft())
        return events
