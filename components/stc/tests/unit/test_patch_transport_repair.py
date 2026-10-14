"""Option 1 transport repair: restore the stripped trailing newline pre-apply.

The SST controller strips the trailing newline of every ``proposed_changes``
(``SSTSearchController._clean_code``; SST is read-only per D7), so STC
custody failed ``git apply`` with "corrupt patch" while the SST fallback only
rescues single-file ``---/+++`` diffs. The STC-owned repair
(:func:`restore_patch_trailing_newline`, applied at both custody-apply seams
in ``dialectic_runner.py``) restores exactly one LF before the apply call.

Option 2 (Part E): model emitters miscount ``@@`` hunk ``oldcount`` /
``newcount`` while context stays verbatim, and ``git apply`` rejects the
patch as corrupt before judging content (csvledger run-1 triage: 15/15
rejections, all rescued by ``git apply --recount``). The STC-owned repair
(:func:`recount_patch_hunk_headers`, chained before Option 1 at both
seams) recomputes counts only; starts, section text, and body lines pass
through so ``git apply`` still judges the actual content.

Scripted only: scratch git repos + fake substrate/gateway in-process; no
model calls, no network. Behavior-critical bytes are pinned (size + sha256).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sst.core.contracts import CandidateProposal, TaskPacket
from sst.gateway.contracts import GatewayRequest, GatewayResponse
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager, PatchApplicationResult
from sst.search.policy import SearchPolicy

from stc.integration.adapters import AdapterContext, Budgets
from stc.integration.dialectic_runner import (
    DialecticRunner,
    NoChampionResult,
    STCCustodyWrapper,
    _routes_to_git_apply,
    _with_recounted_patch_headers,
    _with_restored_patch_newline,
)
from stc.integration.diff_binding import (
    recount_patch_hunk_headers,
    recount_patch_hunk_headers_bytes,
    restore_patch_trailing_newline,
    restore_patch_trailing_newline_bytes,
)
from stc.schemas.models import (
    ExecutionReceipt,
    FileTarget,
    GateReport,
    JudiciaryVerdict,
    TaskBundle,
)

# --- Pinned behavior-critical bytes (size + sha256; drift fails loudly) ---

_MOD_PRE = b"line1\nold\nline3\n"
_MOD_PRE_PIN = (16, "40720d6b7d52b4b455b143dd581f92919cf86821caccbd26fea675a4d6a5950e")
_OTHER_PRE = b"a1\nb1\n"
_OTHER_PRE_PIN = (6, "f2833555023ddfa36e9256af3b3940e17e0fd88daf28d98e0098c935aff98e01")
_MOD_POST_ONE = b"line1\nnew\nline3\n"
_MOD_POST_ONE_PIN = (
    16,
    "a638d02df67c851a05a8640042d10c7064cf73deacf555e68f7895733c377b91",
)
_OTHER_POST = b"a1\nb2\n"
_OTHER_POST_PIN = (6, "dc670a7a6993f5f4ccdd619895af00e4adc2fda46d95cdd7e5ee745e0c49025b")
_MERGE_POST = b'def add(a: int, b: int) -> int:\n    """Repaired branch."""\n    return a + b\n'
_MERGE_POST_PIN = (
    76,
    "77ead0b6efd9a169ebaac3d87b5349744e240e793e8d5c539f7a72c9e2b515d7",
)

_ONE_FULL = "--- a/mod.py\n+++ b/mod.py\n@@ -1,3 +1,3 @@\n line1\n-old\n+new\n line3\n"
_ONE_FULL_PIN = (66, "583b28407e59e657a5ab0babfecc598f3427f914e353b94ffa517128f53f4a64")
_MULTI_FULL = (
    "diff --git a/mod.py b/mod.py\n"
    "--- a/mod.py\n"
    "+++ b/mod.py\n"
    "@@ -1,3 +1,3 @@\n"
    " line1\n"
    "-old\n"
    "+new\n"
    " line3\n"
    "diff --git a/other.py b/other.py\n"
    "--- a/other.py\n"
    "+++ b/other.py\n"
    "@@ -1,2 +1,2 @@\n"
    " a1\n"
    "-b1\n"
    "+b2\n"
)
_MULTI_FULL_PIN = (
    186,
    "d1f938b839ac0dc03393037471fd86bd95fc67c9d2b6e31f394d2b4866e2c2ac",
)
_MERGE_DIFF_FULL = (
    "--- a/mod.py\n"
    "+++ b/mod.py\n"
    "@@ -1,3 +1,3 @@\n"
    " def add(a: int, b: int) -> int:\n"
    '-    """Good branch."""\n'
    '+    """Repaired branch."""\n'
    "     return a + b\n"
)
_MERGE_DIFF_FULL_PIN = (
    145,
    "25aa7eb5426f183ffbed42f564e1df77fc4a2bd1af6e90cd515f0e1a4c4a7c8f",
)

_GOOD_CODE = 'def add(a: int, b: int) -> int:\n    """Good branch."""\n    return a + b\n'


def _pinned(data: bytes, pin: tuple[int, str], name: str) -> bytes:
    size, sha = pin
    assert len(data) == size, f"{name} size drift"
    assert hashlib.sha256(data).hexdigest() == sha, f"{name} byte drift"
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- Part A: normalization unit cases ---

_RESTORE_CASES: list[tuple[str, bytes, bytes]] = [
    ("missing", b"--- a/f\n+x", b"--- a/f\n+x\n"),
    ("present", b"--- a/f\n+x\n", b"--- a/f\n+x\n"),
    ("empty", b"", b""),
    ("multi-lf", b"a\n\n", b"a\n\n"),
    ("single-lf", b"\n", b"\n"),
    ("cr-only-end", b"line\r", b"line\r\n"),
    ("only-cr", b"\r", b"\r\n"),
    ("crlf-interior-preserved", b"a\r\nb", b"a\r\nb\n"),
    ("crlf-terminated", b"a\r\n", b"a\r\n"),
    ("full-patch", _ONE_FULL[:-1].encode(), _ONE_FULL.encode()),
]


@pytest.mark.parametrize(("name", "raw", "expected"), _RESTORE_CASES)
def test_restore_bytes_cases(name: str, raw: bytes, expected: bytes) -> None:
    _ = name
    got = restore_patch_trailing_newline_bytes(raw)
    assert got == expected
    if raw and not raw.endswith(b"\n"):
        assert got == raw + b"\n"  # exactly one LF, every other byte kept
        assert len(got) == len(raw) + 1
    else:
        assert got == raw  # identity: empty, terminated, or multi-LF
    assert restore_patch_trailing_newline_bytes(got) == got  # idempotent


@pytest.mark.parametrize(("name", "raw", "expected"), _RESTORE_CASES)
def test_restore_str_cases(name: str, raw: bytes, expected: bytes) -> None:
    _ = name
    text, want = raw.decode("utf-8"), expected.decode("utf-8")
    got = restore_patch_trailing_newline(text)
    assert got == want
    assert got.encode("utf-8") == restore_patch_trailing_newline_bytes(raw)  # parity
    assert restore_patch_trailing_newline(got) == got  # idempotent


def test_restore_does_not_fold_line_endings() -> None:
    """Unlike normalize_diff: CRLF/CR bytes pass through untouched (append-only)."""
    raw = b"diff --git a/f b/f\r\n--- a/f\r\n+++ b/f\r\n@@ -1 +1 @@\r\n-a\r\n+b"
    got = restore_patch_trailing_newline_bytes(raw)
    assert got == raw + b"\n"
    assert b"\r\n" in got  # no folding to LF


def test_restore_pinned_full_patches_roundtrip() -> None:
    _pinned(_ONE_FULL.encode(), _ONE_FULL_PIN, "one-file patch")
    _pinned(_MULTI_FULL.encode(), _MULTI_FULL_PIN, "multi-file patch")
    _pinned(_MERGE_DIFF_FULL.encode(), _MERGE_DIFF_FULL_PIN, "merge patch")
    for full in (_ONE_FULL, _MULTI_FULL, _MERGE_DIFF_FULL):
        assert restore_patch_trailing_newline(full) == full  # already terminated
        assert restore_patch_trailing_newline(full[:-1]) == full  # strip repaired


# --- Part B: proposal-level helper ---


def _proposal(
    candidate_id: str = "cand-t1",
    patch_diff: str = "",
    *,
    targets: list[str] | None = None,
    file_ops: list[dict[str, Any]] | None = None,
) -> CandidateProposal:
    return CandidateProposal(
        candidate_id=candidate_id,
        tree_id="tree-t",
        role="DIVERGE",
        title=f"Proposal {candidate_id}",
        rationale="transport-repair test",
        target_paths=targets if targets is not None else ["mod.py"],
        patch_diff=patch_diff,
        file_operations=file_ops if file_ops is not None else [],
        model_id="scripted-test-double",
    )


def test_with_restored_newline_identity_when_nothing_to_repair() -> None:
    for diff in ("", _ONE_FULL, _MULTI_FULL):
        proposal = _proposal(patch_diff=diff)
        assert _with_restored_patch_newline(proposal) is proposal


def test_with_restored_newline_copies_only_patch_diff() -> None:
    proposal = _proposal(patch_diff=_ONE_FULL[:-1], targets=["mod.py", "other.py"])
    fixed = _with_restored_patch_newline(proposal)
    assert fixed is not proposal
    assert fixed.patch_diff == _ONE_FULL
    assert proposal.patch_diff == _ONE_FULL[:-1]  # original untouched
    before = proposal.model_dump(exclude={"patch_diff"})
    after = fixed.model_dump(exclude={"patch_diff"})
    assert before == after
    assert _with_restored_patch_newline(fixed) is fixed  # idempotent


_ROUTE_CASES: list[tuple[str, str, bool, bool]] = [
    ("dash-headers", _ONE_FULL[:-1], True, False),
    ("git-headers", _MULTI_FULL[:-1], True, False),
    ("hunk-only", "@@ -1,3 +1,3 @@\n line1\n-old\n+new", True, False),
    # at-signs-in-text: inherited SST @@-substring rule — non-diff text with
    # @@ routes to git (faithful mirror, deliberate); both git and fallback
    # still reject it, and STC keeps the original bytes. Do not "fix".
    ("at-signs-in-text", "x = a @@ b  # matrix twice", True, False),
    ("raw-code", _GOOD_CODE.strip(), False, False),
    ("raw-code-terminated", _GOOD_CODE, False, False),
    ("empty", "", False, False),
    ("file-ops-win", _ONE_FULL[:-1], False, True),
]


@pytest.mark.parametrize(("name", "diff", "expected", "with_ops"), _ROUTE_CASES)
def test_routes_to_git_apply_mirrors_sst_dispatch(
    name: str, diff: str, expected: bool, with_ops: bool
) -> None:
    """Gate mirror of SST's git-apply dispatch (custody.py, read-only)."""
    _ = name
    ops = [{"path": "mod.py", "content": diff, "action": "write"}] if with_ops else None
    assert _routes_to_git_apply(_proposal("cand-r", diff, file_ops=ops)) is expected


