"""Audit Log and Data Export Manager.

Enforces:
1. Complete transparency over consumer queries, purpose statements, and disclosed scopes.
2. Immutable, local-only audit logging of all system actions and policy events.
3. User-controlled full system data export (JSON or ZIP archive).
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import zipfile

from entorhinal.schemas.models import generate_uuidv7

logger = logging.getLogger(__name__)


class AuditLogManager:
    """Manages audit trails and full-system data exports."""

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        max_in_memory: int = 10000,
    ) -> None:
        self.storage_path: Optional[Path] = Path(storage_path) if storage_path else None
        self.max_in_memory = max_in_memory
        self._events: List[Dict[str, Any]] = []

        if self.storage_path and self.storage_path.exists():
            self._load_audit_logs()

    # --------------------------------------------------------------------------
    # Storage & Persistence
    # --------------------------------------------------------------------------

    def _load_audit_logs(self) -> None:
        """Load persisted audit logs from JSONL file."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    event = json.loads(line_str)
                    self._events.append(event)
        except Exception as e:
            logger.error("Failed to load audit logs from %s: %s", self.storage_path, e)

    def _persist_event(self, event: Dict[str, Any]) -> None:
        """Append an audit event to disk."""
        if not self.storage_path:
            return

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, sort_keys=True, default=str) + "\n"
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    # --------------------------------------------------------------------------
    # Event Recording
    # --------------------------------------------------------------------------

    def record_event(
        self,
        action: str,
        details: Union[str, Dict[str, Any]],
        consumer_id: Optional[str] = None,
        stated_purpose: Optional[str] = None,
        disclosed_scopes: Optional[List[str]] = None,
        disclosed_fact_count: int = 0,
        permitted: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record an immutable audit event entry."""
        now = datetime.now(timezone.utc)
        event_id = generate_uuidv7()

        detail_payload = details if isinstance(details, dict) else {"message": str(details)}

        event: Dict[str, Any] = {
            "audit_id": event_id,
            "timestamp": now.isoformat(),
            "action": action,
            "consumer_id": consumer_id or "user",
            "stated_purpose": stated_purpose,
            "disclosed_scopes": list(disclosed_scopes or []),
            "disclosed_fact_count": disclosed_fact_count,
            "permitted": permitted,
            "details": detail_payload,
            "metadata": dict(metadata or {}),
        }

        self._events.append(event)
        if len(self._events) > self.max_in_memory:
            self._events = self._events[-self.max_in_memory:]

        self._persist_event(event)
        return event

    # --------------------------------------------------------------------------
    # Querying
    # --------------------------------------------------------------------------

    def query_logs(
        self,
        limit: int = 100,
        consumer_filter: Optional[str] = None,
        action_filter: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Query audit log records with optional filtering."""
        filtered: List[Dict[str, Any]] = []

        for ev in reversed(self._events):
            if consumer_filter and consumer_filter.lower() not in str(ev.get("consumer_id", "")).lower():
                continue

            if action_filter and action_filter.lower() not in str(ev.get("action", "")).lower():
                continue

            if start_time or end_time:
                try:
                    ev_ts = datetime.fromisoformat(ev["timestamp"])
                    if start_time and ev_ts < start_time:
                        continue
                    if end_time and ev_ts > end_time:
                        continue
                except Exception:
                    pass

            filtered.append(ev)
            if len(filtered) >= limit:
                break

        return filtered

    def get_all_logs(self) -> List[Dict[str, Any]]:
        """Return full in-memory audit log list."""
        return list(self._events)

    def count(self) -> int:
        """Return total event count."""
        return len(self._events)

    # --------------------------------------------------------------------------
    # Data Export (JSON or ZIP Archive)
    # --------------------------------------------------------------------------

    def export_data(
        self,
        format: str = "json",
        journal_records: Optional[List[Dict[str, Any]]] = None,
        graph_state: Optional[Dict[str, Any]] = None,
        corrections: Optional[List[Dict[str, Any]]] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> Union[str, bytes]:
        """Export comprehensive system audit and state payload."""
        export_payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format": format.lower(),
            "audit_logs": self._events,
            "journal_records": journal_records or [],
            "graph_state": graph_state or {},
            "user_corrections": corrections or [],
        }

        if format.lower() == "zip":
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1. Audit logs
                zf.writestr(
                    "audit_logs.json",
                    json.dumps(self._events, indent=2, sort_keys=True, default=str),
                )
                # 2. Journal records
                zf.writestr(
                    "journal.jsonl",
                    "\n".join(json.dumps(r, sort_keys=True, default=str) for r in (journal_records or [])) + "\n",
                )
                # 3. Graph state
                zf.writestr(
                    "semantic_graph.json",
                    json.dumps(graph_state or {}, indent=2, sort_keys=True, default=str),
                )
                # 4. User corrections
                zf.writestr(
                    "user_corrections.json",
                    json.dumps(corrections or [], indent=2, sort_keys=True, default=str),
                )
                # 5. Manifest
                manifest = {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "total_audit_events": len(self._events),
                    "total_journal_records": len(journal_records or []),
                    "total_corrections": len(corrections or []),
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True, default=str))

            zip_bytes = zip_buffer.getvalue()
            if output_path:
                p = Path(output_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(zip_bytes)
            return zip_bytes

        # Default JSON format
        json_str = json.dumps(export_payload, indent=2, sort_keys=True, default=str)
        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json_str, encoding="utf-8")
        return json_str
