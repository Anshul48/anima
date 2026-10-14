"""Purpose-bound temporal/cutoff packet serving (F9).

:class:`TemporalPacketService` is the serving API for resumption packets. It
reads the runtime's single temporal projection through the shared holder
(``runtime/projection_holder.py`` -- never a second store build), enforces
the authenticated principal's purpose and source scopes plus the CURRENT
deletion/revocation restrictions on every read, and builds the packet with
the real :class:`temporal.packet.ResumptionPacketBuilder` (cutoff, budgets,
provenance, uncertainty, corrections/deletions, TTL/freshness).

Excluded events are disclosed via the serving report (surfaced as response
headers + audit entries), never by mutating the sealed packet, so the
packet hash stays truthful.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from entorhinal.policy.engine import BudgetExceededError
from entorhinal.schemas.models import source_scope_for_source_id
from entorhinal.temporal.packet import (
    PacketRequest,
    ResumptionPacket,
    ResumptionPacketBuilder,
    count_chars,
    count_tokens,
)
from entorhinal.temporal.projection import CommittedTaskEvent, TaskProjection

logger = logging.getLogger(__name__)


class PacketAccessDenied(PermissionError):
    """Raised when a packet request violates role/purpose/scope grants."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class UnknownTaskError(KeyError):
    """Raised when no events exist for the requested task id."""

    def __init__(self, task_id: str) -> None:
        super().__init__(task_id)
        self.task_id = task_id


@dataclass(frozen=True)
class PacketServingReport:
    """Disclosure accompanying one served packet (headers + audit)."""

    task_id: str
    cutoff_seq: Optional[int]
    watermark: int
    deletion_generation: int
    revocation_generation: int
    candidate_events: int
    served_events: int
    excluded_out_of_scope: int
    excluded_restricted: int
    budget_clamped_to_grant: Optional[int] = None


