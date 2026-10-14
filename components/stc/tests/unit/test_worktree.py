"""Unit tests for Morphogenetic Cellular Worktree Manager & Worker Dispatch (Stage 4).

Verifies:
- WorktreeManagerProtocol & WorkerProtocol conformance
- Isolated branch (feature/stc-{id}-e{epoch}) and directory (worktrees/stc-{id}) allocation
- Lease collision protection (WorktreeLeaseActiveError)
- TTL lifecycle: Leased -> Expired -> Quarantined transition with refutation recording
- Resuming requires a brand-new lease record, never silent reuse
- Worktree release and purge (branch and directory cleanup)
- Accurate git diff extraction
- Chaperone worker confinement enforcement (static traversal & dynamic write fail-closed)
- Notary custody report generation with SHA-256 hashes
- Orchestrator dispatch across WorkerProtocol (orchestrator never shells CLIs directly)
- Exit Gate: lease -> commit -> gates -> purge cycle leaves main branch completely untouched!
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from stc.cli import main
from stc.core.errors import WorktreeError, WorktreeLeaseActiveError
from stc.orchestrator.dispatch import (
    ChaperoneWorker,
    ConfinementViolationError,
    OrchestratorDispatcher,
    dispatch_worker,
)
from stc.protocols.interfaces import WorkerProtocol, WorktreeManagerProtocol
from stc.schemas.models import (
    FileTarget,
    TaskBundle,
    WorktreeLease,
)
from stc.substrate.runner import SubstrateRunner
from stc.worktree.manager import WorktreeManager


@pytest.fixture
def real_git_repo(tmp_path: Path) -> Path:
    """Fixture creating an isolated, initialized real Git repository with initial commit on main."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "stc-worker@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "STC Worker"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo, check=True, capture_output=True)

    # Initial structure on main
    (repo / "README.md").write_text("# Main Repository\n", encoding="utf-8")
    (repo / ".gitignore").write_text("worktrees/\nartifacts/\n", encoding="utf-8")
    src_dir = repo / "src" / "stc"
    src_dir.mkdir(parents=True, exist_ok=True)
    proto_dir = src_dir / "protocols"
    proto_dir.mkdir(parents=True, exist_ok=True)
    (proto_dir / "interfaces.py").write_text("# protocols\n", encoding="utf-8")
    schemas_dir = src_dir / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    (schemas_dir / "models.py").write_text("# models\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit on main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _create_sample_bundle(task_id: str, targets: list[FileTarget] | None = None) -> TaskBundle:
    """Helper to create a valid minimal TaskBundle for worker testing."""
    return TaskBundle(
        task_id=task_id,
        epoch_index=1,
        spec_id="spec_worktree_test",
        goal_statement="Test worker confinement and dispatch",
        invariants=["No contamination of main"],
        target_files=targets or [FileTarget(path="src/module.py", action="create")],
        membrane_protocols=["WorkerProtocol"],
        negative_inhibitors=[],
    )


def test_protocols_runtime_checkable(real_git_repo: Path) -> None:
    """Verify that WorktreeManager and ChaperoneWorker conform to runtime-checkable Protocols."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    assert isinstance(mgr, WorktreeManagerProtocol)

    worker = ChaperoneWorker()
    assert isinstance(worker, WorkerProtocol)


def test_worktree_allocation_isolated_branch_and_directory(real_git_repo: Path) -> None:
    """Verify worktree allocation creates physical directory and isolated branch."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-WT-001", base_branch="main")

    assert lease.task_id == "TASK-WT-001"
    assert lease.branch_name == "feature/stc-task-wt-001-e1"
    assert lease.is_active is True
    assert lease.expires_at > lease.leased_at

    wt_path = Path(lease.worktree_path)
    assert wt_path.is_dir()
    assert mgr._leases_file.is_file()

    # Verify clean git status in worktree
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=wt_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res.stdout.strip() == ""


