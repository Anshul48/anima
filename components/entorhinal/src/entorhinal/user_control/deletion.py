"""Cascade Deletion & Revocation Engine.

Enforces:
1. Complete cryptographic payload erasure across durable journal entries.
2. Invalidation and purging of all downstream DerivedFact, Hypothesis, and SemanticGraph nodes.
3. Snapshot cache invalidation to prevent stale disclosures.
4. Tamper-evident proof-of-deletion reports with zero residual data verification.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.projections.graph import SemanticGraphManager
from entorhinal.query.service import ContextSnapshotService
from entorhinal.schemas.models import (
    ClassificationLevel,
    EvidenceRecord,
    generate_uuidv7,
)

logger = logging.getLogger(__name__)

DELETION_GENERATION_META_KEY = "deletion_generation"

# Default dev-task adapter sidecar filenames (see sources/dev_task.py); used to
# resolve producer residue files when per-source options do not override them.
_DEV_TASK_STATE_DIRNAME = "dev-task-state"
_DEV_TASK_SPOOL_FILENAME = "sanitized.spool.jsonl"
_DEV_TASK_ERROR_FILENAME = "denied.jsonl"
_LEGACY_JOURNAL_FILENAME = "evidence_journal.jsonl"


def _as_aware(value: datetime) -> datetime:
    """Normalize a timestamp for comparison (naive values read as UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _record_time(record: EvidenceRecord) -> Optional[datetime]:
    """Best-effort event time for engine-side range filtering."""
    candidate = getattr(record, "persisted_at", None) or getattr(record, "committed_at", None)
    if candidate is None:
        return None
    return _as_aware(candidate)


class CascadeDeletionEngine:
    """Coordinates cryptographic tombstoning across journal, projections, and caches."""

    def __init__(
        self,
        journal: EvidenceJournal,
        graph_manager: Optional[SemanticGraphManager] = None,
        compiler: Optional[MultiTimescaleCompiler] = None,
        snapshot_service: Optional[ContextSnapshotService] = None,
        storage_root: Optional[Path] = None,
        source_specs: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.journal = journal
        self.graph_manager = graph_manager
        self.compiler = compiler
        self.snapshot_service = snapshot_service
        self.storage_root = Path(storage_root) if storage_root else None
        # Plain-dict source specs ({name, adapter, options}) so this module
        # stays independent of runtime.config; the service/factory layer
        # translates SourceSpec objects. Used to locate producer residue
        # files (inbox + adapter sidecars) for the deletion proof.
        self.source_specs = list(source_specs or [])

    async def forget_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        reason: str = "User deletion request",
    ) -> Dict[str, Any]:
        """Execute cascade deletion across a bounded temporal window.

        Steps:
        1. Identify all EvidenceRecord entries in the time range.
        2. Tombstone each record in the journal (zeroing payload in place).
        3. Purge dependent nodes and edges from the semantic graph.
        4. Invalidate compiler active facts and snapshot service caches.
        5. Verify zero residual payload leakage and return cryptographic deletion proof.
        """
        return await self.cascade_delete(
            time_range_start=start_time,
            time_range_end=end_time,
            reason=reason,
        )

    async def cascade_delete(
        self,
        time_range_start: Optional[datetime] = None,
        time_range_end: Optional[datetime] = None,
        domain: Optional[str] = None,
        app_identifier: Optional[str] = None,
        reason: str = "User deletion request",
        force_all: bool = False,
        record_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute targeted cascade deletion based on time range, domain, app, or IDs."""
        if (
            time_range_start is None
            and time_range_end is None
            and domain is None
            and app_identifier is None
            and not record_ids
            and not force_all
        ):
            raise ValueError(
                "Cascade deletion requires at least one filter criterion (time_range_start, "
                "time_range_end, domain, app_identifier, or record_ids) or explicit force_all=True."
            )
        id_set = set(record_ids) if record_ids else None

        deletion_id = generate_uuidv7()
        now = datetime.now(timezone.utc)
        start_aware = _as_aware(time_range_start) if time_range_start else None
        end_aware = _as_aware(time_range_end) if time_range_end else None

        # 1. Scan candidate records from the backing store. The backend may or
        # may not apply the time window itself, so the engine always enforces
        # the range below (F13: forget must be a true bounded-window delete).
        all_records = await self.journal.scan_evidence(
            start_time=time_range_start,
            end_time=time_range_end,
            limit=100000,
        )

        matching_records: List[EvidenceRecord] = []
        for r in all_records:
            if r.is_tombstone:
                continue

            # Engine-side time filter (inclusive bounds).
            if start_aware is not None or end_aware is not None:
                event_time = _record_time(r)
                if event_time is None:
                    continue
                if start_aware is not None and event_time < start_aware:
                    continue
                if end_aware is not None and event_time > end_aware:
                    continue

            # Check domain match if specified
            if domain:
                uri = (r.target_uri or "").lower()
                if domain.lower() not in uri:
                    continue

            # Check app match if specified
            if app_identifier:
                app = r.app_identifier.lower()
                if app_identifier.lower() not in app:
                    continue

            # Check explicit ID selection (retention enforcement path).
            if id_set is not None and r.record_id not in id_set:
                continue

            matching_records.append(r)

        # Residue markers must be collected BEFORE tombstoning zeroes payloads.
        residue_markers = self._collect_residue_markers(matching_records)

        tombstoned_count = 0
        tombstoned_ids: List[str] = []
        tombstoned_event_ids: List[str] = []
        affected_entities: Set[str] = set()

        # 2. Tombstone all matching records in the backing store
        for record in matching_records:
            success = await self.journal.tombstone_record(
                record_id=record.record_id,
                reason=reason,
            )
            if success:
                tombstoned_count += 1
                tombstoned_ids.append(record.record_id)
                event_id = getattr(record, "event_id", None)
                if event_id:
                    tombstoned_event_ids.append(str(event_id))

                # 3. Invalidate evidence in semantic graph
                if self.graph_manager is not None:
                    pruned = self.graph_manager.invalidate_evidence(record.record_id)
                    affected_entities.update(pruned)

        # 4. Invalidate compiler and re-compile projections if compiler attached
        purged_facts_count = 0
        if self.compiler is not None:
            # Recompile batch projection to purge derived facts dependent on tombstoned records
            new_facts = await self.compiler.compile_batch_projection()
            purged_facts_count = max(0, len(self.compiler.get_active_facts()) - len(new_facts))

        # 4b. Sibling focus/aggregate purge (N1, per api-repair/INTERFACES.md
        # §7: MultiTimescaleCompiler.purge_evidence(record_ids, *, reason)).
        # When the compiler exposes the entry point, call it and record its
        # measured per-section counts; otherwise the proof discloses the gap.
        focus_purged = False
        focus_purge_counts: Dict[str, Any] = {}
        focus_purge_error: Optional[str] = None
        compiler_purge = getattr(self.compiler, "purge_evidence", None)
        if self.compiler is not None and callable(compiler_purge):
            try:
                result = compiler_purge(
                    list(tombstoned_ids), reason=reason
                )
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, dict):
                    focus_purge_counts = dict(result)
                focus_purged = True
            except Exception as e:
                focus_purge_error = f"{type(e).__name__}: {e}"
                logger.error("Compiler purge_evidence failed: %s", e)

        # 5. Invalidate snapshot cache
        if self.snapshot_service is not None:
            self.snapshot_service._snapshot_cache.clear()

        # 6. Verify integrity and zero residual payload leakage
        is_valid, corrupted_id, _ = self.journal.verify_journal_integrity()

        # Verification: inspect store records in the deleted set to verify payloads are empty
        residual_leaks = 0
        for ev_id in tombstoned_ids:
            rec = await self.journal.get_by_id(ev_id)
            if rec:
                if rec.sanitized_payload != {} or rec.classification != ClassificationLevel.PROHIBITED:
                    residual_leaks += 1

        # 6b. Store-level event keys for targeted adapter purge (N4).
        # EvidenceRecord carries no event_id; SQLite-backed stores map
        # evidence_id -> (source_id, event_id) for purge_managed scoping.
        event_keys: Dict[str, Dict[str, str]] = {}
        keys_hook = getattr(self.journal, "event_keys_for", None)
        if callable(keys_hook) and tombstoned_ids:
            try:
                event_keys = keys_hook(list(tombstoned_ids)) or {}
            except Exception as e:
                logger.error("event_keys_for failed: %s", e)
                event_keys = {}
        for record_id in tombstoned_ids:
            key = event_keys.get(record_id, {})
            if key.get("event_id") and key["event_id"] not in tombstoned_event_ids:
                tombstoned_event_ids.append(key["event_id"])

        # 7. Producer-side residue scan: purge what Entorhinal owns (sanitized
        # spool copies) and disclose what it does not (producer inbox lines,
        # denial dispositions, legacy mirrors). Spool purge is scoped to
        # targeted event identity (I-1): only spool lines whose event_id is
        # among the tombstoned event ids are removed, so non-target pending
        # lines sharing producer boilerplate survive.
        residue_report = self._scan_producer_residues(
            residue_markers, target_event_ids=set(tombstoned_event_ids)
        )

        # 8. Monotonic deletion generation on backends that persist control
        # metadata (SQLite meta table). Consumers can compare generations to
        # detect that a forget ran after their snapshot was taken.
        generation = self._bump_deletion_generation()
        backend_name = type(self.journal).__name__

        proof = {
            "deletion_id": deletion_id,
            "timestamp": now.isoformat(),
            "backend": backend_name,
            "time_range_start": time_range_start.isoformat() if time_range_start else None,
            "time_range_end": time_range_end.isoformat() if time_range_end else None,
            "time_filter_applied": start_aware is not None or end_aware is not None,
            "domain_filter": domain,
            "app_filter": app_identifier,
            "scanned_candidate_count": len(all_records),
            "reason": reason,
            "tombstoned_records_count": tombstoned_count,
            "purged_facts_count": purged_facts_count,
            "purged_nodes_count": len(affected_entities),
            "affected_entities": list(affected_entities),
            "tombstoned_record_ids": tombstoned_ids,
            "tombstoned_event_ids": tombstoned_event_ids,
            "journal_integrity_valid": is_valid,
            "residual_leakage_count": residual_leaks,
            "deletion_generation": generation,
            "deletion_generation_note": (
                None
                if generation is not None
                else f"{backend_name} persists no deletion generation; consumers cannot detect this forget"
            ),
            "producer_residues": residue_report,
            "uncovered_residues": [r for r in residue_report if r.get("matched_lines", 0) > 0 and r.get("purged_lines", 0) < r.get("matched_lines", 0)],
            "focus_aggregates_purged": focus_purged,
            "focus_purge_counts": focus_purge_counts,
            "focus_purge_error": focus_purge_error,
            "focus_aggregates_note": (
                None
                if focus_purged
                else (
                    "ImmediateFocusState/temporal focus aggregates are not purged by this engine; "
                    "pending sibling API repair (N1 interface). Proof discloses the gap rather than claiming it."
                )
            ),
            "audit_log_retained_by_design": True,
        }

        logger.info(
            "Cascade deletion %s complete: %d records tombstoned, %d entities affected, integrity=%s, backend=%s",
            deletion_id,
            tombstoned_count,
            len(affected_entities),
            is_valid,
            backend_name,
        )
        return proof

    # ------------------------------------------------------------------
    # Residue measurement (F13 disclosure scope)
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_residue_markers(records: List[EvidenceRecord]) -> Set[str]:
        """Content markers identifying deleted records in producer-side files."""
        markers: Set[str] = set()
        for record in records:
            for candidate in (
                record.record_id,
                getattr(record, "event_id", None),
                record.window_title,
                record.target_uri,
            ):
                if candidate:
                    markers.add(str(candidate))
            payload = record.sanitized_payload or {}
            if isinstance(payload, dict):
                stack = list(payload.values())
                while stack:
                    value = stack.pop()
                    if isinstance(value, str) and len(value) >= 4:
                        markers.add(value)
                    elif isinstance(value, dict):
                        stack.extend(value.values())
                    elif isinstance(value, (list, tuple)):
                        stack.extend(value)
        return markers

    def _producer_files(self) -> List[Dict[str, Any]]:
        """Resolve producer-side residue files from storage root + source specs."""
        files: List[Dict[str, Any]] = []
        if self.storage_root is not None:
            legacy = self.storage_root / _LEGACY_JOURNAL_FILENAME
            files.append({
                "source": None,
                "kind": "legacy-journal-mirror",
                "path": str(legacy),
                "purgeable": False,
                "retained_reason": "foreign-writer mirror (legacy CLI); scanned only, never modified",
            })
        for spec in self.source_specs:
            options = dict(spec.get("options") or {})
            inbox_raw = options.get("inbox_path")
            if not inbox_raw:
                files.append({
                    "source": spec.get("name"),
                    "kind": "inbox",
                    "path": None,
                    "purgeable": False,
                    "retained_reason": "inbox_path not configured for this source; unscannable",
                })
                continue
            inbox = Path(str(inbox_raw))
            files.append({
                "source": spec.get("name"),
                "kind": "inbox",
                "path": str(inbox),
                "purgeable": False,
                "retained_reason": "producer-owned inbox; Entorhinal deletion does not modify producer files",
            })
            state_dir_raw = options.get("state_dir")
            state_dir = (
                Path(str(state_dir_raw))
                if state_dir_raw
                else inbox.parent / _DEV_TASK_STATE_DIRNAME
            )
            spool = options.get("spool_path", state_dir / _DEV_TASK_SPOOL_FILENAME)
            files.append({
                "source": spec.get("name"),
                "kind": "sanitized-spool",
                "path": str(spool),
                "purgeable": True,
                "retained_reason": None,
            })
            error_log = options.get("error_log_path", state_dir / _DEV_TASK_ERROR_FILENAME)
            files.append({
                "source": spec.get("name"),
                "kind": "denial-log",
                "path": str(error_log),
                "purgeable": False,
                "retained_reason": "denial dispositions carry no payload; retained as admission audit",
            })
        return files

    def _scan_producer_residues(
        self,
        markers: Set[str],
        target_event_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Scan (and where owned, purge) producer-side copies of deleted records.

        ``markers`` drive disclosure scanning on every file (lines mentioning
        deleted content). Purging of owned sanitized-spool copies is scoped
        to ``target_event_ids`` (tombstoned event ids): a spool line is
        removed only when it parses as JSON carrying a targeted event_id
        (I-1 bounded-delete integrity). Lines that merely share producer
        boilerplate with a targeted record are disclosed as matched but
        never purged.
        """
        report: List[Dict[str, Any]] = []
        if not markers:
            return report
        targets = set(target_event_ids or set())
        for entry in self._producer_files():
            item: Dict[str, Any] = {
                "source": entry.get("source"),
                "kind": entry.get("kind"),
                "path": entry.get("path"),
                "purgeable": entry.get("purgeable"),
                "retained_reason": entry.get("retained_reason"),
                "lines_scanned": 0,
                "matched_lines": 0,
                "purged_lines": 0,
            }
            raw_path = entry.get("path")
            if not raw_path:
                item["status"] = "unconfigured"
                report.append(item)
                continue
            path = Path(str(raw_path))
            if not path.exists():
                item["status"] = "missing"
                report.append(item)
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                item["status"] = f"unreadable: {exc}"
                report.append(item)
                continue
            lines = text.splitlines()
            item["lines_scanned"] = len(lines)
            matched = [i for i, line in enumerate(lines) if any(m in line for m in markers)]
            item["matched_lines"] = len(matched)
            if entry.get("purgeable") and (matched or targets):
                purge_idx = self._spool_purge_indexes(lines, targets)
                item["purge_scope"] = "event-identity"
                item["target_event_ids"] = len(targets)
                item["attributed_lines"] = len(purge_idx)
                if not targets:
                    item["purge_note"] = (
                        "no tombstoned event ids known (backend lacks "
                        "event_keys_for); spool purge skipped, disclosure only"
                    )
                if purge_idx:
                    purge_set = set(purge_idx)
                    kept = [line for i, line in enumerate(lines) if i not in purge_set]
                    try:
                        self._atomic_rewrite_lines(path, kept)
                    except OSError as exc:
                        item["status"] = f"purge-failed: {exc}"
                        report.append(item)
                        continue
                    item["purged_lines"] = len(purge_idx)
            item["status"] = "ok"
            report.append(item)
        return report

    @staticmethod
    def _spool_purge_indexes(lines: List[str], targets: Set[str]) -> List[int]:
        """Return spool line indexes attributable to targeted event ids.

        Every line is identity-checked (not only marker-matched lines): a
        targeted copy is removed even when redaction left no marker overlap.
        A line is purgeable only when it parses as JSON with an ``event_id``
        in ``targets``. Unparseable lines fail closed toward preservation:
        they are disclosed via the marker scan but never removed.
        """
        if not targets:
            return []
        purgeable: List[int] = []
        for i, line in enumerate(lines):
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, dict) and obj.get("event_id") in targets:
                purgeable.append(i)
        return purgeable

    @staticmethod
    def _atomic_rewrite_lines(path: Path, kept: List[str]) -> None:
        """Atomically rewrite a residue file keeping only non-matching lines."""
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".purge", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for line in kept:
                    handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _bump_deletion_generation(self) -> Optional[int]:
        """Advance the durable deletion generation counter when supported."""
        get_meta = getattr(self.journal, "get_meta", None)
        set_meta = getattr(self.journal, "set_meta", None)
        if not callable(get_meta) or not callable(set_meta):
            return None
        try:
            current = int(get_meta(DELETION_GENERATION_META_KEY, "0") or "0")
        except (TypeError, ValueError):
            current = 0
        generation = current + 1
        set_meta(DELETION_GENERATION_META_KEY, str(generation))
        return generation
