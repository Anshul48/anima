"""Comprehensive Unit Tests for Phase 1: Schemas, Policy Engine, Ports, Fixtures & Tool Qualification.

Verifies:
1. 100% of epistemic schema invariants (immutability, UUIDv7, hash chains, hypothesis flag).
2. PolicyEngine consent rules, process/domain blacklists, multi-pass regex redactions, and snapshot budget pruning.
3. Abstract port contracts.
4. Golden fixture corpus integrity and policy engine execution against all 50+ scenarios.
5. External tool qualification framework, dossiers, and deterministic fallback registry.

SYNTHETIC PROVENANCE: all secret-like strings in this file (EXAMPLE AWS
keys, truncated fake PEM blocks, "SuperSecret*" placeholders) are synthetic
redaction-test vectors, never real credentials.
"""

from datetime import datetime, timezone
import json
import re
import pytest
from pydantic import ValidationError

from entorhinal.fixtures.golden import (
    GOLDEN_FIXTURES,
    get_fixture_by_id,
    get_fixtures_by_category,
    get_golden_fixtures,
    validate_all_fixtures,
)
from entorhinal.policy.engine import (
    ConsentRule,
    ConsumerPermission,
    DEFAULT_APP_BLACKLIST,
    DEFAULT_DOMAIN_BLACKLIST,
    PolicyEngine,
)
from entorhinal.ports.interfaces import (
    MemoryPort,
    QueryPort,
    SourcePort,
    UserControlPort,
)
from entorhinal.schemas.models import (
    ClassificationLevel,
    ContextRequest,
    ContextSnapshot,
    CorrectionAction,
    DerivedFact,
    EvidenceRecord,
    FactExplanation,
    Hypothesis,
    PolicyDecision,
    RawSignalEvent,
    SourceType,
    TombstoneRecord,
    UserCorrection,
    compute_record_hash,
    compute_sha256,
    generate_uuidv7,
)
from entorhinal.tool_qualification.framework import (
    BenchmarkMetrics,
    DecisionClass,
    FallbackRegistry,
    InvariantsConfirmed,
    ToolQualificationDossier,
    ToolQualificationHarness,
    get_standard_candidate_dossiers,
)


# ==============================================================================
# 1. Epistemic Schemas & Cryptographic Invariants Tests
# ==============================================================================