def test_worktree_allocation_normalization_and_custom_options(real_git_repo: Path) -> None:
    """Verify task_id normalization avoids duplicate prefixes, and supports custom branch/epoch."""
    mgr = WorktreeManager(repo_root=real_git_repo)

    # STC-001 should normalize to 001
    lease = mgr.allocate_lease(task_id="STC-001", base_branch="main", epoch=2)
    assert lease.branch_name == "feature/stc-001-e2"
    assert lease.worktree_path.endswith("stc-001")
    mgr.release_lease(lease, purge=True)

    # Explicit custom branch
    lease_custom = mgr.allocate_lease(
        task_id="TASK-002",
        branch="feature/custom-branch",
        epoch=3,
    )
    assert lease_custom.branch_name == "feature/custom-branch"
    mgr.release_lease(lease_custom, purge=True)


def test_worktree_empty_task_id_rejected(real_git_repo: Path) -> None:
    """Verify that an empty or whitespace-only task_id raises WorktreeError."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    with pytest.raises(WorktreeError, match="task_id must be a non-empty string"):
        mgr.allocate_lease(task_id="   ")


def test_worktree_lease_collision_raises_active_error(real_git_repo: Path) -> None:
    """Verify attempting to lease an already active worktree raises WorktreeLeaseActiveError."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-COLLISION", base_branch="main")

    with pytest.raises(WorktreeLeaseActiveError, match="Worktree lease already active"):
        mgr.allocate_lease(task_id="TASK-COLLISION", base_branch="main")

    mgr.release_lease(lease, purge=True)


def test_worktree_ttl_expiry_path_leased_expired_quarantined(real_git_repo: Path) -> None:
    """Verify the explicit Leased -> Expired -> Quarantined transition on TTL expiry."""
    mgr = WorktreeManager(repo_root=real_git_repo, ttl_seconds=1)
    lease = mgr.allocate_lease(task_id="TASK-TTL-EXP", base_branch="main")

    # Manually backdate expires_at to simulate TTL lapse
    records = mgr._load_leases()
    norm_id = mgr._normalize_task_id("TASK-TTL-EXP")
    past_time = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    records[norm_id]["expires_at"] = past_time
    mgr._save_leases(records)

    # Trigger TTL check
    quarantined = mgr.check_ttl()
    assert len(quarantined) == 1
    assert quarantined[0]["status"] == "QUARANTINED"
    assert quarantined[0]["is_active"] is False
    assert quarantined[0]["refutation_record"] is not None
    assert "TTL lapsed" in quarantined[0]["refutation_record"]["reason"]

    # Verify worktree is frozen for inspection with .quarantined.json
    wt_path = Path(lease.worktree_path)
    quarantine_file = wt_path / ".quarantined.json"
    assert quarantine_file.is_file()
    q_data = json.loads(quarantine_file.read_text(encoding="utf-8"))
    assert q_data["status"] == "QUARANTINED"

    # Inactive leases list should no longer include this lease
    active_leases = mgr.list_leases()
    assert not any(lease_item.task_id == "TASK-TTL-EXP" for lease_item in active_leases)

    # Resuming requires a brand-new lease record, never silent reuse
    new_lease = mgr.allocate_lease(task_id="TASK-TTL-EXP", base_branch="main")
    assert new_lease.lease_id != lease.lease_id
    assert new_lease.is_active is True
    assert Path(new_lease.worktree_path).is_dir()
    assert not (Path(new_lease.worktree_path) / ".quarantined.json").exists()

    mgr.release_lease(new_lease, purge=True)


