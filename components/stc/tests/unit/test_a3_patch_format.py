"""A3 patch-format gap: emitter-frame pin + SST custody-tolerance validation.

FOLLOWUP accept-2 finding A3 (high): every live §2 proposal so far carried
codex apply_patch markers (`*** Begin Patch` / `*** Add File:` /
`*** End Patch`) in `proposed_changes` despite the unified-diff
instruction, and SST custody has no marker-tolerant path (git apply +
strict fallback reject marker-bearing diffs; non-diff payloads are
written verbatim as target files). Custody is SST-owned, so this stage
delivers (1) an STC-owned unified-diff-only pin in the gateway emitter
frame and (2) the SST custody-tolerance change as a concrete proposed
diff validated here against a scratch copy (sst itself is never
written).

All regression payloads are the EXACT live bytes from the attempt-2
dossier (cand `_0_0` 5182 B + cand `_1_0` 3929 B), embedded below and
guarded by sha256 pins plus a live cross-check against the dossier's
events.json + store.db. Zero live calls; fully deterministic.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
from sst.core.contracts import CandidateProposal
from sst.sandbox import custody as pristine_custody

from stc.integration.cli_gateway import (
    SST_PROMPT_BEGIN,
    SST_PROMPT_END,
    CLIGatewayBackend,
    shape_gateway_prompt,
)
from stc.integration.harness_worker import SpendLedger

_LIVE_CAND_0_LINES: tuple[str, ...] = (
    "--- /dev/null",
    "+++ b/tests/unit/test_integration_runner_pins.py",
    "@@ -0,0 +1,213 @@",
    '+"""Regression pins for the P04 runner\'s defensive branches.',
    "+",
    "+All collaborators are local stubs.  These tests intentionally exercise a real",
    "+DialecticRunner and its real merge/audit control flow.",
    '+"""',
    "+",
    "+from __future__ import annotations",
    "+",
    "+from dataclasses import dataclass",
    "+from pathlib import Path",
    "+from typing import Any",
    "+",
    "+import pytest",
    "+",
    "+from praxist.dialectic.errors import DialecticError",
    "+from praxist.dialectic.results import NoChampionResult",
    "+from praxist.dialectic.runner import DialecticRunner",
    "+",
    "+",
    "+@dataclass",
    "+class _Proposal:",
    '+    proposal_id: str = "champion"',
    '+    content: str = "return 42"',
    "+",
    "+",
    "+class _Store:",
    "+    def __init__(self, root: Path, events: list[dict[str, Any]] | None = None):",
    "+        self.root = root",
    "+        self.events = list(events or [])",
    "+",
    "+    def append(self, event: dict[str, Any]) -> None:",
    "+        self.events.append(event)",
    "+",
    "+    def write_json(self, name: str, value: Any) -> None:",
    "+        import json",
    "+",
    '+        (self.root / name).write_text(json.dumps(value), encoding="utf-8")',
    "+",
    "+",
    "+class _Gateway:",
    "+    def __init__(self, payload: Any = None):",
    "+        self.payload = payload",
    "+",
    "+    async def complete(self, *_args: Any, **_kwargs: Any) -> Any:",
    "+        return self.payload",
    "+",
    "+",
    "+class _Harness:",
    "+    async def verify(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    '+        return {"ok": True}',
    "+",
    "+",
    "+class _VerifyThenMergeApply:",
    "+    def __init__(self):",
    "+        self.calls = 0",
    "+",
    "+    def __call__(self, *_args: Any, **_kwargs: Any) -> None:",
    "+        self.calls += 1",
    "+        if self.calls == 2:",
    '+            raise RuntimeError("synthetic merge application failure")',
    "+",
    "+",
    "+def _runner(tmp_path: Path, *, store: _Store, auditor: Any = None) -> DialecticRunner:",
    "+    kwargs: dict[str, Any] = {",
    '+        "store": store,',
    '+        "gateway": _Gateway(),',
    '+        "harness": _Harness(),',
    "+    }",
    "+    if auditor is not None:",
    '+        kwargs["auditor"] = auditor',
    "+    return DialecticRunner(**kwargs)",
    "+",
    "+",
    "+@pytest.mark.asyncio",
    "+async def test_merge_apply_failure_returns_typed_no_champion_and_preserves_partial_evidence(",
    "+    tmp_path: Path,",
    "+    monkeypatch: pytest.MonkeyPatch,",
    "+) -> None:",
    "+    store = _Store(tmp_path)",
    "+    runner = _runner(tmp_path, store=store)",
    "+    apply_proposal = _VerifyThenMergeApply()",
    '+    monkeypatch.setattr(runner, "apply_proposal", apply_proposal)',
    "+",
    "+    async def execute_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    '+        return {"champion": _Proposal(), "proposals": [_Proposal()]}',
    "+",
    '+    monkeypatch.setattr(runner, "execute_search", execute_search)',
    "+",
    "+    result = await runner.run_async()",
    "+",
    "+    assert isinstance(result, NoChampionResult)",
    '+    assert result.reason == "merge-apply-failed"',
    "+    assert apply_proposal.calls == 2",
    '+    assert not (tmp_path / "merged").exists()',
    '+    for artifact in ("veto_log.json", "synthesis.json", "loss_ledger.json", "result.json"):',
    "+        assert (tmp_path / artifact).is_file(), artifact",
    "+",
    "+",
    "+@pytest.mark.asyncio",
    "+async def test_vetoed_champion_without_reconstructible_alternate_returns_typed_result(",
    "+    tmp_path: Path,",
    "+) -> None:",
    "+    store = _Store(",
    "+        tmp_path,",
    "+        events=[",
    "+            {",
    '+                "type": "CHAMPION_SELECTED",',
    '+                "proposal_id": "tainted-champion",',
    '+                "fallback_critique": True,',
    '+                "verified": True,',
    "+            },",
    "+            {",
    '+                "type": "PROPOSAL_VERIFIED",',
    '+                "proposal_id": "untainted-alternate",',
    '+                "verified": True,',
    '+                "tainted": False,',
    "+            },",
    "+            # Deliberately no NODE_PROPOSED or SYNTHESIS_PROPOSED event.",
    "+        ],",
    "+    )",
    "+    runner = _runner(tmp_path, store=store)",
    "+",
    "+    async def execute_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    '+        return {"champion": {"proposal_id": "tainted-champion"}}',
    "+",
    "+    runner.execute_search = execute_search  # type: ignore[method-assign]",
    "+",
    "+    result = await runner.run_async()",
    "+",
    "+    assert isinstance(result, NoChampionResult)",
    '+    assert result.reason == "reselect-reconstruction-failed"',
    "+",
    "+",
    "+class _AuditFlag:",
    "+    def __init__(self):",
    "+        self.with_codex = False",
    "+",
    "+    async def audit(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    '+        return {"ok": True}',
    "+",
    "+",
    "+@pytest.mark.asyncio",
    "+async def test_audit_time_with_codex_is_fail_closed_with_rt08(",
    "+    tmp_path: Path,",
    "+    monkeypatch: pytest.MonkeyPatch,",
    "+) -> None:",
    "+    auditor = _AuditFlag()",
    "+    runner = _runner(tmp_path, store=_Store(tmp_path), auditor=auditor)",
    "+",
    "+    async def execute_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    '+        return {"champion": _Proposal(), "proposals": [_Proposal()]}',
    "+",
    '+    monkeypatch.setattr(runner, "execute_search", execute_search)',
    "+",
    "+    original_audit = auditor.audit",
    "+",
    "+    async def flip_before_audit(*args: Any, **kwargs: Any) -> dict[str, Any]:",
    "+        auditor.with_codex = True",
    "+        return await original_audit(*args, **kwargs)",
    "+",
    '+    monkeypatch.setattr(auditor, "audit", flip_before_audit)',
    "+",
    '+    with pytest.raises(DialecticError, match="RT-08"):',
    "+        await runner.run_async()",
    "+",
    "*** End Patch",
)