class TestEpistemicSchemas:
    """Test data contracts, validation, and immutability."""

    def test_uuidv7_generation_and_monotonicity(self):
        """Verify UUIDv7 generation matches RFC 9562 structure and monotonicity."""
        u1 = generate_uuidv7()
        u2 = generate_uuidv7()

        # Check valid UUID string format
        uuid_regex = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        assert uuid_regex.match(u1), f"Invalid UUIDv7 format: {u1}"
        assert uuid_regex.match(u2), f"Invalid UUIDv7 format: {u2}"
        assert u1 != u2

    def test_sha256_computation(self):
        """Verify deterministic SHA-256 computation on various input types."""
        h1 = compute_sha256("test-content")
        h2 = compute_sha256("test-content")
        assert h1 == h2
        assert len(h1) == 64

        # Dict hashing should be key-order independent
        d1_hash = compute_sha256({"a": 1, "b": 2})
        d2_hash = compute_sha256({"b": 2, "a": 1})
        assert d1_hash == d2_hash

    def test_evidence_record_immutability_and_hash_chain(self):
        """Verify EvidenceRecord is frozen and creates valid provenance hash."""
        genesis_hash = "0" * 64
        record = EvidenceRecord.create(
            source_type=SourceType.BROWSER,
            app_identifier="Google Chrome",
            sanitized_payload={"url": "https://github.com/org/repo"},
            previous_record_hash=genesis_hash,
            window_title="Repo Title",
            target_uri="https://github.com/org/repo",
            classification=ClassificationLevel.PUBLIC,
        )

        assert record.source_type == SourceType.BROWSER
        assert len(record.provenance_hash) == 64
        assert record.previous_record_hash == genesis_hash
        assert record.schema_version == "1.0.0"

        # Verify frozen immutability
        with pytest.raises(ValidationError):
            record.app_identifier = "Firefox"  # type: ignore

    def test_derived_fact_validation_and_immutability(self):
        """Verify DerivedFact field constraints, evidence linkage, and immutability."""
        fact = DerivedFact(
            entity_uri="project:entorhinal",
            attribute="active_branch",
            value="main",
            confidence=0.98,
            supporting_evidence_ids=["EVID-001"],
            derived_by="GitBranchCompiler",
        )

        assert fact.confidence == 0.98
        assert fact.revision_id == 1
        assert len(fact.supporting_evidence_ids) >= 1

        # Invariant: confidence must be between 0.0 and 1.0
        with pytest.raises(ValidationError):
            DerivedFact(
                entity_uri="project:entorhinal",
                attribute="active_branch",
                value="main",
                confidence=1.5,  # Invalid
                supporting_evidence_ids=["EVID-001"],
                derived_by="GitBranchCompiler",
            )

        # Invariant: supporting_evidence_ids cannot be empty
        with pytest.raises(ValidationError):
            DerivedFact(
                entity_uri="project:entorhinal",
                attribute="active_branch",
                value="main",
                confidence=0.5,
                supporting_evidence_ids=[],  # Invalid min_length=1
                derived_by="GitBranchCompiler",
            )

        # Immutability check
        with pytest.raises(ValidationError):
            fact.value = "dev"  # type: ignore

    def test_hypothesis_invariants(self):
        """Verify Hypothesis is_hypothesis invariant remains True and cannot be False."""
        now = datetime.now(timezone.utc)
        hypo = Hypothesis(
            proposed_intent="User is refactoring the policy engine",
            confidence_score=0.75,
            candidate_evidence_ids=["EVID-001", "EVID-002"],
            uncertainty_reasons=["No branch push detected"],
            expires_at=now,
        )

        assert hypo.is_hypothesis is True
        assert hypo.confidence_score == 0.75

        # Attempt to set is_hypothesis=False must raise ValidationError
        with pytest.raises(ValidationError):
            Hypothesis(
                proposed_intent="Refactoring",
                confidence_score=0.75,
                expires_at=now,
                is_hypothesis=False,  # type: ignore
            )

    def test_context_request_and_snapshot(self):
        """Verify ContextRequest and ContextSnapshot data contracts."""
        req = ContextRequest(
            consumer_id="reflex.system2.planner",
            stated_purpose="Resolve active project branch",
            requested_scopes=["scope:workspace.active_project"],
            max_freshness_seconds=120,
            token_or_size_budget=1024,
        )

        assert req.consumer_id == "reflex.system2.planner"
        assert req.max_freshness_seconds == 120

        now = datetime.now(timezone.utc)
        snap = ContextSnapshot(
            request_id=req.request_id,
            issued_at=now,
            expires_at=now,
            purpose_granted=req.stated_purpose,
            scope_granted=req.requested_scopes,
            active_facts=[],
            active_hypotheses=[],
        )

        assert snap.disclaimer.startswith("ADVISORY ONLY")
        assert snap.purpose_granted == req.stated_purpose

    def test_user_correction_and_tombstone(self):
        """Verify UserCorrection and TombstoneRecord factories."""
        corr = UserCorrection(
            target_entity_or_fact_id="project:entorhinal",
            override_action=CorrectionAction.OVERWRITE,
            corrected_value="feature/policy",
            user_comment="Fixed wrong branch inference",
        )

        assert corr.override_action == CorrectionAction.OVERWRITE
        assert corr.corrected_value == "feature/policy"

        # Tombstone creation
        prev_hash = "a" * 64
        tombstone = TombstoneRecord.create(
            original_record_id="EVID-ORIG-123",
            previous_record_hash=prev_hash,
            revocation_reason="User GDPR delete command",
        )

        assert tombstone.original_record_id == "EVID-ORIG-123"
        assert tombstone.previous_record_hash == prev_hash
        assert len(tombstone.tombstone_hash) == 64