def test_worktree_quarantine_manual(real_git_repo: Path) -> None:
    """Verify manual quarantine lease transition."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-MANUAL-Q", base_branch="main")

    rec = mgr.quarantine_lease(lease, reason="Circuit breaker tripped by Gate 3")
    assert rec["status"] == "QUARANTINED"
    assert rec["is_active"] is False
    assert rec["refutation_record"]["reason"] == "Circuit breaker tripped by Gate 3"

    wt_path = Path(lease.worktree_path)
    assert (wt_path / ".quarantined.json").is_file()
    mgr.release_lease(lease, purge=True)


def test_worktree_release_non_purge(real_git_repo: Path) -> None:
    """Verify releasing without purge removes worktree directory but keeps git branch."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-NON-PURGE", base_branch="main")
    wt_path = Path(lease.worktree_path)
    branch_name = lease.branch_name

    mgr.release_lease(lease, purge=False)
    assert not wt_path.exists()

    # Branch should still exist in git
    res = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
        cwd=real_git_repo,
        capture_output=True,
        check=False,
    )
    assert res.returncode == 0

    # Cleanup branch
    subprocess.run(["git", "branch", "-D", branch_name], cwd=real_git_repo, check=True)


def test_worktree_release_and_purge(real_git_repo: Path) -> None:
    """Verify releasing with purge removes directory and deletes the git branch."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-PURGE", base_branch="main")
    wt_path = Path(lease.worktree_path)
    branch_name = lease.branch_name

    mgr.release_lease(lease, purge=True)
    assert not wt_path.exists()

    # Branch should be pruned/deleted
    res = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
        cwd=real_git_repo,
        capture_output=True,
        check=False,
    )
    assert res.returncode != 0


def test_worktree_release_idempotent(real_git_repo: Path) -> None:
    """Verify releasing an already cleaned or non-existent worktree does not raise error."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    res = mgr.release_by_task_id("TASK-NON-EXISTENT", purge=True)
    assert res["status"] == "RELEASED"
    assert res["cleaned_now"] is False


def test_worktree_get_diff_committed_and_uncommitted(real_git_repo: Path) -> None:
    """Verify get_diff captures both committed changes on branch and uncommitted working changes."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-DIFF", base_branch="main")
    wt = Path(lease.worktree_path)

    # 1. Committed change
    (wt / "feature.py").write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.py"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "add feature.py"], cwd=wt, check=True)

    # 2. Uncommitted change
    (wt / "README.md").write_text("# Updated Readme\n", encoding="utf-8")

    diff = mgr.get_diff(lease)
    assert "diff --git" in diff
    assert "feature.py" in diff
    assert "def hello()" in diff
    assert "Updated Readme" in diff

    mgr.release_lease(lease, purge=True)


def test_chaperone_worker_confinement_root(real_git_repo: Path) -> None:
    """Verify confinement_root returns resolved worktree path."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-ROOT", base_branch="main")
    worker = ChaperoneWorker()

    assert worker.confinement_root(lease) == Path(lease.worktree_path).resolve()
    mgr.release_lease(lease, purge=True)


def test_chaperone_worker_membrane_verification(real_git_repo: Path) -> None:
    """Verify N11 membrane check fails closed if upstream interfaces or models are missing."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-MEMBRANE", base_branch="main")
    wt = Path(lease.worktree_path)

    worker = ChaperoneWorker(enforce_membrane=True)
    # Both interfaces.py and models.py exist in real_git_repo
    assert worker.prove_membrane(lease) is True

    # Remove models.py to simulate broken membrane
    (wt / "src" / "stc" / "schemas" / "models.py").unlink()
    assert worker.prove_membrane(lease) is False

    bundle = _create_sample_bundle("TASK-MEMBRANE")
    with pytest.raises(WorktreeError, match="Membrane verification failed"):
        worker.dispatch(bundle, lease)

    mgr.release_lease(lease, purge=True)


def test_chaperone_worker_static_confinement_violation_fails_closed(
    real_git_repo: Path,
) -> None:
    """Verify target file path attempting directory traversal outside root fails closed."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-TRAVERSAL", base_branch="main")
    worker = ChaperoneWorker(enforce_membrane=False)

    malicious_target = FileTarget(path="../../outside_secret.txt", action="modify")
    bundle = _create_sample_bundle("TASK-TRAVERSAL", targets=[malicious_target])

    with pytest.raises(ConfinementViolationError, match="escapes confinement root"):
        worker.dispatch(bundle, lease)

    mgr.release_lease(lease, purge=True)