_LIVE_CAND_1_LINES: tuple[str, ...] = (
    "*** Begin Patch",
    "*** Add File: tests/unit/test_integration_runner_pins.py",
    '+"""P04 runner defensive-branch pins.',
    "+",
    "+These tests deliberately exercise the real DialecticRunner.  External model",
    "+and harness boundaries are replaced with deterministic local stubs only.",
    '+"""',
    "+",
    "+from __future__ import annotations",
    "+",
    "+from dataclasses import dataclass",
    "+from pathlib import Path",
    "+from typing import Any",
    "+",
    "+import pytest",
    "+",
    "+from dialectic.errors import DialecticError",
    "+from dialectic.result import NoChampionResult",
    "+from dialectic.runner import DialecticRunner",
    "+",
    "+",
    "+@dataclass",
    "+class _EventStore:",
    "+    events: list[dict[str, Any]]",
    "+    root: Path",
    "+",
    "+    def append(self, event: dict[str, Any]) -> None:",
    "+        self.events.append(event)",
    "+",
    "+    def record(self, event: dict[str, Any]) -> None:",
    "+        self.append(event)",
    "+",
    "+",
    "+class _CustodyProposal:",
    "+    def __init__(self) -> None:",
    "+        self.calls = 0",
    "+",
    "+    def apply_proposal(self, *_args: Any, **_kwargs: Any) -> None:",
    "+        self.calls += 1",
    "+        if self.calls == 2:",
    '+            raise RuntimeError("synthetic merge-time application failure")',
    "+",
    "+",
    "+class _Gateway:",
    "+    with_codex = False",
    "+",
    "+    async def complete(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    '+        return {"text": "deterministic gateway response"}',
    "+",
    "+",
    "+class _Auditor:",
    "+    def __init__(self) -> None:",
    "+        self.with_codex = False",
    "+",
    "+    async def audit(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    '+        return {"passed": True, "issues": []}',
    "+",
    "+",
    "+def _runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DialecticRunner:",
    "+    store = _EventStore([], tmp_path)",
    "+    runner = DialecticRunner(",
    "+        gateway=_Gateway(),",
    "+        auditor=_Auditor(),",
    "+        store=store,",
    "+        output_dir=tmp_path,",
    "+    )",
    '+    monkeypatch.setattr(runner, "execute_search", _deterministic_search)',
    "+    return runner",
    "+",
    "+",
    "+async def _deterministic_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:",
    "+    return {",
    '+        "proposal": "synthetic proposal",',
    '+        "verified": True,',
    '+        "score": 1.0,',
    "+    }",
    "+",
    "+",
    "+def _assert_partial_evidence(tmp_path: Path) -> None:",
    '+    for name in ("veto_log.json", "synthesis.json", "loss_ledger.json", "result.json"):',
    "+        assert (tmp_path / name).is_file(), name",
    '+    assert not (tmp_path / "merged").exists()',
    "+",
    "+",
    "+@pytest.mark.asyncio",
    "+async def test_merge_apply_failure_returns_typed_no_champion(",
    "+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch",
    "+) -> None:",
    "+    runner = _runner(tmp_path, monkeypatch)",
    "+    custody = _CustodyProposal()",
    '+    monkeypatch.setattr(runner, "_proposal_from_events", lambda *_: custody)',
    "+",
    "+    result = await runner.run_async()",
    "+",
    "+    assert isinstance(result, NoChampionResult)",
    '+    assert result.reason == "merge-apply-failed"',
    "+    assert custody.calls >= 2",
    "+    _assert_partial_evidence(tmp_path)",
    "+",
    "+",
    "+@pytest.mark.asyncio",
    "+async def test_vetoed_champion_without_alternate_proposal_returns_no_champion(",
    "+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch",
    "+) -> None:",
    "+    runner = _runner(tmp_path, monkeypatch)",
    "+    runner.store.events.extend(",
    "+        [",
    '+            {"type": "NODE_PROPOSED", "node_id": "champion", "tainted": True},',
    '+            {"type": "NODE_VETOED", "node_id": "champion", "reason": "fallback-critique"},',
    '+            {"type": "NODE_VERIFIED", "node_id": "alternate", "tainted": False},',
    "+        ]",
    "+    )",
    '+    monkeypatch.setattr(runner, "_proposal_from_events", lambda *_: None)',
    "+",
    "+    result = await runner.run_async()",
    "+",
    "+    assert isinstance(result, NoChampionResult)",
    '+    assert result.reason == "reselect-reconstruction-failed"',
    "+",
    "+",
    "+@pytest.mark.asyncio",
    "+async def test_audit_time_codex_flag_fails_closed_with_rt08(",
    "+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch",
    "+) -> None:",
    "+    runner = _runner(tmp_path, monkeypatch)",
    "+    runner.auditor.with_codex = True",
    "+",
    '+    with pytest.raises(DialecticError, match="RT-08"):',
    "+        await runner.run_async()",
    "*** End Patch",
)