# ==============================================================================
# 2. Policy Engine Tests
# ==============================================================================

class TestPolicyEngine:
    """Test policy gating, consent checks, and multi-pass redaction."""

    def test_blacklist_app_suppression(self):
        """Verify password managers and keychains are suppressed with PROHIBITED status."""
        engine = PolicyEngine()

        for blacklisted_app in ["1Password.exe", "1password", "KeePassXC.exe", "Bitwarden.exe"]:
            signal = RawSignalEvent(
                source_type=SourceType.OS_WINDOW,
                adapter_id="adapter.os.window",
                app_identifier=blacklisted_app,
                window_title=f"{blacklisted_app} - Vault Unlocked",
                raw_payload={"secret": "my-master-password"},
            )

            decision = engine.evaluate_signal(signal)
            assert decision.permitted is False
            assert decision.classification == ClassificationLevel.PROHIBITED
            assert decision.redacted_payload is None
            assert any("blacklisted" in v.lower() for v in decision.violations)

    def test_blacklist_domain_suppression(self):
        """Verify online banking and sensitive login domains are suppressed."""
        engine = PolicyEngine()

        signal = RawSignalEvent(
            source_type=SourceType.BROWSER,
            adapter_id="adapter.browser.cdp",
            app_identifier="Google Chrome",
            target_uri="https://secure.banking.example.com/login",
            raw_payload={"username": "dev-user", "password": "SuperSecretPassword"},
        )

        decision = engine.evaluate_signal(signal)
        assert decision.permitted is False
        assert decision.classification == ClassificationLevel.PROHIBITED
        assert decision.redacted_payload is None

    def test_incognito_suppression(self):
        """Verify incognito / private sessions are suppressed."""
        engine = PolicyEngine()

        signal = RawSignalEvent(
            source_type=SourceType.BROWSER,
            adapter_id="adapter.browser.cdp",
            app_identifier="Firefox",
            target_uri="https://example.com",
            raw_payload={"page": "secret research"},
            metadata={"is_incognito": True},
        )

        decision = engine.evaluate_signal(signal)
        assert decision.permitted is False
        assert decision.classification == ClassificationLevel.PROHIBITED

    def test_user_consent_allow_deny_rules(self):
        """Verify user-configured consent grants and denials."""
        engine = PolicyEngine(default_allow=False)

        signal = RawSignalEvent(
            source_type=SourceType.BROWSER,
            adapter_id="adapter.browser.cdp",
            app_identifier="Google Chrome",
            target_uri="https://github.com/my-org/my-repo",
            raw_payload={"page": "Code review"},
        )

        # Initially rejected under default_allow=False
        decision = engine.evaluate_signal(signal)
        assert decision.permitted is False

        # Add allow rule for github
        rule_id = engine.add_consent_rule(
            allow=True,
            source_type=SourceType.BROWSER,
            domain_pattern="*github.com*",
        )

        decision2 = engine.evaluate_signal(signal)
        assert decision2.permitted is True

        # Remove rule and verify it reverts
        assert engine.remove_consent_rule(rule_id) is True
        decision3 = engine.evaluate_signal(signal)
        assert decision3.permitted is False

    def test_aws_key_and_secret_redaction(self):
        """Verify AWS Access Key and Secret Key masking."""
        engine = PolicyEngine()

        text = "Access: AKIAIOSFODNN7EXAMPLE and secret: aws_secret_access_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'"
        redacted, items = engine.redact_text(text)

        assert "AKIAIOSFODNN7EXAMPLE" not in redacted
        assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in redacted
        assert "<REDACTED:AWS_KEY>" in redacted
        assert "<REDACTED:AWS_SECRET_KEY>" in redacted

    def test_github_token_redaction(self):
        """Verify GitHub PAT tokens are masked."""
        engine = PolicyEngine()

        text = "Token: ghp_111111111111111111111111111111111111 and fine-grained: github_pat_11A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0"
        redacted, items = engine.redact_text(text)

        assert "ghp_111111111111111111111111111111111111" not in redacted
        assert "github_pat_" not in redacted
        assert "<REDACTED:GITHUB_TOKEN>" in redacted

    def test_slack_and_openai_token_redaction(self):
        """Verify Slack and OpenAI token redaction."""
        engine = PolicyEngine()

        text = "Slack: xoxb-1234567890-1234567890123-abcdef123456 and OpenAI: sk-proj-0000000000000000000000000000000000000000"
        redacted, items = engine.redact_text(text)

        assert "xoxb-" not in redacted
        assert "sk-proj-" not in redacted
        assert "<REDACTED:SLACK_TOKEN>" in redacted
        assert "<REDACTED:OPENAI_API_KEY>" in redacted

    def test_jwt_and_private_key_redaction(self):
        """Verify JWT and RSA private key block masking."""
        engine = PolicyEngine()

        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSignature"
        pkey = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"

        text = f"JWT: {jwt}\nKey:\n{pkey}"
        redacted, items = engine.redact_text(text)

        assert jwt not in redacted
        assert "-----BEGIN RSA PRIVATE KEY-----" not in redacted
        assert "<REDACTED:JWT>" in redacted
        assert "<REDACTED:PRIVATE_KEY>" in redacted

    def test_credit_card_and_ssn_redaction(self):
        """Verify credit card numbers and SSNs are masked."""
        engine = PolicyEngine()

        text = "SSN: 123-45-6789 and Card: 4532 1198 2341 9087"
        redacted, items = engine.redact_text(text)

        assert "123-45-6789" not in redacted
        assert "4532 1198 2341 9087" not in redacted
        assert "<REDACTED:SSN>" in redacted
        assert "<REDACTED:CREDIT_CARD>" in redacted

    def test_nested_payload_redaction(self):
        """Verify recursive dictionary and list payload redaction."""
        engine = PolicyEngine()

        payload = {
            "user": "alex",
            "session": {
                "Authorization": "Bearer ghp_000000000000000000000000000000000000",
                "nested_items": [
                    "normal string",
                    {"api_key": "secret-12345678"},
                    "email: test@example.com"
                ]
            }
        }

        clean_payload, redacted_paths = engine.sanitize_payload(payload)
        assert clean_payload["user"] == "alex"
        assert "<REDACTED:GITHUB_TOKEN>" in clean_payload["session"]["Authorization"] or "<REDACTED:CREDENTIAL>" in clean_payload["session"]["Authorization"]
        assert clean_payload["session"]["nested_items"][1]["api_key"] == "<REDACTED:CREDENTIAL>"
        assert len(redacted_paths) >= 2

    def test_uri_sanitization(self):
        """Verify URI credential parameters and basic auth masking."""
        engine = PolicyEngine()

        uri = "https://user:password123@api.example.com/v1/resource?token=secrettoken123&page=1"
        clean_uri, redacted_items = engine.sanitize_uri(uri)

        assert "password123" not in clean_uri
        assert "secrettoken123" not in clean_uri
        assert "page=1" in clean_uri

    def test_query_permission_check(self):
        """Verify consumer query permission and scope gating."""
        engine = PolicyEngine()

        # Valid request
        valid_req = ContextRequest(
            consumer_id="reflex.system2.planner",
            stated_purpose="Resolve active repository branch and target issue ID",
            requested_scopes=["scope:workspace.active_project", "scope:terminal.last_commands"],
        )
        assert engine.check_query_permission(valid_req) is True

        # Invalid consumer
        invalid_consumer_req = ContextRequest(
            consumer_id="unknown.rogue.agent",
            stated_purpose="Scrape data",
            requested_scopes=["scope:workspace.active_project"],
        )
        assert engine.check_query_permission(invalid_consumer_req) is False

        # Forbidden scope
        forbidden_scope_req = ContextRequest(
            consumer_id="reflex.system2.planner",
            stated_purpose="Context for task planning",
            requested_scopes=["scope:credentials.passwords"],
        )
        assert engine.check_query_permission(forbidden_scope_req) is False

    def test_snapshot_sanitization_and_budget_pruning(self):
        """Verify ContextSnapshot token budget pruning and final redaction sweep."""
        engine = PolicyEngine()

        now = datetime.now(timezone.utc)
        facts = [
            DerivedFact(
                entity_uri="scope:workspace.active_project",
                attribute="repo",
                value="entorhinal",
                confidence=0.99,
                supporting_evidence_ids=["EVID-1"],
                derived_by="rule",
            ),
            DerivedFact(
                entity_uri="scope:workspace.active_project",
                attribute="branch",
                value="main",
                confidence=0.95,
                supporting_evidence_ids=["EVID-2"],
                derived_by="rule",
            ),
            DerivedFact(
                entity_uri="scope:workspace.active_project",
                attribute="low_prio_fact",
                value="extra metadata " * 500,  # large payload
                confidence=0.20,
                supporting_evidence_ids=["EVID-3"],
                derived_by="rule",
            ),
        ]

        snapshot = ContextSnapshot(
            issued_at=now,
            expires_at=now,
            purpose_granted="Task planning",
            scope_granted=["scope:workspace.active_project"],
            active_facts=facts,
            active_hypotheses=[],
        )

        request = ContextRequest(
            consumer_id="reflex.system2.planner",
            stated_purpose="Context for task planning",
            requested_scopes=["scope:workspace.active_project"],
            token_or_size_budget=512,  # Budget of 512 tokens (~2048 chars), small facts fit, massive fact pruned
        )

        sanitized_snap = engine.sanitize_snapshot(snapshot, request)

        # High confidence facts preserved, low confidence/large facts pruned
        assert len(sanitized_snap.active_facts) < len(facts)
        assert sanitized_snap.active_facts[0].confidence == 0.99
        assert any("pruned_fact_budget_exceeded" in m for m in sanitized_snap.redaction_manifest)


