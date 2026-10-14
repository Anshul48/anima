"""Reflex Trace Bridge.

Non-blocking, loss-tolerant episodic memory and telemetry exporter connecting
Reflex to the Trace self-organizing episodic memory backend (http://127.0.0.1:4150).

Enforces:
1. Client-side privacy redaction before queueing or transmission.
2. In-memory ring buffer with drop-oldest overflow policy (default 1000 items).
3. Non-blocking asynchronous record_transition path (zero action path blocking).
4. Background batched spooling with loss tolerance.
5. Full implementation of MemoryPort port interface.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import json
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional
import urllib.error
import urllib.request

from reflex.episodes.redactor import PrivacyRedactor
from reflex.integrations.bridges.config import EcosystemIntegrationConfig
from reflex.ports.memory import MemoryPort
from reflex.schemas.memory import MotorSkill, TransitionTuple

logger = logging.getLogger(__name__)


@dataclass
class TraceBridgeMetrics:
    """Telemetry counters for Trace memory bridge operations."""
    total_recorded: int = 0
    dropped_count: int = 0
    exported_count: int = 0
    failed_export_count: int = 0
    batch_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_recorded": self.total_recorded,
            "dropped_count": self.dropped_count,
            "exported_count": self.exported_count,
            "failed_export_count": self.failed_export_count,
            "batch_count": self.batch_count,
        }


# Type alias for custom HTTP transport callable
TraceHttpTransport = Callable[[str, List[Dict[str, Any]], Dict[str, str], float], Awaitable[Dict[str, Any]]]


class TraceBridge(MemoryPort):
    """Asynchronous, loss-tolerant telemetry and memory export adapter for Trace."""

    def __init__(
        self,
        config: Optional[EcosystemIntegrationConfig] = None,
        redactor: Optional[PrivacyRedactor] = None,
        transport: Optional[TraceHttpTransport] = None,
    ) -> None:
        self.config = config or EcosystemIntegrationConfig()
        self.redactor = redactor or (PrivacyRedactor() if self.config.auto_redact else None)
        self._transport = transport

        # In-memory ring buffer
        self._capacity = max(1, self.config.trace_buffer_capacity)
        self._buffer: Deque[TransitionTuple] = deque()
        self._lock = threading.RLock()

        # In-memory motor skill storage
        self._skills_by_id: Dict[str, MotorSkill] = {}
        self._skills_by_preconditions: Dict[str, List[MotorSkill]] = {}

        # Background flusher task
        self._flusher_task: Optional[asyncio.Task] = None
        self._running = False

        # Metrics
        self.metrics = TraceBridgeMetrics()

    @property
    def buffer_size(self) -> int:
        """Current number of transitions in the ring buffer."""
        with self._lock:
            return len(self._buffer)

    @property
    def dropped_count(self) -> int:
        """Total number of transitions dropped due to buffer overflow."""
        return self.metrics.dropped_count

    @property
    def exported_count(self) -> int:
        """Total number of transitions successfully exported to Trace."""
        return self.metrics.exported_count

    @property
    def failed_export_count(self) -> int:
        """Total number of transitions that failed export."""
        return self.metrics.failed_export_count

    def clear_buffer(self) -> None:
        """Clears in-memory ring buffer."""
        with self._lock:
            self._buffer.clear()

    async def start(self) -> None:
        """Starts the background telemetry spooler task."""
        if self._running or not self.config.trace_enabled:
            return
        self._running = True
        self._flusher_task = asyncio.create_task(self._flusher_loop())

    async def close(self) -> None:
        """Shuts down background flusher and performs final flush attempt."""
        self._running = False
        if self._flusher_task is not None:
            self._flusher_task.cancel()
            try:
                await self._flusher_task
            except asyncio.CancelledError:
                pass
            self._flusher_task = None

        if self.config.trace_enabled and len(self._buffer) > 0:
            await self.flush_now()

    async def record_transition(self, transition: TransitionTuple) -> None:
        """Asynchronously enqueues a redacted transition tuple into the ring buffer.

        Execution is sub-millisecond and never blocks action execution or verification.
        """
        self.metrics.total_recorded += 1

        if not self.config.trace_enabled or (not self.config.trace_endpoint and self._transport is None):
            return

        # Client-side secret & PII redaction
        if self.config.auto_redact and self.redactor is not None:
            tx = self.redactor.redact_transition(transition)
        else:
            tx = transition

        # Enqueue with drop-oldest overflow policy
        with self._lock:
            if len(self._buffer) >= self._capacity:
                self._buffer.popleft()
                self.metrics.dropped_count += 1
            self._buffer.append(tx)

    async def _flusher_loop(self) -> None:
        """Periodic background flusher coroutine."""
        interval_sec = max(0.05, self.config.trace_flush_interval_ms / 1000.0)
        while self._running:
            try:
                await asyncio.sleep(interval_sec)
                if len(self._buffer) > 0:
                    await self.flush_now()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Trace flusher loop error: %s", e)

    async def flush_now(self) -> int:
        """Drains pending buffer and flushes in batches to Trace endpoint.

        Returns total number of transitions successfully exported.
        """
        if not self.config.trace_enabled or (not self.config.trace_endpoint and self._transport is None):
            return 0

        # Drain batch from buffer
        with self._lock:
            if not self._buffer:
                return 0
            batch_size = min(len(self._buffer), self.config.trace_batch_size)
            batch: List[TransitionTuple] = [self._buffer.popleft() for _ in range(batch_size)]

        if not batch:
            return 0

        endpoint_url = f"{self.config.trace_endpoint.rstrip('/')}{self.config.trace_transitions_path}"
        payload = [tx.to_dict() for tx in batch]
        headers = dict(self.config.extra_headers)
        timeout_sec = max(0.1, self.config.trace_timeout_ms / 1000.0)

        try:
            if self._transport is not None:
                await self._transport(endpoint_url, payload, headers, timeout_sec)
            else:
                await asyncio.to_thread(self._sync_http_post_batch, endpoint_url, payload, headers, timeout_sec)

            self.metrics.exported_count += len(batch)
            self.metrics.batch_count += 1
            return len(batch)

        except Exception as e:
            logger.warning("Trace telemetry export failed for batch of %d items: %s", len(batch), e)
            self.metrics.failed_export_count += len(batch)
            # Under loss tolerance policy, failed items are recorded as failed
            # without disrupting execution.
            return 0

    @staticmethod
    def _sync_http_post_batch(
        url: str,
        payload: List[Dict[str, Any]],
        headers: Dict[str, str],
        timeout_sec: float,
    ) -> Dict[str, Any]:
        """Synchronous HTTP POST batch executed in worker thread."""
        body_bytes = json.dumps({"transitions": payload, "count": len(payload)}).encode("utf-8")
        req_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Reflex-Trace-Bridge/1.0",
        }
        req_headers.update(headers)

        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            status_code = resp.status
            if status_code < 200 or status_code >= 300:
                raise urllib.error.HTTPError(url, status_code, f"HTTP Error {status_code}", resp.headers, None)
            resp_body = resp.read().decode("utf-8")
            return json.loads(resp_body) if resp_body else {"status": "ok"}

    # =========================================================================
    # MemoryPort Interface Implementations
    # =========================================================================

    async def get_episode_transitions(self, episode_id: str) -> List[TransitionTuple]:
        """Retrieves matching transitions currently buffered in memory."""
        with self._lock:
            return [tx for tx in self._buffer if tx.episode_id == episode_id]

    async def find_transitions_by_state(self, state_hash: str) -> List[TransitionTuple]:
        """Retrieves matching transitions originating from a specific state hash."""
        with self._lock:
            return [tx for tx in self._buffer if tx.ui_state_hash == state_hash]

    async def save_skill(self, skill: MotorSkill) -> None:
        """Saves a compiled motor skill in local cache."""
        self._skills_by_id[skill.skill_id] = skill
        pre_list = self._skills_by_preconditions.setdefault(skill.preconditions_hash, [])
        for idx, item in enumerate(pre_list):
            if item.skill_id == skill.skill_id:
                pre_list[idx] = skill
                break
        else:
            pre_list.append(skill)

    async def record_skill(self, skill: MotorSkill) -> None:
        """Alias for save_skill."""
        await self.save_skill(skill)

    async def get_skill(self, skill_id: str) -> Optional[MotorSkill]:
        """Retrieves a motor skill by ID."""
        return self._skills_by_id.get(skill_id)

    async def find_skills_by_preconditions(self, preconditions_hash: str) -> List[MotorSkill]:
        """Retrieves motor skills matching preconditions hash."""
        return list(self._skills_by_preconditions.get(preconditions_hash, []))

    async def list_skills(self) -> List[MotorSkill]:
        """Lists all cached motor skills."""
        return list(self._skills_by_id.values())

    async def check_health(self) -> Dict[str, Any]:
        """Queries health status of Trace backend."""
        if not self.config.trace_enabled or (not self.config.trace_endpoint and self._transport is None):
            return {
                "status": "DISABLED",
                "enabled": False,
                "buffer_size": self.buffer_size,
                "dropped_count": self.dropped_count,
                "exported_count": self.exported_count,
                "failed_export_count": self.failed_export_count,
                "metrics": self.metrics.to_dict(),
            }

        health_url = f"{self.config.trace_endpoint.rstrip('/')}{self.config.trace_health_path}"
        t_start = time.time()
        try:
            if self._transport is not None:
                await self._transport(health_url, [], dict(self.config.extra_headers), 0.5)
            else:
                await asyncio.to_thread(self._sync_http_get, health_url, dict(self.config.extra_headers), 0.5)
            latency_ms = (time.time() - t_start) * 1000.0
            return {
                "status": "HEALTHY",
                "enabled": True,
                "latency_ms": round(latency_ms, 2),
                "buffer_size": self.buffer_size,
                "dropped_count": self.dropped_count,
                "exported_count": self.exported_count,
                "failed_export_count": self.failed_export_count,
                "metrics": self.metrics.to_dict(),
            }
        except Exception as e:
            return {
                "status": "UNAVAILABLE",
                "enabled": True,
                "error": str(e),
                "buffer_size": self.buffer_size,
                "dropped_count": self.dropped_count,
                "exported_count": self.exported_count,
                "failed_export_count": self.failed_export_count,
                "metrics": self.metrics.to_dict(),
            }

    @staticmethod
    def _sync_http_get(url: str, headers: Dict[str, str], timeout_sec: float) -> Dict[str, Any]:
        """Synchronous HTTP GET for health checks."""
        req_headers = {"Accept": "application/json", "User-Agent": "Reflex-Trace-Bridge/1.0"}
        req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {"status": "ok"}


# Alias for backward/plan compatibility
TraceMemoryAdapter = TraceBridge