def test_with_restored_newline_raw_code_identity() -> None:
    """Raw-code payloads pass through byte-exact (raw-merge contract)."""
    for diff in (_GOOD_CODE.strip(), _GOOD_CODE, "print('hi')"):
        proposal = _proposal("cand-raw", diff)
        assert _with_restored_patch_newline(proposal) is proposal


def test_with_restored_newline_file_operations_identity() -> None:
    """File-operation proposals are untouched (SST ignores patch_diff there)."""
    proposal = _proposal(
        "cand-ops",
        _ONE_FULL[:-1],
        file_ops=[{"path": "mod.py", "content": "x = 1\n", "action": "write"}],
    )
    assert _with_restored_patch_newline(proposal) is proposal


# --- Part C: apply path through the REAL custody entry point (scratch git repo) ---


@dataclass
class _GitApplyCall:
    argv: list[str]
    returncode: int


def _install_git_spy(monkeypatch: pytest.MonkeyPatch) -> list[_GitApplyCall]:
    """Recording passthrough on subprocess.run (installed AFTER scratch setup)."""
    real_run = subprocess.run
    calls: list[_GitApplyCall] = []

    def _spy(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        result = real_run(*args, **kwargs)
        argv = args[0] if args else kwargs.get("args", [])
        if isinstance(argv, list) and argv[:2] == ["git", "apply"]:
            calls.append(_GitApplyCall(argv=list(argv), returncode=result.returncode))
        return result

    monkeypatch.setattr(subprocess, "run", _spy)
    return calls


def _scratch_repo(tmp_path: Path, name: str = "ws") -> Path:
    """Scratch git repo with pinned pre-image bytes (mirrors the lease shape)."""
    if shutil.which("git") is None:
        pytest.skip("git required for custody apply-path tests")
    _pinned(_MOD_PRE, _MOD_PRE_PIN, "mod.py pre-image")
    _pinned(_OTHER_PRE, _OTHER_PRE_PIN, "other.py pre-image")
    ws = tmp_path / name
    ws.mkdir()
    (ws / "mod.py").write_bytes(_MOD_PRE)
    (ws / "other.py").write_bytes(_OTHER_PRE)
    subprocess.run(["git", "-C", str(ws), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(ws), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(ws),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "init",
        ],
        check=True,
    )
    return ws


def _packet(
    task_id: str = "T1",
    source_root: str = "/tmp/src",
    *,
    allowed: list[str] | None = None,
    forbidden: list[str] | None = None,
) -> TaskPacket:
    return TaskPacket(
        task_id=task_id,
        goal="transport-repair test goal",
        source_repo_root=source_root,
        base_commit="abc",
        snapshot_hash="snap",
        allowed_paths=allowed if allowed is not None else ["mod.py", "other.py"],
        forbidden_paths=forbidden if forbidden is not None else [],
        acceptance_commands=["true"],
        evidence_references={"stc.epoch_index": "1"},
    )


def _apply_via_seam(
    mgr: CandidateCustodyManager, proposal: CandidateProposal, ws: Path, task: TaskPacket
) -> PatchApplicationResult:
    """The exact expression both seams execute (node verify + merge apply)."""
    return mgr.apply_proposal(
        _with_restored_patch_newline(_with_recounted_patch_headers(proposal)),
        ws,
        task=task,
    )


def _custody(tmp_path: Path) -> CandidateCustodyManager:
    return CandidateCustodyManager(base_worktree_dir=tmp_path / "custody")


def test_single_file_stripped_applies_via_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripped valid 1-file patch applies through git with exact bytes."""
    ws = _scratch_repo(tmp_path)
    spy = _install_git_spy(monkeypatch)
    result = _apply_via_seam(_custody(tmp_path), _proposal("cand-1", _ONE_FULL[:-1]), ws, _packet())
    assert result.success is True, result.error_message
    assert [call.returncode for call in spy] == [0]  # git path, no fallback
    assert (ws / "mod.py").read_bytes() == _pinned(
        _MOD_POST_ONE, _MOD_POST_ONE_PIN, "mod.py post-image"
    )
    assert _sha((ws / "mod.py").read_bytes()) == _MOD_POST_ONE_PIN[1]
    assert (ws / "other.py").read_bytes() == _OTHER_PRE  # untouched


def test_multifile_stripped_applies_via_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripped valid multi-file patch applies through git with exact bytes."""
    ws = _scratch_repo(tmp_path)
    spy = _install_git_spy(monkeypatch)
    result = _apply_via_seam(
        _custody(tmp_path),
        _proposal("cand-m", _MULTI_FULL[:-1], targets=["mod.py", "other.py"]),
        ws,
        _packet(),
    )
    assert result.success is True, result.error_message
    assert [call.returncode for call in spy] == [0]  # git path, no fallback
    assert (ws / "mod.py").read_bytes() == _pinned(
        _MOD_POST_ONE, _MOD_POST_ONE_PIN, "mod.py post-image"
    )
    assert (ws / "other.py").read_bytes() == _pinned(
        _OTHER_POST, _OTHER_POST_PIN, "other.py post-image"
    )
    assert _sha((ws / "mod.py").read_bytes()) == _MOD_POST_ONE_PIN[1]
    assert _sha((ws / "other.py").read_bytes()) == _OTHER_POST_PIN[1]


def test_multifile_beyond_fallback_proves_git_path(tmp_path: Path) -> None:
    """The SST fallback cannot apply the multi-file patch, so success is git's."""
    mgr = _custody(tmp_path)
    assert "diff --git" in _MULTI_FULL  # the form the fallback rejects
    err = mgr._apply_unified_diff_manually(_MULTI_FULL, _scratch_repo(tmp_path), task=_packet())
    assert isinstance(err, str) and err != ""
    err_stripped = mgr._apply_unified_diff_manually(
        _MULTI_FULL[:-1], _scratch_repo(tmp_path, "ws2"), task=_packet()
    )
    assert isinstance(err_stripped, str) and err_stripped != ""


def test_unrepaired_multifile_stripped_fails_control(tmp_path: Path) -> None:
    """Control: without the repair, the stripped multi-file patch is rejected."""
    ws = _scratch_repo(tmp_path)
    mgr = _custody(tmp_path)
    result = mgr.apply_proposal(
        _proposal("cand-ctl", _MULTI_FULL[:-1], targets=["mod.py", "other.py"]),
        ws,
        task=_packet(),
    )
    assert result.success is False
    assert "corrupt patch" in (result.error_message or "")
    assert (ws / "mod.py").read_bytes() == _MOD_PRE  # bytes unchanged
    assert (ws / "other.py").read_bytes() == _OTHER_PRE


def test_raw_code_passthrough_byte_exact(tmp_path: Path) -> None:
    """Raw-code payloads apply byte-exact: no newline is appended (contract)."""
    ws = _scratch_repo(tmp_path)
    raw = _GOOD_CODE.strip()  # what the controller's _clean_code emits
    assert not raw.endswith("\n")
    result = _apply_via_seam(
        _custody(tmp_path), _proposal("cand-raw", raw), ws, _packet(allowed=["mod.py"])
    )
    assert result.success is True, result.error_message
    assert (ws / "mod.py").read_bytes() == raw.encode("utf-8")
    assert _sha((ws / "mod.py").read_bytes()) == _sha(raw.encode("utf-8"))


# --- Part D: negatives matrix (rejection + containment preserved) ---

_MALFORMED = "--- a/mod.py\nTHIS IS NOT A DIFF\n@@ bogus @@\n"
_TRUNC_MIDLINE = _ONE_FULL[:-3]  # cut mid content line, no trailing newline
_TRUNC_HUNKHDR = _ONE_FULL[: _ONE_FULL.index("@@") + 6]  # cut mid hunk header
_WRONG_CTX = "--- a/mod.py\n+++ b/mod.py\n@@ -1,3 +1,3 @@\n WRONGCTX\n-old\n+new\n line3\n"
_ESCAPE_DIFF = "--- a/../escape.txt\n+++ b/../escape.txt\n@@ -0,0 +1 @@\n+pwned\n"

_NEGATIVES: list[tuple[str, str, list[str], dict[str, list[str]]]] = [
    ("malformed", _MALFORMED, ["mod.py"], {}),
    ("truncated-midline", _TRUNC_MIDLINE, ["mod.py"], {}),
    ("truncated-hunkhdr", _TRUNC_HUNKHDR, ["mod.py"], {}),
    ("wrong-context", _WRONG_CTX, ["mod.py"], {}),
    ("escape-target-path", _ONE_FULL, ["../escape.txt"], {}),
    ("escape-diff-internal", _ESCAPE_DIFF, ["mod.py"], {}),
    ("forbidden-path", _ONE_FULL, ["mod.py"], {"forbidden_paths": ["mod.py"]}),
]


@pytest.mark.parametrize(("name", "diff", "targets", "task_kw"), _NEGATIVES)
def test_negatives_still_rejected(
    tmp_path: Path, name: str, diff: str, targets: list[str], task_kw: dict[str, list[str]]
) -> None:
    """Each negative fails raw (genuine) AND via the seam (no gate weakening)."""
    mgr = _custody(tmp_path)
    task = _packet(
        allowed=["mod.py", "other.py"],
        forbidden=task_kw.get("forbidden_paths"),
    )
    ws = _scratch_repo(tmp_path)
    raw = mgr.apply_proposal(_proposal(f"c-raw-{name}", diff, targets=targets), ws, task=task)
    assert raw.success is False, f"{name}: raw unexpectedly applied"
    via_seam = _apply_via_seam(mgr, _proposal(f"c-seam-{name}", diff, targets=targets), ws, task)
    assert via_seam.success is False, f"{name}: repair weakened the gate"
    assert (ws / "mod.py").read_bytes() == _MOD_PRE  # target bytes unchanged
    assert (ws / "other.py").read_bytes() == _OTHER_PRE
    assert not (tmp_path / "escape.txt").exists()  # no ../ escape artifact
    assert not (ws / "escape.txt").exists()


# --- Part E: seam wiring (node verify + full merge, scripted fakes) ---


def _gate(name: str) -> GateReport:
    return GateReport(
        gate_name=name,
        exit_code=0,
        duration_seconds=0.5,
        violations_count=0,
        raw_output_snippet="ok",
    )


def _receipt(task_id: str = "T1") -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id="rc-transport",
        task_id=task_id,
        epoch_index=1,
        commit_hash="abc",
        timestamp_utc="2026-09-13T00:00:00Z",
        python_version="3.12",
        os_platform="linux",
        gate_ruff=_gate("ruff"),
        gate_mypy=_gate("mypy"),
        gate_pytest=_gate("pytest"),
        gate_mutmut=GateReport(
            gate_name="mutmut",
            exit_code=0,
            duration_seconds=0.0,
            violations_count=0,
            raw_output_snippet="Mutmut Gate disabled by runner configuration.",
        ),
        sha256_signature="test-signature",
    )


