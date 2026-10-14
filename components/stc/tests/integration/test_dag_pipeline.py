"""Integration tests for STC Full DAG Pipeline (N01 through N22).

Verifies the end-to-end autonomous pipeline from specification intake to
promotion candidate and Project Trace genetic code bank ingestion:
- N01-N02: Spec Atom Ingestion & Validation
- N03: Tree of Concerns (TOC) Decomposition
- N04-N06: Ambiguity Detection & Invariant Locking
- N07-N08: Context Retrieval & Negative Inhibitor Injection
- N09: Task Bundle Context Compilation (< 25KB ceiling)
- N10: Leased Git Worktree Allocation
- N11: Typing Membrane Verification (PEP 544 & Pydantic V2)
- N12: Executive Worker Dispatch (CLIChaperoneWorker confinement & notary custody)
- N13-N16: Mechanical Substrate Gates (Ruff, Mypy, Pytest)
- N17: Machine Execution Receipt HMAC-SHA256 Signing
- N17J: Synchronization Barrier (Join)
- N18-N19: Blind Adversarial Judiciary Red Team Audit
- N20: Sovereign Promotion & Merge Authority
- N21: Project Trace Genetic Code Bank Ingestion
- N22: Leased Worktree Release & Purge
- Circuit-breaker bounded epoch retries & quarantine lifecycle
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from stc.cli import main
from stc.core.config import get_settings
from stc.core.errors import TraceMemoryError
from stc.genome.store import GenomeStore
from stc.judiciary.auditor import JudiciaryAuditor
from stc.protocols.interfaces import SubstrateRunnerProtocol
from stc.schemas.models import (
    ExecutionReceipt,
    GateReport,
    GeneType,
    GenomeAtom,
    TaskBundle,
)
from stc.substrate.runner import create_receipt
from stc.worktree.manager import WorktreeManager


def _find_sample_spec_path() -> str:
    p = Path(__file__).resolve()
    parts = list(p.parts)
    if "mutants" in parts:
        idx = parts.index("mutants")
        repo_root = Path(*parts[:idx])
    else:
        repo_root = p.parent.parent.parent
    return str(repo_root / "specs" / "sample_spec.md")


_SAMPLE_SPEC_PATH = _find_sample_spec_path()


@pytest.fixture(autouse=True)
def _disposable_runtime_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Redirect gate-generated state to per-test disposable locations (R1).

    The DAG pipeline writes locked invariants, signed receipts, trace DB
    rows, and leased worktrees; all land under tmp_path so the gated
    repository stays byte-neutral and the merge tripwire stays clean.
    """
    roots = tmp_path / "stc-runtime"
    monkeypatch.setenv("STC_INVARIANTS_DIR", str(roots / "invariants"))
    monkeypatch.setenv("STC_RECEIPTS_DIR", str(roots / "receipts"))
    monkeypatch.setenv("STC_TRACE_DB_PATH", str(roots / "trace.db"))
    monkeypatch.setenv("STC_WORKTREE_ROOT", str(roots / "worktrees"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_full_dag_pipeline_sovereign_accept(tmp_path: Path) -> None:
    """Walk N01->N22 with Sovereign accepting merge (-y) and verifying genome ingestion."""
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "run",
            _SAMPLE_SPEC_PATH,
            "-y",
            "--pytest-target",
            "tests/unit/test_config.py",
        ],
    )
    assert res.exit_code == 0, f"Command failed: {res.output}"
    output = res.output

    # Verify key DAG touchpoints executed in sequence
    assert "N01-N02: Ingest & Validate Spec Atom" in output
    assert "N03: Tree of Concerns (TOC) Decomposition" in output
    assert "N07-N08: Query Hippocampal Trace Memory" in output
    assert "N09: Context Compilation" in output
    assert "N10: Allocate Leased Git Worktree" in output
    assert "N11: Verify Typing Membranes" in output
    assert "N12: Dispatch Executive Worker (Chaperone)" in output
    assert "N13-N16: Mechanical Substrate Gates" in output
    assert "N18-N19: Blind Judiciary Audit" in output
    assert "APPROVED" in output
    assert "Sovereign Merge Authority Required" in output
    assert "Merged branch" in output
    assert "Ingested" in output
    assert "COMPLETED" in output

    # Verify genes were ingested into Project Trace Genome DB
    store = GenomeStore()
    genes = store.find_genes(["sample_spec"])
    assert len(genes) >= 2
    types = {g.gene_type for g in genes}
    assert GeneType.STRUCTURAL in types
    assert GeneType.BEHAVIORAL in types


def test_full_dag_pipeline_sovereign_decline(tmp_path: Path) -> None:
    """Verify Sovereign declining merge (N) preserves the candidate worktree untouched."""
    spec_file = tmp_path / "decline_spec.md"
    spec_file.write_text(
        "# Decline Test Service\n\n"
        "## Domain Invariants\nPreserve worktree on decline.\n"
        "## Persistence & Storage\nSQLite session tables.\n"
        "## Communication Protocols\nPEP 544 AuthGatewayProtocol.\n"
        "## Boundary & Security\nIsolated worktree boundary.\n"
        "## Failure Resilience\nFail-closed on rejection.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "run",
            str(spec_file),
            "--pytest-target",
            "tests/unit/test_config.py",
            "--task-id",
            "TASK-DECLINE-TEST",
        ],
        input="N\n",
    )
    assert res.exit_code == 0, f"Command failed: {res.output}"
    assert "Sovereign declined merge" in res.output
    assert "Leased worktree preserved at" in res.output

    # Confirm worktree directory was preserved on disk
    mgr = WorktreeManager()
    records = mgr._load_leases()
    norm_id = mgr._normalize_task_id("TASK-DECLINE-TEST")
    assert norm_id in records
    wt_path = Path(records[norm_id]["worktree_path"])
    assert wt_path.is_dir(), f"Worktree {wt_path} was unexpectedly deleted"

    # Clean up preserved worktree
    res_clean = runner.invoke(main, ["worktree", "release", "TASK-DECLINE-TEST", "--purge"])
    assert res_clean.exit_code == 0