def test_chaperone_worker_dynamic_confinement_violation_fails_closed(
    real_git_repo: Path,
) -> None:
    """Verify worker attempting to write outside confinement root fails closed."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-BREACH", base_branch="main")

    def rogue_worker(bundle: TaskBundle, root: Path) -> None:
        # Deliberately attempt write outside confinement root
        escaped_file = root.parent / "unauthorized_escape.txt"
        escaped_file.write_text("breach!", encoding="utf-8")

    worker = ChaperoneWorker(worker_fn=rogue_worker, enforce_membrane=False)
    bundle = _create_sample_bundle("TASK-BREACH")

    with pytest.raises(ConfinementViolationError, match="Worker breached confinement"):
        worker.dispatch(bundle, lease)

    # Verify unauthorized file was cleaned up
    assert not (Path(lease.worktree_path).parent / "unauthorized_escape.txt").exists()
    mgr.release_lease(lease, purge=True)


def test_chaperone_worker_notary_custody_report(real_git_repo: Path) -> None:
    """Verify Chaperone generates notary custody report with SHA-256 hashes for modified files."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-NOTARY", base_branch="main")

    def legitimate_worker(bundle: TaskBundle, root: Path) -> None:
        code_file = root / "src" / "stc" / "auth.py"
        code_file.write_text("AUTH_TOKEN = 'secret'\n", encoding="utf-8")

    worker = ChaperoneWorker(worker_fn=legitimate_worker, enforce_membrane=False)
    bundle = _create_sample_bundle("TASK-NOTARY")

    result_json = worker.dispatch(bundle, lease)
    report = json.loads(result_json)

    assert report["lease_id"] == lease.lease_id
    assert report["task_id"] == "TASK-NOTARY"
    assert report["notary_verified"] is True
    assert len(report["modified_files"]) == 1
    assert report["modified_files"][0]["path"] == "src/stc/auth.py"
    assert len(report["modified_files"][0]["sha256"]) == 64

    mgr.release_lease(lease, purge=True)