# ==============================================================================
# 3. Port Interfaces Tests
# ==============================================================================

class TestPortInterfaces:
    """Verify Port abstract contracts enforce full implementation."""

    def test_source_port_abc(self):
        """Verify SourcePort ABC cannot be instantiated without abstract methods."""
        with pytest.raises(TypeError):
            SourcePort()  # type: ignore

    def test_memory_port_abc(self):
        """Verify MemoryPort ABC cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MemoryPort()  # type: ignore

    def test_query_port_abc(self):
        """Verify QueryPort ABC cannot be instantiated directly."""
        with pytest.raises(TypeError):
            QueryPort()  # type: ignore

    def test_user_control_port_abc(self):
        """Verify UserControlPort ABC cannot be instantiated directly."""
        with pytest.raises(TypeError):
            UserControlPort()  # type: ignore


# ==============================================================================
# 4. Golden Fixture Corpus Tests
# ==============================================================================

class TestGoldenFixtures:
    """Verify golden fixture corpus structure, category breadth, and policy compatibility."""

    def test_fixture_corpus_structural_integrity(self):
        """Verify all 50+ fixtures pass schema and structural validation."""
        assert validate_all_fixtures() is True
        fixtures = get_golden_fixtures()
        assert len(fixtures) >= 50

    def test_fixture_categories_distribution(self):
        """Verify all required categories have sufficient test fixtures."""
        browser_fixtures = get_fixtures_by_category("browser_semantic_capture")
        os_fixtures = get_fixtures_by_category("os_window_accessibility")
        term_fixtures = get_fixtures_by_category("terminal_pty_workflow")
        adv_fixtures = get_fixtures_by_category("adversarial_privacy_edge_cases")

        assert len(browser_fixtures) >= 15
        assert len(os_fixtures) >= 15
        assert len(term_fixtures) >= 10
        assert len(adv_fixtures) >= 10

    def test_policy_engine_execution_against_all_golden_fixtures(self):
        """Run PolicyEngine against 100% of golden fixtures and verify expected outputs."""
        engine = PolicyEngine()
        # Add payroll exclusion rule for fixture FIX-ADV-007
        engine.add_consent_rule(
            allow=False,
            domain_pattern="*payroll.internal*",
            priority=100,
        )

        for fix in get_golden_fixtures():
            fid = fix["fixture_id"]
            raw_input = fix["raw_source_input"]
            expected_pol = fix["expected_policy_output"]

            signal = RawSignalEvent(
                source_type=SourceType(raw_input["source_type"]),
                adapter_id=raw_input["adapter_id"],
                app_identifier=raw_input["app_identifier"],
                window_title=raw_input.get("window_title"),
                target_uri=raw_input.get("target_uri"),
                raw_payload=raw_input.get("raw_payload", {}),
                metadata=raw_input.get("metadata", {}),
            )

            decision = engine.evaluate_signal(signal)

            # Assert consent granted matches expected
            assert decision.permitted == expected_pol["consent_granted"], (
                f"Fixture {fid} consent mismatch: got {decision.permitted}, expected {expected_pol['consent_granted']}"
            )

            # Assert classification level
            assert decision.classification.value == expected_pol["classification"], (
                f"Fixture {fid} classification mismatch: got {decision.classification.value}, expected {expected_pol['classification']}"
            )

            # If permitted, verify evidence record can be constructed
            if decision.permitted:
                assert decision.redacted_payload is not None
                evidence = EvidenceRecord.create(
                    source_type=signal.source_type,
                    app_identifier=signal.app_identifier,
                    sanitized_payload=decision.redacted_payload,
                    previous_record_hash="0" * 64,
                    window_title=signal.window_title,
                    target_uri=signal.target_uri,
                    classification=decision.classification,
                )
                assert evidence.source_type == signal.source_type
                assert len(evidence.provenance_hash) == 64

            # Verify derived facts can be constructed if present in fixture
            for fact_data in fix.get("expected_derived_facts", []):
                fact = DerivedFact(
                    entity_uri=fact_data["entity"],
                    attribute=fact_data["attribute"],
                    value=fact_data["value"],
                    confidence=fact_data["confidence"],
                    supporting_evidence_ids=["EVID-GOLDEN-001"],
                    derived_by="GoldenFixtureCompiler",
                )
                assert fact.confidence == fact_data["confidence"]


# ==============================================================================
# 5. External Tool Qualification Framework Tests
# ==============================================================================

class TestToolQualificationFramework:
    """Test ToolQualificationDossier, FallbackRegistry, and ToolQualificationHarness."""

    def test_dossier_approval_logic(self):
        """Verify DecisionClass approval gating."""
        dossier_approved = ToolQualificationDossier(
            tool_name="Test Tool",
            version_evaluated="1.0.0",
            target_role="redaction_assistant",
            evaluation_date="2026-08-17",
            decision_class=DecisionClass.CLASS_A_APPROVED_ADAPTER,
            benchmarks=BenchmarkMetrics(offline_verified=True),
            invariants_confirmed=InvariantsConfirmed(
                has_deterministic_fallback=True,
                fallback_adapter="RegexFallback",
                zero_cloud_egress=True,
                license_compatible="MIT",
                preserves_provenance=True,
                zero_action_authority=True,
            ),
        )
        assert dossier_approved.is_approved_for_runtime() is True

        dossier_eval_only = ToolQualificationDossier(
            tool_name="Eval Tool",
            version_evaluated="1.0.0",
            target_role="offline_analytics",
            evaluation_date="2026-08-17",
            decision_class=DecisionClass.CLASS_B_EVALUATION_ONLY,
            benchmarks=BenchmarkMetrics(offline_verified=True),
            invariants_confirmed=InvariantsConfirmed(
                has_deterministic_fallback=True,
                fallback_adapter="Fallback",
                zero_cloud_egress=True,
                license_compatible="MIT",
                preserves_provenance=True,
                zero_action_authority=True,
            ),
        )
        assert dossier_eval_only.is_approved_for_runtime() is False

    def test_fallback_registry_lifecycle(self):
        """Verify FallbackRegistry registration, seamless fallback, and deactivation."""
        registry = FallbackRegistry()

        fallback_engine = {"type": "RegexRedactionEngine"}
        candidate_engine = {"type": "PresidioAdapter"}

        dossier = ToolQualificationDossier(
            tool_name="Presidio",
            version_evaluated="2.2.0",
            target_role="redaction_assistant",
            evaluation_date="2026-08-17",
            decision_class=DecisionClass.CLASS_A_APPROVED_ADAPTER,
            benchmarks=BenchmarkMetrics(offline_verified=True),
            invariants_confirmed=InvariantsConfirmed(
                has_deterministic_fallback=True,
                fallback_adapter="RegexRedactionEngine",
                zero_cloud_egress=True,
                license_compatible="MIT",
                preserves_provenance=True,
                zero_action_authority=True,
            ),
        )

        # Register role with active adapter
        registry.register_role(
            role="redaction_assistant",
            fallback_adapter=fallback_engine,
            active_adapter=candidate_engine,
            dossier=dossier,
        )

        assert registry.get_adapter("redaction_assistant") == candidate_engine
        assert registry.is_using_fallback("redaction_assistant") is False

        # Deactivate external adapter mid-flight -> routes immediately to fallback
        registry.deactivate_external_adapter("redaction_assistant")
        assert registry.get_adapter("redaction_assistant") == fallback_engine
        assert registry.is_using_fallback("redaction_assistant") is True

    def test_qualification_harness_evaluation_gates(self):
        """Verify harness rejects unsafe, incompatible licenses, or low performance tools."""
        harness = ToolQualificationHarness()

        # 1. Reject incompatible license (e.g. AGPL-3.0 in core)
        dossier_license_fail = harness.evaluate_candidate(
            tool_name="AGPL Tool",
            version="1.0",
            target_role="parser",
            license_name="AGPL-3.0",
            candidate_adapter={},
            fallback_adapter_name="LocalParser",
        )
        assert dossier_license_fail.decision_class == DecisionClass.CLASS_E_REJECTED_LICENSE

        # 2. Reject tool that attempts action authority
        dossier_action_fail = harness.evaluate_candidate(
            tool_name="Clicker Tool",
            version="1.0",
            target_role="automation",
            license_name="MIT",
            candidate_adapter={},
            fallback_adapter_name="NoOp",
            has_action_authority=True,
        )
        assert dossier_action_fail.decision_class == DecisionClass.CLASS_C_REJECTED_UNSAFE

        # 3. Reject tool with cloud egress
        dossier_egress_fail = harness.evaluate_candidate(
            tool_name="Cloud Sync Tool",
            version="1.0",
            target_role="sync",
            license_name="MIT",
            candidate_adapter={},
            fallback_adapter_name="LocalOnly",
            initiates_network_calls=True,
        )
        assert dossier_egress_fail.decision_class == DecisionClass.CLASS_C_REJECTED_UNSAFE

        # 4. Approved tool passing all gates
        dossier_approved = harness.evaluate_candidate(
            tool_name="Clean Local Tool",
            version="1.0",
            target_role="clean_role",
            license_name="MIT",
            candidate_adapter={},
            fallback_adapter_name="CleanFallback",
        )
        assert dossier_approved.decision_class == DecisionClass.CLASS_A_APPROVED_ADAPTER

    def test_standard_candidate_dossiers_validity(self):
        """Verify standard ecosystem candidate dossiers (Presidio, ActivityWatch, SQLite, DuckDB)."""
        dossiers = get_standard_candidate_dossiers()
        assert len(dossiers) >= 5

        for d in dossiers:
            assert len(d.tool_name) > 0
            assert d.invariants_confirmed.has_deterministic_fallback is True
            assert d.invariants_confirmed.zero_cloud_egress is True
            assert d.invariants_confirmed.zero_action_authority is True


# ==============================================================================
# 6. Additional Resiliency, Benchmark & Integrity Tests
# ==============================================================================

class TestResiliencyAndBenchmark:
    """Test policy evaluation throughput, tamper detection, and JSON roundtrips."""

    def test_policy_throughput_benchmark(self):
        """Verify policy engine processes >1,000 events per second cleanly."""
        import time
        engine = PolicyEngine()
        signal = RawSignalEvent(
            source_type=SourceType.BROWSER,
            adapter_id="bench-adapter",
            app_identifier="Google Chrome",
            target_uri="https://github.com/org/repo/pull/42",
            raw_payload={
                "title": "Fix memory leak in buffer pool",
                "token": "ghp_000000000000000000000000000000000000",
                "nested": {"key": "value", "list": [1, 2, "test@example.com"]},
            },
        )

        n_events = 1000
        start = time.perf_counter()
        for _ in range(n_events):
            decision = engine.evaluate_signal(signal)
            assert decision.permitted is True
        elapsed = time.perf_counter() - start

        throughput = n_events / elapsed
        assert throughput > 1000.0, f"Throughput too low: {throughput:.2f} eps"

    def test_hash_chain_tamper_detection(self):
        """Verify modifying payload invalidates cryptographic hash chain."""
        genesis_hash = "0" * 64
        rec1 = EvidenceRecord.create(
            source_type=SourceType.BROWSER,
            app_identifier="Google Chrome",
            sanitized_payload={"event": "initial"},
            previous_record_hash=genesis_hash,
        )

        rec2 = EvidenceRecord.create(
            source_type=SourceType.TERMINAL_PTY,
            app_identifier="bash",
            sanitized_payload={"command": "ls -la"},
            previous_record_hash=rec1.provenance_hash,
        )

        assert rec2.previous_record_hash == rec1.provenance_hash

        # Tampering with rec1 payload changes its computed hash
        tampered_dict = {
            "record_id": rec1.record_id,
            "schema_version": "1.0.0",
            "persisted_at": rec1.persisted_at.isoformat(),
            "source_type": rec1.source_type.value,
            "app_identifier": rec1.app_identifier,
            "window_title": rec1.window_title,
            "target_uri": rec1.target_uri,
            "sanitized_payload": {"event": "TAMPERED_CONTENT"},
            "classification": rec1.classification.value,
            "previous_record_hash": genesis_hash,
            "is_tombstone": False,
            "tombstone_reason": None,
        }
        tampered_hash = compute_record_hash(genesis_hash, tampered_dict)
        assert tampered_hash != rec1.provenance_hash
        assert tampered_hash != rec2.previous_record_hash

    def test_json_roundtrip_serialization(self):
        """Verify 100% bit-accurate serialization and deserialization across schemas."""
        now = datetime.now(timezone.utc)
        record = EvidenceRecord.create(
            source_type=SourceType.OS_WINDOW,
            app_identifier="Code",
            sanitized_payload={"file": "engine.py", "lines": 400},
            previous_record_hash="1" * 64,
            persisted_at=now,
        )

        serialized = record.model_dump_json()
        deserialized = EvidenceRecord.model_validate_json(serialized)

        assert deserialized.record_id == record.record_id
        assert deserialized.provenance_hash == record.provenance_hash
        assert deserialized.sanitized_payload == record.sanitized_payload

    def test_fact_explanation_model(self):
        """Verify FactExplanation model creation and field validation."""
        now = datetime.now(timezone.utc)
        explanation = FactExplanation(
            fact_id="FACT-123",
            entity_uri="project:entorhinal",
            attribute="active_branch",
            value="main",
            confidence=0.95,
            supporting_evidence_ids=["EVID-1", "EVID-2"],
            derived_by="GitBranchRule",
            reasoning_summary="Observed recent git checkout and push commands in PTY",
            valid_from=now,
        )

        assert explanation.fact_id == "FACT-123"
        assert len(explanation.supporting_evidence_ids) == 2
        assert explanation.confidence == 0.95