#: Exact live §2 payloads (no trailing newline, as emitted).
LIVE_CAND_0: str = "\n".join(_LIVE_CAND_0_LINES)
LIVE_CAND_1: str = "\n".join(_LIVE_CAND_1_LINES)

#: Hash pins for the embedded live bytes (attempt-2 dossier, both stores agree).
LIVE_CAND_0_BYTES: int = 5182
LIVE_CAND_0_SHA256: str = "44a77e3048d6ce0ee9c5571912d41f1cac5de6a617ceb4793a291d0c90509a11"
LIVE_CAND_1_BYTES: int = 3929
LIVE_CAND_1_SHA256: str = "0c7052d6bc37e6e7d26a7037842244228c75b38fb3bc6f6b6d72567a03db2fe3"

#: Live target module shared by both candidates.
LIVE_TARGET: str = "tests/unit/test_integration_runner_pins.py"

#: Attempt-2 dossier node ids (cross-check oracles).
CAND_0_ID: str = "cand_TASK-P05_ACCEPTANCE-06f26d5e_0_0"
CAND_1_ID: str = "cand_TASK-P05_ACCEPTANCE-06f26d5e_1_0"

#: Expected applied-file pins post-fix (translation output, byte-exact).
CAND_0_FILE_BYTES: int = 4923
CAND_0_FILE_SHA256: str = "75f3af96e40933111e626817f929c90b98d1d5a363f780a93104793182e880a1"
CAND_1_FILE_BYTES: int = 3716
CAND_1_FILE_SHA256: str = "f746b09d41a9de4764eae60aa36f8e140cb5084ab46baccc255c15e9e2a20e9a"