def test_orchestrator_dispatch_across_worker_protocol(real_git_repo: Path) -> None:
    """Verify Orchestrator dispatches strictly across WorkerProtocol without shelling CLIs."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-ORCH", base_branch="main")

    class ConformingTestWorker:
        def confinement_root(self, lease_arg: WorktreeLease) -> Path:
            return Path(lease_arg.worktree_path).resolve()

        def dispatch(self, bundle_arg: TaskBundle, lease_arg: WorktreeLease) -> str:
            return json.dumps({"dispatched": True, "task_id": bundle_arg.task_id})

    worker = ConformingTestWorker()
    assert isinstance(worker, WorkerProtocol)

    bundle = _create_sample_bundle("TASK-ORCH")
    res = dispatch_worker(bundle, lease, worker)
    parsed = json.loads(res)
    assert parsed["dispatched"] is True
    assert parsed["task_id"] == "TASK-ORCH"

    # Test OrchestratorDispatcher class
    dispatcher = OrchestratorDispatcher(worker=worker)
    res2 = dispatcher.dispatch(bundle, lease)
    assert json.loads(res2)["dispatched"] is True

    # Test rejection of non-WorkerProtocol
    class InvalidWorker:
        pass

    with pytest.raises(TypeError, match="Expected WorkerProtocol implementation"):
        dispatch_worker(bundle, lease, InvalidWorker())  # type: ignore[arg-type]

    mgr.release_lease(lease, purge=True)


def test_worktree_lease_commit_gates_purge_cycle_leaves_main_untouched(
    real_git_repo: Path,
) -> None:
    """STAGE 4 EXIT GATE: lease -> commit -> gates -> purge cycle leaves main branch untouched.

    Verifies complete cellular morphogenesis lifecycle:
    1. Snapshot pristine state of main branch (HEAD commit and clean working tree).
    2. Allocate leased worktree for task.
    3. Modify files and commit on isolated feature branch in worktree.
    4. Execute substrate hard quality gates against the leased worktree.
    5. Purge the worktree lease.
    6. Verify main branch is 100% untouched and uncontaminated.
    """
    repo = real_git_repo

    # 1. Snapshot pristine main state
    res_main_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    main_head_commit = res_main_head.stdout.strip()

    res_main_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_main_status.stdout.strip() == "", "Main repo must start completely clean"

    # 2. Allocate leased worktree
    mgr = WorktreeManager(repo_root=repo)
    lease = mgr.allocate_lease(task_id="TASK-STAGE4-EXIT", base_branch="main")
    wt = Path(lease.worktree_path)
    assert wt.is_dir()
    assert lease.branch_name == "feature/stc-task-stage4-exit-e1"

    # 3. Modify files and commit in leased worktree
    (wt / "service.py").write_text(
        'def add(a: int, b: int) -> int:\n    """Add two integers."""\n    return a + b\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "service.py"], cwd=wt, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: implement service.py in isolated worktree"],
        cwd=wt,
        check=True,
    )

    # Verify worktree branch is ahead of main
    res_wt_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=wt,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_wt_head.stdout.strip() != main_head_commit

    # 4. Execute substrate quality gates inside worktree (without mutmut for unit isolation)
    runner = SubstrateRunner(run_mutmut=False)
    receipt = runner.execute_gates(
        worktree_path=wt,
        task_id="TASK-STAGE4-EXIT",
        epoch_index=1,
    )
    assert receipt.receipt_id.startswith("rcpt_")
    assert receipt.commit_hash == res_wt_head.stdout.strip()

    # 5. Purge the worktree lease
    mgr.release_lease(lease, purge=True)
    assert not wt.exists()

    # 6. VERIFY MAIN IS 100% UNTOUCHED
    # Current branch in main repo
    res_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_branch.stdout.strip() == "main"

    # Current HEAD in main repo must be identical to snapshot
    res_curr_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_curr_head.stdout.strip() == main_head_commit, "Main HEAD commit was contaminated!"

    # Working tree in main repo must be completely clean
    res_curr_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_curr_status.stdout.strip() == "", "Main working directory was contaminated!"

    # Feature branch must no longer exist
    res_feature_branch = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/heads/feature/stc-task-stage4-exit-e1"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert res_feature_branch.returncode != 0, "Feature branch was not purged!"


def test_chaperone_worker_confinement_violation_outside_worktrees_in_main_repo(
    real_git_repo: Path,
) -> None:
    """Verify that a rogue worker writing to the main repo outside worktrees fails closed."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-BREACH-MAIN", base_branch="main")

    def rogue_worker(bundle: TaskBundle, root: Path) -> None:
        # Deliberately attempt write to main repo outside of worktrees/ directory
        (real_git_repo / "main_tampered.txt").write_text("breach!", encoding="utf-8")

    worker = ChaperoneWorker(worker_fn=rogue_worker, enforce_membrane=False)
    bundle = _create_sample_bundle("TASK-BREACH-MAIN")

    with pytest.raises(ConfinementViolationError, match="Worker breached confinement"):
        worker.dispatch(bundle, lease)

    # Ensure the unauthorized file was cleaned up from the main repo
    assert not (real_git_repo / "main_tampered.txt").exists()
    mgr.release_lease(lease, purge=True)


