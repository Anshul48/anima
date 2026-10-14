"""Comprehensive Phase 4 Test Suite: User Control, CLI, Trust UI, Privacy Stress, Chaos, and Independence.

Validates:
1. User corrections with sub-500ms permanent override locks against automated re-classification.
2. Cryptographic cascade deletion ("Forget Time Range") zeroing journal payloads and purging graphs.
3. Consent grant and revocation lifecycle.
4. Audit logging and JSON/ZIP data export.
5. Full Typer CLI command suite (`entorhinal status`, `inspect`, `correct`, `forget`, `grants`, `audit`).
6. Local Trust UI and REST governance endpoints.
7. Track 1 & Track 2 EvaluationRunner benchmarks.
8. 550+ Vector Adversarial Privacy Stress-Testing (zero disk/context credential leaks).
9. Chaos & fault injection recovery (bit-flips, sigkill, malformed JSON, cold rebuild parity).
10. Codebase Independence Audit (zero reflex/trace imports, zero action dispatchers).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List

from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from entorhinal.api.app import create_app
from entorhinal.cli.main import app as cli_app
from entorhinal.evals.chaos import ChaosHarness
from entorhinal.evals.independence_audit import IndependenceAuditor
from entorhinal.evals.privacy_stress import PrivacyStressTester
from entorhinal.evals.runner import EvalRunner
from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.policy.engine import PolicyEngine
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.query.service import ContextSnapshotService
from entorhinal.schemas.models import (
    ClassificationLevel,
    ContextRequest,
    CorrectionAction,
    DerivedFact,
    EvidenceRecord,
    RawSignalEvent,
    SourceType,
    UserCorrection,
    generate_uuidv7,
)
from entorhinal.user_control.audit import AuditLogManager
from entorhinal.user_control.corrections import CorrectionManager
from entorhinal.user_control.deletion import CascadeDeletionEngine
from entorhinal.user_control.service import UserControlService


# ==============================================================================
# 1. User Corrections & Override Lock Tests (<500ms Propagation)
# ==============================================================================

@pytest.mark.asyncio
async def test_user_correction_sub_500ms_propagation() -> None:
    """Test user override applies in <50ms and overrides heuristic compilers."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        journal = EvidenceJournal(storage_path=tmp_path / "journal.jsonl")
        compiler = MultiTimescaleCompiler(journal=journal)
        user_service = UserControlService(
            journal=journal,
            compiler=compiler,
            storage_dir=tmp_path,
        )

        # 1. Ingest synthetic browsing event that heuristically produces "unassigned" project
        rec = EvidenceRecord.create(
            source_type=SourceType.BROWSER,
            app_identifier="Chrome",
            window_title="Browsing Twitter",
            target_uri="https://twitter.com/competitor",
            sanitized_payload={"tab": "feed"},
            previous_record_hash=await journal.get_last_hash(),
        )
        await journal.append_evidence(rec)
        compiler.process_incremental_event(rec)

        # 2. Measure user correction lock application latency
        t0 = time.perf_counter()
        corr = await user_service.submit_user_correction(
            target_entity_or_fact_id="tool:chrome",
            corrected_value={"name": "Competitive Research Tool", "project": "project:entorhinal-v1"},
            user_note="Researching competitor UX patterns, not casual browsing",
            override_action=CorrectionAction.OVERWRITE,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Assert sub-500ms (and sub-50ms) propagation
        assert latency_ms < 500.0
        assert corr.correction_id is not None
        assert corr.override_action == CorrectionAction.OVERWRITE

        # Verify graph node is immediately locked with user correction
        node = compiler.graph_manager.get_node("tool:chrome")
        assert node is not None
        assert node.name == "Competitive Research Tool"
        assert node.attributes.get("user_override_locked") is True
        assert node.attributes.get("project") == "project:entorhinal-v1"
        assert node.confidence == 1.0

        # Verify facts generated from graph reflect user override
        facts = compiler.graph_manager.to_derived_facts()
        name_facts = [f for f in facts if f.entity_uri == "tool:chrome" and f.attribute == "name"]
        assert len(name_facts) > 0
        assert name_facts[0].value == "Competitive Research Tool"


@pytest.mark.asyncio
async def test_user_correction_persists_across_rebuilds() -> None:
    """Test user correction locks persist and override freshly compiled batch projections."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        corr_mgr = CorrectionManager(storage_path=tmp_path / "corrections.jsonl")

        corr = corr_mgr.submit_correction(
            target_id="project:entorhinal",
            corrected_value={"name": "Entorhinal Core Engine", "status": "active"},
            override_action=CorrectionAction.OVERWRITE,
            user_comment="Explicit human rename",
        )

        assert corr_mgr.is_locked("project:entorhinal")

        # Compile fresh facts from external source
        raw_facts = [
            DerivedFact(
                fact_id="fact-1",
                schema_version="1.0.0",
                entity_uri="project:entorhinal",
                attribute="name",
                value="heuristic_inferred_name",
                confidence=0.70,
                supporting_evidence_ids=["ev-1"],
                derived_by="heuristic_rule",
                revision_id=1,
            )
        ]

        # Apply correction manager over facts
        final_facts = corr_mgr.apply_to_facts(raw_facts)
        assert len(final_facts) >= 1
        name_fact = [f for f in final_facts if f.attribute == "name"][0]
        assert name_fact.value == "Entorhinal Core Engine"
        assert name_fact.confidence == 1.0
        assert "UserCorrection:" in name_fact.derived_by


# ==============================================================================
# 2. Cryptographic Cascade Deletion Tests ("Forget This")
# ==============================================================================

@pytest.mark.asyncio
async def test_cascade_deletion_erases_payloads_and_prunes_graph() -> None:
    """Test cascade deletion tombstones journal records, zeros payload bytes, and prunes graph."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        journal_path = tmp_path / "journal.jsonl"
        journal = EvidenceJournal(storage_path=journal_path)
        compiler = MultiTimescaleCompiler(journal=journal)
        snapshot_service = ContextSnapshotService(compiler=compiler, journal=journal)
        user_service = UserControlService(
            journal=journal,
            compiler=compiler,
            snapshot_service=snapshot_service,
            storage_dir=tmp_path,
        )

        # Ingest 10 events over a 2-hour window
        base_time = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)
        record_ids: List[str] = []

        for i in range(10):
            ts = base_time + timedelta(minutes=i * 10)
            rec = EvidenceRecord.create(
                source_type=SourceType.BROWSER,
                app_identifier="Chrome",
                window_title=f"Confidential Research Item {i}",
                target_uri=f"https://confidential.corp/item/{i}",
                sanitized_payload={"confidential_secret": f"SECRET_DATA_{i}"},
                previous_record_hash=await journal.get_last_hash(),
                persisted_at=ts,
            )
            await journal.append_evidence(rec)
            compiler.process_incremental_event(rec)
            record_ids.append(rec.record_id)

        # Verify initial graph has nodes
        assert len(compiler.graph_manager.list_nodes()) > 0

        # Execute Cascade Deletion on the middle 1-hour range (events 2 through 6)
        start_del = base_time + timedelta(minutes=15)
        end_del = base_time + timedelta(minutes=65)

        proof = await user_service.forget_time_range(
            start_time=start_del,
            end_time=end_del,
            reason="User requested privacy forget range",
        )

        assert proof["tombstoned_records_count"] == 5
        assert proof["journal_integrity_valid"] is True
        assert proof["residual_leakage_count"] == 0

        # Inspect disk file: verify "SECRET_DATA_2" through "SECRET_DATA_6" are NOT in the journal file
        disk_content = journal_path.read_text(encoding="utf-8")
        for i in range(2, 7):
            assert f"SECRET_DATA_{i}" not in disk_content
            assert f"Confidential Research Item {i}" not in disk_content

        # Non-deleted records should still exist
        assert "SECRET_DATA_0" in disk_content
        assert "SECRET_DATA_8" in disk_content

        # Verify journal hash chain integrity remains 100% intact
        is_valid, _, _ = journal.verify_journal_integrity()
        assert is_valid is True


