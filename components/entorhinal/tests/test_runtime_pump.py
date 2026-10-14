"""F5/F12 regression tests: admission-pump retry, backpressure, visibility.

Covers:
1. Rejected signals are recorded, not retried.
2. Retryable storage failures are retried with backoff until commit.
3. Exhausted retries are dead-lettered and visible (never silently dropped).
4. Failing adapters get poll backoff instead of a hot failure loop.
5. Pump stats are exposed through runtime health.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, List

import pytest

from entorhinal.evidence.receipts import CommitReceipt, CommitState
from entorhinal.runtime.config import RuntimeConfig
from entorhinal.runtime.factory import build_runtime
from entorhinal.schemas.models import RawSignalEvent, SourceType


class _ScriptedAdapter:
    """Minimal fake adapter: scripted signals or poll failures."""

    def __init__(self, signals: List[Any] | None = None, failures: int = 0) -> None:
        self._signals = list(signals or [])
        self._failures = failures
        self.poll_calls = 0

    async def poll_signals(self) -> List[Any]:
        self.poll_calls += 1
        if self._failures > 0:
            self._failures -= 1
            raise IOError("simulated poll failure")
        pending, self._signals = self._signals, []
        return pending


def _make_signal() -> RawSignalEvent:
    return RawSignalEvent(
        source_type=SourceType.BROWSER,
        adapter_id="fake",
        app_identifier="Chrome",
        window_title="Pump Test",
        target_uri="https://example.test/pump",
        raw_payload={"event_type": "focus"},
    )


def _build(tmp_dir: str, **config_kwargs: Any):
    config = RuntimeConfig.from_root(tmp_dir, **config_kwargs)
    return build_runtime(config)


@pytest.mark.asyncio
async def test_pump_records_rejection_without_retry() -> None:
    """F12: policy-rejected signals are counted once, never retried."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = _build(tmp_dir, default_allow=False)
        try:
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals=[_make_signal()])
            await runtime._pump_once()
            stats = runtime.pump_stats()["fake"]
            assert stats["polled"] == 1
            assert stats["rejected"] == 1
            assert stats["retried_attempts"] == 0
            assert stats["committed"] == 0
            assert stats["last_receipt_state"] == CommitState.REJECTED.value
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_pump_retries_retryable_failure_until_commit() -> None:
    """F5: retryable receipts are retried; eventual commit is recorded."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = _build(tmp_dir, default_allow=True)
        try:
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals=[_make_signal()])
            real_commit = runtime.store.commit_event
            calls = {"n": 0}

            async def flaky_commit(*args: Any, **kwargs: Any):
                calls["n"] += 1
                if calls["n"] < 3:
                    return CommitReceipt(
                        state=CommitState.RETRYABLE_STORAGE_FAILURE,
                        source_id="fake",
                        event_id="evt",
                        reason="simulated transient failure",
                    )
                return await real_commit(*args, **kwargs)

            runtime.store.commit_event = flaky_commit  # type: ignore[method-assign]
            await runtime._pump_once()
            stats = runtime.pump_stats()["fake"]
            assert calls["n"] == 3
            assert stats["retried_attempts"] == 2
            assert stats["committed"] == 1
            assert stats["dead_lettered"] == 0
            assert stats["last_receipt_state"] in (
                CommitState.COMMITTED_PROJECTED.value,
                CommitState.COMMITTED_PENDING_DEGRADED.value,
            )
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_pump_dead_letters_exhausted_retries() -> None:
    """F5/F12: persistent retryable failure is dead-lettered, never dropped silently."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = _build(tmp_dir, default_allow=True)
        try:
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals=[_make_signal()])

            async def always_retryable(*args: Any, **kwargs: Any):
                return CommitReceipt(
                    state=CommitState.RETRYABLE_STORAGE_FAILURE,
                    source_id="fake",
                    event_id="evt",
                    reason="disk wedged",
                )

            runtime.store.commit_event = always_retryable  # type: ignore[method-assign]
            await runtime._pump_once()
            stats = runtime.pump_stats()["fake"]
            assert stats["retried_attempts"] == 2  # 3 attempts, 2 inter-attempt sleeps
            assert stats["retryable_exhausted"] == 1
            assert stats["dead_lettered"] == 1
            assert stats["committed"] == 0
            assert "wedged" in (stats["last_error"] or "")
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_pump_backs_off_failing_adapter() -> None:
    """F12: poll failures back off instead of hot-looping; recovery clears."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = _build(tmp_dir)
        try:
            adapter = _ScriptedAdapter(failures=100)
            runtime.sources._adapters["fake"] = adapter
            await runtime._pump_once()
            await runtime._pump_once()
            stats = runtime.pump_stats()["fake"]
            assert stats["poll_failures"] == 1
            assert stats["consecutive_poll_failures"] == 1
            assert stats["polls_backed_off"] == 1
            assert adapter.poll_calls == 1

            # Backoff expiry + healthy poll clears the consecutive counter.
            runtime._pump_poll_backoff.clear()
            adapter._failures = 0
            await runtime._pump_once()
            stats = runtime.pump_stats()["fake"]
            assert stats["consecutive_poll_failures"] == 0
            assert adapter.poll_calls == 2
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_pump_stats_exposed_in_health() -> None:
    """F12: health() carries the pump section with per-source outcomes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = _build(tmp_dir, default_allow=False)
        try:
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals=[_make_signal()])
            await runtime._pump_once()
            health = runtime.health()
            assert health["pump"]["running"] is False
            assert health["pump"]["sources"]["fake"]["rejected"] == 1
        finally:
            runtime.close()
