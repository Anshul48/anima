"""Unit tests verifying Pydantic V2 immutable data contracts and PEP 544 protocols for STC."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from stc.protocols.interfaces import (
    ContextCompilerProtocol,
    GenomeStoreProtocol,
    HormoneBusProtocol,
    JudiciaryAuditorProtocol,
    SocraticDecomposerProtocol,
    SpecIngestorProtocol,
    SubstrateRunnerProtocol,
    TraceMemoryProtocol,
    WorkerProtocol,
    WorktreeManagerProtocol,
)
from stc.schemas.hormones import (
    HormoneEvent,
    HormoneScope,
    HormoneSignalType,
)
from stc.schemas.models import (
    ArchetypeDiff,
    ArchetypeOption,
    AuditFinding,
    ConcernDimension,
    ExecutionReceipt,
    FileTarget,
    GateReport,
    GeneType,
    GenomeAtom,
    HealthStatus,
    JudiciaryVerdict,
    SpecAtom,
    SystemMetrics,
    TaskBundle,
    TaskPriority,
    TaskReceipt,
    TaskSpec,
    TaskStatus,
    TreeOfConcerns,
    WorktreeLease,
)


def test_spec_atom_valid_and_immutable() -> None:
    """Verify that SpecAtom validates correctly and enforces frozen immutability."""
    atom = SpecAtom(
        spec_id="SPEC-001",
        source_path="specs/feature_a.md",
        raw_content="# Feature A Specification\nMust execute reliably.",
        content_sha256="a" * 64,
    )
    assert atom.spec_id == "SPEC-001"
    assert len(atom.content_sha256) == 64

    # Enforce frozen immutability
    with pytest.raises(ValidationError):
        atom.spec_id = "MUTATED"


def test_spec_atom_invalid_checksum() -> None:
    """Verify that SpecAtom rejects non-64 character checksums."""
    with pytest.raises(ValidationError):
        SpecAtom(
            spec_id="SPEC-001",
            source_path="specs/feature_a.md",
            raw_content="Content is here",
            content_sha256="too_short",
        )

    with pytest.raises(ValidationError):
        SpecAtom(
            spec_id="SPEC-001",
            source_path="specs/feature_a.md",
            raw_content="Content is here",
            content_sha256="a" * 65,
        )


def test_spec_atom_raw_content_length_and_extra_forbid() -> None:
    """Verify SpecAtom raw_content min_length and forbidden extra fields."""
    with pytest.raises(ValidationError):
        SpecAtom(
            spec_id="SPEC-001",
            source_path="specs/feature_a.md",
            raw_content="Short",  # < 10 characters
            content_sha256="a" * 64,
        )

    with pytest.raises(ValidationError):
        SpecAtom.model_validate(
            {
                "spec_id": "SPEC-001",
                "source_path": "specs/feature_a.md",
                "raw_content": "# Feature A Specification\nMust execute reliably.",
                "content_sha256": "a" * 64,
                "unexpected_field": "disallowed",
            }
        )


def test_tree_of_concerns_structure() -> None:
    """Verify 5-dimensional Tree of Concerns serialization and bounds."""
    dim = ConcernDimension(
        dimension_name="domain_invariants",
        invariants=["No negative balance"],
        contracts=["Protocol AccountBalance"],
        failure_modes=["Timeout"],
        acceptance_tests=["test_balance.py"],
    )
    toc = TreeOfConcerns(
        spec_id="SPEC-001",
        domain_invariants=dim,
        persistence_storage=dim,
        communication_protocols=dim,
        boundary_security=dim,
        failure_resilience=dim,
        ambiguity_score=0.25,
    )
    assert toc.ambiguity_score == 0.25
    assert toc.domain_invariants.dimension_name == "domain_invariants"

    # Ambiguity score must be between 0.0 and 1.0
    with pytest.raises(ValidationError):
        TreeOfConcerns(
            spec_id="SPEC-001",
            domain_invariants=dim,
            persistence_storage=dim,
            communication_protocols=dim,
            boundary_security=dim,
            failure_resilience=dim,
            ambiguity_score=1.5,
        )

    with pytest.raises(ValidationError):
        TreeOfConcerns(
            spec_id="SPEC-001",
            domain_invariants=dim,
            persistence_storage=dim,
            communication_protocols=dim,
            boundary_security=dim,
            failure_resilience=dim,
            ambiguity_score=-0.1,
        )


def test_tree_of_concerns_immutability_and_extra_forbid() -> None:
    """Verify TreeOfConcerns frozen immutability and extra field forbidding."""
    dim = ConcernDimension(dimension_name="dim")
    toc = TreeOfConcerns(
        spec_id="SPEC-001",
        domain_invariants=dim,
        persistence_storage=dim,
        communication_protocols=dim,
        boundary_security=dim,
        failure_resilience=dim,
        ambiguity_score=0.2,
    )

    with pytest.raises(ValidationError):
        toc.ambiguity_score = 0.5

    with pytest.raises(ValidationError):
        dim_data = dim.model_dump()
        TreeOfConcerns.model_validate(
            {
                "spec_id": "SPEC-001",
                "domain_invariants": dim_data,
                "persistence_storage": dim_data,
                "communication_protocols": dim_data,
                "boundary_security": dim_data,
                "failure_resilience": dim_data,
                "ambiguity_score": 0.2,
                "extra_field": "disallowed",
            }
        )


def test_concern_dimension_immutability_and_extra_forbid() -> None:
    """Verify ConcernDimension immutability and extra field forbidding."""
    dim = ConcernDimension(dimension_name="domain_invariants")
    assert dim.dimension_name == "domain_invariants"

    with pytest.raises(ValidationError):
        dim.dimension_name = "mutated"

    with pytest.raises(ValidationError):
        ConcernDimension.model_validate({"dimension_name": "test", "unallowed_key": 123})


def test_archetype_option_pattern_validation() -> None:
    """Verify ArchetypeOption regex pattern on option_id."""
    opt_valid = ArchetypeOption(
        option_id="option_a",
        title="Conservative Fail-Closed",
        tradeoff_pro="High security",
        tradeoff_con="Higher latency",
        invariants_to_lock=["Strict verification required"],
    )
    assert opt_valid.option_id == "option_a"

    with pytest.raises(ValidationError):
        ArchetypeOption(
            option_id="INVALID_ID",
            title="Invalid",
            tradeoff_pro="Pro",
            tradeoff_con="Con",
            invariants_to_lock=[],
        )


def test_archetype_option_immutability_and_extra_forbid() -> None:
    """Verify ArchetypeOption title min length, immutability, and extra forbid."""
    opt = ArchetypeOption(
        option_id="option_b",
        title="Valid Title",
        tradeoff_pro="Pro",
        tradeoff_con="Con",
        invariants_to_lock=[],
    )

    with pytest.raises(ValidationError):
        opt.title = "Mutated"

    with pytest.raises(ValidationError):
        ArchetypeOption(
            option_id="option_b",
            title="Tiny",  # < 5 chars
            tradeoff_pro="Pro",
            tradeoff_con="Con",
            invariants_to_lock=[],
        )

    with pytest.raises(ValidationError):
        ArchetypeOption.model_validate(
            {
                "option_id": "option_b",
                "title": "Valid Title",
                "tradeoff_pro": "Pro",
                "tradeoff_con": "Con",
                "invariants_to_lock": [],
                "extra_param": "forbidden",
            }
        )


def test_archetype_diff_valid_and_immutable() -> None:
    """Verify ArchetypeDiff instantiation, immutability, and extra field rejection."""
    opt_a = ArchetypeOption(
        option_id="option_a",
        title="Option Alpha",
        tradeoff_pro="Pro A",
        tradeoff_con="Con A",
        invariants_to_lock=["Inv A"],
    )
    opt_b = ArchetypeOption(
        option_id="option_b",
        title="Option Beta",
        tradeoff_pro="Pro B",
        tradeoff_con="Con B",
        invariants_to_lock=["Inv B"],
    )
    diff = ArchetypeDiff(
        diff_id="DIFF-001",
        concern_dimension="persistence_storage",
        core_dilemma="Synchronous vs Asynchronous WAL commit",
        option_a=opt_a,
        option_b=opt_b,
        selected_option="option_a",
    )
    assert diff.diff_id == "DIFF-001"
    assert diff.selected_option == "option_a"

    with pytest.raises(ValidationError):
        diff.selected_option = "option_b"

    with pytest.raises(ValidationError):
        ArchetypeDiff.model_validate(
            {
                "diff_id": "DIFF-001",
                "concern_dimension": "persistence_storage",
                "core_dilemma": "Dilemma",
                "option_a": opt_a.model_dump(),
                "option_b": opt_b.model_dump(),
                "extra_arg": "invalid",
            }
        )


def test_task_bundle_validation() -> None:
    """Verify TaskBundle validation rules."""
    bundle = TaskBundle(
        task_id="TASK-001",
        epoch_index=1,
        spec_id="SPEC-001",
        goal_statement="Implement Reciprocal Rank Fusion",
        invariants=["Zero division damping"],
        target_files=[FileTarget(path="src/fusion.py", action="create")],
        membrane_protocols=["FusionEngine"],
        negative_inhibitors=["Do not use raw linear sum"],
    )
    assert bundle.epoch_index == 1
    assert len(bundle.target_files) == 1

    # Empty goal statement must be rejected
    with pytest.raises(ValidationError):
        TaskBundle(
            task_id="TASK-001",
            epoch_index=1,
            spec_id="SPEC-001",
            goal_statement="   ",
            invariants=[],
            target_files=[],
            membrane_protocols=[],
            negative_inhibitors=[],
        )


def test_task_bundle_epoch_bounds_and_immutability() -> None:
    """Verify TaskBundle epoch bounds (1 to 3), immutability, and extra forbid."""
    bundle = TaskBundle(
        task_id="TASK-001",
        epoch_index=2,
        spec_id="SPEC-001",
        goal_statement="Goal",
        invariants=[],
        target_files=[],
        membrane_protocols=[],
        negative_inhibitors=[],
    )

    with pytest.raises(ValidationError):
        bundle.epoch_index = 3

    # epoch_index must be between 1 and 3
    with pytest.raises(ValidationError):
        TaskBundle(
            task_id="TASK-001",
            epoch_index=0,
            spec_id="SPEC-001",
            goal_statement="Goal",
            invariants=[],
            target_files=[],
            membrane_protocols=[],
            negative_inhibitors=[],
        )

    with pytest.raises(ValidationError):
        TaskBundle(
            task_id="TASK-001",
            epoch_index=4,
            spec_id="SPEC-001",
            goal_statement="Goal",
            invariants=[],
            target_files=[],
            membrane_protocols=[],
            negative_inhibitors=[],
        )

    # Extra forbid
    with pytest.raises(ValidationError):
        TaskBundle.model_validate(
            {
                "task_id": "TASK-001",
                "epoch_index": 1,
                "spec_id": "SPEC-001",
                "goal_statement": "Goal",
                "invariants": [],
                "target_files": [],
                "membrane_protocols": [],
                "negative_inhibitors": [],
                "unknown": "disallowed",
            }
        )


def test_execution_receipt_passing_logic() -> None:
    """Verify ExecutionReceipt.is_passing returns True only when all gates exit 0."""
    g_pass = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.5,
        violations_count=0,
        raw_output_snippet="OK",
    )
    g_fail = GateReport(
        gate_name="gate",
        exit_code=1,
        duration_seconds=0.5,
        violations_count=2,
        raw_output_snippet="Error",
    )

    rcpt_passing = ExecutionReceipt(
        receipt_id="RCPT-001",
        task_id="TASK-001",
        epoch_index=1,
        commit_hash="a8f9c42b",
        timestamp_utc="2026-09-03T10:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        sha256_signature="0" * 64,
    )
    assert rcpt_passing.is_passing is True

    rcpt_failing = ExecutionReceipt(
        receipt_id="RCPT-002",
        task_id="TASK-001",
        epoch_index=1,
        commit_hash="a8f9c42b",
        timestamp_utc="2026-09-03T10:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        gate_ruff=g_pass,
        gate_mypy=g_fail,  # Gate 2 fails
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        sha256_signature="0" * 64,
    )
    assert rcpt_failing.is_passing is False


def test_file_target_offsets_and_validation() -> None:
    """Verify FileTarget line and byte offset bounds and monotonic invariants."""
    target = FileTarget(
        path="src/stc/core/config.py",
        action="modify",
        expected_symbols=["get_settings"],
        start_line=10,
        end_line=25,
        start_byte=200,
        end_byte=550,
    )
    assert target.start_line == 10
    assert target.end_line == 25
    assert target.start_byte == 200
    assert target.end_byte == 550

    # Test end_line < start_line error
    with pytest.raises(ValidationError, match=r"end_line .* cannot be less than start_line"):
        FileTarget(
            path="src/test.py",
            start_line=50,
            end_line=20,
        )

    # Test end_byte < start_byte error
    with pytest.raises(ValidationError, match=r"end_byte .* cannot be less than start_byte"):
        FileTarget(
            path="src/test.py",
            start_byte=1000,
            end_byte=500,
        )

    # Equal bounds are allowed (e.g. single line, empty byte slice)
    boundary_target = FileTarget(
        path="src/test.py",
        start_line=1,
        end_line=1,
        start_byte=0,
        end_byte=0,
    )
    assert boundary_target.start_line == boundary_target.end_line == 1
    assert boundary_target.start_byte == boundary_target.end_byte == 0

    # Test start_line < 1 (ge=1 violation)
    with pytest.raises(ValidationError):
        FileTarget(path="src/test.py", start_line=0)

    # Test start_byte < 0 (ge=0 violation)
    with pytest.raises(ValidationError):
        FileTarget(path="src/test.py", start_byte=-1)


def test_file_target_actions_and_immutability() -> None:
    """Verify FileTarget permitted actions, immutability, and extra forbid."""
    for action in ("create", "modify", "delete"):
        ft = FileTarget(path="src/test.py", action=action)
        assert ft.action == action

    with pytest.raises(ValidationError):
        FileTarget(path="src/test.py", action="remove")  # disallowed action

    ft_valid = FileTarget(path="src/test.py", action="create")
    with pytest.raises(ValidationError):
        ft_valid.action = "modify"

    with pytest.raises(ValidationError):
        FileTarget.model_validate({"path": "src/test.py", "extra": "disallowed"})


def test_task_bundle_restored_causation_and_correlation() -> None:
    """Verify TaskBundle correlation_id and causation_id propagation."""
    bundle = TaskBundle(
        task_id="TASK-CORR-001",
        epoch_index=2,
        spec_id="SPEC-AUTH",
        goal_statement="Implement authentication gateway",
        invariants=["Stateless JWT only"],
        target_files=[],
        membrane_protocols=["AuthGatewayProtocol"],
        negative_inhibitors=[],
        correlation_id="corr_custom_trace_99",
        causation_id="cause_event_parent_42",
    )
    assert bundle.correlation_id == "corr_custom_trace_99"
    assert bundle.causation_id == "cause_event_parent_42"


def test_execution_receipt_restored_correlation_fields() -> None:
    """Verify ExecutionReceipt correlation_id and causation_id."""
    g_pass = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = ExecutionReceipt(
        receipt_id="RCPT-RESTORED-001",
        task_id="TASK-CORR-001",
        epoch_index=2,
        commit_hash="c0ffee1234",
        timestamp_utc="2026-09-03T12:00:00Z",
        python_version="3.12.4",
        os_platform="Linux",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        sha256_signature="1" * 64,
        correlation_id="corr_custom_trace_99",
        causation_id="cause_event_parent_42",
    )
    assert receipt.correlation_id == "corr_custom_trace_99"
    assert receipt.causation_id == "cause_event_parent_42"

    with pytest.raises(ValidationError):
        receipt.task_id = "TASK-MUTATED"

    with pytest.raises(ValidationError):
        g_pass_data = g_pass.model_dump()
        ExecutionReceipt.model_validate(
            {
                "receipt_id": "RCPT-RESTORED-001",
                "task_id": "TASK-CORR-001",
                "epoch_index": 2,
                "commit_hash": "c0ffee1234",
                "timestamp_utc": "2026-09-03T12:00:00Z",
                "python_version": "3.12.4",
                "os_platform": "Linux",
                "gate_ruff": g_pass_data,
                "gate_mypy": g_pass_data,
                "gate_pytest": g_pass_data,
                "gate_mutmut": g_pass_data,
                "sha256_signature": "1" * 64,
                "extra_field": "forbidden",
            }
        )


def test_worktree_lease_valid_and_immutable() -> None:
    """Verify WorktreeLease validation, frozen immutability, and extra forbid."""
    now = datetime.now(UTC)
    lease = WorktreeLease(
        lease_id="lease_12345",
        task_id="TASK-WT-001",
        branch_name="stc/TASK-WT-001",
        worktree_path="worktrees/stc-TASK-WT-001",
        leased_at=now,
        expires_at=now + timedelta(hours=1),
        is_active=True,
    )
    assert lease.lease_id == "lease_12345"
    assert lease.is_active is True

    with pytest.raises(ValidationError):
        lease.is_active = False

    with pytest.raises(ValidationError):
        WorktreeLease.model_validate(
            {
                "lease_id": "lease_12345",
                "task_id": "TASK-WT-001",
                "branch_name": "stc/TASK-WT-001",
                "worktree_path": "worktrees/stc-TASK-WT-001",
                "expires_at": (now + timedelta(hours=1)).isoformat(),
                "disallowed": "field",
            }
        )


def test_gate_report_valid_and_immutable() -> None:
    """Verify GateReport frozen immutability and extra forbid."""
    gr = GateReport(
        gate_name="ruff",
        exit_code=0,
        duration_seconds=1.2,
        violations_count=0,
        raw_output_snippet="All checks passed!",
    )
    assert gr.gate_name == "ruff"

    with pytest.raises(ValidationError):
        gr.exit_code = 1

    with pytest.raises(ValidationError):
        GateReport.model_validate(
            {
                "gate_name": "ruff",
                "exit_code": 0,
                "duration_seconds": 1.2,
                "violations_count": 0,
                "raw_output_snippet": "All checks passed!",
                "extra_forbidden": True,
            }
        )


def test_audit_finding_severity_and_immutability() -> None:
    """Verify AuditFinding regex pattern on severity, immutability, and extra forbid."""
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        af = AuditFinding(
            rule_name="NO_MOCKS",
            severity=sev,
            filepath="src/test.py",
            line_number=42,
            snippet="forbidden_syntax_construct()",
            rationale="Mock detected.",
        )
        assert af.severity == sev

    with pytest.raises(ValidationError):
        AuditFinding(
            rule_name="NO_MOCKS",
            severity="INVALID_SEVERITY",
            filepath="src/test.py",
            snippet="mock",
            rationale="Mock detected.",
        )

    finding = AuditFinding(
        rule_name="NO_MOCKS",
        severity="HIGH",
        filepath="src/test.py",
        snippet="mock",
        rationale="Mock detected.",
    )
    with pytest.raises(ValidationError):
        finding.severity = "LOW"

    with pytest.raises(ValidationError):
        AuditFinding.model_validate(
            {
                "rule_name": "NO_MOCKS",
                "severity": "HIGH",
                "filepath": "src/test.py",
                "snippet": "mock",
                "rationale": "Mock detected.",
                "unknown": 123,
            }
        )


def test_judiciary_verdict_status_and_immutability() -> None:
    """Verify JudiciaryVerdict status regex, immutability, and extra forbid."""
    for status in ("APPROVED", "QUARANTINED", "REJECTED"):
        jv = JudiciaryVerdict(
            task_id="TASK-001",
            status=status,
            findings=[],
            summary_rationale=f"Verdict is {status}",
        )
        assert jv.status == status

    with pytest.raises(ValidationError):
        JudiciaryVerdict(
            task_id="TASK-001",
            status="UNKNOWN",
            findings=[],
            summary_rationale="Unknown",
        )

    verdict = JudiciaryVerdict(
        task_id="TASK-001",
        status="APPROVED",
        findings=[],
        summary_rationale="Approved",
    )
    with pytest.raises(ValidationError):
        verdict.status = "REJECTED"

    with pytest.raises(ValidationError):
        JudiciaryVerdict.model_validate(
            {
                "task_id": "TASK-001",
                "status": "APPROVED",
                "findings": [],
                "summary_rationale": "Approved",
                "disallowed": "forbidden",
            }
        )


def test_genome_atom_gene_type_and_immutability() -> None:
    """Verify GenomeAtom GeneType enum validation, immutability, and extra forbid."""
    for gtype in (GeneType.STRUCTURAL, GeneType.BEHAVIORAL, GeneType.INHIBITOR):
        gene = GenomeAtom(
            gene_id="GENE-001",
            gene_type=gtype,
            component_name="stc.substrate.receipt",
            pattern_signature="sha256_canonical_json",
            raw_code_or_rule="Rule content",
            receipt_reference="RCPT-001",
        )
        assert gene.gene_type == gtype

    with pytest.raises(ValidationError):
        GenomeAtom.model_validate(
            {
                "gene_id": "GENE-001",
                "gene_type": "invalid_gene_type",
                "component_name": "comp",
                "pattern_signature": "sig",
                "raw_code_or_rule": "rule",
                "receipt_reference": "rcpt",
            }
        )

    gene_valid = GenomeAtom(
        gene_id="GENE-001",
        gene_type=GeneType.STRUCTURAL,
        component_name="comp",
        pattern_signature="sig",
        raw_code_or_rule="rule",
        receipt_reference="rcpt",
    )
    with pytest.raises(ValidationError):
        gene_valid.component_name = "mutated"

    with pytest.raises(ValidationError):
        GenomeAtom.model_validate(
            {
                "gene_id": "GENE-001",
                "gene_type": GeneType.STRUCTURAL.value,
                "component_name": "comp",
                "pattern_signature": "sig",
                "raw_code_or_rule": "rule",
                "receipt_reference": "rcpt",
                "extra": "disallowed",
            }
        )


def test_hormone_event_and_scope_valid_and_immutable() -> None:
    """Verify HormoneScope and HormoneEvent validation, automatic sha256, and immutability."""
    scope = HormoneScope(
        producer_subsystem="substrate",
        target_subsystems=["judiciary", "orchestrator"],
        topic="membrane.contracts",
        channel="cell.isolated",
    )
    assert scope.producer_subsystem == "substrate"

    with pytest.raises(ValidationError):
        scope.topic = "mutated"

    event = HormoneEvent(
        signal_type=HormoneSignalType.TEST_FAILURE,
        scope=scope,
        payload={"gate": "pytest", "failed": 2},
    )
    assert event.signal_type == HormoneSignalType.TEST_FAILURE
    assert len(event.payload_sha256) == 64

    with pytest.raises(ValidationError):
        event.signal_type = HormoneSignalType.CONTRACT_DRIFT

    with pytest.raises(ValidationError):
        HormoneEvent.model_validate(
            {
                "signal_type": HormoneSignalType.TEST_FAILURE.value,
                "scope": scope.model_dump(),
                "extra": "forbidden",
            }
        )


# =====================================================================
# PEP 544 Protocol Conformance Tests
# =====================================================================


class CompliantWorker:
    """Dummy worker conforming to PEP 544 WorkerProtocol."""

    def dispatch(self, bundle: TaskBundle, lease: WorktreeLease) -> str:
        return f"dispatched_{bundle.task_id}"

    def confinement_root(self, lease: WorktreeLease) -> Path:
        return Path(lease.worktree_path)


class IncompleteWorker:
    """Incomplete worker missing confinement_root method."""

    def dispatch(self, bundle: TaskBundle, lease: WorktreeLease) -> str:
        return "dispatched"


def test_worker_protocol_conformance() -> None:
    """Verify WorkerProtocol PEP 544 runtime checkable membrane enforcement."""
    compliant = CompliantWorker()
    incomplete = IncompleteWorker()

    assert isinstance(compliant, WorkerProtocol)
    assert not isinstance(incomplete, WorkerProtocol)


class CompliantSubstrateRunner:
    """Dummy runner conforming to PEP 544 SubstrateRunnerProtocol."""

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        epoch_index: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        pytest_target: str | None = None,
    ) -> ExecutionReceipt:
        raise NotImplementedError

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool:
        return True


class IncompleteSubstrateRunner:
    """Incomplete runner missing verify_receipt."""

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        epoch_index: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        pytest_target: str | None = None,
    ) -> ExecutionReceipt:
        raise NotImplementedError


def test_substrate_runner_protocol_conformance() -> None:
    """Verify SubstrateRunnerProtocol PEP 544 runtime checkable membrane enforcement."""
    compliant = CompliantSubstrateRunner()
    incomplete = IncompleteSubstrateRunner()

    assert isinstance(compliant, SubstrateRunnerProtocol)
    assert not isinstance(incomplete, SubstrateRunnerProtocol)


def test_all_membrane_protocols_runtime_checkable() -> None:
    """Verify that all 10 core STC protocols are runtime_checkable protocols."""
    protocols = [
        ContextCompilerProtocol,
        GenomeStoreProtocol,
        HormoneBusProtocol,
        JudiciaryAuditorProtocol,
        SocraticDecomposerProtocol,
        SpecIngestorProtocol,
        SubstrateRunnerProtocol,
        TraceMemoryProtocol,
        WorkerProtocol,
        WorktreeManagerProtocol,
    ]
    for proto in protocols:
        # runtime_checkable protocols permit isinstance() checks without TypeError
        class EmptyClass:
            pass

        assert isinstance(EmptyClass(), proto) is False


# =====================================================================
# STL Decoupled Model Tests
# =====================================================================


def test_task_spec_validation_and_immutability() -> None:
    """Verify TaskSpec defaults, frozen immutability, and extra forbid."""
    spec = TaskSpec(
        name="Compile AST",
        action="build_ast",
        priority=TaskPriority.HIGH,
        payload={"target": "main.py"},
        timeout_seconds=45.0,
    )
    assert spec.name == "Compile AST"
    assert spec.priority == TaskPriority.HIGH
    assert spec.timeout_seconds == 45.0
    assert spec.task_id.startswith("task_")

    with pytest.raises(ValidationError):
        spec.name = "Mutated"

    with pytest.raises(ValidationError):
        TaskSpec.model_validate(
            {
                "name": "Compile AST",
                "action": "build_ast",
                "extra_key": "forbidden",
            }
        )

    with pytest.raises(ValidationError):
        TaskSpec(name="", action="build_ast")  # min_length=1

    with pytest.raises(ValidationError):
        TaskSpec(name="Valid", action="build_ast", timeout_seconds=0.0)  # gt=0.0


def test_task_receipt_validation_and_immutability() -> None:
    """Verify TaskReceipt validation, frozen immutability, and extra forbid."""
    now = datetime.now(UTC)
    receipt = TaskReceipt(
        task_id="task_12345678",
        status=TaskStatus.COMPLETED,
        started_at=now,
        finished_at=now + timedelta(seconds=1),
        duration_ms=1000.0,
        result={"artifacts": 3},
        checksum_sha256="c" * 64,
    )
    assert receipt.status == TaskStatus.COMPLETED
    assert receipt.duration_ms == 1000.0

    with pytest.raises(ValidationError):
        receipt.status = TaskStatus.FAILED

    with pytest.raises(ValidationError):
        TaskReceipt.model_validate(
            {
                "task_id": "task_12345678",
                "status": "completed",
                "started_at": now.isoformat(),
                "finished_at": (now + timedelta(seconds=1)).isoformat(),
                "duration_ms": 1000.0,
                "checksum_sha256": "c" * 64,
                "unknown_field": True,
            }
        )


def test_system_metrics_and_health_status_validation_and_immutability() -> None:
    """Verify SystemMetrics and HealthStatus validation and frozen immutability."""
    metrics = SystemMetrics(
        active_workers=4,
        tasks_processed=100,
        tasks_succeeded=95,
        tasks_failed=5,
        uptime_seconds=3600.0,
    )
    assert metrics.tasks_processed == 100

    with pytest.raises(ValidationError):
        metrics.active_workers = 5

    with pytest.raises(ValidationError):
        SystemMetrics.model_validate({"active_workers": -1})

    health = HealthStatus(
        status="ok",
        service="stc",
        version="0.1.0",
        metrics=metrics,
    )
    assert health.status == "ok"
    assert health.service == "stc"
    assert health.metrics.tasks_succeeded == 95

    with pytest.raises(ValidationError):
        health.status = "degraded"

    with pytest.raises(ValidationError):
        HealthStatus.model_validate(
            {
                "status": "ok",
                "service": "stc",
                "version": "0.1.0",
                "metrics": metrics.model_dump(),
                "unexpected": 42,
            }
        )


def test_task_priority_and_status_enums() -> None:
    """Verify TaskPriority and TaskStatus enum values."""
    assert TaskPriority.LOW.value == "low"
    assert TaskPriority.NORMAL.value == "normal"
    assert TaskPriority.HIGH.value == "high"
    assert TaskPriority.CRITICAL.value == "critical"

    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.CANCELLED.value == "cancelled"


# =====================================================================
# Additional PEP 544 Protocol Conformance Tests
# =====================================================================


class CompliantSpecIngestor:
    def ingest_path(self, path: Path) -> SpecAtom:
        raise NotImplementedError

    def ingest_string(self, content: str, source_name: str) -> SpecAtom:
        raise NotImplementedError


class IncompleteSpecIngestor:
    def ingest_path(self, path: Path) -> SpecAtom:
        raise NotImplementedError


def test_spec_ingestor_protocol_conformance() -> None:
    assert isinstance(CompliantSpecIngestor(), SpecIngestorProtocol)
    assert not isinstance(IncompleteSpecIngestor(), SpecIngestorProtocol)


class CompliantSocraticDecomposer:
    def decompose(self, spec: SpecAtom) -> TreeOfConcerns:
        raise NotImplementedError

    def detect_ambiguity(self, toc: TreeOfConcerns) -> list[ArchetypeDiff]:
        raise NotImplementedError

    def lock_invariants(self, toc: TreeOfConcerns, selected_archetypes: list[int]) -> Path:
        raise NotImplementedError


class IncompleteSocraticDecomposer:
    def decompose(self, spec: SpecAtom) -> TreeOfConcerns:
        raise NotImplementedError


def test_socratic_decomposer_protocol_conformance() -> None:
    assert isinstance(CompliantSocraticDecomposer(), SocraticDecomposerProtocol)
    assert not isinstance(IncompleteSocraticDecomposer(), SocraticDecomposerProtocol)


class CompliantTraceMemory:
    def query_semantic_context(self, keywords: list[str], max_results: int = 3) -> list[str]:
        # Protocol conformance dummy stub - not error swallowing
        return []

    def query_negative_inhibitors(self, component: str) -> list[str]:
        # Protocol conformance dummy stub - not error swallowing
        return []


class IncompleteTraceMemory:
    def query_semantic_context(self, keywords: list[str], max_results: int = 3) -> list[str]:
        # Protocol conformance dummy stub - not error swallowing
        return []


def test_trace_memory_protocol_conformance() -> None:
    assert isinstance(CompliantTraceMemory(), TraceMemoryProtocol)
    assert not isinstance(IncompleteTraceMemory(), TraceMemoryProtocol)


class CompliantContextCompiler:
    def compile_task(
        self,
        task_id: str,
        spec: SpecAtom,
        toc: TreeOfConcerns,
        inhibitors: list[str],
    ) -> TaskBundle:
        raise NotImplementedError


class IncompleteContextCompiler:
    pass


def test_context_compiler_protocol_conformance() -> None:
    assert isinstance(CompliantContextCompiler(), ContextCompilerProtocol)
    assert not isinstance(IncompleteContextCompiler(), ContextCompilerProtocol)


class CompliantWorktreeManager:
    def allocate_lease(self, task_id: str, base_branch: str = "main") -> WorktreeLease:
        raise NotImplementedError

    def release_lease(self, lease: WorktreeLease, purge: bool = True) -> None:
        pass

    def get_diff(self, lease: WorktreeLease) -> str:
        return ""


class IncompleteWorktreeManager:
    def allocate_lease(self, task_id: str, base_branch: str = "main") -> WorktreeLease:
        raise NotImplementedError


def test_worktree_manager_protocol_conformance() -> None:
    assert isinstance(CompliantWorktreeManager(), WorktreeManagerProtocol)
    assert not isinstance(IncompleteWorktreeManager(), WorktreeManagerProtocol)


class CompliantJudiciaryAuditor:
    def audit_diff(
        self,
        diff_text: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
    ) -> JudiciaryVerdict:
        raise NotImplementedError


class IncompleteJudiciaryAuditor:
    pass


def test_judiciary_auditor_protocol_conformance() -> None:
    assert isinstance(CompliantJudiciaryAuditor(), JudiciaryAuditorProtocol)
    assert not isinstance(IncompleteJudiciaryAuditor(), JudiciaryAuditorProtocol)


class CompliantGenomeStore:
    def save_gene(self, gene: GenomeAtom) -> str:
        return gene.gene_id

    def find_genes(self, tags: list[str]) -> list[GenomeAtom]:
        # Protocol conformance dummy stub - not error swallowing
        return []


class IncompleteGenomeStore:
    def save_gene(self, gene: GenomeAtom) -> str:
        return gene.gene_id


def test_genome_store_protocol_conformance() -> None:
    assert isinstance(CompliantGenomeStore(), GenomeStoreProtocol)
    assert not isinstance(IncompleteGenomeStore(), GenomeStoreProtocol)


class CompliantHormoneBus:
    def publish(self, event: HormoneEvent) -> str:
        return event.event_id

    def subscribe(self, subsystem_id: str, topics: list[str] | None = None) -> None:
        pass

    def poll_events(self, subsystem_id: str, max_events: int = 10) -> list[HormoneEvent]:
        # Protocol conformance dummy stub - not error swallowing
        return []


class IncompleteHormoneBus:
    def publish(self, event: HormoneEvent) -> str:
        return event.event_id


def test_hormone_bus_protocol_conformance() -> None:
    assert isinstance(CompliantHormoneBus(), HormoneBusProtocol)
    assert not isinstance(IncompleteHormoneBus(), HormoneBusProtocol)