def test_worktree_get_diff_untracked_file(real_git_repo: Path) -> None:
    """Verify that newly created untracked files are captured by get_diff via intent-to-add."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-UNTRACKED-DIFF", base_branch="main")
    wt = Path(lease.worktree_path)

    # Create a new file without running git add
    (wt / "new_untracked.py").write_text(
        "def untracked() -> int:\n    return 42\n", encoding="utf-8"
    )

    diff = mgr.get_diff(lease)
    assert "new_untracked.py" in diff
    assert "def untracked()" in diff
    assert "+    return 42" in diff

    mgr.release_lease(lease, purge=True)


def test_worktree_list_excludes_main_repo(real_git_repo: Path) -> None:
    """Verify that list_active_leases_for_cli never returns the main repository root."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    # When no leases allocated:
    entries = mgr.list_active_leases_for_cli()
    assert entries == [], "Repository root must not be listed as an active worktree lease"

    # Allocate one lease
    lease = mgr.allocate_lease(task_id="TASK-LIST-CHECK", base_branch="main")
    entries_after = mgr.list_active_leases_for_cli()
    assert len(entries_after) == 1
    assert Path(entries_after[0]["worktree"]).resolve() == Path(lease.worktree_path).resolve()
    assert entries_after[0]["branch"] == "feature/stc-task-list-check-e1"

    mgr.release_lease(lease, purge=True)
    assert mgr.list_active_leases_for_cli() == []