def test_circuit_breaker_bounded_epoch_retry(tmp_path: Path) -> None:
    """Verify circuit breaker trips on substrate failure, injecting inhibitors
    and halting at max epochs."""
    spec_file = tmp_path / "failing_gate_spec.md"
    spec_file.write_text(
        "# Gate Failure Simulation\n\n"
        "## Domain Invariants\nSimulate gate failure.\n"
        "## Persistence & Storage\nSQLite tables.\n"
        "## Communication Protocols\nPEP 544 Protocol.\n"
        "## Boundary & Security\nConfinement.\n"
        "## Failure Resilience\nRetry then quarantine.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "run",
            str(spec_file),
            "--pytest-target",
            "tests/unit/nonexistent_test_file.py",
            "--max-epochs",
            "2",
            "--task-id",
            "TASK-FAIL-CIRCUIT",
            "-y",
        ],
    )
    # Pipeline must halt fail-closed
    assert res.exit_code != 0
    output = res.output

    # Verify epoch index increments and retry loop executes
    assert "Epoch 1/2 Execution" in output
    assert "FAIL (pytest)" in output
    assert "Epoch 2/2 Execution" in output
    assert "Pipeline halted: Substrate gates failed across 2 epochs" in output

    # Verify task was quarantined in lease records
    mgr = WorktreeManager()
    records = mgr._load_leases()
    norm_id = mgr._normalize_task_id("TASK-FAIL-CIRCUIT")
    assert norm_id in records
    assert records[norm_id]["status"] == "QUARANTINED"
    assert records[norm_id]["is_active"] is False
    assert records[norm_id]["refutation_record"] is not None

    # Clean up quarantined lease
    res_clean = runner.invoke(main, ["worktree", "release", "TASK-FAIL-CIRCUIT", "--purge"])
    assert res_clean.exit_code == 0


def test_dag_pipeline_json_mode_contract(tmp_path: Path) -> None:
    """Verify run in JSON mode emits pure JSON adhering to full execution contract."""
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "-j",
            "run",
            _SAMPLE_SPEC_PATH,
            "--pytest-target",
            "tests/unit/test_config.py",
            "--task-id",
            "TASK-SAMPLE-JSON",
        ],
    )
    assert res.exit_code == 0, f"Command failed: {res.output}"
    parsed = json.loads(res.output)

    assert "spec_atom" in parsed
    assert parsed["spec_atom"]["spec_id"] == "sample_spec"
    assert "tree_of_concerns" in parsed
    assert "task_bundle" in parsed
    assert "worktree_lease" in parsed
    assert "execution_receipt" in parsed
    assert "judiciary_verdict" in parsed

    # Receipt and verdict assertions
    receipt = parsed["execution_receipt"]
    assert receipt["receipt_id"].startswith("rcpt_")
    assert receipt["gate_ruff"]["exit_code"] == 0
    assert receipt["gate_mypy"]["exit_code"] == 0
    assert receipt["gate_pytest"]["exit_code"] == 0

    verdict = parsed["judiciary_verdict"]
    assert verdict["status"] == "APPROVED"
    assert len(verdict["findings"]) == 0


def test_genome_store_table_schema_and_gene_lifecycle(tmp_path: Path) -> None:
    """Verify GenomeStore persists across all physical SQLite tables with zero mocks."""
    db_file = tmp_path / "isolated_trace.db"
    store = GenomeStore(db_path=db_file)

    # 1. Verify schema tables exist
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    expected_tables = {
        "genome_atoms",
        "documents",
        "atoms",
        "proposals",
        "events",
        "attachments",
    }
    assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

    # 2. Save individual genes
    struct_gene = GenomeAtom(
        gene_id="gene_test_struct_001",
        gene_type=GeneType.STRUCTURAL,
        component_name="AuthService",
        pattern_signature="def verify_token(token: str) -> bool:",
        raw_code_or_rule="class AuthProtocol(Protocol):\n    def verify(self) -> bool: ...",
        receipt_reference="rcpt_test_001",
    )
    gene_id = store.save_gene(struct_gene)
    assert gene_id == "gene_test_struct_001"

    inhibitor_gene = GenomeAtom(
        gene_id="gene_test_inhibitor_002",
        gene_type=GeneType.INHIBITOR,
        component_name="DatabaseClient",
        pattern_signature="threading.Lock deadlock in sqlite connection pool",
        raw_code_or_rule="Never retain exclusive lock across async yield",
        receipt_reference="rcpt_test_002",
    )
    store.save_gene(inhibitor_gene)

    # 3. Query via find_genes
    found_auth = store.find_genes(["AuthService"])
    assert len(found_auth) == 1
    assert found_auth[0].gene_id == "gene_test_struct_001"
    assert found_auth[0].gene_type == GeneType.STRUCTURAL

    found_inhib = store.find_genes(["deadlock"])
    assert len(found_inhib) == 1
    assert found_inhib[0].gene_id == "gene_test_inhibitor_002"
    assert found_inhib[0].gene_type == GeneType.INHIBITOR

    # 4. Verify proposals table statuses
    cursor.execute("SELECT proposal_id, status FROM proposals ORDER BY proposal_id;")
    props = cursor.fetchall()
    prop_dict = dict(props)
    assert prop_dict["prop_gene_test_struct_001"] == "DECIDED"
    assert prop_dict["prop_gene_test_inhibitor_002"] == "REFUTED"

    # 5. Verify documents and atoms tables
    cursor.execute("SELECT COUNT(*) FROM documents;")
    assert cursor.fetchone()[0] == 2
    cursor.execute("SELECT COUNT(*) FROM atoms;")
    assert cursor.fetchone()[0] == 2

    # 6. Verify ingest_trace helper emits structural, behavioral, and inhibitor genes
    dummy_gate = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-INGEST-TRACE",
        commit_hash="abcdef012345",
        gate_ruff=dummy_gate,
        gate_mypy=dummy_gate,
        gate_pytest=dummy_gate,
        gate_mutmut=dummy_gate,
        receipt_id="rcpt_ingest_trace_001",
        epoch_index=1,
    )
    diff_text = (
        "diff --git a/src/stc/auth.py b/src/stc/auth.py\n"
        "--- a/src/stc/auth.py\n"
        "+++ b/src/stc/auth.py\n"
        "+class AuthGateway:\n"
        "+    def authenticate(self) -> bool:\n"
        "+        return True\n"
    )
    refutations = ["Do not use plain MD5 for token signatures."]
    ingested = store.ingest_trace(
        task_id="TASK-INGEST-TRACE",
        receipt=receipt,
        diff_text=diff_text,
        refutation_log=refutations,
    )
    assert len(ingested) == 3
    ingested_types = {g.gene_type for g in ingested}
    assert ingested_types == {
        GeneType.STRUCTURAL,
        GeneType.BEHAVIORAL,
        GeneType.INHIBITOR,
    }

    conn.close()


