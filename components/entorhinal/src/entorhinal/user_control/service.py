"""Unified User Control and Governance Service.

Implements UserControlPort and provides comprehensive human-in-the-loop controls:
1. User correction submission with permanent attribute override locks (<50ms).
2. Cryptographic cascade deletion ("Forget Time Range") with zero residual data verification.
3. Dynamic grant/revocation of source and domain permissions.
4. Full consumer query auditing and system data export (JSON/ZIP).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.policy.engine import ConsentRule, PolicyEngine
from entorhinal.ports.interfaces import UserControlPort
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.projections.graph import SemanticGraphManager
from entorhinal.query.service import ContextSnapshotService
from entorhinal.schemas.models import (
    CorrectionAction,
    DerivedFact,
    SourceType,
    UserCorrection,
    generate_uuidv7,
)
from entorhinal.user_control.audit import AuditLogManager
from entorhinal.user_control.corrections import CorrectionManager
from entorhinal.user_control.deletion import CascadeDeletionEngine

logger = logging.getLogger(__name__)


class UserControlService(UserControlPort):
    """Core governance service managing user sovereignty, corrections, consent, and deletions."""

    def __init__(
        self,
        journal: Optional[EvidenceJournal] = None,
        policy_engine: Optional[PolicyEngine] = None,
        compiler: Optional[MultiTimescaleCompiler] = None,
        snapshot_service: Optional[ContextSnapshotService] = None,
        graph_manager: Optional[SemanticGraphManager] = None,
        correction_manager: Optional[CorrectionManager] = None,
        deletion_engine: Optional[CascadeDeletionEngine] = None,
        audit_manager: Optional[AuditLogManager] = None,
        storage_dir: Optional[Union[str, Path]] = None,
        source_specs: Optional[List[Dict[str, Any]]] = None,
        on_forget: Optional[Callable[[Dict[str, Any]], None]] = None,
        adapter_accessor: Optional[Callable[[], Dict[str, Any]]] = None,
        activity_service: Optional[Any] = None,
    ) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else None
        # Post-forget hook (F6.3): the runtime factory wires temporal
        # projection invalidation here so every deletion path through this
        # service rewinds derived state. Failures are recorded on the proof,
        # never silent, and never fail the deletion itself.
        self.on_forget = on_forget
        # Live-adapter accessor (N4): the factory wires lifecycle.adapters
        # here so adapter-owned managed copies (cursors, denied log,
        # compaction) are purged via the adapter's own purge_managed hook.
        self.adapter_accessor = adapter_accessor
        # Local activity service (activity-build §8.4): the factory wires
        # the runtime's ActivityService here so forget cascades into
        # derived sessions/labels/connections. None disables the cascade.
        self.activity_service = activity_service
        self.journal = journal or EvidenceJournal()
        self.policy_engine = policy_engine or PolicyEngine()
        self.compiler = compiler or MultiTimescaleCompiler(journal=self.journal)
        self.graph_manager = graph_manager or self.compiler.graph_manager
        self.snapshot_service = snapshot_service

        # Initialize sub-managers
        corr_storage = self.storage_dir / "user_corrections.jsonl" if self.storage_dir else None
        audit_storage = self.storage_dir / "audit_log.jsonl" if self.storage_dir else None
        self.consent_storage = self.storage_dir / "consent_rules.jsonl" if self.storage_dir else None

        if self.consent_storage and self.consent_storage.exists():
            self._load_consent_rules()

        self.correction_manager = correction_manager or CorrectionManager(
            storage_path=corr_storage,
            graph_manager=self.graph_manager,
        )
        if self.compiler and not getattr(self.compiler, "correction_manager", None):
            self.compiler.correction_manager = self.correction_manager
        if self.snapshot_service and not getattr(self.snapshot_service, "correction_manager", None):
            self.snapshot_service.correction_manager = self.correction_manager

        self.deletion_engine = deletion_engine or CascadeDeletionEngine(
            journal=self.journal,
            graph_manager=self.graph_manager,
            compiler=self.compiler,
            snapshot_service=self.snapshot_service,
            storage_root=self.storage_dir,
            source_specs=source_specs,
        )
        self.audit_manager = audit_manager or AuditLogManager(
            storage_path=audit_storage,
        )

    def _load_consent_rules(self) -> None:
        """Load persisted consent rules from disk."""
        if not self.consent_storage or not self.consent_storage.exists():
            return
        try:
            with open(self.consent_storage, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    data = json.loads(line_str)
                    st_val = data.get("source_type")
                    st = SourceType(st_val) if st_val else None
                    rule = ConsentRule(
                        rule_id=data["rule_id"],
                        source_type=st,
                        app_pattern=data.get("app_pattern"),
                        domain_pattern=data.get("domain_pattern"),
                        allow=data.get("allow", True),
                        priority=data.get("priority", 0),
                    )
                    if not any(r.rule_id == rule.rule_id for r in self.policy_engine.consent_rules):
                        self.policy_engine.consent_rules.append(rule)
            self.policy_engine.consent_rules.sort(key=lambda r: r.priority, reverse=True)
        except Exception as e:
            logger.error("Failed to load consent rules: %s", e)

    def _persist_consent_rules(self) -> None:
        """Persist active consent rules to disk."""
        if not self.consent_storage:
            return
        self.consent_storage.parent.mkdir(parents=True, exist_ok=True)
        with open(self.consent_storage, "w", encoding="utf-8") as f:
            for r in self.policy_engine.consent_rules:
                item = {
                    "rule_id": r.rule_id,
                    "source_type": r.source_type.value if r.source_type else None,
                    "app_pattern": r.app_pattern,
                    "domain_pattern": r.domain_pattern,
                    "allow": r.allow,
                    "priority": r.priority,
                }
                f.write(json.dumps(item, sort_keys=True, default=str) + "\n")


    # --------------------------------------------------------------------------
    # 1. User Corrections & Override Locks
    # --------------------------------------------------------------------------

    async def submit_correction(self, correction: UserCorrection) -> bool:
        """UserControlPort: Apply an explicit user correction override lock."""
        try:
            self.correction_manager.register_correction_object(correction)

            # Record audit event
            self.audit_manager.record_event(
                action="USER_CORRECTION_SUBMITTED",
                details={
                    "correction_id": correction.correction_id,
                    "target": correction.target_entity_or_fact_id,
                    "action": correction.override_action.value,
                    "comment": correction.user_comment,
                },
                permitted=True,
            )
            return True
        except Exception as e:
            logger.error("Failed to submit correction: %s", e)
            return False

    async def submit_user_correction(
        self,
        target_entity_or_fact_id: str,
        corrected_value: Any,
        user_note: Optional[str] = None,
        override_action: CorrectionAction = CorrectionAction.OVERWRITE,
    ) -> UserCorrection:
        """Record explicit user override with static attribute lock (<50ms propagation)."""
        corr = self.correction_manager.submit_correction(
            target_id=target_entity_or_fact_id,
            corrected_value=corrected_value,
            override_action=override_action,
            user_comment=user_note,
        )

        self.audit_manager.record_event(
            action="USER_CORRECTION_SUBMITTED",
            details={
                "correction_id": corr.correction_id,
                "target": target_entity_or_fact_id,
                "action": override_action.value,
                "corrected_value": corrected_value,
                "user_note": user_note,
            },
            permitted=True,
        )
        return corr

    def list_corrections(self) -> List[UserCorrection]:
        """List all active user corrections and attribute locks."""
        return self.correction_manager.list_corrections()

    # --------------------------------------------------------------------------
    # 2. Dynamic Consent & Source Governance
    # --------------------------------------------------------------------------

    async def grant_consent(
        self,
        source_type: SourceType,
        app_pattern: str,
        domain_pattern: str,
    ) -> str:
        """UserControlPort: Add a permitted consent rule."""
        rule_id = self.policy_engine.add_consent_rule(
            allow=True,
            source_type=source_type,
            app_pattern=app_pattern if app_pattern != "*" else None,
            domain_pattern=domain_pattern if domain_pattern != "*" else None,
        )
        self._persist_consent_rules()
        # F12 recovery: a new grant may unblock policy-denied spooled
        # events. Ask live adapters to re-emit drained-but-uncommitted
        # backlog (adapter-repair/INTERFACES.md: requeue_pending); the
        # commit path stays idempotent, so re-emission is safe.
        requeued: Dict[str, Any] = {}
        if self.adapter_accessor is not None:
            try:
                adapters = self.adapter_accessor()
            except Exception as e:
                logger.error("Adapter accessor failed on grant: %s", e)
                adapters = {}
            for name, adapter in (adapters or {}).items():
                hook = getattr(adapter, "requeue_pending", None)
                if not callable(hook):
                    continue
                try:
                    result = hook()
                    if asyncio.iscoroutine(result):
                        result = await result
                    requeued[name] = result
                except Exception as e:
                    logger.error("requeue_pending failed for %s: %s", name, e)
                    requeued[name] = {"error": f"{type(e).__name__}: {e}"}
        self.audit_manager.record_event(
            action="CONSENT_GRANTED",
            details={
                "rule_id": rule_id,
                "source_type": source_type.value,
                "app_pattern": app_pattern,
                "domain_pattern": domain_pattern,
                "requeued_pending": requeued,
            },
            permitted=True,
        )
        return rule_id

    async def revoke_consent(self, rule_id: str) -> bool:
        """UserControlPort: Revoke an active consent rule."""
        removed = self.policy_engine.remove_consent_rule(rule_id)
        if removed:
            self._persist_consent_rules()
            generation = self._bump_revocation_generation()
            self.audit_manager.record_event(
                action="CONSENT_REVOKED",
                details={"rule_id": rule_id, "revocation_generation": generation},
                permitted=True,
            )
        return removed

    def _bump_revocation_generation(self) -> Optional[int]:
        """Advance the durable revocation generation counter when supported.

        Consumers compare generations to detect that a revoke ran after
        their snapshot was taken; the temporal holder adopts it on rebuild
        (api-repair/INTERFACES.md §7.5). Serve-time consent filtering
        enforces current revocation on every read regardless.
        """
        get_meta = getattr(self.journal, "get_meta", None)
        set_meta = getattr(self.journal, "set_meta", None)
        if not callable(get_meta) or not callable(set_meta):
            return None
        try:
            current = int(get_meta("revocation_generation", "0") or "0")
        except (TypeError, ValueError):
            current = 0
        generation = current + 1
        set_meta("revocation_generation", str(generation))
        return generation

    async def update_source_permission(
        self,
        adapter_id: str,
        scope_pattern: str,
        is_granted: bool,
    ) -> None:
        """Dynamically enable or revoke capture consent for a specific adapter/pattern."""
        # Find source type if possible
        st: Optional[SourceType] = None
        for s in SourceType:
            if s.value in adapter_id.lower():
                st = s
                break

        if is_granted:
            self.policy_engine.add_consent_rule(
                allow=True,
                source_type=st,
                app_pattern=scope_pattern,
                domain_pattern=scope_pattern,
            )
        else:
            self.policy_engine.add_consent_rule(
                allow=False,
                source_type=st,
                app_pattern=scope_pattern,
                domain_pattern=scope_pattern,
                priority=100,  # High priority deny
            )

        self._persist_consent_rules()
        self.audit_manager.record_event(
            action="SOURCE_PERMISSION_UPDATED",
            details={
                "adapter_id": adapter_id,
                "scope_pattern": scope_pattern,
                "is_granted": is_granted,
            },
            permitted=True,
        )

    def list_consent_rules(self) -> List[ConsentRule]:
        """List active policy consent rules."""
        return list(self.policy_engine.consent_rules)

    # --------------------------------------------------------------------------
    # 3. Cryptographic Cascade Deletion ("Forget This")
    # --------------------------------------------------------------------------

    async def _after_forget(self, proof: Dict[str, Any]) -> None:
        """Run post-forget hooks; record failures on the proof.

        1. ``on_forget`` (F6.3 temporal projection invalidation).
        2. Live-adapter ``purge_managed(*, reason, event_ids)`` (N4, per
           adapter-repair/INTERFACES.md): adapters that expose the hook
           purge their own managed copies and report measured counts;
           adapters without it are skipped (the engine's direct spool
           purge + residue disclosure still apply). ``managed_paths()``
           output is disclosed when offered.
        3. Activity cascade (activity-build §8.4): the same window/app/
           domain selectors tombstone derived activity state.
        """
        if self.on_forget is not None:
            try:
                self.on_forget(proof)
            except Exception as e:
                logger.error("Post-forget hook failed: %s", e)
                proof["post_forget_hook_error"] = f"{type(e).__name__}: {e}"
        if self.adapter_accessor is None:
            return
        try:
            adapters = self.adapter_accessor()
        except Exception as e:
            logger.error("Adapter accessor failed: %s", e)
            proof["adapter_purge_error"] = f"{type(e).__name__}: {e}"
            return
        purges: Dict[str, Any] = {}
        managed: Dict[str, Any] = {}
        event_ids = proof.get("tombstoned_event_ids") or None
        for name, adapter in (adapters or {}).items():
            paths_hook = getattr(adapter, "managed_paths", None)
            if callable(paths_hook):
                try:
                    managed[name] = paths_hook()
                except Exception as e:
                    managed[name] = {"error": f"{type(e).__name__}: {e}"}
            hook = getattr(adapter, "purge_managed", None)
            if not callable(hook):
                continue
            try:
                # Contract: purge_managed(*, reason, event_ids=None,
                # match_all=False). Targeted forget passes the tombstoned
                # event ids; full-forget match_all stays a future CLI path.
                result = hook(
                    reason=proof.get("reason", "User deletion request"),
                    event_ids=list(event_ids) if event_ids else None,
                )
                if asyncio.iscoroutine(result):
                    result = await result
                purges[name] = result if isinstance(result, dict) else {"result": result}
            except Exception as e:
                logger.error("Adapter purge_managed failed for %s: %s", name, e)
                purges[name] = {"error": f"{type(e).__name__}: {e}"}
        if managed:
            proof["adapter_managed_paths"] = managed
        if purges:
            proof["adapter_purge"] = purges
        await self._cascade_activity_forget(proof)

    async def _cascade_activity_forget(self, proof: Dict[str, Any]) -> None:
        """Cascade a forget into the local ActivityService (activity §8.4).

        Selectors map from the engine proof (time window, app/domain
        filters; retention passes its cutoff as the window end). With no
        selector at all the cascade is skipped rather than wiping all
        activity. Failures are recorded on the proof, never silent.
        """
        activity = self.activity_service
        if activity is None:
            return
        request_deletion = getattr(activity, "request_deletion", None)
        if not callable(request_deletion):
            proof["activity_deletion_error"] = "activity service has no request_deletion"
            return

        def _parse_moment(value: Any) -> Optional[datetime]:
            if not value or not isinstance(value, str):
                return None
            try:
                moment = datetime.fromisoformat(value)
            except ValueError:
                return None
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return moment

        time_start = _parse_moment(proof.get("time_range_start"))
        time_end = _parse_moment(proof.get("time_range_end"))
        if time_start is None and time_end is None and proof.get("cutoff_iso"):
            # Retention path: tombstone-by-id carries no window; the cutoff
            # end-bounds the activity cascade identically.
            time_end = _parse_moment(proof.get("cutoff_iso"))
        app_substring = proof.get("app_filter")
        domain = proof.get("domain_filter")
        if (
            time_start is None
            and time_end is None
            and not app_substring
            and not domain
        ):
            proof["activity_deletion_skipped"] = (
                "no mappable selector (id-only forget); activity cascade skipped"
            )
            return
        try:
            result = request_deletion(
                time_start=time_start,
                time_end=time_end,
                app_substring=app_substring,
                domain=domain,
                reason=proof.get("reason", "User deletion request"),
            )
            if asyncio.iscoroutine(result):
                result = await result
            dump = getattr(result, "model_dump", None)
            proof["activity_deletion"] = (
                dump(mode="json") if callable(dump) else dict(result)
            )
        except Exception as e:
            logger.error("Activity cascade deletion failed: %s", e)
            proof["activity_deletion_error"] = f"{type(e).__name__}: {e}"
            return
        save_snapshot = getattr(activity, "save_snapshot", None)
        if callable(save_snapshot):
            try:
                saved = save_snapshot()
                if asyncio.iscoroutine(saved):
                    await saved
            except Exception as e:
                logger.error("Activity snapshot save failed: %s", e)
                proof["activity_snapshot_error"] = f"{type(e).__name__}: {e}"

    async def request_deletion(
        self,
        time_range_start: Optional[datetime] = None,
        time_range_end: Optional[datetime] = None,
        domain: Optional[str] = None,
        app_identifier: Optional[str] = None,
    ) -> int:
        """UserControlPort: Execute cascade cryptographic tombstoning."""
        result = await self.deletion_engine.cascade_delete(
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            domain=domain,
            app_identifier=app_identifier,
        )
        await self._after_forget(result)
        count = result.get("tombstoned_records_count", 0)

        self.audit_manager.record_event(
            action="CASCADE_DELETION_EXECUTED",
            details=result,
            permitted=True,
        )
        return count

    async def forget_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        reason: str = "User deletion request",
    ) -> Dict[str, Any]:
        """Execute cascade deletion across a bounded temporal window with cryptographic proof."""
        proof = await self.deletion_engine.forget_time_range(
            start_time=start_time,
            end_time=end_time,
            reason=reason,
        )
        await self._after_forget(proof)

        self.audit_manager.record_event(
            action="FORGET_TIME_RANGE_EXECUTED",
            details=proof,
            permitted=True,
        )
        return proof

    async def enforce_retention(
        self,
        max_age_days: int = 30,
        reason: str = "Retention enforcement (P11 30-day payload retention)",
    ) -> Dict[str, Any]:
        """Tombstone records older than the retention window (G23).

        Selection keys on durable ``committed_at`` via the store's commit
        index — the same clock as ``retention_status`` — so the candidate set
        matches the measured expired set; already-tombstoned rows are
        skipped by the engine and reported via the proof counts.
        Enforcement is explicit (CLI ``retention --enforce``); nothing here
        runs automatically.
        """
        from datetime import timedelta

        commit_index = getattr(self.journal, "commit_index", None)
        if not callable(commit_index):
            raise TypeError(
                f"{type(self.journal).__name__} exposes no commit index; "
                "retention enforcement requires the SQLite backend"
            )
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        expired_ids = [
            evidence_id
            for evidence_id, (_seq, committed_at) in commit_index().items()
            if committed_at is not None and committed_at < cutoff
        ]
        if not expired_ids:
            return {
                "retention_enforced": True,
                "max_age_days": max_age_days,
                "cutoff_iso": cutoff.isoformat(),
                "expired_count": 0,
                "tombstoned_records_count": 0,
                "reason": reason,
            }
        proof = await self.deletion_engine.cascade_delete(
            record_ids=sorted(expired_ids),
            reason=reason,
        )
        proof["retention_enforced"] = True
        proof["max_age_days"] = max_age_days
        proof["cutoff_iso"] = cutoff.isoformat()
        await self._after_forget(proof)

        self.audit_manager.record_event(
            action="RETENTION_ENFORCED",
            details=proof,
            permitted=True,
        )
        return proof

    # --------------------------------------------------------------------------
    # 4. Audit Trail & Full-System Export
    # --------------------------------------------------------------------------

    async def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """UserControlPort: Retrieve recent policy and query audit events."""
        return self.audit_manager.query_logs(limit=limit)

    async def get_audit_log(
        self,
        limit: int = 100,
        consumer_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return log of all queries, consumers, disclosed scopes, and governance events."""
        return self.audit_manager.query_logs(
            limit=limit,
            consumer_filter=consumer_filter,
        )

    async def export_data(
        self,
        format: str = "json",
        output_path: Optional[Union[str, Path]] = None,
    ) -> Union[str, bytes]:
        """Export comprehensive system audit and state payload (JSON or ZIP archive)."""
        journal_records = [r.model_dump() for r in (await self.journal.scan_evidence(limit=100000))]
        graph_state = self.graph_manager.export_state().model_dump()
        corrections = [c.model_dump() for c in self.correction_manager.list_corrections()]

        exported = self.audit_manager.export_data(
            format=format,
            journal_records=journal_records,
            graph_state=graph_state,
            corrections=corrections,
            output_path=output_path,
        )

        self.audit_manager.record_event(
            action="DATA_EXPORTED",
            details={"format": format, "records_count": len(journal_records)},
            permitted=True,
        )
        return exported