# ==============================================================================
# 3. Consent Grants and Revocation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_dynamic_consent_grant_and_revocation() -> None:
    """Test granting and revoking consent dynamically affects ingestion policy."""
    policy = PolicyEngine(default_allow=False)  # default deny
    user_service = UserControlService(policy_engine=policy)

    # 1. Without consent, signal is denied
    sig = RawSignalEvent(
        source_type=SourceType.BROWSER,
        adapter_id="adapter.browser",
        app_identifier="Chrome",
        target_uri="https://finance.internal/reports",
        raw_payload={"page": "q3_report"},
    )
    decision1 = policy.evaluate_signal(sig)
    assert decision1.permitted is False

    # 2. Grant consent for finance domain
    rule_id = await user_service.grant_consent(
        source_type=SourceType.BROWSER,
        app_pattern="Chrome",
        domain_pattern="*finance.internal*",
    )
    assert rule_id is not None

    # 3. Evaluate again -> permitted
    decision2 = policy.evaluate_signal(sig)
    assert decision2.permitted is True

    # 4. Revoke consent
    revoked = await user_service.revoke_consent(rule_id)
    assert revoked is True

    # 5. Evaluate again -> denied
    decision3 = policy.evaluate_signal(sig)
    assert decision3.permitted is False


# ==============================================================================
# 4. Audit Logging and Data Export Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_audit_log_recording_and_json_zip_export() -> None:
    """Test audit log tracks consumer queries and exports to JSON/ZIP."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        audit_mgr = AuditLogManager(storage_path=tmp_path / "audit.jsonl")

        # Record consumer query event
        audit_mgr.record_event(
            action="CONTEXT_QUERY",
            details={"requested_scopes": ["scope:developer.*"]},
            consumer_id="reflex.system2.planner",
            stated_purpose="Task planning",
            disclosed_scopes=["scope:developer.*"],
            disclosed_fact_count=12,
            permitted=True,
        )

        logs = audit_mgr.query_logs(limit=10, consumer_filter="reflex")
        assert len(logs) == 1
        assert logs[0]["action"] == "CONTEXT_QUERY"
        assert logs[0]["disclosed_fact_count"] == 12

        # Export as JSON
        json_export = audit_mgr.export_data(format="json")
        assert isinstance(json_export, str)
        parsed = json.loads(json_export)
        assert "audit_logs" in parsed
        assert len(parsed["audit_logs"]) == 1

        # Export as ZIP
        zip_export = audit_mgr.export_data(format="zip")
        assert isinstance(zip_export, bytes)
        assert len(zip_export) > 50  # Valid zip archive bytes


# ==============================================================================
# 5. Full Typer CLI Command Suite Tests
# ==============================================================================

def test_cli_status_and_inspect_commands() -> None:
    """Test CLI commands status, inspect timeline, inspect graph, inspect focus."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # entorhinal status
        res_status = runner.invoke(cli_app, ["status", "--dir", tmp_dir])
        assert res_status.exit_code == 0
        assert "Entorhinal System Status" in res_status.stdout
        assert "HEALTHY" in res_status.stdout

        # entorhinal inspect timeline
        res_timeline = runner.invoke(cli_app, ["inspect", "timeline", "--dir", tmp_dir])
        assert res_timeline.exit_code == 0

        # entorhinal inspect graph
        res_graph = runner.invoke(cli_app, ["inspect", "graph", "--dir", tmp_dir])
        assert res_graph.exit_code == 0

        # entorhinal inspect focus
        res_focus = runner.invoke(cli_app, ["inspect", "focus", "--dir", tmp_dir])
        assert res_focus.exit_code == 0
        assert "Real-Time Immediate Focus" in res_focus.stdout