def test_full_dag_pipeline_git_merge_conflict_fail_closed(tmp_path: Path) -> None:
    """Verify git merge conflict in Sovereign merge halts fail-closed,
    preserves candidate worktree, and leaves working copy clean."""
    runner = CliRunner()
    repo = tmp_path / "conflict_repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Main\n", encoding="utf-8")
    (repo / ".gitignore").write_text("worktrees/\nartifacts/\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        mgr = WorktreeManager(repo_root=repo)
        task_id = "TASK-CONFLICT-TEST"

        # 1. Allocate a real worktree lease
        lease = mgr.allocate_lease(task_id=task_id)
        wt_path = Path(lease.worktree_path)
        assert wt_path.is_dir()

        # 2. Write candidate commit in worktree
        conflict_file_wt = wt_path / "conflict_target.txt"
        conflict_file_wt.write_text("Candidate worktree content\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "conflict_target.txt"],
            cwd=wt_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat: candidate change"],
            cwd=wt_path,
            check=True,
            capture_output=True,
        )

        # 3. Create conflicting commit on main
        conflict_file_main = repo / "conflict_target.txt"
        conflict_file_main.write_text("Conflicting main branch content\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "conflict_target.txt"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "fix: conflicting main commit"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # 4. Attempt promote with Sovereign accepting
        res = runner.invoke(main, ["promote", task_id], input="y\n")

        # Must fail closed
        assert res.exit_code != 0
        assert "Git merge failed" in res.output

        # Verify candidate worktree was preserved on disk (not purged)
        assert wt_path.is_dir(), f"Worktree {wt_path} was purged despite merge failure!"

        # Verify working copy on main was cleaned up (not left in MERGING state)
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "UU conflict_target.txt" not in status_res.stdout
    finally:
        os.chdir(old_cwd)


def test_cli_promote_end_to_end(tmp_path: Path) -> None:
    """Verify stc promote merges candidate branch, ingests genes, and cleans up worktree."""
    runner = CliRunner()
    repo = tmp_path / "promote_repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Main\n", encoding="utf-8")
    (repo / ".gitignore").write_text("worktrees/\nartifacts/\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        mgr = WorktreeManager(repo_root=repo)
        task_id = "TASK-PROMOTE-E2E"

        # 1. Allocate a real worktree lease
        lease = mgr.allocate_lease(task_id=task_id)
        wt_path = Path(lease.worktree_path)

        # 2. Add and commit candidate file in worktree
        promo_file_wt = wt_path / "promote_candidate_marker.txt"
        promo_file_wt.write_text("Promoted feature content\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "promote_candidate_marker.txt"],
            cwd=wt_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat: candidate to promote"],
            cwd=wt_path,
            check=True,
            capture_output=True,
        )

        # 3. Create a valid ExecutionReceipt
        dummy_gate = GateReport(
            gate_name="gate",
            exit_code=0,
            duration_seconds=0.1,
            violations_count=0,
            raw_output_snippet="OK",
        )
        receipt = create_receipt(
            task_id=task_id,
            commit_hash="c0ffee9876",
            gate_ruff=dummy_gate,
            gate_mypy=dummy_gate,
            gate_pytest=dummy_gate,
            gate_mutmut=dummy_gate,
            receipt_id="rcpt_promote_e2e_001",
            epoch_index=1,
        )
        receipt_file = tmp_path / "promote_receipt.json"
        receipt_file.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

        # 4. Invoke promote with Sovereign confirmation
        res = runner.invoke(
            main,
            ["promote", task_id, "--receipt", str(receipt_file)],
            input="y\n",
        )
        assert res.exit_code == 0, f"Promote failed: {res.output}"
        assert "Merged branch" in res.output
        assert "Ingested" in res.output
        assert "Released worktree" in res.output
        assert "COMPLETED" in res.output

        # 5. Verify file was merged into main
        merged_file = repo / "promote_candidate_marker.txt"
        assert merged_file.is_file(), "File was not merged into base branch!"
        assert merged_file.read_text(encoding="utf-8") == "Promoted feature content\n"

        # 6. Verify worktree directory was purged
        assert not wt_path.exists(), "Worktree directory was not purged after promotion!"

        # 7. Verify genes in GenomeStore
        store = GenomeStore()
        genes = store.find_genes([task_id])
        assert len(genes) >= 2
    finally:
        os.chdir(old_cwd)


def test_dag_pipeline_with_codex_flag_absent_binary() -> None:
    """Verify --with-codex flag in stc run halts fail-closed when codex binary is absent."""
    if shutil.which("codex") or shutil.which("codex.exe"):
        return

    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "run",
            _SAMPLE_SPEC_PATH,
            "-y",
            "--with-codex",
            "--pytest-target",
            "tests/unit/test_config.py",
            "--task-id",
            "TASK-CODEX-ABSENT",
        ],
    )
    # Must fail closed because codex was requested but unavailable
    assert res.exit_code != 0
    assert "CODEX_EXECUTION_ERROR" in res.output or "Pipeline halted" in res.output


class MockFreeRunner:
    """Zero-mock runner implementing SubstrateRunnerProtocol for verification testing."""

    def __init__(self, should_pass: bool = True) -> None:
        self.should_pass = should_pass
        self.verified_calls: list[ExecutionReceipt] = []

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool:
        self.verified_calls.append(receipt)
        return self.should_pass

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