class _FakeSubstrate:
    """Scripted substrate: always passing, calls recorded (offline)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        **kwargs: Any,
    ) -> ExecutionReceipt:
        self.calls.append({"worktree": str(worktree_path), "task_id": task_id, **kwargs})
        return _receipt(task_id)

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool:
        _ = receipt
        return True


def test_node_seam_stripped_diff_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Node seam: a stripped unified diff verifies through the real wrapper."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_bytes(_MOD_PRE)
    substrate: Any = _FakeSubstrate()
    wrapper = STCCustodyWrapper(_custody(tmp_path), substrate, leases_root=tmp_path / "leases")
    spy = _install_git_spy(monkeypatch)
    result = wrapper.verify_candidate_proposal(
        _packet(source_root=str(src), allowed=["mod.py"]),
        _proposal("cand-node", _ONE_FULL[:-1]),
        src,
    )
    assert result.passed is True, result.stderr
    assert [call.returncode for call in spy] == [0]  # git path, no fallback
    assert wrapper.binding_diffs["cand-node"] != b""  # full path ran
    assert list((tmp_path / "leases").iterdir()) == [tmp_path / "leases" / "_quarantine"]


class _ScriptGateway(ModelGateway):
    """Gateway serving scripted role responses (deterministic search)."""

    def __init__(self, handler: Any) -> None:
        super().__init__(profiles={}, routes={})
        self.profiles["test"] = "test"  # type: ignore[assignment]
        self._handler = handler

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        content = self._handler(request)
        return GatewayResponse(content=content, model="script", profile="test")


class _FakeAuditor:
    """Scripted judiciary: one approval (offline)."""

    def __init__(self) -> None:
        self.with_codex = False
        self.calls: list[str] = []

    def audit_diff(
        self, diff_text: str, bundle: TaskBundle, receipt: ExecutionReceipt
    ) -> JudiciaryVerdict:
        _ = (bundle, receipt)
        self.calls.append(diff_text)
        return JudiciaryVerdict(
            task_id="T1", status="APPROVED", findings=[], summary_rationale="test verdict"
        )


def _git_source(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git required for merge-path test")
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text(_GOOD_CODE, encoding="utf-8")
    (src / "test_mod.py").write_text(
        "from mod import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(src), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(src),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "init",
        ],
        check=True,
    )
    return src


def test_merge_seam_controller_stripped_diff_merges_exact(tmp_path: Path) -> None:
    """Merge seam: gateway emits a valid diff; the real controller strips it.

    End-to-end through ``DialecticRunner.run`` with scripted fakes: the
    controller's ``_clean_code`` strip reproduces the production transport
    fault, and both seams (node verify + merge apply) must repair it. The
    merged bytes are asserted exact (bytes + sha256).
    """
    _pinned(_MERGE_DIFF_FULL.encode(), _MERGE_DIFF_FULL_PIN, "merge patch")

    def handle(request: GatewayRequest) -> str:
        if request.role == "diverge":
            return json.dumps(
                {
                    "branches": [
                        {
                            "strategy_title": "strategy-0",
                            "hypothesis_or_rationale": "test hypothesis",
                            "proposed_changes": _MERGE_DIFF_FULL,
                        }
                    ]
                }
            )
        if request.role == "critique":
            return json.dumps(
                {
                    "value_score": 0.9,
                    "verdict": "APPROVE",
                    "rationale": "thorough review, solid types",
                }
            )
        raise AssertionError(f"unexpected role {request.role!r}")

    src = _git_source(tmp_path)
    substrate: Any = _FakeSubstrate()
    auditor: Any = _FakeAuditor()
    runner = DialecticRunner(
        ctx=AdapterContext(
            epoch_index=1,
            spec_id="spec-1",
            budgets=Budgets(time_budget_seconds=60),
            acceptance_commands=("true",),
            source_repo_root=str(src),
            base_commit="abc",
            adapter_version="p04-test",
        ),
        gateway=_ScriptGateway(handle),
        substrate=substrate,
        evidence_root=tmp_path / "ev",
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4),
        auditor=auditor,
    )
    bundle = TaskBundle(
        task_id="T1",
        epoch_index=1,
        spec_id="spec-1",
        goal_statement="repair the docstring",
        invariants=["keep add correct"],
        target_files=[FileTarget(path="mod.py", action="modify")],
        membrane_protocols=["proto-a"],
        negative_inhibitors=[],
    )
    result = runner.run(bundle)
    assert not isinstance(result, NoChampionResult), getattr(result, "reason", "")
    merged = Path(result.evidence_dir) / "merged" / "mod.py"
    assert merged.read_bytes() == _pinned(_MERGE_POST, _MERGE_POST_PIN, "merged mod.py")
    assert _sha(merged.read_bytes()) == _MERGE_POST_PIN[1]
    assert '+    """Repaired branch."""' in result.merged_diff


# --- Part E: hunk-count recount (Option 2) ---

_MISCOUNTED_ONE = _ONE_FULL.replace("@@ -1,3 +1,3 @@", "@@ -1,5 +1,9 @@")
_MISCOUNTED_MULTI = _MULTI_FULL.replace("@@ -1,3 +1,3 @@", "@@ -1,7 +1,1 @@").replace(
    "@@ -1,2 +1,2 @@", "@@ -1,9 +1,0 @@"
)
_IMPLICIT_ONE = "--- a/f\n+++ b/f\n@@ -4 +4 @@\n-a\n+b\n"
_SECTIONED = "--- a/f\n+++ b/f\n@@ -1,9 +1,9 @@ def f():\n x\n-y\n+z\n"
_SECTIONED_FIXED = "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@ def f():\n x\n-y\n+z\n"
_NO_NEWLINE = "--- a/f\n+++ b/f\n@@ -1,4 +1,4 @@\n a\n-b\n+c\n\\ No newline at end of file\n"
_NO_NEWLINE_FIXED = "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n\\ No newline at end of file\n"
_GARBAGE_BODY = "--- a/f\n+++ b/f\n@@ -1,9 +1,9 @@\n a\n??? not a hunk line\n+b\n"
_UNPARSEABLE_HDR = "--- a/f\n+++ b/f\n@@ -x +y @@\n-a\n+b\n"

_RECOUNT_CASES: list[tuple[str, str, str]] = [
    ("miscounted-one-file", _MISCOUNTED_ONE, _ONE_FULL),
    ("miscounted-multi-file", _MISCOUNTED_MULTI, _MULTI_FULL),
    ("correct-identity", _ONE_FULL, _ONE_FULL),
    ("implicit-one-identity", _IMPLICIT_ONE, _IMPLICIT_ONE),
    ("section-preserved", _SECTIONED, _SECTIONED_FIXED),
    ("no-newline-uncounted", _NO_NEWLINE, _NO_NEWLINE_FIXED),
    ("garbage-body-conservative", _GARBAGE_BODY, _GARBAGE_BODY),
    ("unparseable-header-passthrough", _UNPARSEABLE_HDR, _UNPARSEABLE_HDR),
    ("non-diff-passthrough", _GOOD_CODE, _GOOD_CODE),
    ("empty", "", ""),
]


@pytest.mark.parametrize(("name", "raw", "expected"), _RECOUNT_CASES)
def test_recount_str_cases(name: str, raw: str, expected: str) -> None:
    _ = name
    got = recount_patch_hunk_headers(raw)
    assert got == expected
    assert recount_patch_hunk_headers(got) == got  # idempotent
    if got != raw:
        # Only header lines change: strip them and both sides are identical.
        def _no_headers(s: str) -> str:
            return "\n".join(line for line in s.split("\n") if not line.startswith("@@ "))

        assert _no_headers(got) == _no_headers(raw)
        assert got.count("@@ -") == raw.count("@@ -")


@pytest.mark.parametrize(("name", "raw", "expected"), _RECOUNT_CASES)
def test_recount_bytes_cases(name: str, raw: str, expected: str) -> None:
    _ = name
    raw_b, want_b = raw.encode("utf-8"), expected.encode("utf-8")
    got = recount_patch_hunk_headers_bytes(raw_b)
    assert got == want_b
    assert got.decode("utf-8") == recount_patch_hunk_headers(raw)  # parity
    assert recount_patch_hunk_headers_bytes(got) == got  # idempotent


def test_recount_preserves_starts_and_section() -> None:
    """Only counts change: starts, section text, and body stay byte-exact."""
    raw = "--- a/f\n+++ b/f\n@@ -42,7 +45,7 @@ def g():\n a\n-b\n+c1\n+c2\n d\n"
    got = recount_patch_hunk_headers(raw)
    assert got.split("\n")[2] == "@@ -42,3 +45,4 @@ def g():"
    assert got.split("\n")[3:] == raw.split("\n")[3:]


def test_with_recounted_headers_identity_when_correct() -> None:
    for diff in ("", _ONE_FULL, _MULTI_FULL, _GOOD_CODE):
        proposal = _proposal(patch_diff=diff)
        assert _with_recounted_patch_headers(proposal) is proposal


def test_with_recounted_headers_copies_only_patch_diff() -> None:
    proposal = _proposal(patch_diff=_MISCOUNTED_ONE, targets=["mod.py", "other.py"])
    fixed = _with_recounted_patch_headers(proposal)
    assert fixed is not proposal
    assert fixed.patch_diff == _ONE_FULL
    assert proposal.patch_diff == _MISCOUNTED_ONE  # original untouched
    before = proposal.model_dump(exclude={"patch_diff"})
    after = fixed.model_dump(exclude={"patch_diff"})
    assert before == after
    assert _with_recounted_patch_headers(fixed) is fixed  # idempotent


def test_with_recounted_headers_file_operations_identity() -> None:
    proposal = _proposal(
        "cand-ops",
        _MISCOUNTED_ONE,
        file_ops=[{"path": "mod.py", "content": "x = 1\n", "action": "write"}],
    )
    assert _with_recounted_patch_headers(proposal) is proposal


def test_unrepaired_miscounted_multifile_fails_control(tmp_path: Path) -> None:
    """Control: without the repair, miscounted headers are rejected as corrupt."""
    ws = _scratch_repo(tmp_path)
    mgr = _custody(tmp_path)
    result = mgr.apply_proposal(
        _proposal("cand-ctl", _MISCOUNTED_MULTI, targets=["mod.py", "other.py"]),
        ws,
        task=_packet(),
    )
    assert result.success is False
    assert "corrupt patch" in (result.error_message or "")
    assert (ws / "mod.py").read_bytes() == _MOD_PRE  # bytes unchanged
    assert (ws / "other.py").read_bytes() == _OTHER_PRE


def test_miscounted_multifile_applies_via_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Miscounted-but-verbatim patch applies through the seam with exact bytes."""
    ws = _scratch_repo(tmp_path)
    spy = _install_git_spy(monkeypatch)
    result = _apply_via_seam(
        _custody(tmp_path),
        _proposal("cand-m", _MISCOUNTED_MULTI, targets=["mod.py", "other.py"]),
        ws,
        _packet(),
    )
    assert result.success is True, result.error_message
    assert [call.returncode for call in spy] == [0]  # git path, no fallback
    assert (ws / "mod.py").read_bytes() == _pinned(
        _MOD_POST_ONE, _MOD_POST_ONE_PIN, "mod.py post-image"
    )
    assert (ws / "other.py").read_bytes() == _pinned(
        _OTHER_POST, _OTHER_POST_PIN, "other.py post-image"
    )