class TemporalPacketService:
    """Serve purpose-bound cutoff packets to authenticated readers."""

    def __init__(self, store: Any, policy: Any, holder: Any = None) -> None:
        self._store = store
        self._policy = policy
        self._holder = holder

    def _get_holder(self) -> Any:
        if self._holder is None:
            # Local import: runtime/__init__ pulls the factory (which pulls
            # query.service), so this stays out of module scope.
            from entorhinal.runtime.projection_holder import ProjectionHolder

            self._holder = ProjectionHolder(self._store)
        return self._holder

    async def request_packet(
        self,
        principal: Any,
        packet_request: PacketRequest,
    ) -> Tuple[ResumptionPacket, PacketServingReport]:
        """Build and seal one purpose-bound packet for an authenticated reader.

        ``principal`` is the authenticated ``runtime.auth.Principal``
        (duck-typed). Raises :class:`PacketAccessDenied` (HTTP 403),
        :class:`UnknownTaskError` (HTTP 404), :class:`BudgetExceededError`
        (HTTP 422), or ValueError for malformed requests (HTTP 422).
        """
        role = str(getattr(principal, "role", "") or "")
        if role not in ("reader", "admin"):
            raise PacketAccessDenied(
                f"403 PacketDenied: role '{role}' may not request packets",
                reason="role",
            )
        purpose = packet_request.purpose or "resumption"
        covers_purpose = getattr(principal, "covers_purpose", None)
        purpose_ok = (
            covers_purpose(purpose)
            if callable(covers_purpose)
            else purpose in list(getattr(principal, "allowed_purposes", []) or [])
        )
        if not purpose_ok:
            raise PacketAccessDenied(
                f"403 PacketDenied: purpose '{purpose}' not granted to "
                f"'{getattr(principal, 'principal_id', '?')}'",
                reason="purpose",
            )
        if packet_request.cutoff_seq is not None and packet_request.cutoff_seq < 0:
            raise ValueError("cutoff_seq must be >= 0")

        holder = self._get_holder()
        projection: TaskProjection = await holder.get()
        task_id = packet_request.task_id
        candidates = [e for e in projection.event_log if e.task_id == task_id]
        if not candidates:
            raise UnknownTaskError(task_id)

        control_state = projection.to_dict()
        tombstoned_events = set((control_state.get("deleted_event_ids") or {}).keys())
        revoked_sources = set((control_state.get("revoked_sources") or {}).keys())

        covered: List[CommittedTaskEvent] = []
        excluded_scope = 0
        excluded_restricted = 0
        for entry in candidates:
            if entry.event_id in tombstoned_events or entry.source_id in revoked_sources:
                excluded_restricted += 1
                continue
            if not self._source_covered(principal, entry.source_id):
                excluded_scope += 1
                continue
            if not await self._event_permitted_now(entry):
                excluded_restricted += 1
                continue
            covered.append(entry)
        if not covered:
            raise PacketAccessDenied(
                f"403 PacketDenied: no grant-covered, currently-permitted "
                f"evidence for task '{task_id}' "
                f"(out_of_scope={excluded_scope}, restricted={excluded_restricted})",
                reason="scope",
            )

        serving = TaskProjection.rebuild(covered)
        serving.adopt_generations(
            deletion=projection.deletion_generation,
            revocation=projection.revocation_generation,
        )

        # Clamp the token budget to the principal's granted maximum.
        grant_max: Optional[int] = None
        try:
            grant_max = int(getattr(principal, "max_budget", 0) or 0) or None
        except (TypeError, ValueError):
            grant_max = None
        effective = packet_request
        clamped: Optional[int] = None
        if grant_max is not None and grant_max >= 1:
            wanted = packet_request.budget_tokens
            if wanted is None or wanted > grant_max:
                effective = packet_request.model_copy(update={"budget_tokens": grant_max})
                clamped = grant_max

        packet = ResumptionPacketBuilder(serving).build(effective)

        # Independent post-check: the SEALED serialization must fit the
        # declared budgets. Overflow-with-fit (normal pruning) is served with
        # its disclosure; overflow-with-excess is an honest explicit failure.
        serialized = packet.serialize()
        used_chars = count_chars(serialized)
        used_tokens = count_tokens(serialized)
        over_chars = effective.budget_chars is not None and used_chars > effective.budget_chars
        over_tokens = (
            effective.budget_tokens is not None and used_tokens > effective.budget_tokens
        )
        if over_chars or over_tokens:
            raise BudgetExceededError(
                f"minimum packet envelope ({used_chars} chars, {used_tokens} "
                f"tokens) exceeds the declared budget "
                f"(chars={effective.budget_chars}, tokens={effective.budget_tokens})",
                budget_tokens=int(effective.budget_tokens or 0),
                used_tokens=used_tokens,
                used_chars=used_chars,
                tokenizer="m2-regex-v1",
            )

        report = PacketServingReport(
            task_id=task_id,
            cutoff_seq=packet_request.cutoff_seq,
            watermark=serving.watermark,
            deletion_generation=serving.deletion_generation,
            revocation_generation=serving.revocation_generation,
            candidate_events=len(candidates),
            served_events=len(covered),
            excluded_out_of_scope=excluded_scope,
            excluded_restricted=excluded_restricted,
            budget_clamped_to_grant=clamped,
        )
        logger.info(
            "packet served task=%s cutoff=%s served=%d/%d restricted=%d",
            task_id,
            packet_request.cutoff_seq,
            len(covered),
            len(candidates),
            excluded_restricted,
        )
        return packet, report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _source_covered(self, principal: Any, source_id: str) -> bool:
        covers_scope = getattr(principal, "covers_scope", None)
        tag = source_scope_for_source_id(source_id)
        if callable(covers_scope):
            return bool(covers_scope(tag))
        import fnmatch

        for allowed in list(getattr(principal, "allowed_scopes", []) or []):
            if allowed == "*" or tag == allowed or fnmatch.fnmatch(tag, allowed):
                return True
        return False

    async def _event_permitted_now(self, entry: CommittedTaskEvent) -> bool:
        """Whether the event's evidence is currently disclosable.

        Fail-closed: missing records, tombstones, and currently-unconsented
        records are excluded. Every historical cutoff view obeys the CURRENT
        deletion/revocation state, not the admission-time state.
        """
        getter = getattr(self._store, "get_by_id", None)
        if not callable(getter):
            return False
        try:
            record = await getter(entry.evidence_id)
        except Exception:
            return False
        if record is None or getattr(record, "is_tombstone", False):
            return False
        is_consented = getattr(self._policy, "is_consented", None)
        if not callable(is_consented):
            return False
        try:
            permitted, _ = is_consented(
                record.source_type, record.app_identifier, record.target_uri
            )
        except Exception:
            return False
        return bool(permitted)

    def serving_status(self) -> Dict[str, Any]:
        """Small status dict for health/detail and tests."""
        holder = self._holder
        status = getattr(holder, "status", None)
        if callable(status):
            try:
                return {"projection_holder": status()}
            except Exception:
                pass
        return {"projection_holder": {"built": False}}