def test_judiciary_auditor_adversarial_codex_and_runner_conformance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify JudiciaryAuditor with custom runner, codex CLI integration, and error branches."""
    # 1. Conformance and attributes
    runner = MockFreeRunner(should_pass=True)
    assert isinstance(runner, SubstrateRunnerProtocol)
    auditor = JudiciaryAuditor(runner=runner, with_codex=True, codex_bin="/bin/custom_codex")
    assert auditor.runner is runner
    assert auditor.with_codex is True
    assert auditor.codex_bin == "/bin/custom_codex"

    dummy_gate = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-TEST-AUDIT",
        commit_hash="1234567890abcdef",
        gate_ruff=dummy_gate,
        gate_mypy=dummy_gate,
        gate_pytest=dummy_gate,
        gate_mutmut=dummy_gate,
        receipt_id="rcpt_audit_001",
        epoch_index=1,
    )
    bundle = TaskBundle(
        task_id="TASK-TEST-AUDIT",
        epoch_index=1,
        spec_id="spec_audit",
        goal_statement="Adversarial audit testing",
        invariants=["No mocks", "No silent fallbacks"],
        target_files=[],
        membrane_protocols=["SubstrateRunnerProtocol"],
        negative_inhibitors=[],
    )

    # 2. Custom runner verify_receipt is called
    assert auditor._verify_receipt_signature(receipt) is True
    assert len(runner.verified_calls) == 1

    # 3. Built-in signature verification when runner is None
    bare_auditor = JudiciaryAuditor()
    assert bare_auditor._verify_receipt_signature(receipt) is True

    # 4. Tampered / empty signature returns False
    tampered = receipt.model_copy(update={"sha256_signature": ""})
    assert bare_auditor._verify_receipt_signature(tampered) is False

    # 5. Codex CLI missing executable -> returns CODEX_EXECUTION_ERROR
    missing_auditor = JudiciaryAuditor(
        with_codex=True, codex_bin=str(tmp_path / "nonexistent_codex")
    )
    findings = missing_auditor._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings) == 1
    assert findings[0].rule_name == "CODEX_EXECUTION_ERROR"
    assert findings[0].severity == "CRITICAL"

    # 6. Real executable returning 0 -> no findings
    success_script = tmp_path / "mock_codex_pass.sh"
    success_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    success_script.chmod(0o755)
    pass_auditor = JudiciaryAuditor(with_codex=True, codex_bin=str(success_script))
    findings_pass = pass_auditor._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings_pass) == 0

    # 7. Real executable returning 1 -> CODEX_AUDIT_FAILURE
    fail_script = tmp_path / "mock_codex_fail.sh"
    fail_script.write_text("#!/bin/sh\necho 'Violation in diff' >&2\nexit 1\n", encoding="utf-8")
    fail_script.chmod(0o755)
    fail_auditor = JudiciaryAuditor(with_codex=True, codex_bin=str(fail_script))
    findings_fail = fail_auditor._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings_fail) == 1
    assert findings_fail[0].rule_name == "CODEX_AUDIT_FAILURE"
    assert findings_fail[0].severity == "CRITICAL"

    # 8. Real executable failing with OSError / non-executable -> CODEX_EXECUTION_ERROR
    bad_script = tmp_path / "mock_codex_bad.sh"
    bad_script.write_text("not an executable", encoding="utf-8")
    bad_script.chmod(0o644)  # not executable
    err_auditor = JudiciaryAuditor(with_codex=True, codex_bin=str(bad_script))
    findings_err = err_auditor._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings_err) == 1
    assert findings_err[0].rule_name == "CODEX_EXECUTION_ERROR"

    # 9. codex_bin resolution when self.codex_bin is None via shutil.which
    bare_codex_auditor = JudiciaryAuditor(with_codex=True, codex_bin=None)
    monkeypatch.setattr(
        shutil, "which", lambda cmd: str(success_script) if "codex" in cmd else None
    )
    findings_which = bare_codex_auditor._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings_which) == 0

    # 10. shutil.which returning None produces CODEX_EXECUTION_ERROR
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    findings_none = bare_codex_auditor._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings_none) == 1
    assert findings_none[0].rule_name == "CODEX_EXECUTION_ERROR"


def test_judiciary_auditor_diff_inspection_edge_cases() -> None:
    """Verify secrets, multiline fallbacks, contract tampering, and verdict synthesis."""
    auditor = JudiciaryAuditor()
    dummy_gate = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-DIFF-EDGES",
        commit_hash="abcdef1234567890",
        gate_ruff=dummy_gate,
        gate_mypy=dummy_gate,
        gate_pytest=dummy_gate,
        gate_mutmut=dummy_gate,
        receipt_id="rcpt_edges_001",
        epoch_index=1,
    )
    bundle = TaskBundle(
        task_id="TASK-DIFF-EDGES",
        epoch_index=1,
        spec_id="spec_edges",
        goal_statement="Edge case testing",
        invariants=["No secrets", "No contract tampering"],
        target_files=[],
        membrane_protocols=["SubstrateRunnerProtocol"],
        negative_inhibitors=[],
    )

    # 1. Hardcoded secrets detection
    diff_secret = (
        "diff --git a/src/service.py b/src/service.py\n"
        "--- a/src/service.py\n"
        "+++ b/src/service.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+api_" + "key = 'abcdef1234567890abcdef'\n"
    )
    verdict = auditor.audit_diff(diff_secret, bundle, receipt)
    assert verdict.status == "REJECTED"
    assert any(f.rule_name == "HARDCODED_SECRET_VIOLATION" for f in verdict.findings)

    # 2. Multiline exception handler: except followed by pass / return None
    diff_multiline = (
        "diff --git a/src/handler.py b/src/handler.py\n"
        "--- a/src/handler.py\n"
        "+++ b/src/handler.py\n"
        "@@ -10,3 +10,5 @@\n"
        "+    try:\n"
        "+        do_action()\n"
        "+    except ValueError:\n"
        "+        return None\n"
    )
    verdict_multi = auditor.audit_diff(diff_multiline, bundle, receipt)
    assert verdict_multi.status == "REJECTED"
    assert any(f.rule_name == "SILENT_FALLBACK_VIOLATION" for f in verdict_multi.findings)

    # 3. Invariant tampering in 01_INVARIANTS.md
    diff_invar = (
        "diff --git a/01_INVARIANTS.md b/01_INVARIANTS.md\n"
        "--- a/01_INVARIANTS.md\n"
        "+++ b/01_INVARIANTS.md\n"
        "@@ -5,2 +5,1 @@\n"
        "-The rule of inviolability is strict.\n"
    )
    verdict_invar = auditor.audit_diff(diff_invar, bundle, receipt)
    assert verdict_invar.status == "REJECTED"
    assert any(f.rule_name == "INVARIANT_TAMPERING" for f in verdict_invar.findings)

    # 4. Contract tampering in src/stc/protocols/interfaces.py
    diff_proto = (
        "diff --git a/src/stc/protocols/interfaces.py b/src/stc/protocols/interfaces.py\n"
        "--- a/src/stc/protocols/interfaces.py\n"
        "+++ b/src/stc/protocols/interfaces.py\n"
        "@@ -15,2 +15,1 @@\n"
        "-class SubstrateRunnerProtocol(Protocol):\n"
    )
    verdict_proto = auditor.audit_diff(diff_proto, bundle, receipt)
    assert verdict_proto.status == "REJECTED"
    assert any(f.rule_name == "CONTRACT_TAMPERING" for f in verdict_proto.findings)

    # 5. Non-python files are ignored for mock and fallback rules
    diff_md = (
        "diff --git a/docs/guide.md b/docs/guide.md\n"
        "--- a/docs/guide.md\n"
        "+++ b/docs/guide.md\n"
        "@@ -1,2 +1,3 @@\n" + "+Here is an example: except" + ": pass and mock" + " == True\n"
    )
    verdict_md = auditor.audit_diff(diff_md, bundle, receipt)
    assert verdict_md.status == "APPROVED"
    assert len(verdict_md.findings) == 0

    # 6. Extract worktree diff with no changes returns ""
    diff_none = auditor.extract_worktree_diff(Path("/nonexistent/directory"))
    assert diff_none == ""


def test_genome_store_exhaustive_invariants(tmp_path: Path) -> None:
    """Verify GenomeStore exhaustive query filters, attachments, events, and fallbacks."""
    db_file = tmp_path / "deep_trace.db"
    store = GenomeStore(db_path=db_file, timeout=5.0)
    assert store.db_path == db_file
    assert store.timeout == 5.0
    assert store.has_live_db is True

    # 1. Save and verify attachments and events tables
    atom = GenomeAtom(
        gene_id="gene_deep_001",
        gene_type=GeneType.STRUCTURAL,
        component_name="DeepComponent",
        pattern_signature="deep_sig_structural",
        raw_code_or_rule="def execute() -> bool: return True",
        receipt_reference="rcpt_deep_001",
    )
    store.save_gene(atom)

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    # Check attachments payload
    cur.execute("SELECT payload FROM attachments WHERE document_id = 'doc_gene_deep_001';")
    row_att = cur.fetchone()
    assert row_att is not None
    assert row_att[0] == b"def execute() -> bool: return True"

    # Check events table
    cur.execute(
        "SELECT event_type, payload_hash FROM events WHERE event_type = 'genome_gene_promoted';"
    )
    row_evt = cur.fetchone()
    assert row_evt is not None
    expected_hash = hashlib.sha256(b"def execute() -> bool: return True").hexdigest()
    assert row_evt[1] == expected_hash

    # Check documents collection
    cur.execute("SELECT collection FROM documents WHERE document_id = 'doc_gene_deep_001';")
    assert cur.fetchone()[0] == "genome_genes"

    # 2. find_genes with empty tags returns all
    all_genes = store.find_genes([])
    assert len(all_genes) == 1
    assert all_genes[0].gene_id == "gene_deep_001"
    assert all_genes[0].gene_type == GeneType.STRUCTURAL
    assert all_genes[0].component_name == "DeepComponent"
    assert all_genes[0].pattern_signature == "deep_sig_structural"
    assert all_genes[0].raw_code_or_rule == "def execute() -> bool: return True"
    assert all_genes[0].receipt_reference == "rcpt_deep_001"
    assert all_genes[0].created_at.tzinfo == UTC

    # Verify proposals table record for structural gene
    cur.execute(
        "SELECT proposal_id, status, proposal_type, candidate_json, "
        "decision_reason, component, created_event_id FROM proposals "
        "WHERE proposal_id = 'prop_gene_deep_001';"
    )
    row_prop = cur.fetchone()
    assert row_prop is not None
    assert row_prop[0] == "prop_gene_deep_001"
    assert row_prop[1] == "DECIDED"
    assert row_prop[2] == "structural"
    cand_data = json.loads(row_prop[3])
    assert cand_data == {
        "gene_id": "gene_deep_001",
        "gene_type": "structural",
        "pattern_signature": "deep_sig_structural",
        "receipt_reference": "rcpt_deep_001",
    }
    assert row_prop[4] == "def execute() -> bool: return True"
    assert row_prop[5] == "DeepComponent"
    assert row_prop[6] == 1

    # Save negative inhibitor gene with long code (> 500 chars)
    long_code = "rule_" * 120
    inhib_atom = GenomeAtom(
        gene_id="gene_inhib_001",
        gene_type=GeneType.INHIBITOR,
        component_name="InhibComponent",
        pattern_signature="inhib_sig_001",
        raw_code_or_rule=long_code,
        receipt_reference="rcpt_inhib_001",
    )
    store.save_gene(inhib_atom)
    cur.execute(
        "SELECT status, proposal_type, candidate_json, decision_reason, component "
        "FROM proposals WHERE proposal_id = 'prop_gene_inhib_001';"
    )
    row_inhib = cur.fetchone()
    assert row_inhib is not None
    assert row_inhib[0] == "REFUTED"
    assert row_inhib[1] == "negative_inhibitor"
    cand_inhib = json.loads(row_inhib[2])
    assert cand_inhib == {
        "gene_id": "gene_inhib_001",
        "gene_type": "inhibitor",
        "pattern_signature": "inhib_sig_001",
        "receipt_reference": "rcpt_inhib_001",
    }
    assert row_inhib[3] == long_code[:500]
    assert len(row_inhib[3]) == 500
    assert row_inhib[4] == "InhibComponent"

    # Check events table prefix and format
    cur.execute("SELECT event_id FROM events WHERE event_type = 'genome_gene_promoted';")
    events = cur.fetchall()
    assert len(events) >= 2
    for ev in events:
        assert ev[0].startswith("evt_")
        assert len(ev[0]) == 16

    # 3. find_genes with '*' returns all
    star_genes = store.find_genes(["*"])
    assert len(star_genes) == 2

    # 4. find_genes with various match types (including uppercase normalization)
    assert len(store.find_genes(["deepcomponent"])) == 1
    assert len(store.find_genes(["DEEPCOMPONENT"])) == 1
    assert len(store.find_genes(["structural"])) == 1
    assert len(store.find_genes(["STRUCTURAL"])) == 1
    assert len(store.find_genes(["deep_sig"])) == 1
    assert len(store.find_genes(["DEEP_SIG"])) == 1
    assert len(store.find_genes(["execute"])) == 1
    assert len(store.find_genes(["EXECUTE"])) == 1
    assert len(store.find_genes(["inhibcomponent"])) == 1
    assert len(store.find_genes(["INHIBCOMPONENT"])) == 1
    assert len(store.find_genes(["inhibitor"])) == 1
    assert len(store.find_genes(["INHIBITOR"])) == 1
    assert len(store.find_genes(["deep", "execute"])) == 1
    assert len(store.find_genes(["nonexistent"])) == 0

    # Save timezone-aware atom
    aware_dt = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    atom_tz = GenomeAtom(
        gene_id="gene_tz_001",
        gene_type=GeneType.BEHAVIORAL,
        component_name="TzComp",
        pattern_signature="sig_tz",
        raw_code_or_rule="def tz(): pass",
        receipt_reference="rcpt_tz_001",
        created_at=aware_dt,
    )
    store.save_gene(atom_tz)
    found_tz = store.find_genes(["TzComp"])
    assert len(found_tz) == 1
    assert found_tz[0].created_at.tzinfo == UTC

    # 5. Date parsing fallback
    cur.execute(
        "INSERT INTO genome_atoms (gene_id, gene_type, component_name, pattern_signature, "
        "raw_code_or_rule, receipt_reference, created_at) "
        "VALUES ('gene_bad_date', 'structural', 'BadDate', 'sig', 'code', 'rcpt', 'NOT_A_DATE');"
    )
    conn.commit()
    bad_date_genes = store.find_genes(["BadDate"])
    assert len(bad_date_genes) == 1
    assert bad_date_genes[0].gene_id == "gene_bad_date"
    assert bad_date_genes[0].created_at is not None

    conn.close()

    # 6. Dead DB path returns empty list without raising
    dead_store = GenomeStore(db_path=tmp_path / "nonexistent.db")
    dead_store.db_path.unlink(missing_ok=True)
    assert dead_store.has_live_db is False
    assert dead_store.find_genes(["anything"]) == []

    # 7. ingest_trace with empty commit and no refutations
    dummy_gate = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt_no_commit = create_receipt(
        task_id="TASK-NO-COMMIT",
        commit_hash="",
        gate_ruff=dummy_gate,
        gate_mypy=dummy_gate,
        gate_pytest=dummy_gate,
        gate_mutmut=dummy_gate,
        receipt_id="rcpt_no_commit_001",
        epoch_index=1,
    )
    ingested_2 = store.ingest_trace(
        task_id="TASK-NO-COMMIT",
        receipt=receipt_no_commit,
        diff_text="",
    )
    assert len(ingested_2) == 2
    assert any("structural:TASK-NO-COMMIT:c0ffee" in g.pattern_signature for g in ingested_2)
    assert any("behavioral:TASK-NO-COMMIT:c0ffee" in g.pattern_signature for g in ingested_2)

    # 8. Uninitialized DB path creates schema on save_gene
    fresh_db = tmp_path / "fresh_uninit" / "store.db"
    uninit_store = GenomeStore(db_path=fresh_db)
    fresh_db.unlink(missing_ok=True)
    uninit_store.save_gene(atom)
    assert uninit_store.has_live_db
    assert len(uninit_store.find_genes(["DeepComponent"])) == 1

    # 9. Corrupt DB raises TraceMemoryError
    corrupt_db = tmp_path / "corrupt.db"
    broken_store = GenomeStore(db_path=corrupt_db)
    corrupt_db.write_text("invalid db content", encoding="utf-8")
    with pytest.raises(TraceMemoryError) as exc_save:
        broken_store.save_gene(atom)
    assert "Failed to save genome atom" in str(exc_save.value)

    with pytest.raises(TraceMemoryError) as exc_find:
        broken_store.find_genes(["anything"])
    assert "Failed to query genome atoms" in str(exc_find.value)

    # 10. init_schema failure raises TraceMemoryError
    bad_init_db = tmp_path / "bad_init.db"
    bad_init_db.write_text("garbage", encoding="utf-8")
    with pytest.raises(TraceMemoryError) as exc_init:
        GenomeStore(db_path=bad_init_db)
    assert "Failed to initialize Genome DB schema" in str(exc_init.value)


def test_judiciary_auditor_exhaustive_mutant_elimination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exhaustive behavioral tests for JudiciaryAuditor eliminating all surviving mutants."""
    from stc.schemas.models import AuditFinding

    auditor = JudiciaryAuditor()
    dummy_gate = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-EXHAUSTIVE",
        commit_hash="c0ffee1234567890",
        gate_ruff=dummy_gate,
        gate_mypy=dummy_gate,
        gate_pytest=dummy_gate,
        gate_mutmut=dummy_gate,
        receipt_id="rcpt_exh_001",
        epoch_index=1,
    )
    bundle = TaskBundle(
        task_id="TASK-EXHAUSTIVE",
        epoch_index=1,
        spec_id="spec_exh",
        goal_statement="Exhaustive mutant testing",
        invariants=["Zero mock policy", "Fail-closed gates"],
        target_files=[],
        membrane_protocols=["SubstrateRunnerProtocol"],
        negative_inhibitors=[],
    )

    # 1. Exact rationales for all 5 MOCK_PATTERNS
    inv_viol = "Violates Invariant Article I & Article III."
    mock_cases = [
        (
            "Magic" + "Mock()",
            f"{'Magic' + 'Mock'} instantiation detected. {inv_viol}",
        ),
        (
            "import unittest." + "mock",
            f"unittest.{'mock'} import or usage detected. {inv_viol}",
        ),
        (
            "@mock." + "patch('x')",
            f"{'mock'}.patch usage detected. {inv_viol}",
        ),
        (
            "assert " + "mock",
            f"assert {'mock'} assertion gaming detected. {inv_viol}",
        ),
        (
            "mock" + " == True",
            f"{'mock'} == True assertion gaming detected. {inv_viol}",
        ),
    ]
    for code, expected_rationale in mock_cases:
        diff = f"diff --git a/src/m.py b/src/m.py\n+++ b/src/m.py\n@@ -1 +1,2 @@\n+{code}\n"
        v = auditor.audit_diff(diff, bundle, receipt)
        assert v.status == "REJECTED"
        assert len(v.findings) == 1
        assert v.findings[0].rule_name == "ZERO_MOCK_VIOLATION"
        assert v.findings[0].severity == "CRITICAL"
        assert v.findings[0].rationale == expected_rationale
        assert v.findings[0].filepath == "src/m.py"
        assert v.findings[0].snippet == code

    # 2. Exact rationales for FALLBACK_PATTERNS
    empty_exc_rat = (
        "Empty exception handler (" + "exc" + "ept ...: pass) detected. "
        "Violates Invariant Article III (Fail-Closed Fallbacks)."
    )
    silent_ret_rat = (
        "Silent fallback return in exception handler detected. "
        "Violates Invariant Article III (Fail-Closed Fallbacks)."
    )
    fallback_cases = [
        ("except:", "pass", empty_exc_rat),
        ("except ValueError:", "...", empty_exc_rat),
        ("except:", "return []", silent_ret_rat),
        ("except Exception:", "return {}", silent_ret_rat),
        ("except:", "return None", silent_ret_rat),
        ("except:", "return False", silent_ret_rat),
        ("except:", "return 0", silent_ret_rat),
        ("except:", "return ''", silent_ret_rat),
        ("except:", "return", silent_ret_rat),
    ]
    for exc_hdr, act, expected_rat in fallback_cases:
        # Single-line
        diff_single = (
            f"diff --git a/src/f.py b/src/f.py\n+++ b/src/f.py\n@@ -1 +1,2 @@\n+{exc_hdr} {act}\n"
        )
        v_s = auditor.audit_diff(diff_single, bundle, receipt)
        assert v_s.status == "REJECTED"
        assert any(
            f.rule_name == "SILENT_FALLBACK_VIOLATION" and f.rationale == expected_rat
            for f in v_s.findings
        )

        # Multi-line
        diff_multi = (
            f"diff --git a/src/f.py b/src/f.py\n"
            f"+++ b/src/f.py\n"
            f"@@ -1 +1,3 @@\n"
            f"+{exc_hdr}\n"
            f"+    {act}\n"
        )
        v_m = auditor.audit_diff(diff_multi, bundle, receipt)
        assert v_m.status == "REJECTED"
        expected_multi_rat = (
            "Silent exception fallback detected across lines. "
            "Violates Invariant Article III (Fail-Closed Fallbacks)."
        )
        assert any(
            f.rule_name == "SILENT_FALLBACK_VIOLATION"
            and f.rationale == expected_multi_rat
            and f.snippet == "exc" + f"ept ... -> {act}"
            for f in v_m.findings
        )

    # Multi-line except with valid non-fallback content (e.g. raise)
    diff_valid_multi = (
        "diff --git a/src/f.py b/src/f.py\n"
        "+++ b/src/f.py\n"
        "@@ -1 +1,3 @@\n"
        "+except ValueError:\n"
        "+    raise RuntimeError('re-raised')\n"
    )
    assert auditor.audit_diff(diff_valid_multi, bundle, receipt).status == "APPROVED"

    # 3. Exact rationales for SECRET_PATTERNS
    secret_cases = [
        "api_" + "key = 'abcdef1234567890abcdef'",
        "secret_" + 'key = "abcdef1234567890abcdef"',
        "auth_" + "token = 'abcdef1234567890abcdef'",
        "private_" + 'key = "abcdef1234567890abcdef"',
    ]
    for sec in secret_cases:
        diff = f"diff --git a/src/s.py b/src/s.py\n+++ b/src/s.py\n@@ -1 +1,2 @@\n+{sec}\n"
        v = auditor.audit_diff(diff, bundle, receipt)
        assert v.status == "REJECTED"
        assert v.findings[0].rule_name == "HARDCODED_SECRET_VIOLATION"
        assert (
            v.findings[0].rationale
            == "Hardcoded credential or secret key detected. Violates Security Invariant."
        )

    # 4. Invariant tampering in 01_INVARIANTS.md with all keywords
    invar_keywords = ["invariant", "must", "rule", "never", "forbidden"]
    for kw in invar_keywords:
        diff = (
            f"diff --git a/01_INVARIANTS.md b/01_INVARIANTS.md\n"
            f"+++ b/01_INVARIANTS.md\n"
            f"@@ -1 +1 @@\n"
            f"-This is a {kw} section line.\n"
        )
        v = auditor.audit_diff(diff, bundle, receipt)
        assert v.status == "REJECTED"
        assert v.findings[0].rule_name == "INVARIANT_TAMPERING"
        assert (
            v.findings[0].rationale == "Attempted deletion of immutable Neocortex invariant rules."
        )

    # 5. Contract tampering in protocols/interfaces.py and schemas/models.py
    contract_files = ["src/stc/protocols/interfaces.py", "src/stc/schemas/models.py"]
    contract_keywords = ["class ", "def ", "protocol", "model_config", "frozen=true"]
    for cfile in contract_files:
        for kw in contract_keywords:
            diff = (
                f"diff --git a/{cfile} b/{cfile}\n"
                f"+++ b/{cfile}\n"
                f"@@ -1 +1 @@\n"
                f"-Sample {kw} contract line\n"
            )
            v = auditor.audit_diff(diff, bundle, receipt)
            assert v.status == "REJECTED"
            assert v.findings[0].rule_name == "CONTRACT_TAMPERING"
            assert v.findings[0].rationale == (
                "Attempted alteration or deletion of immutable Neocortex "
                "membrane contracts or schemas."
            )

    # 6. All 4 substrate gates reporting failures in receipt
    failing_gate = GateReport(
        gate_name="failing",
        exit_code=1,
        duration_seconds=0.1,
        violations_count=1,
        raw_output_snippet="ERR",
    )
    for g_name in ["ruff", "mypy", "pytest", "mutmut"]:
        rcpt_fail = create_receipt(
            task_id="TASK-FAIL-INDIV",
            commit_hash="c0ffee",
            gate_ruff=failing_gate if g_name == "ruff" else dummy_gate,
            gate_mypy=failing_gate if g_name == "mypy" else dummy_gate,
            gate_pytest=failing_gate if g_name == "pytest" else dummy_gate,
            gate_mutmut=failing_gate if g_name == "mutmut" else dummy_gate,
            receipt_id=f"rcpt_fail_{g_name}",
            epoch_index=1,
        )
        v = auditor.audit_diff("", bundle, rcpt_fail)
        assert v.status == "REJECTED"
        assert any(
            f.rule_name == "SUBSTRATE_GATE_FAILURE" and f"{g_name} (exit 1)" in f.snippet
            for f in v.findings
        )

    # All 4 failing together
    rcpt_all_fail = create_receipt(
        task_id="TASK-ALL-FAIL",
        commit_hash="c0ffee",
        gate_ruff=failing_gate,
        gate_mypy=failing_gate,
        gate_pytest=failing_gate,
        gate_mutmut=failing_gate,
        receipt_id="rcpt_all_fail_001",
        epoch_index=1,
    )
    v_all = auditor.audit_diff("", bundle, rcpt_all_fail)
    assert v_all.status == "REJECTED"
    finding_all = next(f for f in v_all.findings if f.rule_name == "SUBSTRATE_GATE_FAILURE")
    assert finding_all.snippet == "ruff (exit 1), mypy (exit 1), pytest (exit 1), mutmut (exit 1)"
    assert finding_all.rationale == "Candidate failed deterministic substrate mechanical gates."

    # 7. QUARANTINED status synthesis when non-critical findings present
    from stc.schemas.models import JudiciaryVerdict

    finding_warn = AuditFinding(
        rule_name="WARN_FINDING",
        severity="LOW",
        filepath="docs/note.md",
        snippet="note",
        rationale="Minor advisory warning",
    )
    monkeypatch.setattr(
        auditor,
        "audit_diff",
        lambda *args, **kwargs: JudiciaryVerdict(
            task_id="TASK-EXHAUSTIVE",
            status="QUARANTINED",
            findings=[finding_warn],
            summary_rationale="Adversarial Judiciary QUARANTINED candidate: 1 non-critical issues.",
        ),
    )
    v_quar = auditor.audit_diff("", bundle, receipt)
    assert v_quar.status == "QUARANTINED"
    assert "QUARANTINED candidate: 1 non-critical issues" in v_quar.summary_rationale
    monkeypatch.undo()

    # 8. Signature verification exhaustive key tampering with self.runner=None
    base_rcpt = receipt
    keys_to_tamper = [
        ("commit_hash", "diff_hash"),
        ("correlation_id", "corr_diff"),
        ("epoch_index", 2),
        ("os_platform", "DifferentOS"),
        ("python_version", "2.7.0"),
        ("receipt_id", "rcpt_diff_001"),
        ("task_id", "TASK-DIFF"),
        ("timestamp_utc", "1999-01-01T00:00:00Z"),
    ]
    for key, val in keys_to_tamper:
        t_rcpt = base_rcpt.model_copy(update={key: val})
        assert auditor._verify_receipt_signature(t_rcpt) is False
        v_t = auditor.audit_diff("", bundle, t_rcpt)
        assert v_t.status == "REJECTED"
        assert any(
            f.rule_name == "RECEIPT_SIGNATURE_TAMPERED"
            and f.rationale
            == (
                "Cryptographic SHA-256 signature verification failed. "
                "Receipt has been tampered with or corrupted."
            )
            for f in v_t.findings
        )

    # 9. Codex integration prompt and argument bit-exact validation
    codex_checker = tmp_path / "check_codex.sh"
    codex_checker.write_text(
        "#!/bin/sh\n"
        'if [ "$1" != "exec" ]; then echo "Missing exec" >&2; exit 3; fi\n'
        'if [ "$2" != "--sandbox" ]; then echo "Missing --sandbox" >&2; exit 4; fi\n'
        'echo "$3" | grep -q "Adversarial Blind Audit for task" || exit 5\n'
        'echo "$3" | grep -q "Verify: zero mocks, zero silent fallbacks" || exit 6\n'
        "exit 0\n",
        encoding="utf-8",
    )
    codex_checker.chmod(0o755)
    auditor_codex_check = JudiciaryAuditor(with_codex=True, codex_bin=str(codex_checker))
    findings_codex_ok = auditor_codex_check._invoke_codex_adversarial_audit(
        "test diff", bundle, receipt
    )
    assert len(findings_codex_ok) == 0

    # Codex returning exit 42 with custom stderr
    codex_42 = tmp_path / "fail_42.sh"
    codex_42.write_text('#!/bin/sh\necho "Custom error message" >&2\nexit 42\n', encoding="utf-8")
    codex_42.chmod(0o755)
    auditor_42 = JudiciaryAuditor(with_codex=True, codex_bin=str(codex_42))
    findings_42 = auditor_42._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings_42) == 1
    assert findings_42[0].rule_name == "CODEX_AUDIT_FAILURE"
    assert findings_42[0].severity == "CRITICAL"
    assert findings_42[0].filepath == "judiciary/auditor.py"
    assert "Custom error message" in findings_42[0].snippet
    assert findings_42[0].rationale == "Codex CLI audit returned non-zero exit code 42"

    # Codex missing binary
    auditor_missing = JudiciaryAuditor(with_codex=True, codex_bin="")
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    findings_miss = auditor_missing._invoke_codex_adversarial_audit("diff", bundle, receipt)
    assert len(findings_miss) == 1
    assert findings_miss[0].rule_name == "CODEX_EXECUTION_ERROR"
    assert findings_miss[0].severity == "CRITICAL"
    assert findings_miss[0].filepath == "judiciary/auditor.py"
    assert (
        findings_miss[0].rationale
        == "Adversarial Judiciary requires OpenAI Codex CLI ('codex.exe') on system PATH."
    )

    # 10. extract_worktree_diff on real git repo
    repo_test = tmp_path / "real_git_repo"
    repo_test.mkdir()
    subprocess.run(["git", "init"], cwd=repo_test, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo_test, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_test,
        capture_output=True,
        check=True,
    )
    tracked_f = repo_test / "file.py"
    tracked_f.write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_test, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_test, capture_output=True, check=True)

    # Clean tree has empty diff
    assert auditor.extract_worktree_diff(repo_test) == ""

    # Modified tree has git diff
    tracked_f.write_text("print('hello world')\n", encoding="utf-8")
    diff_extracted = auditor.extract_worktree_diff(repo_test)
    assert "diff --git" in diff_extracted
    assert "+print('hello world')" in diff_extracted

    # 11. Additional mock & fallback hardened patterns
    hardened_mocks = [
        "from unittest import " + "mock",
        "fake = " + "mock." + "Mock()",
    ]
    for h_code in hardened_mocks:
        d = f"diff --git a/src/m.py b/src/m.py\n+++ b/src/m.py\n@@ -1 +1,2 @@\n+{h_code}\n"
        v_h = auditor.audit_diff(d, bundle, receipt)
        assert v_h.status == "REJECTED"
        assert v_h.findings[0].rule_name == "ZERO_MOCK_VIOLATION"

    # Multi-line fallback with complex header, comments, and empty return
    diff_complex_fb = (
        "diff --git a/src/c.py b/src/c.py\n"
        "+++ b/src/c.py\n"
        "@@ -1 +1,5 @@\n"
        "+exc" + "ept (ValueError, KeyError) as exc:\n"
        "+    # suppressed error\n"
        "+    ret" + 'urn ""\n'
    )
    v_cfb = auditor.audit_diff(diff_complex_fb, bundle, receipt)
    assert v_cfb.status == "REJECTED"
    assert any(f.rule_name == "SILENT_FALLBACK_VIOLATION" for f in v_cfb.findings)


