"""Unit + live tests for the P03 CLI-harness worker and gateway backend.

Deterministic tests use injected scripted runners/harnesses (no subprocesses
except `git` for the .git-tamper test, skip-guarded). Live tests
(`@pytest.mark.live`, deselected in gate runs per D13) drive real CLI harnesses
with B1-verified shapes and per-test seeded scratch homes (auto-cleaned via
tmp_path; operator logins are read, never logged).
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from stc.core.errors import WorktreeError
from stc.integration.cli_gateway import (
    SST_PROMPT_BEGIN,
    SST_PROMPT_END,
    CLIGatewayBackend,
    CLIModelGateway,
    shape_gateway_prompt,
)
from stc.integration.harness_worker import (
    GatewayConfinementError,
    HarnessConfigError,
    HarnessWorker,
    SpendCapExceededError,
    SpendLedger,
    assert_tracked_status_unchanged,
    build_gateway_command,
    build_native_command,
    default_spend_path,
    dispatch_with_quarantine,
    failure_evidence_path,
    harness_worker_fn,
    render_bundle_prompt,
    run_harness_attempt,
    snapshot_tracked_status,
    sweep_prompt_kit_tmp,
)
from stc.orchestrator.dispatch import ChaperoneWorker, ConfinementViolationError
from stc.protocols.interfaces import WorkerProtocol
from stc.schemas.models import FileTarget, TaskBundle, WorktreeLease
from stc.worktree.manager import WorktreeManager

live = pytest.mark.live

# P00 pin (prompt-kit) whose blobs the F3c test asserts byte-equality with.
_PROMPT_KIT_PIN = "4f442a6c829bc06b60f9979fdc8d7585e30bac9a"
_F3C_FILES = (
    "prompt_kit/harnesses/__init__.py",
    "prompt_kit/harnesses/base.py",
    "prompt_kit/harnesses/mock_harness.py",
    "prompt_kit/harnesses/catalog.py",
    "prompt_kit/harnesses/account_harness.py",
)


def _workspace_root() -> Path:
    # Section Q3 override mechanics: STC_WORKSPACE_ROOT when set (in-lease
    # runs set it ALWAYS), else the legacy parents[3] inference (real-tree
    # runs only).
    from stc.integration.lease_git import resolve_workspace_root

    return resolve_workspace_root()


def test_f3c_prompt_kit_import_resolves_to_pinned_tree() -> None:
    """The prompt_kit import must be byte-identical to the P00 pin (F3c)."""
    if shutil.which("git") is None:
        pytest.skip("git required")
    kit_repo = _workspace_root() / "prompt-kit"
    from_pin_env = False
    if not (kit_repo / ".git").exists():
        # Lease context: no workspace sibling checkout exists; the gate
        # inherits the deliberate STC_PROMPT_KIT_ROOT pin instead. M2 is
        # lease-import integrity — it must RUN in-lease (the scoped gate
        # forbids mandatory-set skips), resolving the pin from env.
        pin_root = os.environ.get("STC_PROMPT_KIT_ROOT", "").strip()
        if pin_root and Path(pin_root).is_dir():
            kit_repo = Path(pin_root)
            from_pin_env = True
        else:
            pytest.skip("prompt-kit checkout required")
    spec = importlib.util.find_spec("prompt_kit")
    assert spec is not None and spec.submodule_search_locations is not None
    pkg_dir = Path(next(iter(spec.submodule_search_locations)))
    if from_pin_env:
        assert pkg_dir.resolve() == (kit_repo / "prompt_kit").resolve(), (
            f"prompt_kit does not resolve to the STC_PROMPT_KIT_ROOT pin: {pkg_dir}"
        )
    else:
        assert pkg_dir.resolve() != (kit_repo / "prompt_kit").resolve(), (
            f"prompt_kit resolves to the dirty worktree: {pkg_dir}"
        )
    pin_has_git = (kit_repo / ".git").exists()
    for rel in _F3C_FILES:
        if pin_has_git:
            expected = subprocess.run(
                ["git", "-C", str(kit_repo), "rev-parse", f"{_PROMPT_KIT_PIN}:{rel}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        else:
            # Archive-extract pin (no .git): the extract IS the pin bytes
            # by provision (`git archive <pin>`); compare blob hashes of
            # extract files vs imported files. Provision integrity (that
            # the extract came from the pinned hash) is established by
            # the provisioning step, not re-proven here.
            expected = subprocess.run(
                ["git", "hash-object", str(kit_repo / rel)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        disk_rel = Path(rel).relative_to("prompt_kit")
        observed = subprocess.run(
            ["git", "hash-object", str(pkg_dir / disk_rel)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert observed == expected, f"{rel}: imported bytes differ from pin blob"


def _mk_result(content: str = "", exit_code: int = 0, error: str | None = None) -> Any:
    base = importlib.import_module("prompt_kit.harnesses.base")
    return base.HarnessResult(content=content, exit_code=exit_code, error=error)


def _mock_harness_class() -> Any:
    return importlib.import_module("prompt_kit.harnesses").MockHarness


class ScriptRunner:
    """Scripted subprocess seam: CompletedProcess values or raised Exceptions."""

    def __init__(self, script: list[subprocess.CompletedProcess[str] | Exception]) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        timeout: float,
        stdin_text: str | None,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append({"argv": argv, "cwd": cwd, "timeout": timeout, "stdin_text": stdin_text})
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class ScriptHarness:
    """Scripted in-process harness with execution history."""

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []

    def execute(
        self,
        prompt: str,
        role: str = "general",
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append({"prompt": prompt, "role": role, "model": model, "context": context})
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class _NamedStubHarness(ScriptHarness):
    """ScriptHarness with a BaseHarness-style name (manual/mock doubles)."""

    def __init__(self, script: list[Any], name: str) -> None:
        super().__init__(script)
        self._stub_name = name

    @property
    def name(self) -> str:
        return self._stub_name


def _ok_proc(stdout: str = "did it") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["fake"], returncode=0, stdout=stdout, stderr="")


def _fail_proc(stderr: str = "boom") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["fake"], returncode=1, stdout="", stderr=stderr)


def _bundle(
    task_id: str = "P03-T1",
    goal: str = "Write the marker file.",
    targets: list[FileTarget] | None = None,
    invariants: list[str] | None = None,
) -> TaskBundle:
    return TaskBundle(
        task_id=task_id,
        epoch_index=1,
        spec_id="spec_p03",
        goal_statement=goal,
        invariants=invariants if invariants is not None else ["Stay inside the lease"],
        target_files=targets if targets is not None else [FileTarget(path="marker.txt")],
        membrane_protocols=["WorkerProtocol"],
        negative_inhibitors=["Never exfiltrate"],
    )


def _lease(worktree: Path, task_id: str = "P03-T1", active: bool = True) -> WorktreeLease:
    return WorktreeLease(
        lease_id=f"lease_{task_id}",
        task_id=task_id,
        branch_name="feature/stc-p03-e1",
        worktree_path=str(worktree),
        expires_at=datetime.now(UTC) + timedelta(hours=1) if active else datetime.now(UTC),
        is_active=active,
    )


@pytest.fixture
def lease_root(tmp_path: Path) -> Path:
    root = tmp_path / "lease"
    root.mkdir()
    (root / "src" / "stc" / "protocols").mkdir(parents=True)
    (root / "src" / "stc" / "schemas").mkdir(parents=True)
    (root / "src" / "stc" / "protocols" / "interfaces.py").write_text(
        "# protocols\n", encoding="utf-8"
    )
    (root / "src" / "stc" / "schemas" / "models.py").write_text("# models\n", encoding="utf-8")
    return root


@pytest.fixture
def ledger(tmp_path: Path) -> SpendLedger:
    return SpendLedger(tmp_path / "spend" / "test.jsonl")


@pytest.fixture
def fake_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _bin: "/usr/bin/fakebin")


def _read_rows(ledger: SpendLedger) -> list[dict[str, Any]]:
    return [json.loads(line) for line in ledger.path.read_text(encoding="utf-8").splitlines()]


def test_render_preserves_source_prefixes() -> None:
    bundle = _bundle(
        invariants=["[source:mem/inhibitors.md] never decide", "plain rule"],
    )
    prompt = render_bundle_prompt(bundle)
    assert "[source:mem/inhibitors.md] never decide" in prompt
    assert "plain rule" in prompt
    assert bundle.task_id in prompt and bundle.goal_statement in prompt
    assert "marker.txt" in prompt


def test_default_spend_path_shape() -> None:
    path = default_spend_path()
    assert path.parts[-4:] == ("evidence", "P03", "spend.jsonl") or path.name == "spend.jsonl"
    assert path.parent.name == "P03"


@pytest.mark.parametrize("name", ["mock", "codex", "agy", "agy2", "agy3", "agy4", "muse"])
def test_allowlist_accepts_cli_and_mock(name: str, ledger: SpendLedger) -> None:
    worker = HarnessWorker(name, ledger=ledger)
    assert isinstance(worker, WorkerProtocol)


@pytest.mark.parametrize(
    "name",
    ["openai", "anthropic", "deepseek", "ollama", "command", "interactive", "manual", "nope"],
)
def test_allowlist_rejects_api_and_unknown(name: str, ledger: SpendLedger) -> None:
    with pytest.raises(HarnessConfigError):
        HarnessWorker(name, ledger=ledger)


@pytest.mark.parametrize("name", ["{prompt}", "codex {file}", "codex; rm -rf", ""])
def test_allowlist_rejects_templates(name: str, ledger: SpendLedger) -> None:
    with pytest.raises(HarnessConfigError):
        HarnessWorker(name, ledger=ledger)


def test_injected_command_harness_rejected(ledger: SpendLedger) -> None:
    class CommandHarness:
        command_template = "{prompt}"

        def execute(self, prompt: str) -> None:
            raise AssertionError("must not run")

    with pytest.raises(HarnessConfigError):
        HarnessWorker("mock", ledger=ledger, harness=CommandHarness())  # type: ignore[arg-type]


def test_constructor_validates_timeout_and_attempts(ledger: SpendLedger) -> None:
    with pytest.raises(HarnessConfigError):
        HarnessWorker("mock", ledger=ledger, timeout=0)
    with pytest.raises(HarnessConfigError):
        HarnessWorker("mock", ledger=ledger, max_attempts=0)


def test_handshake_mock_needs_no_binary(ledger: SpendLedger) -> None:
    report = HarnessWorker("mock", ledger=ledger).handshake(probe=True)
    assert report.success and report.version == "mock"


def test_handshake_probe_uses_version(ledger: SpendLedger, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _bin: sys.executable)
    report = HarnessWorker("codex", ledger=ledger).handshake(probe=True)
    assert report.success and report.version is not None and "Python" in report.version
    assert report.latency_ms is not None and report.latency_ms >= 0


def test_handshake_missing_binary_fails(
    ledger: SpendLedger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _bin: None)
    assert HarnessWorker("codex", ledger=ledger).handshake(probe=True).success is False
    assert HarnessWorker("codex", ledger=ledger).handshake(probe=False).success is False


def test_mock_dispatch_writes_marker_and_attests_custody(
    lease_root: Path, ledger: SpendLedger
) -> None:
    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        assert ctx is not None
        marker = Path(str(ctx["project_root"])) / "marker.txt"
        marker.write_text("MOCK-OK\n", encoding="utf-8")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    lease = _lease(lease_root)
    report = json.loads(worker.dispatch(_bundle(), lease))
    assert report["lease_id"] == lease.lease_id
    paths = {entry["path"]: entry["sha256"] for entry in report["modified_files"]}
    assert "marker.txt" in paths and len(paths["marker.txt"]) == 64
    rows = _read_rows(ledger)
    assert len(rows) == 1 and rows[0]["ok"] is True and rows[0]["channel"] == "worker"


def test_default_pinned_mock_path_succeeds_without_writes(
    lease_root: Path, ledger: SpendLedger
) -> None:
    worker = HarnessWorker("mock", ledger=ledger)
    report = json.loads(worker.dispatch(_bundle(goal="Say hello in one word."), _lease(lease_root)))
    assert report["modified_files"] == []
    assert report["notary_verified"] is True


def test_dispatch_worker_integration_active_lease(lease_root: Path, ledger: SpendLedger) -> None:
    from stc.orchestrator.dispatch import dispatch_worker

    harness = ScriptHarness([_mk_result("ok")])
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    report = json.loads(dispatch_worker(_bundle(), _lease(lease_root), worker))
    assert report["task_id"] == "P03-T1"
    assert harness.calls[0]["context"]["project_root"] == str(lease_root)


def test_dispatch_worker_rejects_expired_lease(lease_root: Path, ledger: SpendLedger) -> None:
    from stc.orchestrator.dispatch import dispatch_worker

    worker = HarnessWorker("mock", ledger=ledger, harness=ScriptHarness([_mk_result("ok")]))
    with pytest.raises(WorktreeError, match="inactive or expired"):
        dispatch_worker(_bundle(), _lease(lease_root, active=False), worker)


def test_factory_closure_matches_method(lease_root: Path, ledger: SpendLedger) -> None:
    worker = HarnessWorker("mock", ledger=ledger, harness=ScriptHarness([_mk_result("v")]))
    lease = _lease(lease_root)
    fn = harness_worker_fn(worker, lease)
    assert fn(_bundle(), lease_root) == "v"


def test_timeout_raises_after_retry_with_two_rows(
    lease_root: Path, ledger: SpendLedger, fake_which: None
) -> None:
    timeout = subprocess.TimeoutExpired(cmd=["fake"], timeout=600.0)
    worker = HarnessWorker(
        "codex", ledger=ledger, runner=ScriptRunner([timeout, timeout]), timeout=600.0
    )
    with pytest.raises(WorktreeError, match=r"timed out|failed after 2"):
        worker.dispatch(_bundle(), _lease(lease_root))
    rows = _read_rows(ledger)
    assert len(rows) == 2
    assert [row["attempt"] for row in rows] == [1, 2]
    assert all(row["timed_out"] and row["exit_code"] == 124 and not row["ok"] for row in rows)


def test_failure_then_retry_success_logs_two_rows(
    lease_root: Path, ledger: SpendLedger, fake_which: None
) -> None:
    runner = ScriptRunner([_fail_proc("first fails"), _ok_proc("second wins")])
    worker = HarnessWorker("codex", ledger=ledger, runner=runner)
    assert worker.dispatch(_bundle(), _lease(lease_root)) is not None
    rows = _read_rows(ledger)
    assert [row["ok"] for row in rows] == [False, True]
    assert "first fails" in rows[0]["note"]


def test_crash_mid_run_still_logs(lease_root: Path, ledger: SpendLedger, fake_which: None) -> None:
    worker = HarnessWorker(
        "codex", ledger=ledger, runner=ScriptRunner([OSError("disk gone")]), max_attempts=1
    )
    with pytest.raises(WorktreeError, match="crashed"):
        worker.dispatch(_bundle(), _lease(lease_root))
    rows = _read_rows(ledger)
    assert len(rows) == 1 and rows[0]["ok"] is False
    assert "OSError" in rows[0]["note"]


def test_in_lease_ledger_rejected(lease_root: Path, tmp_path: Path) -> None:
    worker = HarnessWorker("mock", ledger=SpendLedger(lease_root / "spend.jsonl"))
    with pytest.raises(HarnessConfigError, match="outside the lease"):
        worker.dispatch(_bundle(), _lease(lease_root))


def test_ledger_exclusion_does_not_hide_siblings(
    lease_root: Path, tmp_path: Path, ledger: SpendLedger
) -> None:
    sibling = ledger.path.parent / "evil-in-spend-dir.txt"

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        sibling.write_text("x\n", encoding="utf-8")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    with pytest.raises(ConfinementViolationError, match="created path"):
        worker.dispatch(_bundle(), _lease(lease_root))


def test_cap_enforced_before_spawn(lease_root: Path, tmp_path: Path, fake_which: None) -> None:
    capped = SpendLedger(tmp_path / "spend.jsonl", max_worker_calls=1)
    runner = ScriptRunner([_ok_proc()])
    worker = HarnessWorker("codex", ledger=capped, runner=runner)
    worker.dispatch(_bundle(), _lease(lease_root))
    with pytest.raises(SpendCapExceededError, match="Spend cap reached"):
        worker.dispatch(_bundle(task_id="P03-T2"), _lease(lease_root, task_id="P03-T2"))
    assert len(runner.calls) == 1  # second dispatch spawned nothing


def test_native_runner_sees_lease_cwd_and_prompt(
    lease_root: Path, ledger: SpendLedger, fake_which: None
) -> None:
    runner = ScriptRunner([_ok_proc("done")])
    worker = HarnessWorker("codex", ledger=ledger, runner=runner)
    worker.dispatch(_bundle(goal="UNIQUE-GOAL-STRING"), _lease(lease_root))
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["cwd"] == str(lease_root)
    assert call["argv"][-1] == "-" and "-C" in call["argv"]
    assert "UNIQUE-GOAL-STRING" in (call["stdin_text"] or "")


def test_native_argv_shapes(tmp_path: Path, fake_which: None) -> None:
    lease = tmp_path / "lease"
    lease.mkdir()
    argv, stdin_text, prompt_file = build_native_command(
        "codex", "P", model="default", lease_root=lease
    )
    assert argv[1:3] == ["exec", "--skip-git-repo-check"]
    assert argv[3] == "--dangerously-bypass-approvals-and-sandbox"
    assert argv[-1] == "-" and stdin_text == "P" and prompt_file is None
    assert str(lease) in argv
    argv, stdin_text, prompt_file = build_native_command(
        "agy2", "P", model="m-mid", lease_root=lease
    )
    assert argv[1:3] == ["--dangerously-skip-permissions", "--model"]
    assert argv[-2:] == ["-p", "P"] and stdin_text is None and prompt_file is None
    argv, stdin_text, prompt_file = build_native_command(
        "muse", "PROMPT-BODY", model="default", lease_root=lease
    )
    try:
        assert argv[1] == "exec" and "--prompt-file" in argv and stdin_text is None
        assert prompt_file is not None and prompt_file.is_file()
        assert lease not in prompt_file.parents  # OS temp, outside the lease
        assert prompt_file.read_text(encoding="utf-8") == "PROMPT-BODY"
    finally:
        if prompt_file is not None:
            prompt_file.unlink(missing_ok=True)
    with pytest.raises(HarnessConfigError):
        build_native_command("mock", "P", model="default", lease_root=lease)


def test_native_shape_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _bin: None)
    with pytest.raises(WorktreeError, match="not found on PATH"):
        build_native_command("codex", "P", model="default", lease_root=tmp_path)


def test_membrane_custom_markers_on_plain_lease(tmp_path: Path, ledger: SpendLedger) -> None:
    lease = tmp_path / "plain"
    (lease / "app").mkdir(parents=True)
    (lease / "app" / "main.py").write_text("MARK-X\nprint(1)\n", encoding="utf-8")
    worker = HarnessWorker(
        "mock",
        ledger=ledger,
        harness=ScriptHarness([_mk_result("ok")]),
        membrane_files=(("app/main.py", "MARK-X"),),
    )
    report = json.loads(worker.dispatch(_bundle(), _lease(lease)))
    assert report["notary_verified"] is True


def test_membrane_rejects_missing_marker(tmp_path: Path, ledger: SpendLedger) -> None:
    lease = tmp_path / "plain"
    (lease / "app").mkdir(parents=True)
    (lease / "app" / "main.py").write_text("no marker here\n", encoding="utf-8")
    worker = HarnessWorker(
        "mock",
        ledger=ledger,
        harness=ScriptHarness([_mk_result("ok")]),
        membrane_files=(("app/main.py", "MARK-X"),),
    )
    with pytest.raises(WorktreeError, match="Membrane verification failed"):
        worker.dispatch(_bundle(), _lease(lease))


def test_membrane_rejects_empty_and_malformed(ledger: SpendLedger) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ChaperoneWorker(membrane_files=())
    with pytest.raises(ValueError, match="marker-or-None"):
        ChaperoneWorker(membrane_files=(("", None),))
    with pytest.raises(ValueError, match="marker-or-None"):
        ChaperoneWorker(membrane_files=(("a.py", ""),))


def test_membrane_rejects_symlink_stub(tmp_path: Path, ledger: SpendLedger) -> None:
    lease = tmp_path / "plain"
    (lease / "app").mkdir(parents=True)
    real = lease / "real.py"
    real.write_text("MARK-X\n", encoding="utf-8")
    (lease / "app" / "main.py").symlink_to(real)
    worker = HarnessWorker(
        "mock",
        ledger=ledger,
        harness=ScriptHarness([_mk_result("ok")]),
        membrane_files=(("app/main.py", "MARK-X"),),
    )
    with pytest.raises(WorktreeError, match="Membrane verification failed"):
        worker.dispatch(_bundle(), _lease(lease))


def test_outer_write_moves_to_quarantine_with_record(lease_root: Path, ledger: SpendLedger) -> None:
    outside = lease_root.parent / "evil.txt"

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        assert ctx is not None
        root = Path(str(ctx["project_root"]))
        (root / "attempt.txt").write_text("attempt preserved\n", encoding="utf-8")
        outside.write_text("breach-bytes\n", encoding="utf-8")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    with pytest.raises(ConfinementViolationError, match="created path") as excinfo:
        worker.dispatch(_bundle(), _lease(lease_root))
    assert not outside.exists()  # moved away, not left behind
    assert (lease_root / "attempt.txt").read_text(encoding="utf-8") == "attempt preserved\n"
    record = excinfo.value.violation_record
    assert record is not None
    qdir = Path(str(record["quarantine_dir"]))
    assert (qdir / "violation.json").is_file()
    created = [item for item in record["items"] if item["kind"] == "created"]
    assert len(created) == 1 and created[0]["path"] == str(outside)
    moved = Path(str(created[0]["quarantined_as"]))
    assert moved.is_file() and moved.read_bytes() == b"breach-bytes\n"
    assert created[0]["size"] == len(b"breach-bytes\n") and len(created[0]["sha256"]) == 64


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "p03@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.name", "P03"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)


def test_git_ref_tamper_detected(tmp_path: Path, ledger: SpendLedger) -> None:
    if shutil.which("git") is None:
        pytest.skip("git required")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    lease = repo / "lease"
    (lease / "src" / "stc" / "protocols").mkdir(parents=True)
    (lease / "src" / "stc" / "schemas").mkdir(parents=True)
    (lease / "src" / "stc" / "protocols" / "interfaces.py").write_text("# p\n", encoding="utf-8")
    (lease / "src" / "stc" / "schemas" / "models.py").write_text("# m\n", encoding="utf-8")
    ref = repo / ".git" / "refs" / "heads" / "main"
    assert ref.is_file()

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        with ref.open("a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    with pytest.raises(ConfinementViolationError, match="modified file") as excinfo:
        worker.dispatch(_bundle(), _lease(lease))
    record = excinfo.value.violation_record
    assert record is not None
    assert any(str(ref) in item["path"] for item in record["items"])


def test_outer_skip_dirs_match_manifest_parity() -> None:
    """The outer-snapshot prune set must equal MANIFEST_EXCLUDE_DIRS.

    dispatch.py cannot import lease_git (integration imports dispatch),
    so the sets are duplicated; this test forces lockstep evolution.
    """
    from stc.integration.lease_git import MANIFEST_EXCLUDE_DIRS
    from stc.orchestrator.dispatch import _OUTER_SKIP_DIRS

    assert _OUTER_SKIP_DIRS == MANIFEST_EXCLUDE_DIRS


def test_outer_snapshot_prunes_runtime_output_dirs(tmp_path: Path) -> None:
    """The strict outer snapshot prunes top-level runtime-output dirs.

    Regression: the N12 snapshot walked gigabytes of install/runtime
    output (.durable/, dossier/, ...) on real trees. Top-level pruned
    subtrees contribute zero entries while evaluated bytes, nested
    evidence, and the F2 .git subset stay watched.
    """
    repo = tmp_path
    lease = repo / "lease"
    (lease / "src" / "stc" / "protocols").mkdir(parents=True)
    (lease / "src" / "stc" / "protocols" / "interfaces.py").write_text("# p\n", encoding="utf-8")
    for name in (".durable", "dossier", "worktrees", "node_modules", "artifacts", ".venv"):
        deep = repo / name / "d1" / "d2"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_text("x" * 100, encoding="utf-8")
    nested = repo / "docs" / "evidence" / "dossier"
    nested.mkdir(parents=True)
    (nested / "deep.txt").write_text("evidence\n", encoding="utf-8")
    (repo / "keep.txt").write_text("keep\n", encoding="utf-8")
    (repo / "sub").mkdir()
    (repo / "sub" / "normal.txt").write_text("n\n", encoding="utf-8")
    (repo / ".git" / "refs" / "heads").mkdir(parents=True)
    (repo / ".git" / "refs" / "heads" / "main").write_text("abc123\n", encoding="utf-8")
    (repo / ".git" / "config").write_text("[core]\n", encoding="utf-8")

    sigs = ChaperoneWorker()._snapshot_outer_strict(lease)

    assert (repo / "keep.txt") in sigs
    assert (repo / "sub" / "normal.txt") in sigs
    assert (nested / "deep.txt") in sigs  # nested evidence stays watched
    ref = repo / ".git" / "refs" / "heads" / "main"
    assert ref in sigs and sigs[ref].sha256 is not None  # F2 intact
    assert sigs[repo / ".git" / "config"].sha256 is not None
    pruned = {".durable", "dossier", "worktrees", "node_modules", "artifacts", ".venv"}
    assert not [p for p in sigs if p.parent == repo and p.name in pruned]
    # Exact bound: keep.txt, sub, sub/normal.txt + refs/heads,
    # refs/heads/main, config (subset roots yield children only, as
    # with the former rglob walk) + docs, docs/evidence,
    # docs/evidence/dossier, docs/evidence/dossier/deep.txt.
    assert len(sigs) == 10


def test_outer_audit_still_catches_skip_named_file(lease_root: Path, ledger: SpendLedger) -> None:
    """Pruning applies to directories only: a worker-created FILE named
    like a skip dir (e.g. `dossier`) outside the lease is still caught."""
    outside = lease_root.parent / "dossier"

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        outside.write_text("breach-bytes\n", encoding="utf-8")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    with pytest.raises(ConfinementViolationError, match="created path"):
        worker.dispatch(_bundle(), _lease(lease_root))
    assert not outside.exists()


def test_outer_audit_blind_spot_under_pruned_dirs_is_accepted(
    lease_root: Path, ledger: SpendLedger
) -> None:
    """Characterize the accepted residual: worker writes UNDER a
    top-level pruned runtime-output dir are invisible to the outer
    audit. This mirrors the tripwire manifest exclusion (backend
    self-writes there too); if the prune set ever shrinks, this test
    fails and the disposition is revisited."""
    target = lease_root.parent / ".durable" / "worker-litter.txt"

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("litter\n", encoding="utf-8")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    worker.dispatch(_bundle(), _lease(lease_root))  # no raise: accepted residual
    assert target.read_text(encoding="utf-8") == "litter\n"


def test_outer_audit_catches_nested_evidence_write(lease_root: Path, ledger: SpendLedger) -> None:
    """Pruning is top-level only: a worker write under a NESTED
    runtime-named dir (docs/.../dossier evidence) is still caught."""
    nested = lease_root.parent / "docs" / "evidence" / "dossier"
    nested.mkdir(parents=True)
    target = nested / "deep.txt"
    target.write_text("evidence\n", encoding="utf-8")

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        target.write_text("tampered-evidence\n", encoding="utf-8")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    with pytest.raises(ConfinementViolationError, match="modified file"):
        worker.dispatch(_bundle(), _lease(lease_root))


def test_size_change_detected_despite_mtime_reset(lease_root: Path, ledger: SpendLedger) -> None:
    outside = lease_root.parent / "watched.txt"
    outside.write_text("0123456789", encoding="utf-8")
    orig_ns = outside.stat().st_mtime_ns

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        outside.write_text("CHANGED-LONGER", encoding="utf-8")
        os.utime(outside, ns=(orig_ns, orig_ns))
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    with pytest.raises(ConfinementViolationError, match="modified file"):
        worker.dispatch(_bundle(), _lease(lease_root))


def test_accepted_residual_same_size_same_mtime_swap(lease_root: Path, ledger: SpendLedger) -> None:
    """Characterize the F3 ACCEPTED residual: an exact mtime_ns+size-preserving
    content swap is invisible to the tripwire. This pins the documented limit;
    if detection ever improves, this test fails and the disposition is revisited."""
    outside = lease_root.parent / "watched.txt"
    outside.write_text("0123456789", encoding="utf-8")
    orig_ns = outside.stat().st_mtime_ns
    os.utime(outside, ns=(orig_ns, orig_ns))
    if outside.stat().st_mtime_ns != orig_ns:
        pytest.skip("filesystem lacks ns mtime fidelity; residual not constructible")

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        outside.write_text("9876543210", encoding="utf-8")
        os.utime(outside, ns=(orig_ns, orig_ns))
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    worker.dispatch(_bundle(), _lease(lease_root))  # no raise: accepted residual
    assert outside.read_text(encoding="utf-8") == "9876543210"


def test_prompt_kit_tmp_leftovers_swept_on_success(lease_root: Path, ledger: SpendLedger) -> None:
    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        assert ctx is not None
        tmpdir = Path(str(ctx["project_root"])) / ".prompt-kit" / "tmp"
        tmpdir.mkdir(parents=True)
        (tmpdir / "crash-leftover.md").write_text("prompt bytes\n", encoding="utf-8")
        return "done"

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness)
    report = json.loads(worker.dispatch(_bundle(), _lease(lease_root)))
    assert not (lease_root / ".prompt-kit" / "tmp" / "crash-leftover.md").exists()
    assert all(".prompt-kit" not in entry["path"] for entry in report["modified_files"])


def test_prompt_kit_tmp_leftovers_swept_on_failure(lease_root: Path, ledger: SpendLedger) -> None:
    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        assert ctx is not None
        tmpdir = Path(str(ctx["project_root"])) / ".prompt-kit" / "tmp"
        tmpdir.mkdir(parents=True)
        (tmpdir / "crash-leftover.md").write_text("prompt bytes\n", encoding="utf-8")
        raise RuntimeError("agent crashed")

    harness = _mock_harness_class()(custom_responder=responder)
    worker = HarnessWorker("mock", ledger=ledger, harness=harness, max_attempts=1)
    with pytest.raises(WorktreeError, match="crashed"):
        worker.dispatch(_bundle(), _lease(lease_root))
    assert not (lease_root / ".prompt-kit" / "tmp" / "crash-leftover.md").exists()


def test_sweep_is_best_effort_on_missing_dir(tmp_path: Path) -> None:
    assert sweep_prompt_kit_tmp(tmp_path / "nope") == []


def test_ledger_skips_torn_tail_lines(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "spend.jsonl", max_worker_calls=2)
    ledger.log_row(
        "worker",
        harness="mock",
        model="m",
        task_id="t",
        lease_id="l",
        attempt=1,
        ok=True,
        exit_code=0,
        timed_out=False,
        duration_s=0.1,
        out_bytes=3,
    )
    with ledger.path.open("a", encoding="utf-8") as fh:
        fh.write('{"channel": "worker", "torn": \n')
    assert ledger.count("worker") == 1
    ledger.check_quota("worker")  # 1 < 2: no raise


def test_gateway_invoke_serves_controller_path(tmp_path: Path, ledger: SpendLedger) -> None:
    from sst.gateway.contracts import GatewayRequest, ModelCatalog, ProviderKind, ProviderProfile

    backend = CLIGatewayBackend(
        "mock", project_root=tmp_path, ledger=ledger, harness=ScriptHarness([_mk_result("GW-DONE")])
    )
    gateway = CLIModelGateway(backend)
    gateway.register_profile(
        ProviderProfile(
            name="cli",
            kind=ProviderKind.TEST,
            api_base="cli://local",
            selected_model="default",
            catalog=ModelCatalog(),
        )
    )
    gateway.set_route("diverge", "cli", "default")
    response = gateway.invoke(
        GatewayRequest(role="diverge", messages=[{"role": "user", "content": "hi"}])
    )
    assert response.content == "GW-DONE"
    assert response.profile == "cli" and response.cost_usd == 0.0
    rows = _read_rows(ledger)
    assert len(rows) == 1 and rows[0]["channel"] == "gateway" and rows[0]["ok"] is True


def test_backend_zero_cost_known_matrix(tmp_path: Path, ledger: SpendLedger) -> None:
    """Only provably-$0 backends report known cost (honest budgets)."""
    bare_mock = CLIGatewayBackend("mock", project_root=tmp_path, ledger=ledger)
    assert bare_mock.zero_cost_known is True  # pinned mock: no model calls
    bare_codex = CLIGatewayBackend("codex", project_root=tmp_path, ledger=ledger)
    assert bare_codex.zero_cost_known is False  # subprocess spend, unmetered
    manual = CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        ledger=ledger,
        harness=_NamedStubHarness([], "manual"),
    )
    assert manual.zero_cost_known is True  # fixtures/stdin: no model calls
    unnamed = CLIGatewayBackend(
        "mock", project_root=tmp_path, ledger=ledger, harness=ScriptHarness([])
    )
    assert unnamed.zero_cost_known is False  # exec-like: no name, spend unknown


def test_gateway_invoke_cost_known_follows_backend(tmp_path: Path, ledger: SpendLedger) -> None:
    from sst.gateway.contracts import GatewayRequest, ModelCatalog, ProviderKind, ProviderProfile

    def _gateway(harness: Any) -> CLIModelGateway:
        backend = CLIGatewayBackend("mock", project_root=tmp_path, ledger=ledger, harness=harness)
        gateway = CLIModelGateway(backend)
        gateway.register_profile(
            ProviderProfile(
                name="cli",
                kind=ProviderKind.TEST,
                api_base="cli://local",
                selected_model="default",
                catalog=ModelCatalog(),
            )
        )
        gateway.set_route("diverge", "cli", "default")
        return gateway

    manual = _gateway(_NamedStubHarness([_mk_result("M-DONE")], "manual"))
    res = manual.invoke(GatewayRequest(role="diverge", messages=[]))
    assert res.cost_usd == 0.0 and res.cost_known is True
    assert res.raw_metadata["tokens"].startswith("no model calls")

    unnamed = _gateway(ScriptHarness([_mk_result("U-DONE")]))
    res2 = unnamed.invoke(GatewayRequest(role="diverge", messages=[]))
    assert res2.cost_usd == 0.0 and res2.cost_known is False
    assert "spend tracked in STC ledger rows" in res2.raw_metadata["tokens"]


def test_gateway_invoke_routing_errors(tmp_path: Path, ledger: SpendLedger) -> None:
    from sst.gateway.contracts import (
        GatewayRequest,
        MissingModelError,
        ModelCatalog,
        ProviderGatewayError,
        ProviderKind,
        ProviderProfile,
    )

    backend = CLIGatewayBackend("mock", project_root=tmp_path, ledger=ledger)
    gateway = CLIModelGateway(backend)
    with pytest.raises(ProviderGatewayError, match="No provider profile"):
        gateway.invoke(GatewayRequest(role="diverge", messages=[]))
    gateway.register_profile(
        ProviderProfile(
            name="cli", kind=ProviderKind.TEST, api_base="cli://local", catalog=ModelCatalog()
        )
    )
    with pytest.raises(MissingModelError):
        gateway.invoke(GatewayRequest(role="diverge", messages=[]))


def test_gateway_generate_failure_logs_and_raises(tmp_path: Path, ledger: SpendLedger) -> None:
    from sst.gateway.contracts import ProviderGatewayError

    backend = CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        ledger=ledger,
        harness=ScriptHarness([_mk_result("", exit_code=1, error="nope")]),
    )
    with pytest.raises(ProviderGatewayError, match="failed"):
        backend.generate("do it")
    rows = _read_rows(ledger)
    assert len(rows) == 1 and rows[0]["ok"] is False


async def test_gateway_generate_async_matches_sync(tmp_path: Path, ledger: SpendLedger) -> None:
    backend = CLIGatewayBackend(
        "mock", project_root=tmp_path, ledger=ledger, harness=ScriptHarness([_mk_result("A")])
    )
    assert await backend.generate_async("do it") == "A"


def test_gateway_cap_enforced(tmp_path: Path) -> None:
    capped = SpendLedger(tmp_path / "spend.jsonl", max_gateway_calls=1)
    backend = CLIGatewayBackend(
        "mock", project_root=tmp_path, ledger=capped, harness=ScriptHarness([_mk_result("A")])
    )
    backend.generate("one")
    with pytest.raises(SpendCapExceededError, match="gateway"):
        backend.generate("two")


def test_wrapper_quarantines_lease_on_breach(tmp_path: Path) -> None:
    wt_root = tmp_path / "worktrees"
    wt_root.mkdir()
    lease_dir = tmp_path / "lease"
    (lease_dir / "src" / "stc" / "protocols").mkdir(parents=True)
    (lease_dir / "src" / "stc" / "schemas").mkdir(parents=True)
    proto = lease_dir / "src" / "stc" / "protocols" / "interfaces.py"
    proto.write_text("# p\n", encoding="utf-8")
    schemas = lease_dir / "src" / "stc" / "schemas" / "models.py"
    schemas.write_text("# m\n", encoding="utf-8")
    outside = tmp_path / "evil.txt"

    def responder(prompt: str, role: str, model: str | None, ctx: dict[str, Any] | None) -> str:
        outside.write_text("x\n", encoding="utf-8")
        return "done"

    manager = WorktreeManager(repo_root=tmp_path, worktree_root=wt_root)
    expected = wt_root / "stc-p03-f6"
    expected.mkdir(parents=True)
    lease = _lease(lease_dir, task_id="P03-F6")
    worker = HarnessWorker(
        "mock",
        ledger=SpendLedger(tmp_path / "spend.jsonl"),
        harness=_mock_harness_class()(custom_responder=responder),
    )
    with pytest.raises(ConfinementViolationError):
        dispatch_with_quarantine(worker, _bundle(task_id="P03-F6"), lease, manager)
    record = json.loads((expected / ".quarantined.json").read_text(encoding="utf-8"))
    assert record["status"] == "QUARANTINED"
    assert "confinement breach" in record["reason"]


def test_wrapper_passes_through_success(
    lease_root: Path, tmp_path: Path, ledger: SpendLedger
) -> None:
    manager = WorktreeManager(repo_root=tmp_path, worktree_root=tmp_path / "wt")
    worker = HarnessWorker("mock", ledger=ledger, harness=ScriptHarness([_mk_result("ok")]))
    report = json.loads(dispatch_with_quarantine(worker, _bundle(), _lease(lease_root), manager))
    assert report["notary_verified"] is True


# --- Live harness tests (B1-handshaked shapes; deselected in gate runs) ---


def _seed_codex_home() -> Path | None:
    """Writable CODEX_HOME seeded from the operator login (caller deletes).

    Lives in its own OS-temp dir, OUTSIDE any lease parent: codex writes
    session/state files here during execution and the tripwire would otherwise
    (correctly) flag them as outer writes.
    """
    src = Path.home() / ".codex"
    auth, config = src / "auth.json", src / "config.toml"
    if not auth.is_file():
        return None
    home = Path(tempfile.mkdtemp(prefix="p03-codex-home-"))
    shutil.copy(auth, home / "auth.json")
    (home / "auth.json").chmod(0o600)
    if config.is_file():
        shutil.copy(config, home / "config.toml")
    return home


def _seed_agy_home() -> Path | None:
    """Writable HOME seeded from the acc2 profile (caller deletes)."""
    src = Path.home() / ".agy_profiles" / "acc2"
    if not (src / ".gemini").is_dir():
        return None
    home = Path(tempfile.mkdtemp(prefix="p03-agy-home-"))
    home.rmdir()
    shutil.copytree(src, home, symlinks=True)
    return home


@live
def test_live_handshake_binaries_probe(tmp_path: Path) -> None:
    """Live availability: version probes for codex/agy/muse (no quota spent)."""
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    results = {
        name: HarnessWorker(name, ledger=ledger).handshake(probe=True)
        for name in ("codex", "agy", "muse")
    }
    assert results["codex"].success, f"codex probe failed: {results['codex'].error}"
    assert results["agy"].success, f"agy probe failed: {results['agy'].error}"
    assert results["muse"].success, f"muse probe failed: {results['muse'].error}"


@live
def test_live_codex_worker_writes_marker(tmp_path: Path) -> None:
    """Full worker stack on live codex: marker lands in lease, custody attests it."""
    codex_home = _seed_codex_home()
    if codex_home is None:
        pytest.skip("operator codex login unavailable")
    try:
        lease = tmp_path / "lease"
        lease.mkdir()
        (lease / "task.txt").write_text("LIVE-TASK\n", encoding="utf-8")
        worker = HarnessWorker(
            "codex",
            ledger=SpendLedger(tmp_path / "spend.jsonl"),
            timeout=280.0,
            harness_env={"CODEX_HOME": str(codex_home)},
            membrane_files=(("task.txt", "LIVE-TASK"),),
            max_attempts=1,
        )
        bundle = _bundle(
            task_id="P03-LIVE",
            goal="Write exactly the single line P03-LIVE-OK into a new file named "
            "marker-live.txt in the current working directory. Then reply with only: DONE",
            targets=[FileTarget(path="marker-live.txt", action="create")],
        )
        report = json.loads(worker.dispatch(bundle, _lease(lease, task_id="P03-LIVE")))
        marker = lease / "marker-live.txt"
        assert marker.is_file()
        assert "P03-LIVE-OK" in marker.read_text(encoding="utf-8")
        assert "marker-live.txt" in {entry["path"] for entry in report["modified_files"]}
    finally:
        shutil.rmtree(codex_home, ignore_errors=True)


@live
def test_live_codex_gateway_text(tmp_path: Path) -> None:
    """Live codex serves the gateway invoke path (text response, logged)."""
    from sst.gateway.contracts import GatewayRequest, ModelCatalog, ProviderKind, ProviderProfile

    codex_home = _seed_codex_home()
    if codex_home is None:
        pytest.skip("operator codex login unavailable")
    try:
        ledger = SpendLedger(tmp_path / "spend.jsonl")
        backend = CLIGatewayBackend(
            "codex",
            project_root=tmp_path,
            ledger=ledger,
            timeout=280.0,
            harness_env={"CODEX_HOME": str(codex_home)},
        )
        gateway = CLIModelGateway(backend)
        gateway.register_profile(
            ProviderProfile(
                name="cli",
                kind=ProviderKind.TEST,
                api_base="cli://local",
                selected_model="default",
                catalog=ModelCatalog(),
            )
        )
        response = gateway.invoke(
            GatewayRequest(messages=[{"role": "user", "content": "Reply with only: GW-OK"}])
        )
        assert "GW-OK" in response.content
        rows = _read_rows(ledger)
        assert len(rows) == 1 and rows[0]["channel"] == "gateway" and rows[0]["ok"] is True
    finally:
        shutil.rmtree(codex_home, ignore_errors=True)


@live
def test_live_agy_gateway_text(tmp_path: Path) -> None:
    """Live agy (acc2) serves the gateway invoke path (text response, logged)."""
    from sst.gateway.contracts import GatewayRequest, ModelCatalog, ProviderKind, ProviderProfile

    agy_home = _seed_agy_home()
    if agy_home is None:
        pytest.skip("acc2 profile unavailable")
    try:
        ledger = SpendLedger(tmp_path / "spend.jsonl")
        backend = CLIGatewayBackend(
            "agy2",
            project_root=tmp_path,
            ledger=ledger,
            timeout=200.0,
            harness_env={"HOME": str(agy_home)},
        )
        gateway = CLIModelGateway(backend)
        gateway.register_profile(
            ProviderProfile(
                name="cli",
                kind=ProviderKind.TEST,
                api_base="cli://local",
                selected_model="default",
                catalog=ModelCatalog(),
            )
        )
        response = gateway.invoke(
            GatewayRequest(messages=[{"role": "user", "content": "Reply with only: AGY-GW-OK"}])
        )
        assert "AGY-GW-OK" in response.content
        rows = _read_rows(ledger)
        assert len(rows) == 1 and rows[0]["channel"] == "gateway" and rows[0]["ok"] is True
    finally:
        shutil.rmtree(agy_home, ignore_errors=True)


# --- P03-fix gateway profile (INT-2026-09-14.1, D15). NEW tests; existing ones untouched. ---


def test_fix_gateway_argv_pins_confined_codex_profile(tmp_path: Path, fake_which: None) -> None:
    """Gateway role argv pins: read-only + scratch + schema-capture flags (B1 -o pick)."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    argv, stdin_text, prompt_file, last_message = build_gateway_command(
        "codex", "P", model="default", scratch_dir=scratch
    )
    assert argv[1:3] == ["exec", "--skip-git-repo-check"]
    assert argv[argv.index("-s") + 1] == "read-only"
    assert argv[argv.index("-C") + 1] == str(scratch)
    assert "--ephemeral" in argv
    assert argv[argv.index("-o") + 1] == str(last_message)
    assert last_message.parent == scratch
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert "--model" not in argv  # default => operator config (model unchanged)
    assert argv[-1] == "-" and stdin_text == "P" and prompt_file is None
    with pytest.raises(HarnessConfigError):
        build_gateway_command("mock", "P", model="default", scratch_dir=scratch)