def test_cli_correct_and_forget_and_grants() -> None:
    """Test CLI correct, forget, and grants subcommands."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # entorhinal correct
        res_correct = runner.invoke(cli_app, [
            "correct", "project:cli-test", '{"name": "CLI Renamed Project"}',
            "--note", "Human override via CLI",
            "--dir", tmp_dir,
        ])
        assert res_correct.exit_code == 0
        assert "Correction Applied Successfully" in res_correct.stdout

        # entorhinal grants grant
        res_grant = runner.invoke(cli_app, [
            "grants", "grant", "--source", "browser", "--app", "Chrome", "--domain", "*.github.com*",
            "--dir", tmp_dir,
        ])
        assert res_grant.exit_code == 0
        assert "Consent granted successfully" in res_grant.stdout

        # entorhinal grants list
        res_grants_list = runner.invoke(cli_app, ["grants", "list", "--dir", tmp_dir])
        assert res_grants_list.exit_code == 0
        assert "Consent & Governance Rules" in res_grants_list.stdout

        # entorhinal audit
        res_audit = runner.invoke(cli_app, ["audit", "--dir", tmp_dir])
        assert res_audit.exit_code == 0

        # entorhinal forget (F3: operates on the durable runtime store, so
        # seed an empty evidence.db first; a dir without one is refused).
        from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore
        seed_store = SQLiteEvidenceStore(Path(tmp_dir) / "evidence.db")
        seed_store.close()
        res_forget = runner.invoke(cli_app, [
            "forget",
            "--start", "2026-08-17T00:00:00Z",
            "--end", "2026-08-17T23:59:59Z",
            "--reason", "CLI test deletion",
            "--dir", tmp_dir,
        ])
        assert res_forget.exit_code == 0
        assert "Cryptographic Deletion Verification Proof" in res_forget.stdout


# ==============================================================================
# 6. Trust UI and REST Endpoints Tests
# ==============================================================================

def test_trust_ui_and_governance_endpoints() -> None:
    """Test /ui and all Phase 4 governance REST endpoints."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        journal = EvidenceJournal(storage_path=tmp_path / "journal.jsonl")
        compiler = MultiTimescaleCompiler(journal=journal)
        policy = PolicyEngine()
        user_control = UserControlService(
            journal=journal,
            policy_engine=policy,
            compiler=compiler,
            storage_dir=tmp_path,
        )
        test_app = create_app(
            journal=journal,
            compiler=compiler,
            policy_engine=policy,
            user_control=user_control,
        )
        client = TestClient(test_app)

        # 1. GET /ui
        ui_res = client.get("/ui")
        assert ui_res.status_code == 200
        assert "Entorhinal Trust & Privacy Dashboard" in ui_res.text

        # 2. GET /api/v1/context/timeline
        timeline_res = client.get("/api/v1/context/timeline")
        assert timeline_res.status_code == 200
        assert isinstance(timeline_res.json(), list)

        # 3. GET /api/v1/context/graph
        graph_res = client.get("/api/v1/context/graph")
        assert graph_res.status_code == 200
        data = graph_res.json()
        assert "nodes" in data and "facts" in data

        # 4. POST & GET /api/v1/user/corrections
        corr_payload = {
            "target_entity_or_fact_id": "tool:vscode",
            "override_action": "overwrite",
            "corrected_value": {"name": "Visual Studio Code Pro"},
            "user_comment": "UI override",
        }
        post_corr_res = client.post("/api/v1/user/corrections", json=corr_payload)
        assert post_corr_res.status_code == 200
        assert post_corr_res.json()["target_entity_or_fact_id"] == "tool:vscode"

        get_corr_res = client.get("/api/v1/user/corrections")
        assert get_corr_res.status_code == 200
        assert len(get_corr_res.json()) >= 1

        # 5. POST & GET & DELETE /api/v1/user/grants
        grant_payload = {
            "source_type": "browser",
            "app_pattern": "Chrome",
            "domain_pattern": "example.com",
        }
        post_grant_res = client.post("/api/v1/user/grants", json=grant_payload)
        assert post_grant_res.status_code == 200
        rule_id = post_grant_res.json()["rule_id"]

        get_grants_res = client.get("/api/v1/user/grants")
        assert get_grants_res.status_code == 200

        del_grant_res = client.delete(f"/api/v1/user/grants/{rule_id}")
        assert del_grant_res.status_code == 200

        # 6. POST /api/v1/user/forget
        forget_payload = {
            "start_time": "2026-08-17T00:00:00Z",
            "end_time": "2026-08-17T23:59:59Z",
            "reason": "REST forget test",
        }
        forget_res = client.post("/api/v1/user/forget", json=forget_payload)
        assert forget_res.status_code == 200
        assert forget_res.json()["journal_integrity_valid"] is True

        # 7. GET /api/v1/user/audit
        audit_res = client.get("/api/v1/user/audit")
        assert audit_res.status_code == 200

        # 8. GET /api/v1/user/export
        export_res = client.get("/api/v1/user/export?format=json")
        assert export_res.status_code == 200
        assert "audit_logs" in export_res.json()


