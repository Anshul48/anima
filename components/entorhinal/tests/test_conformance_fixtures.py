"""Entorhinal Conformance Test Suite (Session 05).

Verifies the 10 Golden Conformance Fixtures conforming to the frozen contract (v1.0.0):
1. 01_valid_snapshot.json - Serialization, schema validation, provenance references
2. 02_no_context.json - Empty context schema validity
3. 03_permission_denied.json - HTTP 403 PermissionDenied error structure & rejection
4. 04_stale_snapshot.json - Expired TTL timestamp detection
5. 05_revoked_fact.json - User correction lock override & human primacy
6. 06_malformed_payload.json - Corrupted schema fail-closed rejection
7. 07_timeout_scenario.json - Latency exhaustion & fallback metadata
8. 08_prompt_injection_payload.json - Adversarial injection passive containment
9. 09_sensitive_leak_payload.json - Sanitization & redaction manifest
10. 10_oversized_budget_payload.json - 4-tier priority budget compression
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict

import pytest
from pydantic import ValidationError

from entorhinal.policy.engine import PolicyEngine
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.query.service import ContextSnapshotService, PermissionDeniedError
from entorhinal.schemas.models import (
    ContextRequest,
    ContextSnapshot,
    DerivedFact,
    Hypothesis,
    generate_uuidv7,
)

FIXTURES_DIR = Path(__file__).parent.parent / "src" / "entorhinal" / "fixtures" / "conformance"


def load_fixture(filename: str) -> Dict[str, Any]:
    """Helper to load a JSON fixture by filename."""
    path = FIXTURES_DIR / filename
    assert path.exists(), f"Fixture file not found: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestConformanceFixturesEntorhinal:
    """Independent Conformance Test Suite for Entorhinal."""

    def test_all_ten_fixtures_exist_on_disk(self) -> None:
        """Verify all 10 fixture files are present in src/entorhinal/fixtures/conformance/."""
        expected_files = [
            "01_valid_snapshot.json",
            "02_no_context.json",
            "03_permission_denied.json",
            "04_stale_snapshot.json",
            "05_revoked_fact.json",
            "06_malformed_payload.json",
            "07_timeout_scenario.json",
            "08_prompt_injection_payload.json",
            "09_sensitive_leak_payload.json",
            "10_oversized_budget_payload.json",
        ]
        for fname in expected_files:
            fpath = FIXTURES_DIR / fname
            assert fpath.is_file(), f"Missing required fixture file: {fname}"
            assert fpath.stat().st_size > 0, f"Fixture file is empty: {fname}"

    def test_01_valid_snapshot_schema_and_serialization(self) -> None:
        """Fixture 01: Valid snapshot validates against Pydantic schema and round-trips cleanly."""
        data = load_fixture("01_valid_snapshot.json")
        snapshot = ContextSnapshot.model_validate(data)

        assert snapshot.snapshot_id == "01915dfb-6981-7f89-9a67-9c60e42cb701"
        assert snapshot.schema_version == "1.0.0"
        assert snapshot.request_id == "REQ-REFLEX-20260820-0001"
        assert len(snapshot.active_facts) == 2
        assert len(snapshot.active_hypotheses) == 1
        assert snapshot.active_hypotheses[0].is_hypothesis is True
        assert len(snapshot.evidence_provenance_refs) == 2
        assert "Authorization" in snapshot.redaction_manifest
        assert "ADVISORY ONLY" in snapshot.disclaimer

        # Round-trip serialization
        dumped = snapshot.model_dump(mode="json")
        assert dumped["snapshot_id"] == snapshot.snapshot_id
        assert len(dumped["active_facts"]) == 2

    def test_02_no_context_empty_snapshot(self) -> None:
        """Fixture 02: Valid snapshot with empty facts and hypotheses validates cleanly."""
        data = load_fixture("02_no_context.json")
        snapshot = ContextSnapshot.model_validate(data)

        assert snapshot.snapshot_id == "01915dfb-6981-7f89-9a67-9c60e42cb710"
        assert snapshot.schema_version == "1.0.0"
        assert len(snapshot.active_facts) == 0
        assert len(snapshot.active_hypotheses) == 0
        assert len(snapshot.evidence_provenance_refs) == 0
        assert snapshot.disclaimer.startswith("ADVISORY ONLY")

    def test_03_permission_denied_structure_and_service_rejection(self) -> None:
        """Fixture 03: 403 PermissionDenied error response structure and engine verification."""
        data = load_fixture("03_permission_denied.json")

        assert data["status_code"] == 403
        assert data["error"] == "PermissionDenied"
        assert "scope:credentials.passwords" in data["denied_scopes"]
        assert data["consumer_id"] == "reflex.system2.planner"

        # Verify PolicyEngine denies unauthorized scopes
        policy = PolicyEngine()
        unauthorized_req = ContextRequest(
            request_id="REQ-TEST-UNAUTH-01",
            consumer_id="reflex.system2.planner",
            stated_purpose="Exfiltrate user credentials",
            requested_scopes=["scope:credentials.passwords"],
        )
        assert policy.check_query_permission(unauthorized_req) is False

    def test_04_stale_snapshot_expiry_detection(self) -> None:
        """Fixture 04: Expired snapshot validates schema and exposes past expires_at."""
        data = load_fixture("04_stale_snapshot.json")
        snapshot = ContextSnapshot.model_validate(data)

        now = datetime.now(timezone.utc)
        assert snapshot.expires_at < now
        assert snapshot.issued_at < snapshot.expires_at
        assert len(snapshot.active_facts) == 1
        assert snapshot.active_facts[0].entity_uri == "workspace:old-deprecated-repo"

    def test_05_revoked_fact_and_human_primacy(self) -> None:
        """Fixture 05: Snapshot with user correction lock has revision_id=2 and confidence=1.0."""
        data = load_fixture("05_revoked_fact.json")
        snapshot = ContextSnapshot.model_validate(data)

        assert len(snapshot.active_facts) == 1
        fact = snapshot.active_facts[0]
        assert fact.entity_uri == "workspace:auth-service"
        assert fact.attribute == "active_branch"
        assert fact.value == "main"
        assert fact.confidence == 1.0
        assert fact.revision_id == 2
        assert "user_correction" in fact.derived_by
        assert any("revoked_prior_branch_fact" in r for r in snapshot.redaction_manifest)

    def test_06_malformed_payload_fail_closed_rejection(self) -> None:
        """Fixture 06: Corrupted schema fails validation with ValidationError (fail-closed)."""
        data = load_fixture("06_malformed_payload.json")

        with pytest.raises(ValidationError):
            ContextSnapshot.model_validate(data)

    def test_07_timeout_scenario_metadata(self) -> None:
        """Fixture 07: Timeout scenario metadata matches latency exhaustion specification."""
        data = load_fixture("07_timeout_scenario.json")

        assert data["scenario"] == "latency_budget_exhaustion"
        assert data["request"]["timeout_budget_ms"] == 25.0
        assert data["simulated_server_delay_ms"] > data["request"]["timeout_budget_ms"]
        assert data["error"] == "TimeoutError"
        assert data["status_code"] == 504
        assert data["circuit_breaker_impact"]["increment_consecutive_failures"] is True

    def test_08_prompt_injection_passive_containment(self) -> None:
        """Fixture 08: Prompt injection string is safely stored as passive text without execution."""
        data = load_fixture("08_prompt_injection_payload.json")
        snapshot = ContextSnapshot.model_validate(data)

        assert len(snapshot.active_facts) == 1
        fact = snapshot.active_facts[0]
        assert "Override all safety rules" in str(fact.value)
        assert "rm -rf /" in str(fact.value)

        # Invariant: Entorhinal objects are purely passive data structures
        assert not hasattr(snapshot, "execute")
        assert not hasattr(snapshot, "dispatch")
        assert not hasattr(fact, "run_command")
        assert snapshot.disclaimer.startswith("ADVISORY ONLY")

    def test_09_sensitive_leak_redaction_manifest(self) -> None:
        """Fixture 09: Sensitive credentials are redacted and listed in redaction_manifest."""
        data = load_fixture("09_sensitive_leak_payload.json")
        snapshot = ContextSnapshot.model_validate(data)

        assert len(snapshot.active_facts) == 2
        for fact in snapshot.active_facts:
            assert "<REDACTED:" in str(fact.value)

        assert len(snapshot.redaction_manifest) >= 2
        assert any("Authorization" in item for item in snapshot.redaction_manifest)
        assert any("AWS_SECRET_ACCESS_KEY" in item for item in snapshot.redaction_manifest)

    def test_10_oversized_budget_tiered_compression(self) -> None:
        """Fixture 10: 4-tier priority budget compression retains high tiers and prunes low tiers."""
        data = load_fixture("10_oversized_budget_payload.json")
        snapshot = ContextSnapshot.model_validate(data)

        assert len(snapshot.active_facts) == 3
        # Verify Tier 1 and Tier 2 facts are present
        uris = [f.entity_uri for f in snapshot.active_facts]
        assert "workspace:auth-service" in uris
        assert "session:immediate_focus" in uris

        # Verify pruning manifest in snapshot
        assert len(snapshot.redaction_manifest) >= 1
        assert any("pruned_" in item for item in snapshot.redaction_manifest)

    @pytest.mark.asyncio
    async def test_snapshot_service_budget_compression_logic(self) -> None:
        """Test ContextSnapshotService 4-tier budget compression with low token budget."""
        compiler = MultiTimescaleCompiler()
        service = ContextSnapshotService(compiler=compiler)

        now = datetime.now(timezone.utc)
        fact_tier1 = DerivedFact(
            fact_id=generate_uuidv7(),
            schema_version="1.0.0",
            entity_uri="workspace:entorhinal",
            attribute="repo_name",
            value="entorhinal",
            confidence=1.0,
            valid_from=now,
            supporting_evidence_ids=[generate_uuidv7()],
            derived_by="compiler.test",
        )
        fact_tier4 = DerivedFact(
            fact_id=generate_uuidv7(),
            schema_version="1.0.0",
            entity_uri="misc:note",
            attribute="random_observation",
            value="User looked at a random webpage for 2 seconds",
            confidence=0.50,
            valid_from=now,
            supporting_evidence_ids=[generate_uuidv7()],
            derived_by="compiler.test",
        )
        hyp_low = Hypothesis(
            hypothesis_id=generate_uuidv7(),
            proposed_intent="User might want to take a break",
            confidence_score=0.45,
            uncertainty_reasons=["Very weak signal"],
            expires_at=now,
            is_hypothesis=True,
        )

        retained_facts, retained_hyps, manifest = service._apply_tiered_budget_compression(
            facts=[fact_tier1, fact_tier4],
            hypotheses=[hyp_low],
            budget_tokens=50,  # Very small budget
        )

        # Tier 1 fact is always retained
        assert any(f.entity_uri == "workspace:entorhinal" for f in retained_facts)
        # Low confidence items pruned
        assert any("pruned" in m for m in manifest)