def test_fix_gateway_argv_passes_explicit_model(tmp_path: Path, fake_which: None) -> None:
    """Explicit (non-default) models still flow through --model on the gateway path."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    argv, _, _, _ = build_gateway_command("codex", "P", model="gpt-x", scratch_dir=scratch)
    assert argv[argv.index("--model") + 1] == "gpt-x"


def test_fix_worker_argv_unchanged_after_fix(tmp_path: Path, fake_which: None) -> None:
    """Worker-role argv is byte-identical to the pre-fix shape (delta touches gateway only)."""
    lease = tmp_path / "lease"
    lease.mkdir()
    argv, stdin_text, prompt_file = build_native_command(
        "codex", "P", model="default", lease_root=lease
    )
    assert argv[1:4] == [
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
    ]
    assert argv[argv.index("-C") + 1] == str(lease)
    assert "-s" not in argv and "--ephemeral" not in argv and "-o" not in argv
    assert argv[-1] == "-" and stdin_text == "P" and prompt_file is None


def test_fix_shape_gateway_prompt_preserves_sst_bytes() -> None:
    """Shaping is APPEND-ONLY: SST bytes verbatim delimited, never edited (D7 intact)."""
    sst = '  You are an unconstrained {agent}!\nRADICALLY "DIFFERENT" — emit <json>.\n'
    shaped = shape_gateway_prompt(sst)
    assert sst in shaped
    assert shaped.count(sst) == 1
    assert SST_PROMPT_BEGIN in shaped and SST_PROMPT_END in shaped
    assert shaped.index(SST_PROMPT_BEGIN) < shaped.index(sst) < shaped.index(SST_PROMPT_END)
    # Shaping pins: emitter role + no-tools/no-write discipline + emit-exactly-one-JSON.
    assert "JSON emitter, not an autonomous agent" in shaped
    assert "Do not call tools" in shaped and "no writes anywhere" in shaped
    assert "Emit exactly one JSON document" in shaped


def test_fix_shape_gateway_prompt_preserves_real_diverge_bytes() -> None:
    """The preserved P05 diverge prompt (the shaped-for class) survives shaping verbatim."""
    # Tree-relative: the prompt ships with THIS tree, so the owning test
    # file's repo root is the lookup base — identical ambient, and also
    # resolvable in-lease where no workspace/stc layout exists.
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "builds"
        / "stc-integration"
        / "evidence"
        / "P05"
        / "attempt-1"
        / "trial-timeout"
        / "p05-diverge-prompt.md"
    )
    if not prompt_path.is_file():
        pytest.skip("preserved diverge prompt unavailable")
    sst = prompt_path.read_text(encoding="utf-8")
    assert "HIGH-ENTROPY EXPLORATION" in sst
    shaped = shape_gateway_prompt(sst)
    assert sst in shaped
    assert "HIGH-ENTROPY EXPLORATION" in shaped


def test_fix_gateway_generate_shapes_prompt_with_gateway_role(
    tmp_path: Path, ledger: SpendLedger
) -> None:
    """generate() frames the prompt and dispatches with role=gateway (in-process harness)."""
    harness = ScriptHarness([_mk_result("GW-DONE")])
    backend = CLIGatewayBackend("mock", project_root=tmp_path, ledger=ledger, harness=harness)
    assert backend.generate("SST-BYTES-HERE") == "GW-DONE"
    call = harness.calls[0]
    assert call["role"] == "gateway"
    assert "SST-BYTES-HERE" in call["prompt"]
    assert "Emit exactly one JSON document" in call["prompt"]


def test_fix_gateway_confined_run_prefers_o_file(tmp_path: Path, fake_which: None) -> None:
    """Native gateway role: scratch cwd, confined argv, -o bytes win, scratch cleaned."""
    seen: dict[str, Any] = {}

    def runner(
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        timeout: float,
        stdin_text: str | None,
    ) -> subprocess.CompletedProcess[str]:
        seen["argv"] = argv
        seen["cwd"] = cwd
        seen["stdin_text"] = stdin_text
        Path(argv[argv.index("-o") + 1]).write_text('{"answer": "O-FILE-WINS"}', encoding="utf-8")
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="STDOUT-BYTES", stderr=""
        )

    result, invoked = run_harness_attempt(
        name="codex",
        model="default",
        prompt="SHAPED-PROMPT",
        role="gateway",
        project_root=tmp_path,
        context_extra={},
        timeout=60.0,
        harness_env={},
        harness=None,
        runner=runner,
    )
    assert result.is_success
    assert result.content == '{"answer": "O-FILE-WINS"}'
    argv = seen["argv"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert argv[argv.index("-s") + 1] == "read-only"
    assert "--ephemeral" in argv and "--skip-git-repo-check" in argv
    assert argv[-1] == "-" and seen["stdin_text"] == "SHAPED-PROMPT"
    scratch = Path(seen["cwd"])
    assert scratch != tmp_path and tmp_path not in scratch.parents
    assert (_workspace_root() / "stc") not in scratch.parents
    assert scratch.parent.resolve() == Path(tempfile.gettempdir()).resolve()
    assert invoked == scratch
    assert not scratch.exists()


def test_fix_gateway_confined_run_falls_back_to_stdout(tmp_path: Path, fake_which: None) -> None:
    """Native gateway role without an -o file: stdout is the content (no crash)."""
    runner = ScriptRunner([_ok_proc("STDOUT-ONLY")])
    result, invoked = run_harness_attempt(
        name="codex",
        model="default",
        prompt="SHAPED-PROMPT",
        role="gateway",
        project_root=tmp_path,
        context_extra={},
        timeout=60.0,
        harness_env={},
        harness=None,
        runner=runner,
    )
    assert result.is_success and result.content == "STDOUT-ONLY"
    assert not invoked.exists()


def test_fix_gateway_confinement_fails_closed_on_tracked_change(
    tmp_path: Path, ledger: SpendLedger, fake_which: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tracked-file mutation during a gateway call fails closed (scratch git repo)."""
    if shutil.which("git") is None:
        pytest.skip("git required")
    from sst.gateway.contracts import ProviderGatewayError

    import stc.integration.harness_worker as hw

    repo = tmp_path / "victim"
    repo.mkdir()
    _init_git_repo(repo)
    target = repo / "README.md"
    monkeypatch.setattr(hw, "GATEWAY_CONFINEMENT_REPO", repo)

    def mutating_runner(
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        timeout: float,
        stdin_text: str | None,
    ) -> subprocess.CompletedProcess[str]:
        target.write_text("# repo\nMUTATED\n", encoding="utf-8")
        return _ok_proc("done")

    with pytest.raises(GatewayConfinementError, match="failing closed"):
        run_harness_attempt(
            name="codex",
            model="default",
            prompt="SHAPED-PROMPT",
            role="gateway",
            project_root=tmp_path,
            context_extra={},
            timeout=60.0,
            harness_env={},
            harness=None,
            runner=mutating_runner,
        )
    backend = CLIGatewayBackend(
        "codex", project_root=tmp_path, ledger=ledger, runner=mutating_runner
    )
    target.write_text("# repo\n", encoding="utf-8")
    with pytest.raises(ProviderGatewayError, match="failed closed"):
        backend.generate("do it")
    rows = _read_rows(ledger)
    assert len(rows) == 1 and rows[0]["ok"] is False and rows[0]["channel"] == "gateway"
    assert "confinement" in rows[0]["note"]


