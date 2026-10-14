"""Mock Source Adapter for Testing High-Throughput Streams, Bursts, and Edge Cases."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from entorhinal.schemas.models import RawSignalEvent, SourceType, generate_uuidv7
from entorhinal.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)


class MockSourceAdapter(BaseSourceAdapter):
    """High-throughput synthetic signal generator for unit tests, chaos benchmarks, and fuzzing."""

    def __init__(
        self,
        adapter_id: str = "mock.source.generator",
        source_type: SourceType = SourceType.OS_WINDOW,
        max_buffer_size: int = 20000,
    ) -> None:
        super().__init__(max_buffer_size=max_buffer_size)
        self._adapter_id = adapter_id
        self._source_type = source_type

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def source_type(self) -> SourceType:
        return self._source_type

    async def generate_burst(
        self,
        count: int,
        source_type: Optional[SourceType] = None,
        app_name: str = "TestEditor",
        window_title_prefix: str = "Document",
        payload_factory: Optional[Callable[[int], Dict[str, Any]]] = None,
    ) -> List[RawSignalEvent]:
        """Generate a synchronous burst of N events and push to internal buffer."""
        events: List[RawSignalEvent] = []
        st = source_type or self.source_type

        for i in range(count):
            payload = payload_factory(i) if payload_factory else {"index": i, "data": f"item-{i}"}
            event = RawSignalEvent(
                signal_id=generate_uuidv7(),
                source_type=st,
                adapter_id=self.adapter_id,
                captured_at=datetime.now(timezone.utc),
                app_identifier=app_name,
                window_title=f"{window_title_prefix} {i}",
                target_uri=f"file:///workspace/doc_{i}.py",
                raw_payload=payload,
                metadata={"burst_index": i},
            )
            await self.emit_signal(event)
            events.append(event)

        return events

    async def generate_identical_stream(
        self,
        count: int,
        app_name: str = "VSCode",
        window_title: str = "entorhinal - main.py",
        target_uri: str = "file:///workspace/main.py",
        interval_seconds: float = 0.001,
    ) -> List[RawSignalEvent]:
        """Generate N identical rapid events to test temporal smoother & debouncer."""
        events: List[RawSignalEvent] = []
        for i in range(count):
            event = RawSignalEvent(
                signal_id=generate_uuidv7(),
                source_type=self.source_type,
                adapter_id=self.adapter_id,
                app_identifier=app_name,
                window_title=window_title,
                target_uri=target_uri,
                raw_payload={"action": "cursor_move", "line": 42},
                metadata={"iteration": i},
            )
            await self.emit_signal(event)
            events.append(event)
            if interval_seconds > 0:
                await asyncio.sleep(interval_seconds)
        return events

    async def stream_generator(
        self,
        rate_per_sec: float,
        total_events: int,
        app_name: str = "StreamApp",
    ) -> AsyncIterator[RawSignalEvent]:
        """Stream events asynchronously at a targeted events/sec rate."""
        delay = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        for i in range(total_events):
            event = RawSignalEvent(
                signal_id=generate_uuidv7(),
                source_type=self.source_type,
                adapter_id=self.adapter_id,
                app_identifier=app_name,
                window_title=f"Stream Window {i}",
                target_uri=f"https://example.com/item/{i}",
                raw_payload={"stream_seq": i},
                metadata={},
            )
            await self.emit_signal(event)
            yield event
            if delay > 0:
                await asyncio.sleep(delay)
