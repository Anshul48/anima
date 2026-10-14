"""Domain outcome-feedback API recorded as attributable SST events.

SST is a search engine, not an authority on real-world results: **SST never
owns the authoritative verdict** for a candidate. The domain (deploy
pipeline, human operator, downstream evaluator) owns it. :func:`report_outcome`
records that external verdict verbatim — actor, verdict, and evidence refs —
as an append-only event so the outcome is auditable without SST reinterpreting
it.

The outcome event uses the projection-ignored ``OUTCOME_REPORTED`` carrier
kind (with ``payload.record_type == "domain_outcome"``), so replaying the
event log never mutates node state from a domain verdict: SST cannot
override it by construction. :func:`is_outcome_event` also recognizes the
legacy wave-1 interim carrier (``WORKER_INVOKED`` with the same record
type) for backward compatibility with logs written before the dedicated
kind existed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sst.core.events import EventKind, SSTEvent
from sst.protocols.storage import TreeStoreProtocol

OUTCOME_RECORD_TYPE: str = "domain_outcome"

#: Dedicated carrier kind (projection-ignored). Thin delegating wrappers live
#: on SQLiteSSTStore.report_outcome and SSTSearchController.report_outcome.
OUTCOME_CARRIER_KIND: EventKind = EventKind.OUTCOME_REPORTED

#: Legacy wave-1 interim carrier, still recognized by is_outcome_event.
LEGACY_OUTCOME_CARRIER_KIND: EventKind = EventKind.WORKER_INVOKED


def report_outcome(
    store: TreeStoreProtocol,
    *,
    tree_id: str,
    candidate_id: str,
    verdict: str,
    evidence_refs: Sequence[str] | None = None,
    actor: str,
    note: str | None = None,
    idempotency_key: str | None = None,
    event_id: str | None = None,
) -> int:
    """Appends a domain outcome verdict for ``candidate_id`` and returns its sequence id.

    The ``verdict`` is stored verbatim under ``payload.domain_verdict``; SST
    performs no mapping, normalization, or promotion-gate interpretation of
    it. ``actor`` attributes the report to its domain source (operator id,
    pipeline name, ...). ``evidence_refs`` links supporting evidence.
    """
    if not verdict or not verdict.strip():
        raise ValueError("Outcome verdict must be a non-empty string.")
    if not actor or not actor.strip():
        raise ValueError("Outcome actor must be a non-empty string.")
    if not candidate_id or not candidate_id.strip():
        raise ValueError("Outcome candidate_id must be a non-empty string.")
    refs = list(evidence_refs or [])
    event = SSTEvent(
        event_id=event_id or f"evt_{uuid.uuid4().hex[:12]}",
        tree_id=tree_id,
        node_id=candidate_id,
        kind=OUTCOME_CARRIER_KIND,
        actor=actor,
        idempotency_key=idempotency_key or f"outcome_{tree_id}_{candidate_id}_{uuid.uuid4().hex[:8]}",
        payload={
            "record_type": OUTCOME_RECORD_TYPE,
            "domain_verdict": verdict,
            "evidence_refs": refs,
            "note": note or "",
            "sst_authoritative": False,
            "carrier_kind": OUTCOME_CARRIER_KIND.value,
        },
    )
    return store.append_event(event)


def is_outcome_event(event: SSTEvent) -> bool:
    """Returns True if ``event`` is a domain-outcome record (any carrier kind)."""
    if event.payload.get("record_type") == OUTCOME_RECORD_TYPE:
        return True
    return event.kind is OUTCOME_CARRIER_KIND


def get_outcomes(store: TreeStoreProtocol, tree_id: str) -> list[SSTEvent]:
    """Returns all domain-outcome events recorded for ``tree_id``."""
    return [e for e in store.get_events(tree_id) if is_outcome_event(e)]