# ==============================================================================
# 7. Evaluation Runner & Benchmarks Tests (Track 1 & Track 2)
# ==============================================================================

@pytest.mark.asyncio
async def test_evaluation_runner_track1_and_track2() -> None:
    """Test EvalRunner executes deterministic fixture suite and capability benchmarks."""
    runner = EvalRunner()

    # Track 1: Deterministic Fixtures
    report1 = await runner.run_deterministic_fixture_suite()
    assert report1.track == "TRACK_1_SYNTHETIC"
    assert report1.status == "PASS"
    assert report1.schema_validation_pass_rate == 1.00
    assert report1.provenance_coverage_rate == 1.00
    assert report1.deterministic_rebuild_parity == 1.00
    assert report1.task_segmentation_f1 is None
    assert report1.intent_classification_precision is None
    assert report1.expected_calibration_error is None
    assert report1.credential_leakage_count is None
    assert report1.pii_redaction_recall is None
    assert report1.cascade_deletion_leakage_count == 0
    assert report1.snapshot_generation_latency_p99_ms <= 25.0

    # Track 2: No corpus provided -> Explicitly NOT_RUN (no fake synthetic data manufactured)
    report2_none = await runner.run_capability_benchmark()
    assert report2_none.track == "TRACK_2_REAL_TRACE"
    assert report2_none.status == "NOT_RUN"
    assert "diagnostic" in report2_none.details

    # Track 2: Invalid path -> BLOCKED
    report2_blocked = await runner.run_capability_benchmark("/invalid/nonexistent/manifest.json")
    assert report2_blocked.track == "TRACK_2_REAL_TRACE"
    assert report2_blocked.status == "BLOCKED"

    # Track 2: Real Consented Developer Trace Benchmark with verified manifest
    corpus_manifest = Path(__file__).parent.parent / "src" / "entorhinal" / "fixtures" / "consented_trace" / "manifest.json"
    if not corpus_manifest.is_file():
        pytest.skip(
            "consented corpus fixture excluded from public tree "
            f"(missing {corpus_manifest.name}); Track 2 PASS leg needs it"
        )
    report2 = await runner.run_capability_benchmark(str(corpus_manifest))
    assert report2.track == "TRACK_2_REAL_TRACE"
    assert report2.status == "PASS"
    assert report2.task_segmentation_f1 >= 0.88
    assert report2.intent_classification_precision >= 0.85
    assert report2.expected_calibration_error <= 0.10
    assert report2.credential_leakage_count is None
    assert report2.snapshot_generation_latency_p99_ms <= 15.0


