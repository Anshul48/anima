"""Source adapter registry and lifecycle management.

The daemon starts/stops the configured source adapters and exposes actual
producer health (adapter running state, heartbeat/cursor state, lag, pending
counts, gaps) - never a bare enabled flag or process-existence proxy.

Sibling workers register real adapters (e.g. the dev-task inbox tailer) via
``register_adapter``; the lifecycle below drives any ``SourcePort``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from entorhinal.ports.interfaces import SourcePort
from entorhinal.runtime.config import SourceSpec

logger = logging.getLogger(__name__)

AdapterFactory = Callable[[SourceSpec], SourcePort]

# Durable per-source stop records (F11). The lifecycle persists explicit
# stop_source() calls here so a stop survives daemon restarts; the admission
# pump reloads the file so one-shot CLI stop/start takes effect on a running
# daemon without IPC.
STOPPED_RECORDS_FILENAME = "sources_stopped.json"

_ADAPTER_REGISTRY: Dict[str, AdapterFactory] = {}


def register_adapter(key: str, factory: AdapterFactory) -> None:
    """Register a source adapter factory under a registry key."""
    _ADAPTER_REGISTRY[key] = factory


def registered_adapters() -> List[str]:
    return sorted(_ADAPTER_REGISTRY)


def create_adapter(spec: SourceSpec) -> SourcePort:
    try:
        factory = _ADAPTER_REGISTRY[spec.adapter]
    except KeyError:
        raise KeyError(
            f"unknown source adapter {spec.adapter!r}; registered: {registered_adapters()}"
        )
    return factory(spec)


class SourceLifecycle:
    """Owns start/stop/health for the configured source adapters."""

    def __init__(
        self,
        specs: List[SourceSpec],
        storage_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self._specs = [s for s in specs if s.enabled]
        self._adapters: Dict[str, SourcePort] = {}
        self._stopped: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._started_at: Optional[datetime] = None
        self._storage_path = Path(storage_path) if storage_path else None
        self._stopped_mtime: Optional[float] = None
        self._stopped_corrupt: Optional[str] = None
        self._load_stopped()

    @property
    def specs(self) -> List[SourceSpec]:
        return list(self._specs)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Durable stop records (F11)
    # ------------------------------------------------------------------

    def _load_stopped(self) -> None:
        """Load persisted stop records; a corrupt file is disclosed, not fatal."""
        if self._storage_path is None:
            return
        try:
            raw = self._storage_path.read_bytes()
        except FileNotFoundError:
            self._stopped_mtime = None
            return
        except OSError as e:
            logger.error("Cannot read stopped-source records: %s", e)
            self._stopped_corrupt = f"unreadable: {e}"
            return
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            logger.error("Stopped-source records corrupt, ignoring: %s", e)
            self._stopped_corrupt = f"corrupt json: {e}"
            return
        if not isinstance(data, dict):
            self._stopped_corrupt = "corrupt shape: top level is not an object"
            return
        loaded: Dict[str, Dict[str, Any]] = {}
        for name, info in data.items():
            if isinstance(info, dict):
                loaded[str(name)] = dict(info)
        self._stopped = loaded
        self._stopped_corrupt = None
        try:
            self._stopped_mtime = self._storage_path.stat().st_mtime
        except OSError:
            self._stopped_mtime = None

    def _persist_stopped(self) -> None:
        """Atomically persist the current stop records (best effort, logged)."""
        if self._storage_path is None:
            return
        path = self._storage_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self._stopped, handle, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            try:
                self._stopped_mtime = path.stat().st_mtime
            except OSError:
                self._stopped_mtime = None
            self._stopped_corrupt = None
        except OSError as e:
            logger.error("Cannot persist stopped-source records: %s", e)

    def _spec_by_name(self, name: str) -> SourceSpec:
        for spec in self._specs:
            if spec.name == name:
                return spec
        raise ValueError(
            f"unknown source {name!r}; configured: {[s.name for s in self._specs]}"
        )

    async def start(self) -> None:
        if self._running:
            return
        started: List[str] = []
        try:
            for spec in self._specs:
                if spec.name in self._stopped:
                    # Explicitly stopped sources stay stopped across restarts
                    # until start_source() re-enables them.
                    continue
                adapter = create_adapter(spec)
                await adapter.start()
                self._adapters[spec.name] = adapter
                started.append(spec.name)
                logger.info("Source %s (adapter=%s) started", spec.name, spec.adapter)
        except Exception:
            # Atomic start: roll back already-started adapters so a partial
            # failure never leaves running adapters untracked.
            for name in started:
                adapter = self._adapters.pop(name, None)
                if adapter is not None:
                    try:
                        await adapter.stop()
                    except Exception as e:
                        logger.error("Rollback stop failed for source %s: %s", name, e)
            raise
        self._running = True
        self._started_at = datetime.now(timezone.utc)

    async def stop(self) -> None:
        for name, adapter in list(self._adapters.items()):
            try:
                await adapter.stop()
            except Exception as e:
                logger.error("Error stopping source %s: %s", name, e)
        self._adapters.clear()
        self._running = False

    async def stop_source(self, name: str, reason: str = "") -> Dict[str, Any]:
        """Halt one source: stop its adapter and freeze it out of the pump.

        The adapter is removed from the active set (the pump iterates
        :meth:`adapters`, so a stopped source is never polled) and the stop
        is recorded with reason + timestamp for health disclosure. Stopped
        sources stay stopped across :meth:`start` until :meth:`start_source`.
        Halt cooperation inside the adapter (freeze cursor, no advance while
        stopped) is the adapter builder's contract (N5).
        """
        self._spec_by_name(name)  # raises ValueError when unknown
        adapter = self._adapters.pop(name, None)
        if adapter is not None:
            try:
                await adapter.stop()
            except Exception:
                # Keep tracking a source we failed to halt: dropping it would
                # lie about its running state.
                self._adapters[name] = adapter
                raise
        stopped_at = datetime.now(timezone.utc)
        self._stopped[name] = {"reason": reason, "stopped_at": stopped_at.isoformat()}
        self._persist_stopped()
        logger.info("Source %s stopped: %s", name, reason or "no reason given")
        return {"name": name, "stopped": True, "reason": reason,
                "stopped_at": stopped_at.isoformat(),
                "durable": self._storage_path is not None}

    async def start_source(self, name: str) -> Dict[str, Any]:
        """(Re)start one configured source and clear its stopped record."""
        spec = self._spec_by_name(name)  # raises ValueError when unknown
        if name in self._adapters:
            return {"name": name, "started": False, "state": "already-running"}
        adapter = create_adapter(spec)
        await adapter.start()
        self._adapters[name] = adapter
        self._stopped.pop(name, None)
        self._persist_stopped()
        logger.info("Source %s (adapter=%s) started", name, spec.adapter)
        return {"name": name, "started": True, "state": "running"}

    def stopped_sources(self) -> Dict[str, Dict[str, Any]]:
        """Return a copy of the per-source stopped records."""
        return {name: dict(info) for name, info in self._stopped.items()}

    def record_stop(self, name: str, reason: str = "") -> Dict[str, Any]:
        """Write one source's durable stop record without touching adapters.

        One-shot CLI ``sources stop`` uses this: the CLI process runs no
        adapters, so there is nothing to halt in-process. No spec validation
        (serve-time specs are not persisted); a running daemon applies the
        record to its live adapter on the next pump tick and ignores records
        for unconfigured sources.
        """
        stopped_at = datetime.now(timezone.utc)
        self._stopped[name] = {"reason": reason, "stopped_at": stopped_at.isoformat()}
        self._persist_stopped()
        logger.info("Source %s stop recorded: %s", name, reason or "no reason given")
        return {"name": name, "stopped": True, "reason": reason,
                "stopped_at": stopped_at.isoformat(),
                "durable": self._storage_path is not None}

    def clear_stop_record(self, name: str) -> Dict[str, Any]:
        """Clear one source's durable stop record without starting an adapter.

        One-shot CLI ``sources start`` uses this: it must not construct or
        start an adapter in the CLI process. A running daemon restarts the
        source on its next pump tick (see :meth:`sync_stopped_with_adapters`);
        otherwise the source starts on the next daemon start. No spec
        validation, mirroring :meth:`record_stop`.
        """
        had_record = self._stopped.pop(name, None) is not None
        self._persist_stopped()
        logger.info("Source %s stop record cleared (had_record=%s)", name, had_record)
        return {"name": name, "stop_cleared": had_record}

    def _stopped_file_changed(self) -> bool:
        """Whether the durable stop file changed since the last load/persist."""
        if self._storage_path is None:
            return False
        try:
            mtime = self._storage_path.stat().st_mtime
        except FileNotFoundError:
            return self._stopped_mtime is not None or bool(self._stopped)
        except OSError:
            return False
        return self._stopped_mtime is None or mtime != self._stopped_mtime

    async def sync_stopped_with_adapters(self) -> Dict[str, Any]:
        """Apply external stop-file changes to live adapters (pump-driven).

        A one-shot CLI writes stop/start records to the shared runtime root;
        the running daemon's pump calls this each tick so the change takes
        effect without IPC or restart. Stops halt live adapters; cleared
        records restart configured sources. Returns measured counts.
        """
        outcome: Dict[str, Any] = {"reloaded": False, "stopped": [], "started": [],
                                   "errors": []}
        if not self._stopped_file_changed():
            return outcome
        before = set(self._stopped)
        self._load_stopped()
        outcome["reloaded"] = True
        if self._stopped_corrupt is not None:
            outcome["errors"].append(f"stop records: {self._stopped_corrupt}")
            return outcome
        after = set(self._stopped)
        for name in sorted(after - before):
            if name in self._adapters:
                try:
                    await self.stop_source(
                        name,
                        reason=(self._stopped.get(name, {}).get("reason") or "")
                        + " [reloaded]",
                    )
                    outcome["stopped"].append(name)
                except Exception as e:
                    outcome["errors"].append(f"stop {name}: {e}")
        if self._running:
            for name in sorted(before - after):
                if name not in self._adapters:
                    try:
                        self._spec_by_name(name)
                    except ValueError:
                        continue  # record for an unconfigured source; ignore
                    try:
                        await self.start_source(name)
                        outcome["started"].append(name)
                    except Exception as e:
                        outcome["errors"].append(f"start {name}: {e}")
        return outcome

    def get(self, name: str) -> Optional[SourcePort]:
        return self._adapters.get(name)

    def adapters(self) -> Dict[str, SourcePort]:
        return dict(self._adapters)

    def health(self) -> Dict[str, Any]:
        """Truthful health: per-adapter running state plus lifecycle state."""
        per_source: Dict[str, Any] = {}
        for spec in self._specs:
            adapter = self._adapters.get(spec.name)
            if adapter is None:
                entry: Dict[str, Any] = {
                    "adapter": spec.adapter,
                    "configured": True,
                    "is_running": False,
                    "is_healthy": False,
                    "state": "not-started" if self._running else "lifecycle-stopped",
                }
                stopped = self._stopped.get(spec.name)
                if stopped is not None:
                    entry["state"] = "stopped"
                    entry["stopped_reason"] = stopped.get("reason", "")
                    entry["stopped_at"] = stopped.get("stopped_at")
                per_source[spec.name] = entry
                continue
            try:
                healthy = adapter.is_healthy()
            except Exception as e:
                healthy = False
                logger.error("Health probe failed for source %s: %s", spec.name, e)
            detail: Dict[str, Any] = {
                "adapter": spec.adapter,
                "configured": True,
                "is_running": True,
                "is_healthy": healthy,
            }
            probe = getattr(adapter, "health_check", None)
            if callable(probe):
                try:
                    extra = probe()
                    if isinstance(extra, dict):
                        detail.update(extra)
                except Exception as e:
                    detail["health_probe_error"] = str(e)
            per_source[spec.name] = detail
        all_healthy = bool(per_source) and all(
            s.get("is_healthy", False) for s in per_source.values()
        )
        payload: Dict[str, Any] = {
            "lifecycle_running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "configured_sources": [s.name for s in self._specs],
            "all_healthy": all_healthy,
            "sources": per_source,
        }
        if self._stopped_corrupt is not None:
            payload["stopped_records_error"] = self._stopped_corrupt
        return payload
