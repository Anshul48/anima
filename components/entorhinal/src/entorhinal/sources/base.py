"""Base Source Adapter Abstract Contract and Lifecycle Management.

Defines the standard interface for all Entorhinal permitted signal capture adapters:
- OS Window / Process listeners
- Browser DOM / CDP / Extension listeners
- Terminal PTY wrappers
- Mock / Synthetic generators
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from entorhinal.ports.interfaces import SourcePort
from entorhinal.schemas.models import RawSignalEvent, SourceType

logger = logging.getLogger(__name__)


class BaseSourceAdapter(SourcePort, ABC):
    """Standard lifecycle contract and event buffer for all Entorhinal source collectors."""

    def __init__(
        self,
        max_buffer_size: int = 5000,
    ) -> None:
        self._max_buffer_size = max_buffer_size
        self._event_queue: asyncio.Queue[RawSignalEvent] = asyncio.Queue(maxsize=max_buffer_size)
        self._is_running: bool = False
        self._started_at: Optional[datetime] = None
        self._events_captured: int = 0
        self._events_dropped: int = 0
        self._error_count: int = 0
        self._last_error: Optional[str] = None

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this source adapter (e.g. 'browser.chrome.extension')."""
        pass

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Categorical source type produced by this adapter."""
        pass

    async def start(self) -> None:
        """Initialize hooks, listeners, and mark adapter active."""
        if self._is_running:
            return
        self._is_running = True
        self._started_at = datetime.now(timezone.utc)
        logger.info("Source adapter %s started", self.adapter_id)

    async def stop(self) -> None:
        """Gracefully disconnect hooks and stop signal production."""
        if not self._is_running:
            return
        self._is_running = False
        logger.info("Source adapter %s stopped", self.adapter_id)

    def is_healthy(self) -> bool:
        """Check operational health status of the adapter."""
        return self._is_running and self._error_count < 10

    def health_check(self) -> Dict[str, Any]:
        """Return operational health metrics and connection counters."""
        uptime_seconds = 0.0
        if self._started_at and self._is_running:
            uptime_seconds = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        return {
            "adapter_id": self.adapter_id,
            "source_type": self.source_type.value,
            "is_running": self._is_running,
            "is_healthy": self.is_healthy(),
            "uptime_seconds": uptime_seconds,
            "events_captured": self._events_captured,
            "events_dropped": self._events_dropped,
            "queue_size": self._event_queue.qsize(),
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

    async def emit_signal(self, signal: RawSignalEvent) -> bool:
        """Internal/Subclass helper to push a raw event to the memory buffer.

        Applies drop-oldest backpressure if buffer is saturated.
        """
        if not self._is_running:
            return False

        try:
            if self._event_queue.full():
                try:
                    self._event_queue.get_nowait()
                    self._events_dropped += 1
                except asyncio.QueueEmpty:
                    pass
            self._event_queue.put_nowait(signal)
            self._events_captured += 1
            return True
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            logger.error("Failed to emit signal in adapter %s: %s", self.adapter_id, e)
            return False

    async def poll_signals(self) -> List[RawSignalEvent]:
        """Poll all currently queued signals from the volatile buffer without blocking."""
        signals: List[RawSignalEvent] = []
        while not self._event_queue.empty():
            try:
                signals.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return signals

    async def events(self) -> AsyncIterator[RawSignalEvent]:
        """Asynchronous stream of captured, unnormalized raw signal events."""
        while self._is_running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