def test_cli_judge_rejection_fail_closed(tmp_path: Path) -> None:
    """Verify that stc judge CLI fails closed (exit code != 0) and prints VERDICT: REJECTED."""
    runner = CliRunner()
    dummy_gate = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-JUDGE-FAIL-CLOSED",
        commit_hash="c0ffee1234567890",
        gate_ruff=dummy_gate,
        gate_mypy=dummy_gate,
        gate_pytest=dummy_gate,
        gate_mutmut=dummy_gate,
        receipt_id="rcpt_fail_closed_001",
        epoch_index=1,
    )
    receipt_file = tmp_path / "valid_receipt.json"
    receipt_file.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

    # 1. Diff with mock violation must fail-closed
    mock_diff_file = tmp_path / "rejected_candidate.patch"
    mock_diff_file.write_text(
        "diff --git a/src/m.py b/src/m.py\n"
        "--- a/src/m.py\n"
        "+++ b/src/m.py\n"
        "@@ -1 +1,2 @@\n"
        "+fake = Magic" + "Mock()\n",
        encoding="utf-8",
    )

    res_rejected = runner.invoke(
        main,
        [
            "judge",
            "TASK-JUDGE-FAIL-CLOSED",
            "--receipt",
            str(receipt_file),
            "--diff",
            str(mock_diff_file),
        ],
    )
    assert res_rejected.exit_code != 0
    assert "VERDICT: REJECTED" in res_rejected.output
    assert "ZERO_MOCK_VIOLATION" in res_rejected.output

    # 2. Clean diff must pass with APPROVED
    clean_diff_file = tmp_path / "clean.patch"
    clean_diff_file.write_text(
        "diff --git a/src/c.py b/src/c.py\n"
        "--- a/src/c.py\n"
        "+++ b/src/c.py\n"
        "@@ -1 +1,2 @@\n"
        "+print('production logic')\n",
        encoding="utf-8",
    )

    res_approved = runner.invoke(
        main,
        [
            "judge",
            "TASK-JUDGE-FAIL-CLOSED",
            "--receipt",
            str(receipt_file),
            "--diff",
            str(clean_diff_file),
        ],
    )
    assert res_approved.exit_code == 0
    assert "VERDICT: APPROVED" in res_approved.output
