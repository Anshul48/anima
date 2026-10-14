"""Dual-time query over the temporal task projection.

Two questions, kept distinct:

- Valid time -- "what was true at event time ``t``?": claims are evaluated
  by their validity intervals (``valid_from``/``valid_to``).
- Knowledge cutoff -- "what did this system know by commit watermark
  ``k``?": only events with ``commit_seq <= k`` (or ``committed_at <= t``)
  participate. A late arrival observed before ``k`` but committed after
  ``k`` is excluded from cutoff-``k`` views.

Unknown intervals (outages, sequence gaps) stay unknown: queries surface
them explicitly and never interpolate across them. Revocation/deletion
generations are honored on every query, including historical ones: the
*current* tombstones apply to all cutoff views.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.temporal.projection import ClaimRevision, TaskProjection


class ClaimValue(BaseModel):
    """One claim evaluated at a valid time."""

    model_config = ConfigDict(extra="forbid")

    claim_key: str
    status: str = "unknown"  # known | unknown | conflicted | corrected-removed | deleted
    value: Any = None
    value_repr: Optional[str] = None
    revision_id: Optional[str] = None
    source_event_id: Optional[str] = None
    commit_seq: Optional[int] = None
    valid_from_source: Optional[str] = None
    revision_ids: List[str] = Field(default_factory=list)
    note: str = ""


class ValidityView(BaseModel):
    """Result of evaluating claims at one valid time over one cutoff."""

    model_config = ConfigDict(extra="forbid")

    valid_at: Optional[datetime] = None
    cutoff_seq: Optional[int] = None
    watermark: int = 0
    deletion_generation: int = 0
    revocation_generation: int = 0
    values: Dict[str, ClaimValue] = Field(default_factory=dict)
    unknown_interval_ids: List[str] = Field(default_factory=list)
    conflict_ids: List[str] = Field(default_factory=list)


class TemporalQuery:
    """Dual-time query facade over a :class:`TaskProjection`."""

    def __init__(self, projection: TaskProjection) -> None:
        self._projection = projection

    @property
    def projection(self) -> TaskProjection:
        return self._projection

    # -- knowledge cutoff -----------------------------------------------------

    def known_by_commit(self, commit_seq: int) -> TaskProjection:
        """Return the projection view known by commit watermark ``commit_seq``.

        Only events with ``commit_seq <= cutoff`` are applied. Late arrivals
        (observed earlier, committed later) are excluded. Current deletion
        and revocation tombstones still apply.
        """
        return self._projection.spawn_filtered(max_commit_seq=commit_seq)

    def known_by_time(self, committed_at: datetime) -> TaskProjection:
        """Return the projection view committed at or before ``committed_at``."""
        return self._projection.spawn_filtered(max_committed_at=committed_at)

    # -- valid time ---------------------------------------------------------------

    def valid_at(
        self,
        moment: datetime,
        *,
        cutoff_seq: Optional[int] = None,
        cutoff_time: Optional[datetime] = None,
        claim_keys: Optional[List[str]] = None,
    ) -> ValidityView:
        """Evaluate claim validity at event time ``moment``.

        When ``cutoff_seq``/``cutoff_time`` is given, knowledge is first
        restricted to that cutoff, then validity is evaluated -- answering
        "what was true at ``t`` as known by ``k``".
        """
        base = self._projection
        if cutoff_seq is not None:
            base = base.spawn_filtered(max_commit_seq=cutoff_seq)
        elif cutoff_time is not None:
            base = base.spawn_filtered(max_committed_at=cutoff_time)
        if claim_keys is not None:
            keys = claim_keys
        else:
            # Deleted claims are reported as deleted (not silently unknown).
            keys = sorted(set(base.claims.keys()) | set(base.deleted_claim_keys))
        values: Dict[str, ClaimValue] = {}
        for key in keys:
            values[key] = self.evaluate_claim(base, key, moment)
        unknown_ids = [
            interval.interval_id
            for interval in base.unknown_intervals.values()
            if self._interval_covers(interval.started_at, interval.ended_at, moment)
        ]
        conflict_ids = [
            conflict.conflict_id
            for conflict in base.conflicts.values()
            if conflict.status == "open"
        ]
        return ValidityView(
            valid_at=moment,
            cutoff_seq=cutoff_seq if cutoff_seq is not None else base.watermark,
            watermark=base.watermark,
            deletion_generation=base.deletion_generation,
            revocation_generation=base.revocation_generation,
            values=values,
            unknown_interval_ids=sorted(unknown_ids),
            conflict_ids=sorted(conflict_ids),
        )

    @staticmethod
    def _interval_covers(
        started: Optional[datetime], ended: Optional[datetime], moment: datetime
    ) -> bool:
        if started is not None and moment < started:
            return False
        if ended is not None and moment >= ended:
            return False
        return True

    @staticmethod
    def evaluate_claim(
        projection: TaskProjection, claim_key: str, moment: datetime
    ) -> ClaimValue:
        """Evaluate one claim at one valid time over a (possibly cut-off) view."""
        if claim_key in projection.deleted_claim_keys:
            return ClaimValue(claim_key=claim_key, status="deleted", note="claim deleted")
        revisions = projection.claims.get(claim_key, [])
        if not revisions:
            return ClaimValue(
                claim_key=claim_key, status="unknown", note="no revisions observed"
            )
        covering = [
            rev
            for rev in revisions
            if TemporalQuery._revision_covers(rev, moment)
            and not TemporalQuery._invalidated_at(projection, rev, moment)
        ]
        if not covering:
            removed = [
                rev
                for rev in revisions
                if TemporalQuery._revision_covers(rev, moment)
                and TemporalQuery._invalidated_at(projection, rev, moment)
            ]
            if removed:
                return ClaimValue(
                    claim_key=claim_key,
                    status="corrected-removed",
                    revision_ids=sorted(rev.revision_id for rev in removed),
                    note="covering revisions removed by a live scoped correction",
                )
            return ClaimValue(
                claim_key=claim_key,
                status="unknown",
                note="no revision covers the queried valid time",
            )
        live_authoritative = [
            rev
            for rev in covering
            if rev.authoritative and rev.superseded_by is None
        ]
        if live_authoritative:
            # A live correction-authored revision wins within its scope;
            # disagreeing observations stay visible as contested/conflicts.
            distinct_auth = sorted({rev.value_repr for rev in live_authoritative})
            if len(distinct_auth) > 1:
                return ClaimValue(
                    claim_key=claim_key,
                    status="conflicted",
                    revision_ids=sorted(rev.revision_id for rev in covering),
                    note="differing correction-authored values cover the queried time",
                )
            winner = sorted(
                live_authoritative, key=lambda rev: (rev.commit_seq, rev.revision_id)
            )[-1]
            contested = len(covering) - len(live_authoritative)
            return ClaimValue(
                claim_key=claim_key,
                status="known",
                value=winner.value,
                value_repr=winner.value_repr,
                revision_id=winner.revision_id,
                source_event_id=winner.source_event_id,
                commit_seq=winner.commit_seq,
                valid_from_source=winner.valid_from_source,
                revision_ids=sorted(rev.revision_id for rev in covering),
                note=(
                    f"correction-authored value; {contested} contested revision(s) also cover"
                    if contested
                    else "correction-authored value"
                ),
            )
        distinct = sorted({rev.value_repr for rev in covering})
        if len(distinct) > 1:
            return ClaimValue(
                claim_key=claim_key,
                status="conflicted",
                revision_ids=sorted(rev.revision_id for rev in covering),
                note=f"{len(distinct)} differing values cover the queried valid time",
            )
        winner = sorted(covering, key=lambda rev: (rev.commit_seq, rev.revision_id))[-1]
        return ClaimValue(
            claim_key=claim_key,
            status="known",
            value=winner.value,
            value_repr=winner.value_repr,
            revision_id=winner.revision_id,
            source_event_id=winner.source_event_id,
            commit_seq=winner.commit_seq,
            valid_from_source=winner.valid_from_source,
            revision_ids=sorted(rev.revision_id for rev in covering),
        )

    @staticmethod
    def _revision_covers(revision: ClaimRevision, moment: datetime) -> bool:
        # Superseded revisions still cover their own historical interval
        # [valid_from, valid_to); succession bounds validity, it does not
        # erase history.
        if revision.valid_from is not None and moment < revision.valid_from:
            return False
        if revision.valid_to is not None and moment >= revision.valid_to:
            return False
        return True

    @staticmethod
    def _invalidated_at(
        projection: TaskProjection, revision: ClaimRevision, moment: datetime
    ) -> bool:
        for scope in revision.invalidated_by:
            record = projection.corrections.get(scope.correction_event_id)
            if record is not None and record.superseded_by is not None:
                continue
            if scope.covers(moment):
                return True
        return False
