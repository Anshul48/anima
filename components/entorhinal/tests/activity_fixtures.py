"""Shared NEW-synthetic fixtures for activity-builder tests (no real data).

All events/helpers here generate clearly-labeled synthetic activity on
`.example.test` hosts and `/synth` paths. Nothing reads user stores.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from entorhinal.activity.events import ActivityEvent, ActivityKind
from entorhinal.activity.grants import GrantStore, SourceGrant

SYNTH_BROWSER = "entorhinal.activity.browser.01"
SYNTH_FILE = "entorhinal.activity.file.01"
SYNTH_GRANT_BROWSER = "grant-synth-browser-01"
SYNTH_GRANT_FILE = "grant-synth-file-01"

T0 = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)


def grant_store(*, with_browser: bool = True, with_file: bool = True) -> GrantStore:
    store = GrantStore()
    if with_browser:
        store.add(SourceGrant(
            grant_id=SYNTH_GRANT_BROWSER, source_id=SYNTH_BROWSER,
            principal="synth-tester", note="NEW synthetic test grant",
        ))
    if with_file:
        store.add(SourceGrant(
            grant_id=SYNTH_GRANT_FILE, source_id=SYNTH_FILE,
            principal="synth-tester", note="NEW synthetic test grant",
        ))
    return store


def make_event(
    event_id: str,
    observed_at: datetime,
    kind: ActivityKind = ActivityKind.WINDOW_FOREGROUND,
    app: str = "Chromium",
    title: Optional[str] = "SYNTH page",
    uri: Optional[str] = "https://video.example.test/watch?v=SYNTH-1",
    payload: Optional[Dict[str, Any]] = None,
    foreground: bool = True,
    source_id: str = SYNTH_BROWSER,
    grant_id: str = SYNTH_GRANT_BROWSER,
    source_seq: Optional[int] = None,
) -> ActivityEvent:
    return ActivityEvent(
        event_id=event_id,
        source_id=source_id,
        grant_id=grant_id,
        observed_at=observed_at,
        source_seq=source_seq,
        clock_domain="synthetic-fixture-clock",
        kind=kind,
        app=app,
        window_title=title,
        uri=uri,
        foreground=foreground,
        payload=dict(payload or {}),
        redaction_labels=["synthetic-fixture"],
        synthetic=True,
    )


def media_payload(
    media_id: str,
    position_s: float,
    state: str,
    host: str = "video.example.test",
    duration_s: float = 3600.0,
) -> Dict[str, Any]:
    return {
        "media_id": media_id,
        "media_host": host,
        "media_position_s": position_s,
        "media_duration_s": duration_s,
        "media_state": state,
    }
