from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import time


class ClockPort(ABC):
    """Abstract port for monotonic time, epoch time, and deterministic scheduling."""

    @abstractmethod
    def now_ms(self) -> float:
        """Current epoch timestamp in milliseconds."""
        ...

    @abstractmethod
    def monotonic_ms(self) -> float:
        """Current monotonic timestamp in milliseconds."""
        ...

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Asynchronously pause execution for specified seconds."""
        ...


class SystemClock(ClockPort):
    """Real system clock implementation backed by standard Python time and asyncio."""

    def now_ms(self) -> float:
        return time.time() * 1000.0

    def monotonic_ms(self) -> float:
        return time.monotonic() * 1000.0

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class DeterministicClock(ClockPort):
    """Deterministic simulated clock for tests and replay verification."""

    def __init__(self, start_time_ms: float = 1000000.0):
        self._current_time_ms = start_time_ms

    def now_ms(self) -> float:
        return self._current_time_ms

    def monotonic_ms(self) -> float:
        return self._current_time_ms

    def advance(self, ms: float) -> None:
        """Advances simulated clock by ms milliseconds."""
        self._current_time_ms += ms

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds * 1000.0)
