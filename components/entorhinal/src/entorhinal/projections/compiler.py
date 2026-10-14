"""Multi-Timescale Semantic Projection Compiler.

Coordinates four operational horizons:
1. Immediate Focus Compiler (1s - 5m): <5ms incremental tracking of active window/app/document.
2. Session & Workflow Compiler (5m - 8h): Groups interleaved windows into Task Clusters.
3. Project & Entity Graph (1d - 30d): Maintains Node-Attribute Triples and typed relations.
4. Long-Horizon Pattern Compiler (1m - 1y): Aggregates developer tool traits and diurnal habits.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Union

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.evidence.stager import ProjectionStager, StagedProjectionContext
from entorhinal.projections.clustering import SessionClusterEngine
from entorhinal.projections.graph import SemanticGraphManager
from entorhinal.projections.models import (
    EntityNodeType,
    ImmediateFocusState,
    MultiTimescaleContext,
    ProjectionCompiler,
    SessionTaskCluster,
)
from entorhinal.projections.uncertainty import HypothesisManager, UncertaintyEngine
from entorhinal.schemas.models import (
    SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE,
    DerivedFact,
    EvidenceRecord,
    Hypothesis,
    SourceType,
    derive_cluster_id,
    derive_fact_id,
    generate_uuidv7,
)

logger = logging.getLogger(__name__)


class MultiTimescaleCompiler(ProjectionCompiler):
    """Multi-timescale projection compiler coordinating immediate, session, graph, and habit models."""

    def __init__(
        self,
        journal: Optional[EvidenceJournal] = None,
        cluster_engine: Optional[SessionClusterEngine] = None,
        graph_manager: Optional[SemanticGraphManager] = None,
        uncertainty_engine: Optional[UncertaintyEngine] = None,
        hypothesis_manager: Optional[HypothesisManager] = None,
        correction_manager: Optional[Any] = None,
    ) -> None:
        self.journal = journal
        self.cluster_engine = cluster_engine or SessionClusterEngine()
        self.graph_manager = graph_manager or SemanticGraphManager()
        self.uncertainty_engine = uncertainty_engine or UncertaintyEngine()
        self.hypothesis_manager = hypothesis_manager or HypothesisManager(self.uncertainty_engine)
        self.correction_manager = correction_manager

        # In-memory timescale state
        self._immediate_focus: Optional[ImmediateFocusState] = None
        self._active_cluster: Optional[SessionTaskCluster] = None
        self._completed_clusters: List[SessionTaskCluster] = []
        self._active_facts: List[DerivedFact] = []
        self._active_hypotheses: List[Hypothesis] = []
        self._app_usage_counts: Dict[str, int] = {}
        self._hourly_activity_histogram: Dict[int, int] = {h: 0 for h in range(24)}
        self._staged_context: Optional[StagedProjectionContext] = None

    # --------------------------------------------------------------------------
    # Horizon 1: Incremental Immediate Focus & Event Processing (<5ms)
    # --------------------------------------------------------------------------

    def process_incremental_event(self, record: EvidenceRecord) -> None:
        """Update fast in-memory immediate focus, active cluster, and graph state (<5ms)."""
        if record.is_tombstone:
            return

        now = record.persisted_at or datetime.now(timezone.utc)

        # 1. Update Immediate Focus State
        prev_dwell = 0.0
        if self._immediate_focus and self._immediate_focus.app_identifier == record.app_identifier:
            prev_dwell = (now - self._immediate_focus.timestamp).total_seconds()

        self._immediate_focus = ImmediateFocusState(
            focus_id=generate_uuidv7(),
            timestamp=now,
            app_identifier=record.app_identifier,
            window_title=record.window_title,
            target_uri=record.target_uri,
            focused_element=record.sanitized_payload.get("focused_element"),
            selected_text=record.sanitized_payload.get("selected_text"),
            source_type=record.source_type,
            duration_seconds=max(0.0, prev_dwell),
            supporting_evidence_id=record.record_id,
            metadata=dict(record.sanitized_payload),
        )

        # 2. Update Session Task Cluster
        updated_cluster, is_new = self.cluster_engine.update_active_cluster(
            self._active_cluster,
            record,
        )
        if is_new and self._active_cluster is not None:
            self._completed_clusters.append(self._active_cluster)
        self._active_cluster = updated_cluster

        # 3. Incrementally extract entity triples in graph
        self.graph_manager.extract_and_ingest_record(record)
        self._active_facts = self.graph_manager.to_derived_facts()

        # 4. Update Long-Horizon Aggregates
        app_name = record.app_identifier
        self._app_usage_counts[app_name] = self._app_usage_counts.get(app_name, 0) + 1
        hour = now.hour
        self._hourly_activity_histogram[hour] = self._hourly_activity_histogram.get(hour, 0) + 1

    # --------------------------------------------------------------------------
    # Horizon 2 & 3: Batch Projection Compiler & Semantic Synthesis
    # --------------------------------------------------------------------------

    async def compile_batch_projection(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[DerivedFact]:
        """Runs deterministic entity extraction, session clustering, and DerivedFact generation."""
        records: List[EvidenceRecord] = []
        if self.journal:
            records = await self.journal.scan_evidence(
                start_time=start_time,
                end_time=end_time,
                limit=100000,
            )

        # Re-populate graph deterministically
        self.graph_manager.clear()
        for r in records:
            if not r.is_tombstone:
                self.graph_manager.extract_and_ingest_record(r)

        # Cluster all records
        clusters = self.cluster_engine.cluster_records(records)
        # Pin deterministic cluster ids (cluster-id/1): identical evidence
        # replays identical session references, so session-fact anchors hold.
        record_scope_by_id: Dict[str, str] = {}
        for r in records:
            tag = SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE.get(r.source_type.value)
            if tag:
                record_scope_by_id[r.record_id] = tag
        for c in clusters:
            c.cluster_id = derive_cluster_id(
                evidence_ids=list(c.supporting_evidence_ids),
                start_time=c.start_time,
                end_time=c.end_time,
                title=c.title,
            )
        self._completed_clusters = clusters
        if clusters:
            self._active_cluster = clusters[-1]

        # Extract Graph Facts (100% evidence-backed)
        graph_facts = self.graph_manager.to_derived_facts()

        # Extract Session Facts
        session_facts: List[DerivedFact] = []
        for c in clusters:
            if c.supporting_evidence_ids:
                ordered_evidence = sorted(set(c.supporting_evidence_ids))
                session_value = {
                    "title": c.title,
                    "primary_app": c.primary_app,
                    "primary_topic": c.primary_topic,
                    "event_count": c.event_count,
                    "duration_seconds": c.duration_seconds,
                    "associated_apps": sorted(set(c.associated_apps)),
                    "associated_uris": sorted(set(c.associated_uris)),
                }
                session_tags = {"scope:workspace"}
                for ev_id in ordered_evidence:
                    tag = record_scope_by_id.get(ev_id)
                    if tag:
                        session_tags.add(tag)
                session_facts.append(
                    DerivedFact(
                        fact_id=derive_fact_id(
                            entity_uri=f"session:{c.cluster_id}",
                            attribute="active_task",
                            value=session_value,
                            valid_from=c.start_time,
                            valid_to=c.end_time,
                            evidence_ids=ordered_evidence,
                            derived_by="MultiTimescaleCompiler.session_task",
                        ),
                        schema_version="1.0.0",
                        entity_uri=f"session:{c.cluster_id}",
                        attribute="active_task",
                        value=session_value,
                        confidence=0.92,
                        valid_from=c.start_time,
                        valid_to=c.end_time,
                        supporting_evidence_ids=ordered_evidence,
                        derived_by="MultiTimescaleCompiler.session_task",
                        revision_id=1,
                        scopes=sorted(session_tags),
                    )
                )

        all_facts = graph_facts + session_facts
        if self.correction_manager:
            self.correction_manager.apply_to_graph(self.graph_manager)
            all_facts = self.correction_manager.apply_to_facts(all_facts)

        self._active_facts = all_facts

        # Generate active hypotheses for the latest session cluster
        if self._active_cluster and self._active_cluster.supporting_evidence_ids:
            self._active_hypotheses = await self.propose_hypotheses(self._active_cluster)
        else:
            self._active_hypotheses = []

        return all_facts

    async def purge_evidence(
        self,
        record_ids: List[str],
        *,
        reason: str = "",
    ) -> Dict[str, int]:
        """Purge deleted-evidence residues from focus + aggregates (N1/F6.1).

        Called by user-control deletion AFTER tombstoning. Clears the
        immediate focus when its grounding was deleted, and rebuilds the
        app-usage and hourly-histogram aggregates from the surviving
        (non-tombstoned) journal/store scan. Returns measured per-section
        counts for disclosure. Graph/facts/clusters are repopulated by the
        deletion-time batch recompile, not here.
        """
        doomed = set(record_ids or [])
        focus_cleared = 0
        focus = self._immediate_focus
        if focus is not None and focus.supporting_evidence_id in doomed:
            self._immediate_focus = None
            focus_cleared = 1
            logger.info("immediate focus cleared by purge: %s", reason)

        before_apps = sum(self._app_usage_counts.values())
        before_hours = sum(self._hourly_activity_histogram.values())
        rebuilt = 0
        scan = getattr(self.journal, "scan_evidence", None) if self.journal is not None else None
        if callable(scan):
            records = await scan(limit=100000)
            app_counts: Dict[str, int] = {}
            hours: Dict[int, int] = {h: 0 for h in range(24)}
            for rec in records or []:
                if getattr(rec, "is_tombstone", False):
                    continue
                app_counts[rec.app_identifier] = app_counts.get(rec.app_identifier, 0) + 1
                stamp = getattr(rec, "persisted_at", None)
                hour = stamp.hour if stamp is not None else 0
                hours[hour] = hours.get(hour, 0) + 1
            self._app_usage_counts = app_counts
            self._hourly_activity_histogram = hours
            rebuilt = 1

        return {
            "focus_cleared": focus_cleared,
            "app_usage_events_before": before_apps,
            "app_usage_events_after": sum(self._app_usage_counts.values()),
            "histogram_events_before": before_hours,
            "histogram_events_after": sum(self._hourly_activity_histogram.values()),
            "aggregates_rebuilt": rebuilt,
        }

    # --------------------------------------------------------------------------
    # Hypothesis Proposal
    # --------------------------------------------------------------------------

    async def propose_hypotheses(
        self,
        cluster_data: Union[Dict[str, Any], SessionTaskCluster],
    ) -> List[Hypothesis]:
        """Generate candidate intent labels with calibrated uncertainty and evidence links."""
        if isinstance(cluster_data, dict):
            cluster = SessionTaskCluster(**cluster_data)
        else:
            cluster = cluster_data

        supporting_records: List[EvidenceRecord] = []
        if self.journal and cluster.supporting_evidence_ids:
            for ev_id in cluster.supporting_evidence_ids[:10]:
                rec = await self.journal.get_by_id(ev_id)
                if rec and not rec.is_tombstone:
                    supporting_records.append(rec)

        return self.hypothesis_manager.propose_intent(
            cluster=cluster,
            supporting_records=supporting_records,
        )

    # --------------------------------------------------------------------------
    # Real-Time Context View
    # --------------------------------------------------------------------------

    def get_current_context(self) -> MultiTimescaleContext:
        """Returns the real-time composite multi-timescale state."""
        now = datetime.now(timezone.utc)

        # Active project nodes
        project_nodes = [
            n.entity_uri for n in self.graph_manager.list_nodes()
            if n.entity_type in (EntityNodeType.PROJECT, EntityNodeType.WORKSPACE, EntityNodeType.GOAL)
        ]

        # Top 3 most used apps
        top_apps = sorted(
            self._app_usage_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]

        long_horizon_traits = {
            "top_applications": [app for app, count in top_apps],
            "app_frequencies": dict(self._app_usage_counts),
            "hourly_activity_histogram": dict(self._hourly_activity_histogram),
            "total_events_observed": sum(self._app_usage_counts.values()),
        }

        return MultiTimescaleContext(
            timestamp=now,
            immediate_focus=self._immediate_focus or {},
            active_session_cluster=self._active_cluster or {},
            active_project_nodes=project_nodes,
            long_horizon_traits=long_horizon_traits,
            active_facts_count=len(self._active_facts),
            active_hypotheses_count=len(self._active_hypotheses),
        )

    # --------------------------------------------------------------------------
    # Staging and Atomic Activation
    # --------------------------------------------------------------------------

    async def stage_and_activate(
        self,
        stager: ProjectionStager,
        version: str = "1.0.0",
    ) -> StagedProjectionContext:
        """Compile, stage, validate invariants, and atomically activate projection."""
        facts = await self.compile_batch_projection()
        hypotheses = self._active_hypotheses
        graph_state = self.graph_manager.export_state()

        staged = stager.stage_new_projection(
            target_version=version,
            facts=facts,
            hypotheses=hypotheses,
            entities={k: v.model_dump() for k, v in graph_state.nodes.items()},
            metadata={"graph_id": graph_state.graph_id},
        )

        is_valid, errors = await stager.validate_candidate(staged)
        if not is_valid:
            raise ValueError(f"Staged projection validation failed: {errors}")

        await stager.activate_staged_projection(staged)
        self._staged_context = staged
        return staged

    # --------------------------------------------------------------------------
    # Getters
    # --------------------------------------------------------------------------

    def get_active_facts(self) -> List[DerivedFact]:
        """Return currently compiled active facts."""
        return list(self._active_facts)

    def get_active_hypotheses(self) -> List[Hypothesis]:
        """Return currently proposed active hypotheses."""
        return list(self._active_hypotheses)