def test_worktree_detect_repo_root_inside_worktree(
    real_git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify WorktreeManager resolves true repo root when called inside worktree."""
    monkeypatch.delenv("STC_WORKTREE_ROOT", raising=False)
    mgr_parent = WorktreeManager(repo_root=real_git_repo)
    lease = mgr_parent.allocate_lease(task_id="TASK-NESTED-DETECT", base_branch="main")
    wt = Path(lease.worktree_path)

    # Instantiate manager without repo_root from inside worktree
    import os

    old_cwd = Path.cwd()
    try:
        os.chdir(wt)
        mgr_inside = WorktreeManager()
        assert mgr_inside.repo_root == real_git_repo.resolve()
        assert mgr_inside.worktree_root == (real_git_repo / "worktrees").resolve()
    finally:
        os.chdir(old_cwd)

    mgr_parent.release_lease(lease, purge=True)


def test_worktree_concurrent_multi_process_allocation(real_git_repo: Path) -> None:
    """Verify concurrent allocations do not corrupt .leases.json thanks to file locking."""
    mgr = WorktreeManager(repo_root=real_git_repo)

    def allocate_task(task_num: int) -> str:
        local_mgr = WorktreeManager(repo_root=real_git_repo)
        lease_entry = local_mgr.allocate_lease(task_id=f"TASK-CONC-{task_num}")
        return lease_entry.lease_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(allocate_task, i) for i in range(4)]
        lease_ids = [f.result() for f in futures]

    assert len(set(lease_ids)) == 4
    active_leases = mgr.list_leases()
    assert len(active_leases) == 4

    for i in range(4):
        mgr.release_by_task_id(f"TASK-CONC-{i}", purge=True)


def test_dispatch_worker_expired_lease_raises_error(real_git_repo: Path) -> None:
    """Verify dispatch_worker fails closed if the lease has expired."""
    mgr = WorktreeManager(repo_root=real_git_repo, ttl_seconds=1)
    lease = mgr.allocate_lease(task_id="TASK-EXP-DISPATCH", base_branch="main")

    # Backdate expires_at
    expired_lease = WorktreeLease(
        lease_id=lease.lease_id,
        task_id=lease.task_id,
        branch_name=lease.branch_name,
        worktree_path=lease.worktree_path,
        leased_at=lease.leased_at - timedelta(seconds=100),
        expires_at=datetime.now(UTC) - timedelta(seconds=50),
        is_active=True,
    )

    worker = ChaperoneWorker(enforce_membrane=False)
    bundle = _create_sample_bundle("TASK-EXP-DISPATCH")

    with pytest.raises(WorktreeError, match="Cannot dispatch worker to inactive or expired lease"):
        dispatch_worker(bundle, expired_lease, worker)

    mgr.release_lease(lease, purge=True)


def test_worktree_safety_guard_refuses_repo_root(real_git_repo: Path) -> None:
    """Verify that operations refuse to touch or remove the repository root."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    # 1. Refuse path traversals in task_id
    with pytest.raises(WorktreeError, match="Invalid task_id"):
        mgr.allocate_lease("..")

    # 2. Refuse to release lease targeting repository root
    dangerous_lease = WorktreeLease(
        lease_id="lease_danger",
        task_id="danger",
        branch_name="main",
        worktree_path=str(real_git_repo),
        leased_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(seconds=60),
        is_active=True,
    )
    with pytest.raises(WorktreeError, match="Refusing to remove or delete repository root"):
        mgr.release_lease(dangerous_lease, purge=True)


def test_chaperone_worker_disallowed_command_rejected(real_git_repo: Path) -> None:
    """Verify worker_cmd binary not in allowed_tools is rejected with WorktreeError."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-DISALLOWED-TOOL", base_branch="main")

    worker = ChaperoneWorker(
        worker_cmd=["curl", "https://example.com"],
        enforce_membrane=False,
        allowed_tools=("agy", "aider", "dsh"),
    )
    bundle = _create_sample_bundle("TASK-DISALLOWED-TOOL")

    with pytest.raises(WorktreeError, match="is not in allowed tools"):
        worker.dispatch(bundle, lease)

    mgr.release_lease(lease, purge=True)


def test_cli_worktree_lease_epoch_option(real_git_repo: Path) -> None:
    """Verify CLI stc worktree lease --epoch 2 creates branch with -e2."""
    runner = CliRunner()
    import os

    old_cwd = Path.cwd()
    try:
        os.chdir(real_git_repo)
        res = runner.invoke(main, ["worktree", "lease", "TASK-CLI-EPOCH", "--epoch", "2"])
        assert res.exit_code == 0
        assert "feature/stc-task-cli-epoch-e2" in res.output

        mgr = WorktreeManager(repo_root=real_git_repo)
        active = mgr.list_leases()
        assert any(item.branch_name == "feature/stc-task-cli-epoch-e2" for item in active)
        mgr.release_by_task_id("TASK-CLI-EPOCH", purge=True)
    finally:
        os.chdir(old_cwd)


def test_worktree_get_diff_with_advancing_main(real_git_repo: Path) -> None:
    """Verify get_diff accurately isolates branch diff even when main branch has new commits."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-DIFF-ADV", base_branch="main")
    wt = Path(lease.worktree_path)

    # 1. Commit on feature branch in worktree
    (wt / "feature_code.py").write_text(
        "def branch_feature() -> int:\n    return 100\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "feature_code.py"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "feat: branch commit"], cwd=wt, check=True)

    # 2. Add a commit to main in the main repo
    (real_git_repo / "main_unrelated.txt").write_text("advance on main\n", encoding="utf-8")
    subprocess.run(["git", "add", "main_unrelated.txt"], cwd=real_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "chore: advance main"], cwd=real_git_repo, check=True)

    # 3. Extract diff
    diff = mgr.get_diff(lease)
    assert "feature_code.py" in diff
    assert "branch_feature" in diff
    # Crucial: main_unrelated.txt must NOT appear in feature branch diff!
    assert "main_unrelated.txt" not in diff

    mgr.release_lease(lease, purge=True)


