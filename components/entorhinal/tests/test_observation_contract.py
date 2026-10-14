"""Tests for Reflex-Entorhinal Observation Ingestion Contract (vNext-2026.1).

Validates the 3 conformance test vectors from OBSERVATION_CONTRACT.md:
1. Scenario 1: Clean Developer Workflow Observation.
2. Scenario 2: Sensitive Credential Exposure (Secret Redaction Pre-Storage).
3. Scenario 3: Prohibited Domain (Fail-Closed Rejection).
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import time
from typing import Any, Dict

import pytest
from starlette.testclient import TestClient

from entorhinal.api.app import create_app
from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.policy.engine import PolicyEngine
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.query.service import ContextSnapshotService
from entorhinal.schemas.observation import (
    ActiveElementInfo,
    ObservationBoundingBox,
    ObservationEpistemicUncertainty,
    ObservationPerceptionPayload,
    PerceptionObservationEvent,
)
from entorhinal.user_control.service import UserControlService


@pytest.fixture
def test_environment():
    """Set up isolated temporary Entorhinal environment."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_path = Path(tmp_dir)
        journal = EvidenceJournal(storage_path=storage_path / "journal.jsonl")
        policy = PolicyEngine(default_allow=True)
        compiler = MultiTimescaleCompiler(journal=journal)
        service = ContextSnapshotService(compiler=compiler, policy_engine=policy, journal=journal)
        user_control = UserControlService(
            journal=journal,
            policy_engine=policy,
            compiler=compiler,
            snapshot_service=service,
            storage_dir=storage_path,
        )

        app = create_app(
            service=service,
            compiler=compiler,
            policy_engine=policy,
            journal=journal,
            user_control=user_control,
        )
        client = TestClient(app)

        yield {
            "client": client,
            "journal": journal,
            "compiler": compiler,
            "policy": policy,
            "user_control": user_control,
        }


def test_conformance_scenario_1_clean_developer_observation(test_environment):
    """Scenario 1: Clean Developer Workflow Observation succeeds and compiles into state."""
    client = test_environment["client"]
    journal = test_environment["journal"]
    compiler = test_environment["compiler"]

    payload = {
        "contract_version": "vNext-2026.1",
        "observation_id": "01a0f000-0000-7000-8000-000000000001",
        "observed_at_ms": 1786960800000.0,
        "source_system": "reflex.linux.native",
        "source_subsystem": "at_spi_accessibility",
        "consent_scope": "scope:developer.ide",
        "epistemic_uncertainty": {
            "grounding_confidence": 0.98,
            "is_inferred": False,
            "freshness_ttl_ms": 300000.0,
        },
        "perception_payload": {
            "app_identifier": "code",
            "window_title": "engine.py - entorhinal - Visual Studio Code",
            "target_uri": "file:///workspace/entorhinal/src/entorhinal/policy/engine.py",
            "active_element": {
                "role": "editor",
                "label": "engine.py text editor",
                "bounds": {"x1": 200.0, "y1": 50.0, "x2": 1920.0, "y2": 1080.0},
            },
            "custom_attributes": {
                "git_branch": "main",
                "cursor_line": 142,
            },
        },
        "provenance_signature": "hmac-sha256-verified",
    }

    # Warm-up request for test client initialization
    client.get("/api/v1/health")

    t0 = time.perf_counter()
    res = client.post("/api/v1/ingest", json=payload)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert res.status_code == 200
    assert elapsed_ms < 30.0  # Fast-path SLA

    data = res.json()
    assert data["status"] == "ingested"
    assert data["observation_id"] == "01a0f000-0000-7000-8000-000000000001"
    assert data["evidence_id"] is not None
    assert data["admitted"] is True

    # Verify journal persisted
    assert len(journal._records) == 1
    rec = journal._records[0]
    assert rec.app_identifier == "code"
    assert "engine.py" in rec.window_title

    # Verify compiler state
    facts = compiler.get_active_facts()
    assert len(facts) > 0


def test_conformance_scenario_2_secret_redaction_pre_storage(test_environment):
    """Scenario 2: Sensitive Credential Exposure is scrubbed pre-storage."""
    client = test_environment["client"]
    journal = test_environment["journal"]

    secret_pat = "ghp_SUPERSECRETPAT1234567890ABCDEF"
    payload = {
        "contract_version": "vNext-2026.1",
        "observation_id": "01a0f000-0000-7000-8000-000000000002",
        "observed_at_ms": 1786960802000.0,
        "source_system": "reflex.browser.cdp",
        "source_subsystem": "cdp_dom",
        "consent_scope": "scope:browser.web",
        "epistemic_uncertainty": {
            "grounding_confidence": 1.0,
            "is_inferred": False,
            "freshness_ttl_ms": 60000.0,
        },
        "perception_payload": {
            "app_identifier": "chrome",
            "window_title": f"GitHub Settings - Token {secret_pat}",
            "target_uri": f"https://api.github.com/user?token={secret_pat}",
            "active_element": None,
            "custom_attributes": {
                "authorization": f"Bearer {secret_pat}",
            },
        },
        "provenance_signature": None,
    }

    res = client.post("/api/v1/ingest", json=payload)
    assert res.status_code == 200

    # Inspect persisted journal record on disk / in memory
    assert len(journal._records) == 1
    rec = journal._records[0]

    # Verify secret is NEVER persisted anywhere in the record
    assert secret_pat not in rec.window_title
    assert secret_pat not in (rec.target_uri or "")
    assert secret_pat not in str(rec.sanitized_payload)
    assert "<REDACTED:GITHUB_TOKEN>" in rec.window_title
    assert "REDACTED" in (rec.target_uri or "")


def test_conformance_scenario_3_prohibited_domain_fail_closed(test_environment):
    """Scenario 3: Prohibited Domain Observation is rejected fail-closed with 0 bytes persisted."""
    client = test_environment["client"]
    journal = test_environment["journal"]
    user_control = test_environment["user_control"]

    payload = {
        "contract_version": "vNext-2026.1",
        "observation_id": "01a0f000-0000-7000-8000-000000000003",
        "observed_at_ms": 1786960804000.0,
        "source_system": "reflex.browser.cdp",
        "source_subsystem": "cdp_dom",
        "consent_scope": "scope:browser.web",
        "epistemic_uncertainty": {
            "grounding_confidence": 1.0,
            "is_inferred": False,
            "freshness_ttl_ms": 60000.0,
        },
        "perception_payload": {
            "app_identifier": "chrome",
            "window_title": "Chase Online - Accounts Summary",
            "target_uri": "https://secure05b.chase.com/web/auth/dashboard",
            "active_element": None,
            "custom_attributes": {},
        },
        "provenance_signature": None,
    }

    res = client.post("/api/v1/ingest", json=payload)

    # Must return 403 Forbidden
    assert res.status_code == 403
    assert "prohibited by policy" in res.json()["detail"].lower()

    # Zero records written to journal
    assert len(journal._records) == 0

    # Audit manager records denial
    events = user_control.audit_manager.query_logs()
    denials = [e for e in events if e["action"] == "OBSERVATION_INGEST_DENIED"]
    assert len(denials) == 1
    assert denials[0]["consumer_id"] == "reflex.browser.cdp"
    assert denials[0]["permitted"] is False
