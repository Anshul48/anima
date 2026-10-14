"""Temporal task projection for the committed dev-task event stream.

Plan EAP-20261004-v0.2, M2. This package turns the committed task-event
stream (contract ``entorhinal.task-event/v1-draft``) into task/attempt/outcome
state that lets a restarted assistant resume real work.

Modules:

- :mod:`entorhinal.temporal.projection` -- incremental + cold-rebuild task
  projection: tasks, attempts, outcomes, versioned claims, corrections,
  conflicts, obligations, episodes, interruptions, branches, artifacts.
- :mod:`entorhinal.temporal.cutoff` -- dual-time query: valid-time
  (true at event time ``t``) vs knowledge-cutoff (known by commit
  watermark ``k``).
- :mod:`entorhinal.temporal.packet` -- bounded resumption-packet builder
  (advisory only).

All identities derived here are deterministic functions of committed data
(no random UUIDs), so incremental application and cold rebuild agree
bit-for-bit.
"""

from entorhinal.temporal.cutoff import TemporalQuery, ValidityView
from entorhinal.temporal.packet import (
    PacketEnrichmentHook,
    PacketRequest,
    ResumptionPacket,
    ResumptionPacketBuilder,
    count_chars,
    count_tokens,
)
from entorhinal.temporal.projection import (
    PROJECTION_ID,
    PROJECTION_VERSION,
    CommittedTaskEvent,
    TaskProjection,
    derive_claim_key,
    revision_identity,
)

__all__ = [
    "PROJECTION_ID",
    "PROJECTION_VERSION",
    "CommittedTaskEvent",
    "TemporalQuery",
    "ValidityView",
    "PacketEnrichmentHook",
    "PacketRequest",
    "ResumptionPacket",
    "ResumptionPacketBuilder",
    "TaskProjection",
    "count_chars",
    "count_tokens",
    "derive_claim_key",
    "revision_identity",
]