def test_worktree_lock_timeout_raises_worktree_error(real_git_repo: Path) -> None:
    """Verify that lock acquisition timeout fails closed by raising WorktreeError."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    mgr.worktree_root.mkdir(parents=True, exist_ok=True)

    import fcntl

    with mgr._lock_file.open("a+b") as lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Attempting to acquire lock with short timeout must raise WorktreeError
        with (
            pytest.raises(WorktreeError, match=r"Timeout.*acquiring lease lock"),
            mgr._lock_leases(timeout=0.05),
        ):
            pass
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)


def test_worktree_release_fallback_cleans_branch_without_record(real_git_repo: Path) -> None:
    """Verify release_by_task_id discovers true branch from git and purges it when unrecorded."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-UNRECORDED", epoch=2)
    branch_name = lease.branch_name  # feature/stc-task-unrecorded-e2

    # Remove the record from .leases.json to simulate missing record
    records = mgr._load_leases()
    del records[mgr._normalize_task_id("TASK-UNRECORDED")]
    mgr._save_leases(records)

    # Purge without record
    res = mgr.release_by_task_id("TASK-UNRECORDED", purge=True)
    assert res["status"] == "RELEASED"
    assert res["branch_name"] == branch_name

    # Confirm branch is gone from git
    check_branch = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
        cwd=real_git_repo,
        capture_output=True,
        check=False,
    )
    assert check_branch.returncode != 0


def test_chaperone_worker_missing_binary_raises_worktree_error(real_git_repo: Path) -> None:
    """Verify missing worker binary raises WorktreeError instead of unhandled FileNotFoundError."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-MISSING-BIN")

    worker = ChaperoneWorker(
        worker_cmd=["non_existent_binary_xyz123"],
        enforce_membrane=False,
        allowed_tools=("non_existent_binary_xyz123",),
    )
    bundle = _create_sample_bundle("TASK-MISSING-BIN")

    with pytest.raises(WorktreeError, match="not found on system PATH"):
        worker.dispatch(bundle, lease)

    mgr.release_lease(lease, purge=True)


def test_chaperone_worker_dynamic_confinement_catches_directory_creation(
    real_git_repo: Path,
) -> None:
    """Verify that a rogue worker creating a directory outside confinement root fails closed."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    lease = mgr.allocate_lease(task_id="TASK-DIR-BREACH")

    def rogue_dir_worker(bundle: TaskBundle, root: Path) -> None:
        rogue_dir = root.parent / "unauthorized_rogue_dir"
        rogue_dir.mkdir(exist_ok=True)

    worker = ChaperoneWorker(worker_fn=rogue_dir_worker, enforce_membrane=False)
    bundle = _create_sample_bundle("TASK-DIR-BREACH")

    with pytest.raises(ConfinementViolationError, match="Worker breached confinement"):
        worker.dispatch(bundle, lease)

    # Verify rogue directory was cleaned up
    assert not (Path(lease.worktree_path).parent / "unauthorized_rogue_dir").exists()
    mgr.release_lease(lease, purge=True)


def test_worktree_invalid_task_id_characters_rejected(real_git_repo: Path) -> None:
    """Verify task_ids with spaces, colons, or illegal characters are rejected."""
    mgr = WorktreeManager(repo_root=real_git_repo)
    for invalid_id in [
        "task with space",
        "task:colon",
        "task~tilde",
        "task^caret",
        "task?mark",
        "task*star",
        ".lock",
    ]:
        with pytest.raises(WorktreeError, match="Invalid task_id"):
            mgr.allocate_lease(invalid_id)


def test_worktree_ttl_transition_history_recorded(real_git_repo: Path) -> None:
    """Verify explicit transition history Leased -> Expired -> Quarantined is recorded."""
    mgr = WorktreeManager(repo_root=real_git_repo, ttl_seconds=1)
    mgr.allocate_lease(task_id="TASK-HIST", base_branch="main")

    records = mgr._load_leases()
    norm_id = mgr._normalize_task_id("TASK-HIST")
    records[norm_id]["expires_at"] = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    mgr._save_leases(records)

    quarantined = mgr.check_ttl()
    assert len(quarantined) == 1
    assert quarantined[0]["transition_history"] == ["LEASED", "EXPIRED", "QUARANTINED"]
    assert "expired_at" in quarantined[0]

    mgr.release_by_task_id("TASK-HIST", purge=True)