#: Pinned sst base the proposal diff applies against (sst never written).
#: Re-based 2026-10-04 for the SST cand-02 pin (attempt-2; attempt-1 kept
#: as the historical 079f4de proposal record).
PINNED_CUSTODY_SHA256: str = "4067772551fbf80cd2b2cd900070a49fc1166549d4735e12a1608927a66562ad"

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_A3_DIR: Path = (
    _REPO_ROOT / "docs" / "builds" / "stc-integration" / "evidence" / "FOLLOWUP" / "a3-fix"
)
_A3_DIFF: Path = _A3_DIR / "attempt-2" / "sst-custody-tolerance.diff"
_DOSSIER_RUN: Path = (
    _REPO_ROOT
    / "docs"
    / "builds"
    / "stc-integration"
    / "evidence"
    / "FOLLOWUP"
    / "accept-2"
    / "attempt-1"
    / "dossier"
    / "runs"
    / "TASK-P05_ACCEPTANCE-06f26d5e"
)

#: The four A3 frame-pin lines (exact text, in order).
PIN_LINES: tuple[str, ...] = (
    "If the JSON carries proposed code changes, emit that patch string",
    "(proposed_changes) as a pure unified diff: '---'/'+++' headers with",
    "'@@' hunks only. NEVER emit codex apply_patch markers: no patch line",
    "may begin with '***' ('*** Begin Patch' / '*** Add File:' / '*** End Patch').",
)


def _proposal(candidate_id: str, diff_text: str, target: str = LIVE_TARGET) -> CandidateProposal:
    """Builds a minimal DIVERGE proposal carrying the given patch bytes."""
    return CandidateProposal(
        candidate_id=candidate_id,
        tree_id="a3-tree",
        title="a3",
        rationale="a3",
        target_paths=[target],
        patch_diff=diff_text,
    )