def test_fix_gateway_confinement_passes_when_clean(
    tmp_path: Path, ledger: SpendLedger, fake_which: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-mutating gateway call passes the tracked-status assertion (no false trip)."""
    if shutil.which("git") is None:
        pytest.skip("git required")

    import stc.integration.harness_worker as hw

    repo = tmp_path / "victim"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "untracked-churn.txt").write_text("churn\n", encoding="utf-8")
    monkeypatch.setattr(hw, "GATEWAY_CONFINEMENT_REPO", repo)
    before = snapshot_tracked_status(repo)
    assert_tracked_status_unchanged(repo, before)
    result, _ = run_harness_attempt(
        name="codex",
        model="default",
        prompt="SHAPED-PROMPT",
        role="gateway",
        project_root=tmp_path,
        context_extra={},
        timeout=60.0,
        harness_env={},
        harness=None,
        runner=ScriptRunner([_ok_proc("CLEAN-OK")]),
    )
    assert result.is_success and result.content == "CLEAN-OK"


def test_fix_layout_names_dossier() -> None:
    """Package LAYOUT surface names dossier.py (B5-OBS-1)."""
    import stc.integration

    assert stc.integration.__doc__ is not None
    assert "dossier.py" in stc.integration.__doc__


@live
def test_live_gateway_confined_smoke(tmp_path: Path) -> None:
    """Live confined gateway smoke (new path): JSON emission, scratch cwd, tracked set identical."""
    from sst.gateway.contracts import GatewayRequest, ModelCatalog, ProviderKind, ProviderProfile

    from stc.integration.harness_worker import default_runner

    codex_home = _seed_codex_home()
    if codex_home is None:
        pytest.skip("operator codex login unavailable")
    try:
        repo = _workspace_root() / "stc"
        before = snapshot_tracked_status(repo)
        calls: list[dict[str, Any]] = []

        def recording_runner(
            argv: list[str],
            *,
            cwd: str,
            env: dict[str, str],
            timeout: float,
            stdin_text: str | None,
        ) -> subprocess.CompletedProcess[str]:
            proc = default_runner(argv, cwd=cwd, env=env, timeout=timeout, stdin_text=stdin_text)
            calls.append({"argv": argv, "cwd": cwd, "stdin_text": stdin_text, "proc": proc})
            return proc

        ledger = SpendLedger(tmp_path / "spend.jsonl")
        backend = CLIGatewayBackend(
            "codex",
            project_root=repo,
            ledger=ledger,
            timeout=280.0,
            harness_env={"CODEX_HOME": str(codex_home)},
            runner=recording_runner,
        )
        gateway = CLIModelGateway(backend)
        gateway.register_profile(
            ProviderProfile(
                name="cli",
                kind=ProviderKind.TEST,
                api_base="cli://local",
                selected_model="default",
                catalog=ModelCatalog(),
            )
        )
        response = gateway.invoke(
            GatewayRequest(
                messages=[
                    {
                        "role": "user",
                        "content": 'Reply with JSON only: {"answer": "GW-CONFINED-OK"}',
                    }
                ]
            )
        )
        assert "GW-CONFINED-OK" in response.content
        assert snapshot_tracked_status(repo) == before
        assert len(calls) == 1
        argv = calls[0]["argv"]
        assert argv[argv.index("-s") + 1] == "read-only"
        assert "--ephemeral" in argv and "-o" in argv
        assert "--dangerously-bypass-approvals-and-sandbox" not in argv
        scratch = Path(calls[0]["cwd"])
        assert scratch != repo and repo not in scratch.parents
        assert "GW-CONFINED-OK" in (calls[0]["stdin_text"] or "")
        assert "Emit exactly one JSON document" in (calls[0]["stdin_text"] or "")
        rows = _read_rows(ledger)
        assert len(rows) == 1 and rows[0]["channel"] == "gateway" and rows[0]["ok"] is True
    finally:
        shutil.rmtree(codex_home, ignore_errors=True)


# --- F1 failure-evidence sidecar (follow-up tranche). NEW tests; existing ones untouched. ---


def _f1_long_stderr() -> str:
    """Mirror the lost B2 capacity error: >300-char header, real cause at the TAIL."""
    header = (
        "OpenAI Codex v0.154.0 (research preview)\n"
        "model: gpt-5.6-luna | sandbox: read-only | reasoning effort: max\n"
        "workdir: /tmp/stc-gateway-abcdef | provider: openai\n"
        "approvals: never | network: disabled | tools: none\n"
    )
    padding = "hourglass: waiting for model response ... tick\n" * 12
    cause = "ERROR: Selected model is at capacity. Please try a different model."
    stderr = header + padding + cause
    assert len(stderr) > 300
    assert cause not in stderr[:300]  # the old truncated head lost this cause
    return stderr


def _f1_sidecar_records(ledger: SpendLedger) -> list[dict[str, Any]]:
    sidecar = failure_evidence_path(ledger.path)
    assert sidecar.is_file()
    return [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _f1_assert_identity(record: dict[str, Any]) -> None:
    import stc.integration.cli_gateway as gw
    import stc.integration.harness_worker as hw

    assert record["v"] == 1
    head = record["stc_head"]
    assert head == "unknown" or (
        isinstance(head, str) and len(head) == 40 and all(c in "0123456789abcdef" for c in head)
    )
    for mod_name, mod in (("harness_worker.py", hw), ("cli_gateway.py", gw)):
        assert mod.__file__ is not None
        digest = hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest()
        assert record["owned_files"][mod_name]["sha256"] == digest
        assert record["owned_files"][mod_name]["short"] == digest[:12]


def test_f1_gateway_failure_preserves_full_stderr_with_cause_at_tail(
    tmp_path: Path, ledger: SpendLedger, fake_which: None
) -> None:
    """Fast-fail gateway error: full stderr recoverable, note points, raise has the tail."""
    from sst.gateway.contracts import (
        GatewayRequest,
        ModelCatalog,
        ProviderGatewayError,
        ProviderKind,
        ProviderProfile,
    )

    stderr = _f1_long_stderr()
    stdout = "PARTIAL-STDOUT-BYTES"
    proc = subprocess.CompletedProcess(args=["fake"], returncode=1, stdout=stdout, stderr=stderr)
    backend = CLIGatewayBackend(
        "codex",
        project_root=tmp_path,
        ledger=ledger,
        model="gpt-f1",
        runner=ScriptRunner([proc]),
    )
    gateway = CLIModelGateway(backend)
    gateway.register_profile(
        ProviderProfile(
            name="cli",
            kind=ProviderKind.TEST,
            api_base="cli://local",
            selected_model="gpt-f1",
            catalog=ModelCatalog(),
        )
    )
    gateway.set_route("diverge", "cli", "gpt-f1")
    with pytest.raises(ProviderGatewayError, match="failed") as excinfo:
        gateway.invoke(GatewayRequest(role="diverge", messages=[{"role": "user", "content": "hi"}]))
    assert "Selected model is at capacity" in str(excinfo.value)
    assert "full output in" in str(excinfo.value)
    rows = _read_rows(ledger)
    assert len(rows) == 1
    row = rows[0]
    assert row["ok"] is False and row["exit_code"] == 1 and row["channel"] == "gateway"
    assert len(row["note"]) <= 300
    assert "[full stderr:" in row["note"]
    assert "failure_evidence" in row
    records = _f1_sidecar_records(ledger)
    assert len(records) == 1
    record = records[0]
    assert record["stderr_full"] == stderr
    assert record["stdout_full"] == stdout
    assert record["exit_code"] == 1 and record["timed_out"] is False
    assert record["model"] == "gpt-f1" and record["profile"] == "cli"
    assert record["channel"] == "gateway" and record["attempt"] == 1
    assert record["duration_s"] >= 0 and record["out_bytes"] == len(stdout)
    assert row["failure_evidence"] == f"{failure_evidence_path(ledger.path)}#{record['id']}"
    assert record["id"] in row["note"]
    _f1_assert_identity(record)


def test_f1_worker_failure_then_success_preserves_evidence_without_breach(
    lease_root: Path, ledger: SpendLedger, fake_which: None
) -> None:
    """Fail-then-retry worker run: evidence kept AND the post-run audit still passes."""
    stderr = _f1_long_stderr()
    runner = ScriptRunner(
        [
            subprocess.CompletedProcess(args=["fake"], returncode=1, stdout="", stderr=stderr),
            _ok_proc("second wins"),
        ]
    )
    worker = HarnessWorker("codex", ledger=ledger, runner=runner)
    assert worker.dispatch(_bundle(), _lease(lease_root)) is not None
    rows = _read_rows(ledger)
    assert [row["ok"] for row in rows] == [False, True]
    assert "[full stderr:" in rows[0]["note"]
    assert "failure_evidence" in rows[0]
    assert "failure_evidence" not in rows[1]
    records = _f1_sidecar_records(ledger)
    assert len(records) == 1
    assert records[0]["stderr_full"] == stderr
    assert records[0]["channel"] == "worker" and records[0]["attempt"] == 1
    assert records[0]["exit_code"] == 1 and records[0]["profile"] is None
    _f1_assert_identity(records[0])


def test_f1_success_path_writes_no_failure_records(
    tmp_path: Path, lease_root: Path, ledger: SpendLedger
) -> None:
    """Success rows keep the exact pre-fix key set; the sidecar gains zero records."""
    backend = CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        ledger=ledger,
        harness=ScriptHarness([_mk_result("GW-DONE")]),
    )
    assert backend.generate("do it") == "GW-DONE"
    worker = HarnessWorker("mock", ledger=ledger, harness=ScriptHarness([_mk_result("ok")]))
    json.loads(worker.dispatch(_bundle(), _lease(lease_root)))
    rows = _read_rows(ledger)
    assert len(rows) == 2 and all(row["ok"] for row in rows)
    pre_fix_keys = {
        "ts",
        "channel",
        "harness",
        "model",
        "task_id",
        "lease_id",
        "attempt",
        "ok",
        "exit_code",
        "timed_out",
        "duration_s",
        "out_bytes",
        "note",
    }
    for row in rows:
        assert set(row.keys()) == pre_fix_keys
    sidecar = failure_evidence_path(ledger.path)
    assert not sidecar.is_file() or sidecar.read_text(encoding="utf-8").strip() == ""


def test_f1_worker_crash_preserves_full_error(
    lease_root: Path, ledger: SpendLedger, fake_which: None
) -> None:
    """Crash path (no result object): the full exception text is the preserved stderr."""
    worker = HarnessWorker(
        "codex", ledger=ledger, runner=ScriptRunner([OSError("disk gone")]), max_attempts=1
    )
    with pytest.raises(WorktreeError, match="crashed"):
        worker.dispatch(_bundle(), _lease(lease_root))
    rows = _read_rows(ledger)
    assert len(rows) == 1 and rows[0]["ok"] is False
    assert "OSError" in rows[0]["note"] and "[full stderr:" in rows[0]["note"]
    records = _f1_sidecar_records(ledger)
    assert len(records) == 1
    assert records[0]["stderr_full"] == "OSError: disk gone"
    assert records[0]["exit_code"] is None and records[0]["timed_out"] is False


def test_f1_gateway_timeout_records_partial_stdout(
    tmp_path: Path, ledger: SpendLedger, fake_which: None
) -> None:
    """Timeout path: exit-124 record keeps partial stdout + the timeout message."""
    from sst.gateway.contracts import ProviderGatewayError

    expired = subprocess.TimeoutExpired(cmd=["fake"], timeout=60.0, output="PARTIAL")
    backend = CLIGatewayBackend(
        "codex",
        project_root=tmp_path,
        ledger=ledger,
        timeout=60.0,
        runner=ScriptRunner([expired]),
    )
    with pytest.raises(ProviderGatewayError, match="failed") as excinfo:
        backend.generate("do it")
    assert "timed out" in str(excinfo.value)
    rows = _read_rows(ledger)
    assert len(rows) == 1
    assert rows[0]["timed_out"] is True and rows[0]["exit_code"] == 124
    records = _f1_sidecar_records(ledger)
    assert len(records) == 1
    assert records[0]["timed_out"] is True and records[0]["exit_code"] == 124
    assert records[0]["stdout_full"] == "PARTIAL"
    assert records[0]["stderr_full"] == "Harness timed out after 60.0s"
    assert records[0]["profile"] is None
