"""F9 controls: serving actual temporal/cutoff packets to granted readers.

The packet route serves the real ResumptionPacketBuilder over the runtime's
single temporal projection (never a pilot-only direct call), enforcing the
authenticated principal's purpose + source scopes and CURRENT
deletion/revocation restrictions on every read, with cutoff echoed and
budgets honestly enforced. Synthetic only.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from entorhinal.api.app import create_app
from entorhinal.policy.engine import BudgetExceededError
from entorhinal.query.packets import (
    PacketAccessDenied,
    TemporalPacketService,
    UnknownTaskError,
)
from entorhinal.runtime import build_runtime, close_runtime
from entorhinal.runtime.auth import AuthStore
from entorhinal.runtime.config import RuntimeConfig
from entorhinal.runtime.projection_holder import ProjectionHolder
from entorhinal.schemas.models import SourceType
from entorhinal.temporal.packet import PacketRequest

SOURCE = "entorhinal.dev-task.01"
TASK = "syn-packet-task-1"
T0 = datetime(2026, 10, 11, 9, 0, 0, tzinfo=timezone.utc)


def _task_event(
    event_id: str,
    sequence: int,
    observed: datetime,
    kind: str = "goal",
    source_id: str = SOURCE,
    task: str = TASK,
) -> dict[str, Any]:
    return {
        "contract_version": "entorhinal.task-event/v1-draft",
        "source_id": source_id,
        "event_id": event_id,
        "producer_run_id": "syn-packet-probe",
        "producer_sequence": sequence,
        "producer_version": "syn-probe/v0",
        "work": {"session_id": "syn-session-1", "task_id": task},
        "kind": kind,
        "time": {
            "observed_at": observed.isoformat(),
            "received_at": None,
            "committed_at": None,
            "clock_domain": "syn-clock",
            "precision_ms": 1.0,
            "uncertainty_ms": 5.0,
            "source_sequence": sequence,
        },
        "payload": {"value": {"objective": f"synthetic objective {event_id}"}},
        "epistemic": "assertion",
        "revision": {},
        "admission": {
            "grant_revision": "grant:r1",
            "retention_class": "payload-30d",
            "deletion_generation": 0,
            "revocation_generation": 0,
        },
        "assistance": {},
    }


def _record_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": "terminal_pty",
        "app_identifier": "synth-probe",
        "window_title": "SYNTHETIC packet probe",
        "target_uri": "file:///synthetic/packet/probe.txt",
        "sanitized_payload": payload,
        "classification": "internal",
    }


@pytest.fixture
def env(tmp_path: Path):
    root = tmp_path / "rt"
    auth = AuthStore(root / "auth_principals.json")
    _, reader_secret = auth.create_principal(
        role="reader",
        principal_id="packet.reader",
        allowed_purposes=["resumption"],
        allowed_scopes=[f"scope:source:{SOURCE}"],
    )
    _, admin_secret = auth.create_principal(
        role="admin",
        principal_id="packet.admin",
        allowed_purposes=["administration"],
        allowed_scopes=["*"],
    )
    rt = build_runtime(RuntimeConfig.from_root(root, default_allow=True))

    async def _seed() -> None:
        # Commit order defines knowledge order: ev1 first, then the
        # late arrival ev2 (observed EARLIER than ev1).
        await rt.store.commit_event(
            SOURCE, "syn-pkt-ev1", _record_dict(_task_event("syn-pkt-ev1", 1, T0 + timedelta(minutes=10))),
            observed_at=T0 + timedelta(minutes=10),
        )
        await rt.store.commit_event(
            SOURCE, "syn-pkt-ev2", _record_dict(_task_event("syn-pkt-ev2", 2, T0)),
            observed_at=T0,
        )

    asyncio.run(_seed())
    holder = ProjectionHolder(rt.store)
    service = TemporalPacketService(store=rt.store, policy=rt.policy, holder=holder)
    reader = auth.authenticate(f"Bearer {reader_secret}")
    assert reader is not None
    yield {
        "runtime": rt,
        "service": service,
        "holder": holder,
        "reader": reader,
        "auth": auth,
        "root": root,
        "reader_headers": {"Authorization": f"Bearer {reader_secret}"},
        "admin_headers": {"Authorization": f"Bearer {admin_secret}"},
    }
    asyncio.run(close_runtime(rt))


def _packet_request(**overrides: Any) -> PacketRequest:
    base: dict[str, Any] = {"task_id": TASK, "purpose": "resumption"}
    base.update(overrides)
    return PacketRequest(**base)


# --------------------------------------------------------------------------
# Serving behavior: real packets, cutoff views, late arrivals
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_serve_full_packet(env) -> None:
    packet, report = await env["service"].request_packet(env["reader"], _packet_request())
    assert packet.task_state.task_id == TASK
    assert packet.task_state.last_commit_seq == 2
    assert packet.metadata.cutoff_seq is None
    assert packet.metadata.watermark >= 2
    assert packet.metadata.packet_hash, "sealed packet must carry its hash"
    assert packet.metadata.expires_at is not None, "TTL/freshness must be present"
    assert packet.disclaimer.startswith("ADVISORY")
    assert packet.budget.used_chars > 0
    assert report.served_events == 2
    assert report.excluded_out_of_scope == 0
    assert report.excluded_restricted == 0


@pytest.mark.asyncio
async def test_cutoff_view_excludes_late_arrival(env) -> None:
    full, _ = await env["service"].request_packet(env["reader"], _packet_request())
    cutoff, report = await env["service"].request_packet(env["reader"], _packet_request(cutoff_seq=1))
    assert cutoff.metadata.cutoff_seq == 1, "cutoff must be echoed in metadata"
    assert cutoff.task_state.last_commit_seq == 1
    assert report.served_events == 2, "cutoff applies inside the builder, not the grant filter"
    assert cutoff.metadata.packet_hash != full.metadata.packet_hash


@pytest.mark.asyncio
async def test_unknown_task(env) -> None:
    with pytest.raises(UnknownTaskError):
        await env["service"].request_packet(env["reader"], _packet_request(task_id="no-such-task"))


@pytest.mark.asyncio
async def test_reads_through_single_shared_holder(env) -> None:
    assert env["holder"].build_count == 0
    await env["service"].request_packet(env["reader"], _packet_request())
    await env["service"].request_packet(env["reader"], _packet_request(cutoff_seq=1))
    assert env["holder"].build_count == 1, "no second store build per request"


# --------------------------------------------------------------------------
# Grant enforcement: role, purpose, source scope
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_role_and_purpose_enforced(env) -> None:
    auth = env["auth"]
    _, source_secret = auth.create_principal(
        role="source", principal_id="packet.source", allowed_purposes=["ingest"], allowed_scopes=[]
    )
    source = auth.authenticate(f"Bearer {source_secret}")
    with pytest.raises(PacketAccessDenied) as exc_info:
        await env["service"].request_packet(source, _packet_request())
    assert exc_info.value.reason == "role"
    with pytest.raises(PacketAccessDenied) as exc_info:
        await env["service"].request_packet(env["reader"], _packet_request(purpose="exfiltration"))
    assert exc_info.value.reason == "purpose"


@pytest.mark.asyncio
async def test_wrong_source_grant_denied(env) -> None:
    auth = env["auth"]
    _, secret = auth.create_principal(
        role="reader",
        principal_id="packet.reader.other",
        allowed_purposes=["resumption"],
        allowed_scopes=["scope:source:some.other.source"],
    )
    other = auth.authenticate(f"Bearer {secret}")
    with pytest.raises(PacketAccessDenied) as exc_info:
        await env["service"].request_packet(other, _packet_request())
    assert exc_info.value.reason == "scope"


# --------------------------------------------------------------------------
# Current restrictions: tombstones and revoked consent filter every read
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tombstoned_evidence_excluded_from_cutoff_views(env) -> None:
    rt = env["runtime"]
    receipt = await rt.store.get_receipt(SOURCE, "syn-pkt-ev2")
    assert receipt is not None and receipt.evidence_id is not None
    assert await rt.store.tombstone_record(receipt.evidence_id, reason="synthetic probe deletion") is True
    env["holder"].invalidate("synthetic probe deletion")
    packet, report = await env["service"].request_packet(env["reader"], _packet_request())
    assert report.candidate_events == 1, "holder rebuild drops the tombstone"
    assert report.served_events == 1
    assert packet.task_state.last_commit_seq == 1


@pytest.mark.asyncio
async def test_serve_time_recheck_catches_stale_holder(env) -> None:
    """Correctness never depends on invalidation ordering (defense in depth)."""
    rt = env["runtime"]
    # Warm the holder cache BEFORE deletion: it now holds both events.
    await env["service"].request_packet(env["reader"], _packet_request())
    receipt = await rt.store.get_receipt(SOURCE, "syn-pkt-ev2")
    assert receipt is not None and receipt.evidence_id is not None
    assert await rt.store.tombstone_record(receipt.evidence_id, reason="synthetic probe deletion") is True
    # Deliberately NO holder.invalidate: the serve-time recheck must still win.
    packet, report = await env["service"].request_packet(env["reader"], _packet_request())
    assert report.candidate_events == 2
    assert report.served_events == 1
    assert report.excluded_restricted == 1
    assert packet.task_state.last_commit_seq == 1


@pytest.mark.asyncio
async def test_revoked_consent_excluded_from_packets(env) -> None:
    env["runtime"].policy.add_consent_rule(
        allow=False, source_type=SourceType.TERMINAL_PTY, app_pattern="*", domain_pattern="*", priority=100
    )
    with pytest.raises(PacketAccessDenied) as exc_info:
        await env["service"].request_packet(env["reader"], _packet_request())
    assert exc_info.value.reason == "scope"


@pytest.mark.asyncio
async def test_tiny_budget_fails_explicitly(env) -> None:
    with pytest.raises(BudgetExceededError):
        await env["service"].request_packet(
            env["reader"], _packet_request(budget_tokens=1, budget_chars=1)
        )


# --------------------------------------------------------------------------
# HTTP route integration
# --------------------------------------------------------------------------

def test_http_packet_route(env) -> None:
    app = create_app(runtime=env["runtime"])
    client = TestClient(app)
    try:
        res = client.post(
            "/api/v1/context/packet",
            headers=env["reader_headers"],
            json={"task_id": TASK, "purpose": "resumption"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["task_state"]["task_id"] == TASK
        assert body["metadata"]["packet_hash"]
        assert res.headers["X-Entorhinal-Excluded-Out-Of-Scope"] == "0"
        assert res.headers["X-Entorhinal-Excluded-Restricted"] == "0"
        missing = client.post(
            "/api/v1/context/packet",
            headers=env["reader_headers"],
            json={"task_id": "no-such-task", "purpose": "resumption"},
        )
        assert missing.status_code == 404
    finally:
        client.close()


@pytest.mark.asyncio
async def test_http_packet_generation_advances_after_forget(env) -> None:
    """I-2/N2: the packet route reads the runtime's ONE shared holder, so a
    forget invalidates the served view and the packet metadata generation
    advances (serve -> forget -> serve)."""
    rt = env["runtime"]
    app = create_app(runtime=rt)
    client = TestClient(app)
    try:
        first = client.post(
            "/api/v1/context/packet",
            headers=env["reader_headers"],
            json={"task_id": TASK, "purpose": "resumption"},
        )
        assert first.status_code == 200, first.text
        gen0 = first.json()["metadata"]["deletion_generation"]
        receipt = await rt.store.get_receipt(SOURCE, "syn-pkt-ev2")
        assert receipt is not None and receipt.evidence_id is not None
        proof = await rt.user_control.deletion_engine.cascade_delete(
            record_ids=[receipt.evidence_id], reason="synthetic I-2 probe"
        )
        await rt.user_control._after_forget(proof)
        assert proof["tombstoned_records_count"] == 1
        second = client.post(
            "/api/v1/context/packet",
            headers=env["reader_headers"],
            json={"task_id": TASK, "purpose": "resumption"},
        )
        assert second.status_code == 200, second.text
        gen1 = second.json()["metadata"]["deletion_generation"]
        assert gen0 is not None and gen1 == gen0 + 1, f"gen0={gen0} gen1={gen1}"
    finally:
        client.close()