def _git_apply_check(workspace: Path, patch_text: str) -> int:
    """Runs `git apply --check` on the given text inside the workspace."""
    patch_file = workspace / ".a3-check.patch"
    patch_file.write_text(patch_text, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", str(patch_file)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        return proc.returncode
    finally:
        patch_file.unlink(missing_ok=True)


class _StubResult:
    """Minimal HarnessResultT-satisfying stub (in-process, zero calls)."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.exit_code = 0
        self.error: str | None = None

    @property
    def is_success(self) -> bool:
        return True


class _StubHarness:
    """Minimal HarnessT-satisfying stub recording execute calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(
        self,
        prompt: str,
        role: str = "general",
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> _StubResult:
        self.calls.append({"prompt": prompt, "role": role, "model": model, "context": context})
        return _StubResult("STUB-OK")


def test_live_bytes_hash_pins() -> None:
    """Embedded payloads are exactly the 5182 B + 3929 B live payloads."""
    raw_0 = LIVE_CAND_0.encode("utf-8")
    raw_1 = LIVE_CAND_1.encode("utf-8")
    assert len(raw_0) == LIVE_CAND_0_BYTES
    assert hashlib.sha256(raw_0).hexdigest() == LIVE_CAND_0_SHA256
    assert len(raw_1) == LIVE_CAND_1_BYTES
    assert hashlib.sha256(raw_1).hexdigest() == LIVE_CAND_1_SHA256
    assert not LIVE_CAND_0.endswith("\n") and not LIVE_CAND_1.endswith("\n")


def _read_proposed_rows(store_path: Path) -> dict[str, str]:
    """Node_id -> patch_diff for the NODE_PROPOSED rows in a dossier store."""
    con = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT node_id, payload_json FROM sst_events WHERE kind='NODE_PROPOSED'"
        ).fetchall()
    finally:
        con.close()
    return {node_id: json.loads(payload)["patch_diff"] for node_id, payload in rows}


def _dossier_store_payloads(events_path: Path, store_path: Path, tmp_path: Path) -> dict[str, str]:
    """Node_id -> patch_diff from the dossier store, seeding to tmp if absent.

    Clean-checkout reproduction (attempt-5 ERRATA E3): ``store.db`` is
    ignored, so a pristine clone lacks it while ``events.json`` is
    tracked. Prefer the historical store when present (genuine
    cross-check); otherwise rebuild exactly the 2 NODE_PROPOSED rows
    from the tracked events through the product store API into
    ``tmp_path``. NEVER writes into the tree: lease-close tripwires
    fail closed on added files.
    """
    if store_path.is_file():
        return _read_proposed_rows(store_path)
    from sst.core.events import EventKind, SSTEvent
    from sst.storage.store import SQLiteSSTStore

    events = json.loads(events_path.read_text(encoding="utf-8"))
    proposed = [e for e in events if e.get("kind") == "NODE_PROPOSED"]
    seeded = tmp_path / "seeded-dossier-store.db"
    store = SQLiteSSTStore(seeded)
    for seq, entry in enumerate(proposed):
        store.append_event(
            SSTEvent(
                event_id=f"a3-seed-{seq}-{entry['node_id']}",
                tree_id="TASK-P05_ACCEPTANCE-06f26d5e",
                kind=EventKind.NODE_PROPOSED,
                node_id=entry["node_id"],
                idempotency_key=f"a3-seed-{seq}-{entry['node_id']}",
                payload=dict(entry["payload"]),
            )
        )
    return _read_proposed_rows(seeded)


def test_embedded_bytes_match_dossier(tmp_path: Path) -> None:
    """Embedded bytes equal the attempt-2 events.json + store.db payloads."""
    events_path = _DOSSIER_RUN / "events.json"
    store_path = _DOSSIER_RUN / "store.db"
    assert events_path.is_file(), f"attempt-2 dossier events missing: {events_path}"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    proposed = [e for e in events if e.get("kind") == "NODE_PROPOSED"]
    assert len(proposed) == 2
    by_id = {e["node_id"]: e["payload"]["patch_diff"] for e in proposed}
    assert by_id[CAND_0_ID] == LIVE_CAND_0
    assert by_id[CAND_1_ID] == LIVE_CAND_1
    store_rows = _dossier_store_payloads(events_path, store_path, tmp_path)
    assert len(store_rows) == 2
    for node_id, patch_diff in store_rows.items():
        assert patch_diff == by_id[node_id]


def test_dossier_store_payloads_seeds_from_tracked_events(tmp_path: Path) -> None:
    """The absent-store branch rebuilds the exact 2 proposal rows in tmp."""
    events_path = _DOSSIER_RUN / "events.json"
    missing = tmp_path / "no-such-store.db"
    first = _dossier_store_payloads(events_path, missing, tmp_path / "a")
    assert set(first) == {CAND_0_ID, CAND_1_ID}
    assert first[CAND_0_ID] == LIVE_CAND_0
    assert first[CAND_1_ID] == LIVE_CAND_1
    second = _dossier_store_payloads(events_path, missing, tmp_path / "b")
    assert second == first  # deterministic rebuild
    assert not missing.exists()


def test_dossier_store_payloads_prefers_historical_store(tmp_path: Path) -> None:
    """The present-store branch reads the file as-is without seeding."""
    from sst.storage.store import SQLiteSSTStore

    events_path = _DOSSIER_RUN / "events.json"
    real = tmp_path / "real.db"
    SQLiteSSTStore(real)  # schema only; zero proposal rows
    assert _dossier_store_payloads(events_path, real, tmp_path / "seed") == {}
    assert not (tmp_path / "seed" / "seeded-dossier-store.db").exists()


def test_frame_pins_unified_diff_only() -> None:
    """The emitter frame pins pure-unified-diff emission naming the markers."""
    shaped = shape_gateway_prompt("SST-BYTES")
    for line in PIN_LINES:
        assert line in shaped
    positions = [shaped.index(line) for line in PIN_LINES]
    assert positions == sorted(positions)
    assert shaped.index(SST_PROMPT_END) < positions[0]
    assert "proposed_changes" in shaped and "unified diff" in shaped


def test_frame_preserves_sst_bytes_verbatim_with_markers() -> None:
    """D7/D15 intact: even marker-bearing SST bytes pass through unedited."""
    sst = "*** Begin Patch\n*** Add File: x.py\n+code\n*** End Patch\n"
    shaped = shape_gateway_prompt(sst)
    assert shaped.count(sst) == 1
    assert shaped.index(SST_PROMPT_BEGIN) < shaped.index(sst) < shaped.index(SST_PROMPT_END)


def test_frame_introduces_no_marker_lines() -> None:
    """No STC frame line itself starts with `***` (self-consistency)."""
    shaped = shape_gateway_prompt("SST")
    before, _, after_block = shaped.partition(SST_PROMPT_BEGIN)
    _, _, after = after_block.partition(SST_PROMPT_END)
    frame_lines = before.splitlines() + after.splitlines()
    assert frame_lines
    assert not any(line.startswith("***") for line in frame_lines)


def test_generate_shapes_with_pin(tmp_path: Path) -> None:
    """generate() dispatches the pin through the gateway role (in-process)."""
    harness = _StubHarness()
    backend = CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        ledger=SpendLedger(tmp_path / "spend" / "test.jsonl"),
        harness=harness,
    )
    assert backend.generate("SST-BYTES-HERE") == "STUB-OK"
    assert len(harness.calls) == 1
    call = harness.calls[0]
    assert call["role"] == "gateway"
    assert "SST-BYTES-HERE" in str(call["prompt"])
    for line in PIN_LINES:
        assert line in str(call["prompt"])


