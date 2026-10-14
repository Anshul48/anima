"""Purpose-Bound Query and ContextSnapshot Service.

Implements QueryPort:
1. Purpose & Scope authorization against active Policy grants (403 reject on ungranted).
2. Freshness and TTL expiration checking.
3. Deterministic 4-tier token/size budget compression:
   - Tier 1: User Corrections & active workspace ID (Always Retained)
   - Tier 2: Immediate Focus & Session Task Clusters (confidence >= 0.85)
   - Tier 3: Project entity relationships and open loops
   - Tier 4: Low-confidence hypotheses (< 0.70) & long-horizon patterns (Pruned First)
4. Outgoing policy sanitization & mandatory epistemic disclaimer.
5. Interactive fact explanations with full provenance chains.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.policy.engine import PolicyEngine, compact_prune_manifest
from entorhinal.ports.interfaces import QueryPort
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.query.explanations import ExplanationEngine
from entorhinal.schemas.models import (
    SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE,
    ContextRequest,
    ContextSnapshot,
    DerivedFact,
    FactExplanation,
    Hypothesis,
    fact_matches_scope,
    generate_uuidv7,
    scope_covers_record_class,
)

logger = logging.getLogger(__name__)

#: Derived-by marker for session aggregate facts. Session values carry raw
#: per-record metadata (full target URIs), so session facts are gated on ALL
#: contributing record classes (AND), not tag OR: serve-time value mutation
#: would break the fact-id/content binding, so whole-fact gating is the only
#: integrity-preserving control. Node/relation fact values carry only coarse
#: slugged entity identities and keep tag-OR disclosure.
SESSION_FACT_DERIVED_BY = "MultiTimescaleCompiler.session_task"


class PermissionDeniedError(PermissionError):
    """Raised when a consumer ContextRequest violates policy purpose or scope grants."""
    pass


class ContextSnapshotService(QueryPort):
    """Core public service for synthesizing purpose-bound, advisory ContextSnapshots."""

    def __init__(
        self,
        compiler: MultiTimescaleCompiler,
        policy_engine: Optional[PolicyEngine] = None,
        journal: Optional[EvidenceJournal] = None,
        explanation_engine: Optional[ExplanationEngine] = None,
        correction_manager: Optional[Any] = None,
    ) -> None:
        self.compiler = compiler
        self.policy_engine = policy_engine or PolicyEngine()
        self.journal = journal
        self.explanation_engine = explanation_engine or ExplanationEngine(
            journal=self.journal,
            compiler=self.compiler,
        )
        self.correction_manager = correction_manager or getattr(compiler, "correction_manager", None)
        self._start_time: float = time.time()
        self._snapshot_cache: Dict[str, ContextSnapshot] = {}

    # --------------------------------------------------------------------------
    # Snapshot Generation (QueryPort Implementation)
    # --------------------------------------------------------------------------

    async def request_snapshot(
        self,
        request: ContextRequest,
        principal: Optional[Any] = None,
    ) -> ContextSnapshot:
        """Synthesize a bounded, sanitized ContextSnapshot for an authorized consumer.

        Steps:
        1. Authorize consumer, stated purpose, and scopes with PolicyEngine.
        2. Gather active facts and hypotheses matching requested scopes.
        3. Apply freshness and TTL filtering (valid_from >= now - max_freshness).
        4. Enforce current deletion/revocation restrictions on every candidate.
        5. Apply 4-tier token/size budget compression (content prioritization).
        6. Sanitize via PolicyEngine (exact scope minimization + VERIFIED
           delivered-serialization budget; raises BudgetExceededError when the
           minimum envelope cannot fit).
        7. Seal with mandatory advisory disclaimer and TTL expiry.

        ``principal`` is the authenticated ``runtime.auth.Principal``
        (duck-typed to avoid an import cycle); when present, the requested
        budget is clamped to the principal's granted maximum and disclosed.
        """
        now = datetime.now(timezone.utc)

        # 1. Purpose & Scope Verification
        authorized = self.policy_engine.check_query_permission(request)
        if not authorized:
            logger.warning(
                "ContextRequest %s denied: consumer='%s', purpose='%s', scopes=%s",
                request.request_id,
                request.consumer_id,
                request.stated_purpose,
                request.requested_scopes,
            )
            raise PermissionDeniedError(
                f"403 PermissionDenied: Unauthorized purpose '{request.stated_purpose}' "
                f"or scopes {request.requested_scopes} for consumer '{request.consumer_id}'."
            )

        clamp_note: Optional[str] = None
        if principal is not None:
            try:
                grant_max = int(getattr(principal, "max_budget", 0) or 0)
            except (TypeError, ValueError):
                grant_max = 0
            if grant_max >= 1 and request.token_or_size_budget > grant_max:
                request.token_or_size_budget = grant_max
                clamp_note = f"budget_clamped_to_grant:{grant_max}"

        # 2. Query Candidate Facts & Hypotheses
        active_facts = self.compiler.get_active_facts()
        active_hypotheses = self.compiler.get_active_hypotheses()

        # If no active facts compiled yet, run batch compilation
        if not active_facts:
            active_facts = await self.compiler.compile_batch_projection()
            active_hypotheses = self.compiler.get_active_hypotheses()
        elif self.correction_manager:
            active_facts = self.correction_manager.apply_to_facts(active_facts)

        # 3. Scope & Freshness Filtering
        freshness_cutoff = now - timedelta(seconds=request.max_freshness_seconds)
        matching_facts: List[DerivedFact] = []

        for fact in active_facts:
            # Check Freshness (allow facts created within max_freshness or valid into the future)
            is_fresh = fact.valid_from >= freshness_cutoff or (fact.valid_to and fact.valid_to >= now)
            if not is_fresh:
                continue

            # Check Scope Match (exact default-deny)
            if self._matches_scopes(fact, request.requested_scopes):
                matching_facts.append(fact)

        matching_hypotheses: List[Hypothesis] = [
            h for h in active_hypotheses
            if h.expires_at >= now and (not h.candidate_evidence_ids or True)
        ]

        # 4. Current deletion/revocation restrictions (every historical read
        # obeys the CURRENT policy, not the admission-time policy) plus
        # session-aggregate scope gating (AND over contributing classes).
        matching_facts, matching_hypotheses, restricted_count, session_excluded = (
            await self._enforce_current_restrictions(
                matching_facts, matching_hypotheses, list(request.requested_scopes or [])
            )
        )

        # 5. Deterministic 4-Tier Budget Pruning (content prioritization; the
        # final verified enforcement happens in sanitize_snapshot).
        pruned_facts, pruned_hypotheses, manifest = self._apply_tiered_budget_compression(
            facts=matching_facts,
            hypotheses=matching_hypotheses,
            budget_tokens=request.token_or_size_budget,
        )
        if clamp_note:
            manifest.append(clamp_note)
        if restricted_count:
            manifest.append(f"restricted_current_policy_count:{restricted_count}")
        if session_excluded:
            manifest.append(f"session_multi_scope_excluded_count:{session_excluded}")

        # 5. Extract Provenance References
        evidence_refs: List[str] = []
        for f in pruned_facts:
            evidence_refs.extend(f.supporting_evidence_ids)
        evidence_refs = sorted(list(set(evidence_refs)))

        # 6. TTL Calculation
        ttl_seconds = min(request.max_freshness_seconds, 300)
        expires_at = now + timedelta(seconds=ttl_seconds)

        # 7. Construct Draft Snapshot
        draft_snapshot = ContextSnapshot(
            snapshot_id=generate_uuidv7(),
            schema_version="1.0.0",
            request_id=request.request_id,
            issued_at=now,
            expires_at=expires_at,
            purpose_granted=request.stated_purpose,
            scope_granted=request.requested_scopes,
            active_facts=pruned_facts,
            active_hypotheses=pruned_hypotheses,
            evidence_provenance_refs=evidence_refs,
            redaction_manifest=manifest,
            disclaimer="ADVISORY ONLY. Direct user instruction and fresh observation take precedence.",
        )

        # 8. Policy Sanitization & Final Seal
        sealed_snapshot = self.policy_engine.sanitize_snapshot(draft_snapshot, request)
        self._snapshot_cache[sealed_snapshot.snapshot_id] = sealed_snapshot
        return sealed_snapshot

    # --------------------------------------------------------------------------
    # Scope Matching Helper
    # --------------------------------------------------------------------------

    def _matches_scopes(self, fact: DerivedFact, requested_scopes: List[str]) -> bool:
        """Exact default-deny scope match for one fact (see fact_matches_scope)."""
        return any(
            fact_matches_scope(fact.entity_uri, fact.scopes, pattern)
            for pattern in requested_scopes
        )

    async def _enforce_current_restrictions(
        self,
        facts: List[DerivedFact],
        hypotheses: List[Hypothesis],
        requested_scopes: Optional[List[str]] = None,
    ) -> Tuple[List[DerivedFact], List[Hypothesis], int, int]:
        """Drop candidates violating current restrictions or aggregate scope.

        Every historical read obeys the CURRENT deletion and consent state:
        a fact survives only when at least one supporting record still exists,
        is not tombstoned, and passes current consent evaluation. A hypothesis
        with cited evidence survives under the same rule; uncited hypotheses
        (explicitly labeled, TTL-bound) pass through.

        Session aggregate facts additionally require EVERY contributing
        record's class to be covered by the requested scopes (AND): their
        values embed raw per-record metadata (full target URIs), and
        serve-time value mutation would break the fact-id/content binding, so
        whole-fact gating is the only integrity-preserving control.
        Tombstoned/unconsented groundings still linger in compiled values, so
        their classes must be covered too (fail-closed).

        Returns the kept items plus the restricted-item count and the
        session-scope-exclusion count for disclosure. Without a journal
        handle, no verification is possible and candidates pass unfiltered
        (the qualified serving path always has a store handle).
        """
        if self.journal is None:
            return facts, hypotheses, 0, 0
        # Fetch each grounding record once per request and memoize consent
        # verdicts per capture class; candidates share groundings heavily.
        unique_ids: List[str] = []
        seen: set = set()
        for fact in facts:
            for evidence_id in fact.supporting_evidence_ids:
                if evidence_id not in seen:
                    seen.add(evidence_id)
                    unique_ids.append(evidence_id)
        for hypo in hypotheses:
            for evidence_id in hypo.candidate_evidence_ids:
                if evidence_id not in seen:
                    seen.add(evidence_id)
                    unique_ids.append(evidence_id)
        groundings = await self._grounding_records(unique_ids)
        verdicts = self._verdicts_from_groundings(groundings)
        scopes = list(requested_scopes or [])
        kept_facts: List[DerivedFact] = []
        restricted = 0
        session_excluded = 0
        for fact in facts:
            if not fact.supporting_evidence_ids:
                restricted += 1
                continue
            if any(str(e).startswith("user-correction:") for e in fact.supporting_evidence_ids):
                kept_facts.append(fact)
                continue
            if not any(verdicts.get(e, False) for e in fact.supporting_evidence_ids):
                restricted += 1
                continue
            if fact.derived_by == SESSION_FACT_DERIVED_BY and not self._session_classes_covered(
                fact.supporting_evidence_ids, groundings, scopes
            ):
                session_excluded += 1
                continue
            kept_facts.append(fact)
        kept_hypotheses: List[Hypothesis] = []
        for hypo in hypotheses:
            if not hypo.candidate_evidence_ids or any(
                verdicts.get(e, False) for e in hypo.candidate_evidence_ids
            ):
                kept_hypotheses.append(hypo)
            else:
                restricted += 1
        return kept_facts, kept_hypotheses, restricted, session_excluded

    @staticmethod
    def _session_classes_covered(
        evidence_ids: List[str],
        groundings: Dict[str, Any],
        requested_scopes: List[str],
    ) -> bool:
        """Whether every contributing record class is covered by the request."""
        for evidence_id in evidence_ids:
            record = groundings.get(evidence_id)
            record_class: Optional[str] = None
            if record is not None:
                record_class = SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE.get(
                    getattr(record.source_type, "value", str(record.source_type))
                )
            if not any(
                scope_covers_record_class(pattern, record_class) for pattern in requested_scopes
            ):
                return False
        return True

    async def _grounding_records(self, evidence_ids: List[str]) -> Dict[str, Any]:
        """Fetch each grounding record once (None when missing/unreadable)."""
        records: Dict[str, Any] = {}
        getter = getattr(self.journal, "get_by_id", None)
        if not callable(getter):
            return {e: None for e in evidence_ids}
        for evidence_id in evidence_ids:
            try:
                records[evidence_id] = await getter(evidence_id)
            except Exception:
                records[evidence_id] = None
        return records

    def _verdicts_from_groundings(self, groundings: Dict[str, Any]) -> Dict[str, bool]:
        """Current disclosability per grounding id from fetched records."""
        verdicts: Dict[str, bool] = {}
        consent_memo: Dict[tuple, bool] = {}
        for evidence_id, record in groundings.items():
            if record is None or getattr(record, "is_tombstone", False):
                verdicts[evidence_id] = False
                continue
            key = (
                getattr(record.source_type, "value", str(record.source_type)),
                record.app_identifier,
                record.target_uri,
            )
            if key not in consent_memo:
                try:
                    permitted, _ = self.policy_engine.is_consented(
                        record.source_type,
                        record.app_identifier,
                        record.target_uri,
                    )
                except Exception:
                    permitted = False
                consent_memo[key] = bool(permitted)
            verdicts[evidence_id] = consent_memo[key]
        return verdicts

    async def _grounding_verdicts(self, evidence_ids: List[str]) -> Dict[str, bool]:
        """Current disclosability per grounding id (one fetch each)."""
        getter = getattr(self.journal, "get_by_id", None)
        if not callable(getter):
            return {e: True for e in evidence_ids}
        return self._verdicts_from_groundings(await self._grounding_records(list(evidence_ids)))

    async def _grounding_permitted_now(self, evidence_ids: List[str]) -> bool:
        """Whether at least one grounding record is currently disclosable."""
        if not evidence_ids:
            return False
        # Explicit first-party user-correction groundings are permitted by the
        # user's own act (consent-gated capture does not apply to them).
        if any(str(e).startswith("user-correction:") for e in evidence_ids):
            return True
        verdicts = await self._grounding_verdicts(list(evidence_ids))
        return any(verdicts.get(e, False) for e in evidence_ids)

    def invalidate_snapshot_cache(self, reason: str = "") -> int:
        """Drop all cached sealed snapshots (deletion/revocation path hook).

        Returns the number of entries dropped for measured disclosure.
        """
        dropped = len(self._snapshot_cache)
        self._snapshot_cache.clear()
        if dropped:
            logger.info("snapshot cache invalidated (%d entries): %s", dropped, reason)
        return dropped

    # --------------------------------------------------------------------------
    # Deterministic 4-Tier Budget Compression
    # --------------------------------------------------------------------------

    def _apply_tiered_budget_compression(
        self,
        facts: List[DerivedFact],
        hypotheses: List[Hypothesis],
        budget_tokens: int,
    ) -> Tuple[List[DerivedFact], List[Hypothesis], List[str]]:
        """Apply deterministic 4-tier priority pruning under token budget constraints.

        Tiers:
        - Tier 1 (Always Retained): Direct User Corrections & active workspace/repo identifier.
        - Tier 2 (High Priority): Immediate Focus & Session Task Clusters (confidence >= 0.85).
        - Tier 3 (Medium Priority): Project entity relationships and open loops.
        - Tier 4 (Pruned First): Low-confidence hypotheses (< 0.70) & long-horizon traits.
        """
        # Character budget approximation (4 chars per token)
        budget_chars = budget_tokens * 4
        manifest: List[str] = []

        tier1: List[DerivedFact] = []
        tier2: List[DerivedFact] = []
        tier3: List[DerivedFact] = []
        tier4_facts: List[DerivedFact] = []

        for f in facts:
            uri = f.entity_uri.lower()
            if "workspace" in uri or "project" in uri or "user_correction" in uri:
                tier1.append(f)
            elif ("session" in uri or "immediate" in uri or "focus" in uri) and f.confidence >= 0.85:
                tier2.append(f)
            elif "relation" in f.attribute or "goal" in uri or "artifact" in uri:
                tier3.append(f)
            else:
                tier4_facts.append(f)

        # Sort each tier by confidence descending, then by valid_from descending
        tier1.sort(key=lambda f: (f.confidence, f.valid_from), reverse=True)
        tier2.sort(key=lambda f: (f.confidence, f.valid_from), reverse=True)
        tier3.sort(key=lambda f: (f.confidence, f.valid_from), reverse=True)
        tier4_facts.sort(key=lambda f: (f.confidence, f.valid_from), reverse=True)

        high_conf_hypotheses = [h for h in hypotheses if h.confidence_score >= 0.70]
        low_conf_hypotheses = [h for h in hypotheses if h.confidence_score < 0.70]
        high_conf_hypotheses.sort(key=lambda h: h.confidence_score, reverse=True)
        low_conf_hypotheses.sort(key=lambda h: h.confidence_score, reverse=True)

        retained_facts: List[DerivedFact] = []
        retained_hypotheses: List[Hypothesis] = []
        current_chars = 0

        # Pack Tier 1 (Always Retained)
        for f in tier1:
            f_size = len(json.dumps(f.model_dump(), default=str))
            retained_facts.append(f)
            current_chars += f_size

        # Pack Tier 2
        for f in tier2:
            f_size = len(json.dumps(f.model_dump(), default=str))
            if current_chars + f_size <= budget_chars:
                retained_facts.append(f)
                current_chars += f_size
            else:
                manifest.append(f"pruned_tier2_fact:{f.fact_id}")

        # Pack High-Confidence Hypotheses
        for h in high_conf_hypotheses:
            h_size = len(json.dumps(h.model_dump(), default=str))
            if current_chars + h_size <= budget_chars:
                retained_hypotheses.append(h)
                current_chars += h_size
            else:
                manifest.append(f"pruned_hypothesis:{h.hypothesis_id}")

        # Pack Tier 3
        for f in tier3:
            f_size = len(json.dumps(f.model_dump(), default=str))
            if current_chars + f_size <= budget_chars:
                retained_facts.append(f)
                current_chars += f_size
            else:
                manifest.append(f"pruned_tier3_fact:{f.fact_id}")

        # Pack Tier 4 Facts
        for f in tier4_facts:
            f_size = len(json.dumps(f.model_dump(), default=str))
            if current_chars + f_size <= budget_chars:
                retained_facts.append(f)
                current_chars += f_size
            else:
                manifest.append(f"pruned_tier4_fact:{f.fact_id}")

        # Pack Low-Confidence Hypotheses (Pruned First)
        for h in low_conf_hypotheses:
            h_size = len(json.dumps(h.model_dump(), default=str))
            if current_chars + h_size <= budget_chars:
                retained_hypotheses.append(h)
                current_chars += h_size
            else:
                manifest.append(f"pruned_low_confidence_hypothesis:{h.hypothesis_id}")

        # Bound the prune ledger so the audit trail cannot itself crowd
        # content out of the final verified budget (counts preserved).
        return retained_facts, retained_hypotheses, compact_prune_manifest(manifest)

    # --------------------------------------------------------------------------
    # Provenance Explanation (QueryPort Implementation)
    # --------------------------------------------------------------------------

    async def explain_fact(self, fact_id: str) -> Optional[FactExplanation]:
        """Generate full provenance explanation for a derived fact in <10ms."""
        return await self.explanation_engine.explain_fact(fact_id)

    # --------------------------------------------------------------------------
    # Fact Queries (QueryPort Implementation)
    # --------------------------------------------------------------------------

    async def query_facts(
        self,
        entity_uri: Optional[str] = None,
        attribute: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[DerivedFact]:
        """Query active derived facts with optional entity, attribute, and confidence filters."""
        facts = self.compiler.get_active_facts()
        if not facts:
            facts = await self.compiler.compile_batch_projection()

        results: List[DerivedFact] = []
        for f in facts:
            if entity_uri and f.entity_uri != entity_uri:
                continue
            if attribute and f.attribute != attribute:
                continue
            if f.confidence < min_confidence:
                continue
            results.append(f)
        return results

    # --------------------------------------------------------------------------
    # Health & Status
    # --------------------------------------------------------------------------

    def get_service_status(self) -> Dict[str, Any]:
        """Return uptime, projection version, fact count, and active grants."""
        uptime = time.time() - self._start_time
        context = self.compiler.get_current_context()

        return {
            "service": "entorhinal.context_snapshot_service",
            "status": "operational",
            "uptime_seconds": round(uptime, 2),
            "projection_version": "1.0.0",
            "active_facts_count": context.active_facts_count,
            "active_hypotheses_count": context.active_hypotheses_count,
            "cached_snapshots_count": len(self._snapshot_cache),
        }