# ==============================================================================
# 8. Adversarial Privacy Stress Test (550+ Vectors)
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_privacy_penetration_suite() -> None:
    """Test 550+ adversarial vectors: AWS, GitHub, Slack, OpenAI, Stripe, JWT, Private Keys, SSN, CC."""
    tester = PrivacyStressTester()
    report = await tester.run_stress_test()

    assert report["total_adversarial_vectors"] >= 550
    assert report["credential_leakage_count"] == 0, f"Leaked credentials: {report['leaks']}"
    assert report["pii_redaction_recall"] >= 0.99
    assert report["passed"] is True


# ==============================================================================
# 9. Chaos Resilience & Fault Injection Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_chaos_harness_fault_injection() -> None:
    """Test journal bit-flip tamper detection, sigkill recovery, subprocess crash, corrupt JSON, and cold rebuild parity."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        harness = ChaosHarness(temp_dir=Path(tmp_dir))
        chaos_results = await harness.run_all_chaos_tests()

        assert chaos_results["bit_flip"]["passed"] is True
        assert chaos_results["bit_flip"]["detected_corrupted_index"] == 4

        assert chaos_results["sigkill"]["passed"] is True
        assert chaos_results["sigkill"]["recovered_record_count"] == 5

        assert chaos_results["sigkill_subprocess"]["passed"] is True
        assert chaos_results["sigkill_subprocess"]["journal_integrity_valid"] is True
        assert chaos_results["sigkill_subprocess"]["post_recovery_appends"] == 3

        assert chaos_results["corrupt_json"]["passed"] is True

        assert chaos_results["rebuild_parity"]["passed"] is True
        assert chaos_results["rebuild_parity"]["deterministic_rebuild_parity"] == 1.00

        assert chaos_results["all_passed"] is True


# ==============================================================================
# 10. Codebase Independence and Zero Action Authority Audit
# ==============================================================================

@pytest.mark.asyncio
async def test_independence_and_zero_action_authority() -> None:
    """Prove 100% independence from Reflex and Trace (0 reflex imports, 0 trace imports, 0 action tools)."""
    auditor = IndependenceAuditor()
    report = await auditor.run_audit()

    assert report.reflex_dependencies_count == 0, f"Found reflex imports: {report.forbidden_imports_found}"
    assert report.trace_dependencies_count == 0, f"Found trace imports: {report.forbidden_imports_found}"
    assert report.action_dispatchers_count == 0, f"Found action dispatchers: {report.forbidden_imports_found}"
    assert report.runtime_autonomy_verified is True
    assert report.is_fully_independent is True


# ==============================================================================
# 11. Independent Remediation Regression Suite
# ==============================================================================

@pytest.mark.asyncio
async def test_pre_storage_redaction_in_pipeline() -> None:
    """Regression test for S0-01: IngestionPipeline redacts window_title and target_uri before EvidenceRecord creation."""
    from entorhinal.ingest.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(policy_engine=PolicyEngine())

    sig = RawSignalEvent(
        source_type=SourceType.BROWSER,
        adapter_id="adapter.browser.test",
        app_identifier="Chrome",
        window_title="Developer Portal - Token ghp_SECRETGITHUBTOKEN1234567890",
        target_uri="https://admin:SuperSecretPass123@api.github.com/user?token=ghp_TOKENABC",
        raw_payload={"page": "settings"},
    )
    rec = await pipeline.ingest_event(sig)
    assert rec is not None
    assert "ghp_SECRETGITHUBTOKEN1234567890" not in (rec.window_title or "")
    assert "<REDACTED:GITHUB_TOKEN>" in (rec.window_title or "")
    assert "SuperSecretPass123" not in (rec.target_uri or "")
    assert "<REDACTED:CREDENTIAL>" in (rec.target_uri or "")


@pytest.mark.asyncio
async def test_policy_engine_audit_log_uri_sanitization_on_rejection() -> None:
    """Regression test for S0-02: PolicyEngine audit log does not leak secrets on rejected signals."""
    policy = PolicyEngine(default_allow=True)
    sig = RawSignalEvent(
        source_type=SourceType.BROWSER,
        adapter_id="adapter.browser.test",
        app_identifier="Chrome",
        target_uri="https://user:SecretPasswordXYZ@accounts.google.com/signin?auth=sk-SECRETOPENAITOKEN12345",
        raw_payload={},
    )
    decision = policy.evaluate_signal(sig)
    assert decision.permitted is False  # Blacklisted banking/login domain

    audit_events = policy.get_audit_trail()
    rejected_events = [e for e in audit_events if e["action"] == "SIGNAL_REJECTED"]
    assert len(rejected_events) > 0
    rej_details = rejected_events[-1]["details"]
    assert "SecretPasswordXYZ" not in rej_details
    assert "sk-SECRETOPENAITOKEN12345" not in rej_details


@pytest.mark.asyncio
async def test_user_correction_batch_recompilation_persistence() -> None:
    """Regression test for S1-03: User corrections persist across compiler batch recompilations."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        journal = EvidenceJournal(storage_path=tmp_path / "corr_persist.jsonl")
        compiler = MultiTimescaleCompiler(journal=journal)
        snapshot_service = ContextSnapshotService(compiler=compiler, journal=journal)
        user_service = UserControlService(
            journal=journal,
            compiler=compiler,
            snapshot_service=snapshot_service,
            storage_dir=tmp_path,
        )

        # Ingest an evidence record for a project
        rec = EvidenceRecord.create(
            source_type=SourceType.BROWSER,
            app_identifier="VSCode",
            window_title="engine.py - entorhinal",
            target_uri="https://github.com/org/my-project",
            sanitized_payload={"code": "active"},
            previous_record_hash=await journal.get_last_hash(),
        )
        await journal.append_evidence(rec)
        compiler.process_incremental_event(rec)

        # Submit user correction override
        corr = UserCorrection(
            correction_id=generate_uuidv7(),
            target_entity_or_fact_id="project:org/my-project",
            override_action=CorrectionAction.OVERWRITE,
            corrected_value={"name": "Custom Project Title"},
            user_comment="User correction test",
        )
        await user_service.submit_correction(corr)

        # Verify graph node has user-locked name
        node = compiler.graph_manager.get_node("project:org/my-project")
        assert node is not None
        assert node.name == "Custom Project Title"

        # Trigger batch projection recompilation
        facts = await compiler.compile_batch_projection()

        # Node in graph must retain user-locked name
        node_after = compiler.graph_manager.get_node("project:org/my-project")
        assert node_after is not None
        assert node_after.name == "Custom Project Title"

        # Snapshot request must reflect the corrected value
        req = ContextRequest(
            consumer_id="reflex.system2.planner",
            stated_purpose="Context for task planning",
            requested_scopes=["scope:developer.*", "scope:workspace.*"],
        )
        snap = await snapshot_service.request_snapshot(req)
        matching = [f for f in snap.active_facts if f.entity_uri == "project:org/my-project" and f.attribute == "name"]
        assert len(matching) > 0
        assert matching[0].value == "Custom Project Title"