@pytest.fixture(scope="module")
def patched_custody(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Loads the SST proposal diff applied to a scratch copy (sst untouched).

    The evidence diff is the single source of truth: it must apply cleanly
    to the pinned sst base, and the patched module must expose the
    normalizer. sst itself is never written (base hash asserted).
    """
    assert _A3_DIFF.is_file(), f"A3 SST proposal diff missing: {_A3_DIFF}"
    assert pristine_custody.__file__ is not None
    pristine_file = Path(pristine_custody.__file__)
    digest = hashlib.sha256(pristine_file.read_bytes()).hexdigest()
    assert digest == PINNED_CUSTODY_SHA256, "sst base drifted from the pinned bytes"
    if shutil.which("git") is None:
        pytest.fail("git required (custody applies via git)")
    stage = tmp_path_factory.mktemp("a3-sst-tolerance") / "sst-tol"
    target = stage / "src" / "sst" / "sandbox" / "custody.py"
    target.parent.mkdir(parents=True)
    shutil.copy2(pristine_file, target)
    proc = subprocess.run(
        ["git", "apply", str(_A3_DIFF)],
        cwd=str(stage),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    spec = importlib.util.spec_from_file_location("a3_patched_custody", str(target))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(getattr(module, "_normalize_patch_markers", None))
    assert callable(getattr(module, "_translate_apply_patch_add_only", None))
    assert callable(getattr(module, "CandidateCustodyManager", None))
    return module


def test_sst_proposal_diff_applies_cleanly(patched_custody: Any) -> None:
    """The evidence diff lands on the pinned base with the normalizer (see fixture)."""
    assert patched_custody.__name__ == "a3_patched_custody"
    assert pristine_custody.__file__ is not None
    digest = hashlib.sha256(Path(pristine_custody.__file__).read_bytes()).hexdigest()
    assert digest == PINNED_CUSTODY_SHA256


def test_cand0_bytes_apply_succeeds_post_fix(tmp_path: Path, patched_custody: Any) -> None:
    """Exact 5182 B live bytes apply post-fix (git fails, fallback carries)."""
    normalize = patched_custody._normalize_patch_markers
    manager_cls = patched_custody.CandidateCustodyManager
    normalized, error = normalize(LIVE_CAND_0)
    assert error is None
    assert isinstance(normalized, str) and "***" not in normalized
    # The hunk-count mismatch (213 claimed, 165 actual) still trips git;
    # the SST fallback is the designed second path and applies it.
    assert _git_apply_check(tmp_path, normalized) != 0
    manager = manager_cls()
    proposal = _proposal(CAND_0_ID, LIVE_CAND_0)
    result = manager.apply_proposal(proposal, tmp_path)
    assert result.success is True, result.error_message
    target = tmp_path / LIVE_TARGET
    content = target.read_bytes()
    assert len(content) == CAND_0_FILE_BYTES
    assert hashlib.sha256(content).hexdigest() == CAND_0_FILE_SHA256
    assert b"***" not in content
    body = LIVE_CAND_0.split("\n")[3:-1]
    assert all(line.startswith("+") for line in body)
    expected = ("\n".join(line[1:] for line in body) + "\n").encode("utf-8")
    assert content == expected
    # New-pin hash form binds (diff, file_operations); the recorded hash
    # must identify the RAW submitted bytes, never the normalized form.
    compute_hash = patched_custody.compute_proposal_hash
    assert result.patch_hash == compute_hash(LIVE_CAND_0, proposal.file_operations)
    assert result.patch_hash != compute_hash(normalized, proposal.file_operations)


def test_cand1_bytes_translate_to_valid_diff(tmp_path: Path, patched_custody: Any) -> None:
    """Exact 3929 B live bytes translate to a git-appliable unified diff."""
    normalize = patched_custody._normalize_patch_markers
    manager_cls = patched_custody.CandidateCustodyManager
    normalized, error = normalize(LIVE_CAND_1)
    assert error is None
    assert isinstance(normalized, str) and "***" not in normalized
    assert normalized.startswith(f"--- /dev/null\n+++ b/{LIVE_TARGET}\n@@ -0,0 +1,127 @@\n")
    assert normalized.endswith("\n")
    assert _git_apply_check(tmp_path, normalized) == 0
    manager = manager_cls()
    result = manager.apply_proposal(_proposal(CAND_1_ID, LIVE_CAND_1), tmp_path)
    assert result.success is True, result.error_message
    target = tmp_path / LIVE_TARGET
    content = target.read_bytes()
    assert len(content) == CAND_1_FILE_BYTES
    assert hashlib.sha256(content).hexdigest() == CAND_1_FILE_SHA256
    assert b"***" not in content
    assert len(content.decode("utf-8").splitlines()) == 127
    body = LIVE_CAND_1.split("\n")[2:-1]
    expected = ("\n".join(line[1:] for line in body) + "\n").encode("utf-8")
    assert content == expected


_REFUSAL_CASES: dict[str, str] = {
    "update-file": ("*** Begin Patch\n*** Update File: a.py\n@@ -1 +1 @@\n-a\n+b\n*** End Patch\n"),
    "delete-file": "*** Begin Patch\n*** Delete File: a.py\n*** End Patch\n",
    "mixed-unified-and-add": (
        "*** Begin Patch\n*** Add File: y\n+x\n--- a/z\n+++ b/z\n*** End Patch\n"
    ),
    "markers-only": "*** Begin Patch\n*** End Patch\n",
    "empty-add-path": "*** Begin Patch\n*** Add File:   \n+x\n*** End Patch\n",
    "empty-section": (
        "*** Begin Patch\n*** Add File: a.py\n*** Add File: b.py\n+x\n*** End Patch\n"
    ),
    "non-plus-body": "*** Begin Patch\n*** Add File: a.py\n context\n*** End Patch\n",
    "move-to": "*** Begin Patch\n*** Add File: a.py\n+x\n*** Move to: b.py\n*** End Patch\n",
}


@pytest.mark.parametrize("case", sorted(_REFUSAL_CASES))
def test_untranslatable_markers_refuse_loudly(
    tmp_path: Path, patched_custody: Any, case: str
) -> None:
    """Marker shapes outside R1/R2 refuse before any write (never garbage)."""
    manager_cls = patched_custody.CandidateCustodyManager
    manager = manager_cls()
    result = manager.apply_proposal(_proposal(f"a3-{case}", _REFUSAL_CASES[case]), tmp_path)
    assert result.success is False
    assert result.error_message is not None
    assert "emit a pure unified diff" in result.error_message
    assert "***" in result.error_message
    assert list(tmp_path.iterdir()) == []


_CLEAN_NEW_FILE: str = "--- /dev/null\n+++ b/pkg/mod.py\n@@ -0,0 +1,2 @@\n+one\n+two\n"
_CLEAN_MODIFY: str = "--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -1,2 +1,2 @@\n-one\n+uno\n two\n"
_CLEAN_RAW: str = "print('raw payload')\n"
_CLEAN_BOLD: str = "--- a/d.md\n+++ b/d.md\n@@ -1 +1 @@\n ***bold***\n+***bold***\n"


def test_no_regression_clean_paths_byte_identical(tmp_path: Path, patched_custody: Any) -> None:
    """Marker-free payloads behave byte-identically pristine vs patched."""
    normalize = patched_custody._normalize_patch_markers
    manager_cls = patched_custody.CandidateCustodyManager
    pristine_manager = pristine_custody.CandidateCustodyManager()
    patched_manager = manager_cls()
    cases = (
        ("new-file", _CLEAN_NEW_FILE, "pkg/mod.py", None),
        ("modify", _CLEAN_MODIFY, "pkg/mod.py", "one\ntwo\n"),
        ("raw", _CLEAN_RAW, "pkg/raw.py", None),
        ("bold", _CLEAN_BOLD, "d.md", "***bold***\n"),
    )
    for name, payload, target, seed in cases:
        normalized, error = normalize(payload)
        assert (normalized, error) == (payload, None), name
        results = []
        for tag, manager in (("pristine", pristine_manager), ("patched", patched_manager)):
            ws = tmp_path / name / tag
            ws.mkdir(parents=True)
            if seed is not None:
                seeded = ws / target
                seeded.parent.mkdir(parents=True, exist_ok=True)
                seeded.write_text(seed, encoding="utf-8")
            result = manager.apply_proposal(_proposal(f"a3-{name}", payload, target), ws)
            assert result.success is True, (name, tag, result.error_message)
            content = (ws / target).read_bytes()
            results.append((result.patch_hash, result.post_patch_digest, content))
        assert results[0] == results[1], name
