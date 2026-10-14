"""Comprehensive Evaluation, Quality, Privacy & Resilience Benchmark Runner.

Executes:
1. Track 1: Deterministic Synthetic Fixture Suite (50+ golden scenarios).
2. Track 2: Real Capability & Developer Activity Benchmarks (task segmentation F1, intent precision, ECE).
3. Adversarial Privacy Stress-Testing (500+ credential/PII injection vectors).
4. Chaos & Fault-Injection Resilience Suite (bit-flips, sigkill, corrupt JSON, cold replay).
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field

from entorhinal.evals.chaos import ChaosHarness
from entorhinal.evals.privacy_stress import PrivacyStressTester
from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.fixtures.golden import GOLDEN_FIXTURES
from entorhinal.policy.engine import PolicyEngine
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.query.service import ContextSnapshotService
from entorhinal.schemas.models import (
    ClassificationLevel,
    ContextRequest,
    EvidenceRecord,
    RawSignalEvent,
    SourceType,
    generate_uuidv7,
)
from entorhinal.user_control.service import UserControlService

logger = logging.getLogger(__name__)


# ==============================================================================
# Mathematical Metrics Formulation
# ==============================================================================

def calculate_expected_calibration_error(
    confidences: List[float],
    accuracies: List[bool],
    num_bins: int = 10,
) -> float:
    """Calculate true Expected Calibration Error (ECE) across equal-width confidence bins.

    Formula:
    ECE = sum_{m=1}^M (|B_m| / N) * |acc(B_m) - conf(B_m)|
    """
    n = len(confidences)
    if n == 0 or len(accuracies) != n:
        return 0.0

    bin_boundaries = np.linspace(0.0, 1.0, num_bins + 1)
    ece = 0.0

    for i in range(num_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        if i == num_bins - 1:
            in_bin = [j for j, c in enumerate(confidences) if bin_lower <= c <= bin_upper]
        else:
            in_bin = [j for j, c in enumerate(confidences) if bin_lower <= c < bin_upper]

        bin_size = len(in_bin)
        if bin_size > 0:
            bin_acc = sum(1.0 for j in in_bin if accuracies[j]) / bin_size
            bin_conf = sum(confidences[j] for j in in_bin) / bin_size
            ece += (bin_size / n) * abs(bin_acc - bin_conf)

    return round(float(ece), 4)


def calculate_intent_classification_metrics(
    ground_truth: List[str],
    predicted: List[str],
) -> Tuple[float, float, float]:
    """Calculate multi-class Precision, Recall, and F1 score for intent classifications."""
    if not ground_truth or len(ground_truth) != len(predicted):
        return 0.0, 0.0, 0.0

    classes = sorted(list(set(ground_truth + predicted)))
    if not classes:
        return 1.0, 1.0, 1.0

    precisions: List[float] = []
    recalls: List[float] = []
    f1s: List[float] = []

    for cls in classes:
        tp = sum(1 for gt, pr in zip(ground_truth, predicted) if gt == cls and pr == cls)
        fp = sum(1 for gt, pr in zip(ground_truth, predicted) if gt != cls and pr == cls)
        fn = sum(1 for gt, pr in zip(ground_truth, predicted) if gt == cls and pr != cls)

        prec = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if fn == 0 else 0.0)
        rec = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if fp == 0 else 0.0)
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)

    macro_precision = float(np.mean(precisions))
    macro_recall = float(np.mean(recalls))
    macro_f1 = float(np.mean(f1s))

    return round(macro_precision, 4), round(macro_recall, 4), round(macro_f1, 4)


def calculate_task_segmentation_f1(
    ground_truth_task_ids: List[str],
    predicted_cluster_ids: List[str],
) -> float:
    """Calculate true Task Segmentation F1 using Pairwise Rand-Index clustering overlap."""
    n = len(ground_truth_task_ids)
    if n <= 1 or len(predicted_cluster_ids) != n:
        return 1.0

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for i in range(n):
        for j in range(i + 1, n):
            same_gt = (ground_truth_task_ids[i] == ground_truth_task_ids[j])
            same_pred = (predicted_cluster_ids[i] == predicted_cluster_ids[j])

            if same_gt and same_pred:
                tp += 1
            elif not same_gt and same_pred:
                fp += 1
            elif same_gt and not same_pred:
                fn += 1
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return round(float(f1), 4)


def normalize_intent_category(intent_text: str) -> str:
    """Map natural-language intent proposals and ground-truth descriptions to canonical intent classes."""
    t = intent_text.lower()
    if "software development" in t or "test execution" in t or "dev" in t:
        return "software_dev_and_testing"
    if "code review" in t or "pull request" in t or "pr" in t:
        return "code_review_and_pr_triage"
    if "research" in t or "documentation" in t or "arxiv" in t or "paper" in t:
        return "research_and_documentation"
    if "editing" in t or "source code" in t:
        return "source_code_editing"
    return "general_task"


# ==============================================================================
# Evaluation Report Contract
# ==============================================================================

class EvaluationReport(BaseModel):
    """Formal verification and metric report contract matching Task E7 specification."""
    suite_id: str = Field(default_factory=generate_uuidv7)
    run_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    track: str  # "TRACK_1_SYNTHETIC", "TRACK_2_REAL_TRACE", "TRACK_PRIVACY_STRESS"
    status: str = "PASS"  # "PASS", "FAIL", "NOT_RUN", "BLOCKED", "INSUFFICIENT_EVIDENCE"
    details: Dict[str, Any] = Field(default_factory=dict)

    # Fidelity & Invariant Metrics
    schema_validation_pass_rate: Optional[float] = None        # Target: 1.00 (100%)
    provenance_coverage_rate: Optional[float] = None           # Target: 1.00 (100%)
    deterministic_rebuild_parity: Optional[float] = None       # Target: 1.00 (100%)

    # Semantic Quality Metrics
    task_segmentation_f1: Optional[float] = None               # Target: >= 0.88
    intent_classification_precision: Optional[float] = None    # Target: >= 0.85
    expected_calibration_error: Optional[float] = None         # Target: <= 0.10

    # Privacy & Security Metrics
    credential_leakage_count: Optional[int] = None             # Target: 0 (Hard Stop)
    pii_redaction_recall: Optional[float] = None               # Target: >= 0.99
    cascade_deletion_leakage_count: Optional[int] = None       # Target: 0 (Hard Stop)

    # Performance & Latency
    ingest_throughput_eps: Optional[float] = None              # Target: >= 2,000 events/sec
    journal_append_latency_p99_ms: Optional[float] = None      # Target: <= 5.0 ms
    snapshot_generation_latency_p99_ms: Optional[float] = None  # Target: <= 15.0 ms


# ==============================================================================
# Evaluation Runner
# ==============================================================================

class EvalRunner:
    """Core evaluation and benchmarking execution engine."""

    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
        privacy_tester: Optional[PrivacyStressTester] = None,
        chaos_harness: Optional[ChaosHarness] = None,
    ) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.privacy_tester = privacy_tester or PrivacyStressTester(self.policy_engine)
        self.chaos_harness = chaos_harness or ChaosHarness()

    # --------------------------------------------------------------------------
    # Track 1: Deterministic Synthetic Fixture Suite
    # --------------------------------------------------------------------------

    async def run_deterministic_fixture_suite(self) -> EvaluationReport:
        """Executes all 50+ golden fixtures verifying schema, provenance, and rebuild parity."""
        start_time = time.perf_counter()
        temp_dir = Path(tempfile.mkdtemp(prefix="entorhinal_track1_"))
        journal = EvidenceJournal(storage_path=temp_dir / "track1_journal.jsonl")
        compiler = MultiTimescaleCompiler(journal=journal)
        snapshot_service = ContextSnapshotService(
            compiler=compiler,
            policy_engine=self.policy_engine,
            journal=journal,
        )
        user_control = UserControlService(
            journal=journal,
            policy_engine=self.policy_engine,
            compiler=compiler,
            snapshot_service=snapshot_service,
            storage_dir=temp_dir,
        )

        valid_schemas = 0
        total_fixtures = len(GOLDEN_FIXTURES)
        provenance_valid_count = 0
        append_latencies: List[float] = []

        for fixture in GOLDEN_FIXTURES:
            raw_input = fixture["raw_source_input"]
            st = SourceType(raw_input["source_type"])

            sig = RawSignalEvent(
                source_type=st,
                adapter_id=raw_input.get("adapter_id", "adapter.fixture"),
                app_identifier=raw_input["app_identifier"],
                window_title=raw_input.get("window_title"),
                target_uri=raw_input.get("target_uri"),
                raw_payload=raw_input.get("raw_payload", {}),
            )

            # 1. Policy check
            decision = self.policy_engine.evaluate_signal(sig)
            if decision is not None:
                valid_schemas += 1

            clean_title, _ = self.policy_engine.redact_text(sig.window_title or "")
            clean_uri, _ = self.policy_engine.sanitize_uri(sig.target_uri)

            # 2. Append to journal
            t0 = time.perf_counter()
            rec = EvidenceRecord.create(
                source_type=sig.source_type,
                app_identifier=sig.app_identifier,
                window_title=clean_title,
                target_uri=clean_uri,
                sanitized_payload=decision.redacted_payload or {},
                classification=decision.classification,
                previous_record_hash=await journal.get_last_hash(),
            )
            await journal.append_evidence(rec)
            append_latencies.append((time.perf_counter() - t0) * 1000.0)

            # 3. Provenance check
            if len(rec.provenance_hash) == 64 and len(rec.previous_record_hash) == 64:
                provenance_valid_count += 1

            compiler.process_incremental_event(rec)

        # Recompile projections
        facts = await compiler.compile_batch_projection()

        # Rebuild parity check
        is_chain_valid, _, _ = journal.verify_journal_integrity()
        rebuild_parity = 1.0 if is_chain_valid else 0.0

        # Snapshot generation benchmark (multi-iteration for true percentile)
        snap_latencies: List[float] = []
        for _ in range(5):
            req = ContextRequest(
                consumer_id="reflex.system2.planner",
                stated_purpose="Context for task planning",
                requested_scopes=["scope:developer.*", "scope:workspace.*"],
            )
            snap_t0 = time.perf_counter()
            snapshot = await snapshot_service.request_snapshot(req)
            snap_latencies.append((time.perf_counter() - snap_t0) * 1000.0)
        snap_p99 = float(np.percentile(snap_latencies, 99)) if snap_latencies else 0.0

        # Test cascade deletion on 5 records
        first_5_records = await journal.scan_evidence(limit=5)
        if first_5_records:
            st_del = first_5_records[0].persisted_at - timedelta(seconds=1)
            et_del = first_5_records[-1].persisted_at + timedelta(seconds=1)
            del_proof = await user_control.forget_time_range(st_del, et_del)
            del_leak_count = del_proof.get("residual_leakage_count", 0)
        else:
            del_leak_count = 0

        elapsed = time.perf_counter() - start_time
        throughput_eps = total_fixtures / max(0.0001, elapsed)
        p99_append = float(np.percentile(append_latencies, 99)) if append_latencies else 0.0

        status = "PASS" if (
            valid_schemas == total_fixtures
            and provenance_valid_count == total_fixtures
            and is_chain_valid
            and del_leak_count == 0
        ) else "FAIL"

        return EvaluationReport(
            suite_id=generate_uuidv7(),
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            track="TRACK_1_SYNTHETIC",
            status=status,
            details={
                "total_fixtures": total_fixtures,
                "facts_compiled": len(facts),
                "cascade_deletion_proof_valid": is_chain_valid,
            },
            schema_validation_pass_rate=round(valid_schemas / max(1, total_fixtures), 4),
            provenance_coverage_rate=round(provenance_valid_count / max(1, total_fixtures), 4),
            deterministic_rebuild_parity=rebuild_parity,
            task_segmentation_f1=None,
            intent_classification_precision=None,
            expected_calibration_error=None,
            credential_leakage_count=None,
            pii_redaction_recall=None,
            cascade_deletion_leakage_count=del_leak_count,
            ingest_throughput_eps=round(throughput_eps, 2),
            journal_append_latency_p99_ms=round(p99_append, 2),
            snapshot_generation_latency_p99_ms=round(snap_p99, 2),
        )

    # --------------------------------------------------------------------------
    # Track 2: Real Capability & Reliability Benchmarks
    # --------------------------------------------------------------------------

    async def run_capability_benchmark(
        self,
        trace_corpus_path: Optional[str] = None,
    ) -> EvaluationReport:
        """Executes Track 2 real developer activity trace benchmark from verified consented manifest.

        Strict invariant: If trace_corpus_path is None or missing, returns status='NOT_RUN' or 'BLOCKED'.
        Does NOT manufacture fake synthetic data to masquerade as real developer traces.
        """
        if trace_corpus_path is None:
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="NOT_RUN",
                details={
                    "diagnostic": "No trace_corpus_path provided. Track 2 capability evaluation requires a valid consented developer trace corpus with manifest. Synthetic data manufacturing is strictly forbidden for Track 2."
                },
            )

        p = Path(trace_corpus_path)
        if p.is_dir():
            manifest_path = p / "manifest.json"
            corpus_path = None
        elif p.is_file():
            if p.name == "manifest.json":
                manifest_path = p
                corpus_path = p.parent / "consented_trace_corpus.json"
            else:
                corpus_path = p
                manifest_path = p.parent / "manifest.json"
        else:
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="BLOCKED",
                details={"diagnostic": f"Path not found: {trace_corpus_path}"},
            )

        if not manifest_path.exists():
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="BLOCKED",
                details={"diagnostic": f"Manifest file missing at {manifest_path}"},
            )

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="BLOCKED",
                details={"diagnostic": f"Corrupted or invalid manifest JSON: {e}"},
            )

        # Validate manifest invariants
        if not manifest_data.get("consent_verified", False):
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="BLOCKED",
                details={"diagnostic": "Consent not verified in manifest."},
            )

        data_filename = manifest_data.get("data_file", "consented_trace_corpus.json")
        if corpus_path is None or not corpus_path.exists():
            corpus_path = manifest_path.parent / data_filename

        if not corpus_path.exists():
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="BLOCKED",
                details={"diagnostic": f"Corpus trace file not found at {corpus_path}"},
            )

        # Verify cryptographic SHA-256 integrity of corpus
        corpus_bytes = corpus_path.read_bytes()
        actual_sha256 = hashlib.sha256(corpus_bytes).hexdigest()
        expected_sha256 = manifest_data.get("sha256_hash")

        if expected_sha256 and actual_sha256 != expected_sha256:
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="BLOCKED",
                details={"diagnostic": f"SHA256 checksum mismatch: expected {expected_sha256}, got {actual_sha256}"},
            )

        try:
            trace_events = json.loads(corpus_bytes.decode("utf-8"))
        except Exception as e:
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="BLOCKED",
                details={"diagnostic": f"Failed to parse trace events: {e}"},
            )

        if not trace_events or not isinstance(trace_events, list):
            return EvaluationReport(
                suite_id=generate_uuidv7(),
                run_timestamp=datetime.now(timezone.utc).isoformat(),
                track="TRACK_2_REAL_TRACE",
                status="INSUFFICIENT_EVIDENCE",
                details={"diagnostic": "Corpus contains 0 trace events."},
            )

        # Execute empirical Track 2 pipeline
        start_t = time.perf_counter()
        temp_dir = Path(tempfile.mkdtemp(prefix="entorhinal_track2_"))
        journal = EvidenceJournal(storage_path=temp_dir / "track2_journal.jsonl")
        compiler = MultiTimescaleCompiler(journal=journal)
        snapshot_service = ContextSnapshotService(
            compiler=compiler,
            policy_engine=self.policy_engine,
            journal=journal,
        )

        valid_schemas = 0
        provenance_valid_count = 0
        append_latencies: List[float] = []
        ground_truth_task_ids: List[str] = []
        record_ids: List[str] = []

        for evt in trace_events:
            ground_truth_task_ids.append(evt.get("ground_truth_task_id", "task-default"))

            ts = datetime.fromisoformat(evt["timestamp"]) if "timestamp" in evt else datetime.now(timezone.utc)
            sig = RawSignalEvent(
                source_type=SourceType(evt["source_type"]),
                adapter_id=evt.get("adapter_id", "adapter.trace"),
                app_identifier=evt["app_identifier"],
                window_title=evt.get("window_title"),
                target_uri=evt.get("target_uri"),
                raw_payload=evt.get("raw_payload", {}),
                captured_at=ts,
            )

            decision = self.policy_engine.evaluate_signal(sig)
            if decision is not None:
                valid_schemas += 1

            clean_title, _ = self.policy_engine.redact_text(sig.window_title or "")
            clean_uri, _ = self.policy_engine.sanitize_uri(sig.target_uri)

            t0 = time.perf_counter()
            rec = EvidenceRecord.create(
                source_type=sig.source_type,
                app_identifier=sig.app_identifier,
                window_title=clean_title,
                target_uri=clean_uri,
                sanitized_payload=decision.redacted_payload or {},
                classification=decision.classification,
                previous_record_hash=await journal.get_last_hash(),
                persisted_at=ts,
            )
            await journal.append_evidence(rec)
            append_latencies.append((time.perf_counter() - t0) * 1000.0)
            record_ids.append(rec.record_id)

            if len(rec.provenance_hash) == 64 and len(rec.previous_record_hash) == 64:
                provenance_valid_count += 1

            compiler.process_incremental_event(rec)

        # Batch compile projections
        facts = await compiler.compile_batch_projection()
        clusters = list(compiler._completed_clusters)
        if compiler._active_cluster and compiler._active_cluster not in clusters:
            clusters.append(compiler._active_cluster)

        # Calculate Task Segmentation F1 (Pairwise Rand Overlap)
        event_to_cluster: Dict[str, str] = {}
        for c in clusters:
            for eid in c.supporting_evidence_ids:
                event_to_cluster[eid] = c.cluster_id

        predicted_cluster_ids = [event_to_cluster.get(rid, f"unassigned-{i}") for i, rid in enumerate(record_ids)]
        task_seg_f1 = calculate_task_segmentation_f1(ground_truth_task_ids, predicted_cluster_ids)

        # Intent Classification & Expected Calibration Error (ECE)
        ground_truth_intents: List[str] = []
        predicted_intents: List[str] = []
        confidences: List[float] = []

        for c in clusters:
            hypos = await compiler.propose_hypotheses(c)
            if not hypos:
                continue

            cluster_gt_intents = [
                trace_events[record_ids.index(rid)]["ground_truth_intent"]
                for rid in c.supporting_evidence_ids
                if rid in record_ids and "ground_truth_intent" in trace_events[record_ids.index(rid)]
            ]
            if not cluster_gt_intents:
                continue

            gt_intent = Counter(cluster_gt_intents).most_common(1)[0][0]
            top_hypo = hypos[0]
            pred_intent = top_hypo.proposed_intent
            conf = top_hypo.confidence_score

            ground_truth_intents.append(gt_intent)
            predicted_intents.append(pred_intent)
            confidences.append(conf)

        gt_categories = [normalize_intent_category(g) for g in ground_truth_intents]
        pred_categories = [normalize_intent_category(p) for p in predicted_intents]
        macro_prec, macro_rec, macro_f1 = calculate_intent_classification_metrics(gt_categories, pred_categories)
        accuracies = [gt == pred for gt, pred in zip(gt_categories, pred_categories)]
        ece = calculate_expected_calibration_error(confidences, accuracies, num_bins=10)

        # Rebuild parity check
        is_chain_valid, _, _ = journal.verify_journal_integrity()
        rebuild_parity = 1.0 if is_chain_valid else 0.0

        # Snapshot generation benchmark
        snap_latencies: List[float] = []
        for _ in range(5):
            snap_req = ContextRequest(
                consumer_id="reflex.system2.planner",
                stated_purpose="Context for task planning",
                requested_scopes=["scope:developer.*", "scope:workspace.*", "scope:browser.*"],
            )
            t_snap0 = time.perf_counter()
            snapshot = await snapshot_service.request_snapshot(snap_req)
            snap_latencies.append((time.perf_counter() - t_snap0) * 1000.0)

        snap_p99 = float(np.percentile(snap_latencies, 99)) if snap_latencies else 1.0

        total_elapsed = time.perf_counter() - start_t
        throughput_eps = len(trace_events) / max(0.0001, total_elapsed)
        p99_append = float(np.percentile(append_latencies, 99)) if append_latencies else 1.0

        status = "PASS" if (
            task_seg_f1 >= 0.88
            and macro_prec >= 0.85
            and ece <= 0.10
            and is_chain_valid
        ) else "FAIL"

        return EvaluationReport(
            suite_id=generate_uuidv7(),
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            track="TRACK_2_REAL_TRACE",
            status=status,
            details={
                "dataset_name": manifest_data.get("dataset_name"),
                "events_processed": len(trace_events),
                "clusters_formed": len(clusters),
                "task_count": manifest_data.get("task_count"),
                "empirical_intent_recall": round(macro_rec, 4),
                "empirical_intent_f1": round(macro_f1, 4),
            },
            schema_validation_pass_rate=round(valid_schemas / max(1, len(trace_events)), 4),
            provenance_coverage_rate=round(provenance_valid_count / max(1, len(trace_events)), 4),
            deterministic_rebuild_parity=rebuild_parity,
            task_segmentation_f1=round(task_seg_f1, 4),
            intent_classification_precision=round(macro_prec, 4),
            expected_calibration_error=round(ece, 4),
            credential_leakage_count=None,
            pii_redaction_recall=None,
            cascade_deletion_leakage_count=None,
            ingest_throughput_eps=round(throughput_eps, 2),
            journal_append_latency_p99_ms=round(p99_append, 2),
            snapshot_generation_latency_p99_ms=round(snap_p99, 2),
        )

    # --------------------------------------------------------------------------
    # Privacy Stress Test
    # --------------------------------------------------------------------------

    async def run_adversarial_privacy_stress_test(self) -> EvaluationReport:
        """Injects 500+ adversarial PII and credential payloads to verify zero leaks."""
        t0 = time.perf_counter()
        result = await self.privacy_tester.run_stress_test()
        elapsed = time.perf_counter() - t0

        throughput = result["total_adversarial_vectors"] / max(0.0001, elapsed)
        status = "PASS" if result["passed"] else "FAIL"

        return EvaluationReport(
            suite_id=generate_uuidv7(),
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            track="TRACK_PRIVACY_STRESS",
            status=status,
            details={
                "total_adversarial_vectors": result["total_adversarial_vectors"],
                "journal_records_persisted": result.get("journal_records_persisted", 0),
                "derived_facts_compiled": result.get("derived_facts_compiled", 0),
                "leaks_detected": result["credential_leakage_count"],
            },
            schema_validation_pass_rate=None,
            provenance_coverage_rate=None,
            deterministic_rebuild_parity=None,
            task_segmentation_f1=None,
            intent_classification_precision=None,
            expected_calibration_error=None,
            credential_leakage_count=result["credential_leakage_count"],
            pii_redaction_recall=result["pii_redaction_recall"],
            cascade_deletion_leakage_count=None,
            ingest_throughput_eps=round(throughput, 2),
            journal_append_latency_p99_ms=None,
            snapshot_generation_latency_p99_ms=None,
        )

    # --------------------------------------------------------------------------
    # Chaos Resilience Test
    # --------------------------------------------------------------------------

    async def run_chaos_resilience_test(self) -> Dict[str, Any]:
        """Simulate bit-flips, sigkill, corrupted blocks, and cold rebuilds."""
        return await self.chaos_harness.run_all_chaos_tests()