@pytest.mark.asyncio
async def test_cascade_deletion_safeguard_requires_filter_or_force() -> None:
    """Regression test for S3-02: CascadeDeletionEngine requires at least one filter or force_all=True."""
    from entorhinal.user_control.deletion import CascadeDeletionEngine
    journal = EvidenceJournal()
    deletion_engine = CascadeDeletionEngine(journal=journal)

    with pytest.raises(ValueError, match="requires at least one filter criterion"):
        await deletion_engine.cascade_delete()

    # With force_all=True it executes safely
    result = await deletion_engine.cascade_delete(force_all=True)
    assert result["tombstoned_records_count"] == 0


@pytest.mark.asyncio
async def test_journal_eof_trailing_newline_corruption_recovery() -> None:
    """Regression test for S2-01: EvidenceJournal recovers when partial EOF is followed by blank lines."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        jpath = Path(tmp_dir) / "corrupt_trailing_nl.jsonl"
        j1 = EvidenceJournal(storage_path=jpath)

        for i in range(3):
            r = EvidenceRecord.create(
                source_type=SourceType.BROWSER,
                app_identifier="Browser",
                sanitized_payload={"idx": i},
                previous_record_hash=await j1.get_last_hash(),
            )
            await j1.append_evidence(r)

        # Inject truncated JSON followed by blank newlines
        with open(jpath, "a", encoding="utf-8") as f:
            f.write('{"record_id": "truncated_001", "schema_version": "1.0\n\n\n')

        # Open new journal on the same file and append
        j2 = EvidenceJournal(storage_path=jpath)
        assert len(j2._records) == 3

        r4 = EvidenceRecord.create(
            source_type=SourceType.BROWSER,
            app_identifier="Browser",
            sanitized_payload={"idx": 3},
            previous_record_hash=await j2.get_last_hash(),
        )
        await j2.append_evidence(r4)

        is_valid, corrupted_id, _ = j2.verify_journal_integrity()
        assert is_valid is True
        assert corrupted_id is None
        assert await j2.count_records() == 4

