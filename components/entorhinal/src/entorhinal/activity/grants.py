"""Explicit opt-in source grants for activity capture (default-deny).

A grant authorizes ONE producer (``source_id``) to emit activity events within
a narrow scope: app substring allowlist, URI host allowlist, and permitted
event kinds, with an expiry time and revocation flag. No grant — no capture.
Grants never mint consumer/query authority; they only scope producers.

Main wiring: main maps API-builder authenticated principals to ``grant_id``s
and persists this store beside the runtime root. This module owns only the
grant model and its local enforcement; it does not touch ``policy/engine.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.activity.events import ActivityEvent, ActivityKind


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceGrant(BaseModel):
    """One explicit opt-in grant for one activity source."""

    model_config = ConfigDict(extra="forbid")

    grant_id: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    principal: str = Field(..., min_length=1)
    allow_apps: List[str] = Field(default_factory=list)
    allow_domains: List[str] = Field(default_factory=list)
    allow_kinds: List[ActivityKind] = Field(default_factory=list)
    expires_at: Optional[datetime] = Field(default=None)
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
    note: str = Field(default="")


class GrantStore:
    """Local grant registry with JSON persistence and attributable checks."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else None
        self._grants: Dict[str, SourceGrant] = {}
        if self._path is not None and self._path.exists():
            self.load()

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def add(self, grant: SourceGrant) -> None:
        self._grants[grant.grant_id] = grant
        self.save()

    def revoke(self, grant_id: str, reason: str = "") -> bool:
        grant = self._grants.get(grant_id)
        if grant is None:
            return False
        self._grants[grant_id] = grant.model_copy(
            update={"revoked": True, "note": f"{grant.note} | revoked: {reason}".strip(" |")}
        )
        self.save()
        return True

    def get(self, grant_id: str) -> Optional[SourceGrant]:
        return self._grants.get(grant_id)

    def grants(self) -> List[SourceGrant]:
        return sorted(self._grants.values(), key=lambda g: g.grant_id)

    def check(self, event: ActivityEvent, now: Optional[datetime] = None) -> Tuple[bool, str]:
        """Return (allowed, reason). Default-deny on every failure mode."""
        now = now or _utcnow()
        grant = self._grants.get(event.grant_id)
        if grant is None:
            return False, f"denied:unknown-grant:{event.grant_id}"
        if grant.revoked:
            return False, f"denied:grant-revoked:{event.grant_id}"
        if grant.source_id != event.source_id:
            return False, "denied:grant-source-mismatch"
        if grant.expires_at is not None and now > grant.expires_at:
            return False, "denied:grant-expired"
        if grant.allow_kinds and event.kind not in grant.allow_kinds:
            return False, f"denied:kind-not-permitted:{event.kind.value}"
        if grant.allow_apps:
            app_lower = event.app.lower()
            if not any(a.lower() in app_lower for a in grant.allow_apps):
                return False, "denied:app-not-permitted"
        if event.uri and grant.allow_domains:
            try:
                host = (urlparse(event.uri).hostname or "").lower()
            except Exception:
                host = ""
            if host and not any(
                host == d.lower() or host.endswith("." + d.lower())
                for d in grant.allow_domains
            ):
                return False, "denied:domain-not-permitted"
        return True, "allowed"

    def save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [g.model_dump(mode="json") for g in self.grants()]
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)

    def load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._grants = {g["grant_id"]: SourceGrant.model_validate(g) for g in raw}
