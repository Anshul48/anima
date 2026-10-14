"""Integration fixtures for the P04 dialectic runner.

Real-gate tests run the STC substrate (ruff + mypy --strict + pytest) and are
guarded by `requires_gate_tools` (sys.executable must serve `ruff`/`mypy`;
in this workspace that is the learn-anything 3.11 interpreter — see
evidence/P04/readiness.md B1.3). A stub-substrate wiring test proves the same
scenario end to end under ANY interpreter. R2b: the P04 tiny-fixture
ChampionResult expects were converted to fail-closed NoChampion proofs
(tiny leases cannot host the ratified §5.2 mandatory set); the maintained
green-path proof is the STC-source real-gate test below. One @live CLI-node
test runs when the operator codex login is present (D13).

F-P04-1 (recorded): the SST controller strips trailing newlines from every
patch (`_clean_code`), so raw-code candidates can never pass STC's
ruff-format gate. Fixture candidates are therefore unified diffs — SST
custody's primary exact-patch shape — which apply (via git apply or the
manual fallback) to newline-terminated files.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from sst.core.contracts import CandidateProposal, TaskPacket
from sst.gateway.contracts import GatewayRequest
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.policy import SearchPolicy

from stc.integration.adapters import AdapterContext, Budgets
from stc.integration.dialectic_runner import (
    DialecticRunner,
    NoChampionResult,
    STCCustodyWrapper,
    count_mutmut_runs,
)
from stc.integration.env_probe import env_digest_of
from stc.integration.linked_records import (
    verify_custody_intake,
    verify_dossier,
    verify_selection_record,
)
from stc.integration.selection import load_selection_config
from stc.schemas.models import ExecutionReceipt, FileTarget, TaskBundle
from stc.substrate.runner import SubstrateRunner

live = pytest.mark.live

BASE_MOD = 'def add(a: int, b: int) -> int:\n    """Add two integers."""\n    return a + b\n'

TEST_MOD = "from mod import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n"

GOOD_MOD = (
    'def add(a: int, b: int) -> int:\n    """Good branch implementation."""\n    return a + b\n'
)

GARBAGE_MOD = (
    "def add(a: int, b: int) -> int:\n"
    '    """Garbage branch implementation."""\n'
    "    # GARBAGE-CRITIQUE\n"
    "    return a + b\n"
)

LOW_MOD = (
    'def add(a: int, b: int) -> int:\n    """Low branch implementation."""\n    return a + b\n'
)

BAD_MOD = (
    "def add(a: int, b: int) -> int:\n"
    '    """Subtract two integers (wrong on purpose)."""\n'
    "    return a - b\n"
)

SYNTH_MOD = (
    'def add(a: int, b: int) -> int:\n    """Synth blend implementation."""\n    return a + b\n'
)


def _full_diff(new_text: str) -> str:
    """Full-file unified diff of mod.py vs BASE_MOD (custody exact-patch shape)."""
    old_lines = BASE_MOD.splitlines()
    new_lines = new_text.splitlines()
    out = [
        "--- a/mod.py",
        "+++ b/mod.py",
        f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@",
    ]
    out.extend(f"-{line}" for line in old_lines)
    out.extend(f"+{line}" for line in new_lines)
    return "\n".join(out) + "\n"


def _probe(executable: str, *args: str) -> bool:
    try:
        proc = subprocess.run(
            [executable, *args],
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _gate_tools_available() -> bool:
    return (
        _probe(sys.executable, "-m", "ruff", "--version")
        and _probe(sys.executable, "-m", "mypy", "--version")
        and shutil.which("git") is not None
    )


GATE_TOOLS = _gate_tools_available()

requires_gate_tools = pytest.mark.skipif(
    not GATE_TOOLS, reason="real gates need ruff+mypy modules and git"
)


def _git_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text(BASE_MOD, encoding="utf-8")
    (src / "test_mod.py").write_text(TEST_MOD, encoding="utf-8")
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


def _ctx(source_root: str) -> AdapterContext:
    return AdapterContext(
        epoch_index=1,
        spec_id="spec-1",
        budgets=Budgets(time_budget_seconds=600),
        acceptance_commands=("true",),
        source_repo_root=source_root,
        base_commit="abc",
        adapter_version="p04-test",
    )


def _bundle(task_id: str = "P04-FIX") -> TaskBundle:
    return TaskBundle(
        task_id=task_id,
        epoch_index=1,
        spec_id="spec-1",
        goal_statement="keep add correct",
        invariants=["add(1, 2) == 3"],
        target_files=[FileTarget(path="mod.py", action="modify")],
        membrane_protocols=["proto-a"],
        negative_inhibitors=[],
    )


class ScriptGateway(ModelGateway):
    def __init__(self, handler: Any) -> None:
        super().__init__(profiles={}, routes={})
        self.profiles["test"] = "test"  # type: ignore[assignment]
        self._handler = handler

    def invoke(self, request: Any) -> Any:
        from sst.gateway.contracts import GatewayResponse

        content = self._handler(request)
        return GatewayResponse(content=content, model="script", profile="test")


def _make_handler(
    diverge_diffs: list[str],
    *,
    synth_diff: str,
    good_score: float = 0.9,
    synth_score: float = 0.88,
) -> Any:
    def handle(request: GatewayRequest) -> str:
        prompt = request.messages[0]["content"] if request.messages else ""
        text = str(prompt)
        if request.role == "diverge":
            return json.dumps(
                {
                    "branches": [
                        {
                            "strategy_title": f"strategy-{index}",
                            "hypothesis_or_rationale": "fixture hypothesis",
                            "proposed_changes": diff,
                        }
                        for index, diff in enumerate(diverge_diffs)
                    ]
                }
            )
        if request.role == "synthesize":
            return json.dumps(
                {
                    "synthesized_title": "synth",
                    "synthesis_rationale": "blend",
                    "executable_content": synth_diff,
                }
            )
        if request.role == "refine":
            return json.dumps(
                {
                    "refined_title": "refined",
                    "refactoring_notes": "notes",
                    "executable_content": _full_diff(GOOD_MOD),
                }
            )
        if request.role == "critique":
            if "GARBAGE-CRITIQUE" in text:
                from sst.gateway.contracts import ProviderGatewayError

                raise ProviderGatewayError(
                    "garbage critique: unparseable model output",
                    category="model_error",
                    remediation="retry",
                )
            if "Low branch" in text:
                return json.dumps(
                    {
                        "value_score": 0.6,
                        "verdict": "APPROVE",
                        "rationale": "meets the goal, minimal margin",
                    }
                )
            if "Synth blend" in text:
                return json.dumps(
                    {
                        "value_score": synth_score,
                        "verdict": "APPROVE",
                        "rationale": "strong blend of both parents",
                    }
                )
            return json.dumps(
                {
                    "value_score": good_score,
                    "verdict": "APPROVE",
                    "rationale": "thorough review, solid types",
                }
            )
        raise AssertionError(f"unexpected role {request.role!r}")

    return handle


def _verifier_failed(events: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for event in events:
        if event["kind"] == "VERIFIER_FINISHED" and event["node_id"] == node_id:
            payload: dict[str, Any] | None = event["payload"]
            return payload
    return None


def _score_of(events: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for event in events:
        if event["kind"] == "SCORE_RECORDED" and event["node_id"] == node_id:
            payload: dict[str, Any] | None = event["payload"]
            return payload
    return None


def _read_events(evidence_dir: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = json.loads(
        (evidence_dir / "events.json").read_text(encoding="utf-8")
    )
    return events


@requires_gate_tools
def test_fixture_full_scenario_real_gates(tmp_path: Path) -> None:
    """Tiny-fixture real gates fail closed with verifying records (R2b).

    P04-era contract conversion (packet decision 2; P1-ADDENDUM item 1):
    the ratified §5.2 mandatory set is STC-task-scoped by construction and
    P04 tiny leases cannot host it, so per-node scoped pytest is red here
    (``stc_pytest`` in the verifier stderr) and NoChampion with reason
    ``no-verified-candidate`` is the contract-correct outcome — not a
    ChampionResult. The red-gate evidence plus the signed dossier below
    prove the fail-closed (nothing silently passed). The maintained
    green-path proof is test_stc_source_real_gates_green_path.
    """
    src = _git_source(tmp_path)
    substrate = SubstrateRunner(timeout_per_gate=180.0, run_mutmut=False)
    handler = _make_handler(
        [
            _full_diff(GARBAGE_MOD),
            _full_diff(GOOD_MOD),
            _full_diff(LOW_MOD),
            _full_diff(BAD_MOD),
        ],
        synth_diff=_full_diff(SYNTH_MOD),
        good_score=0.80,
        synth_score=0.81,
    )
    key = b"r2b-fixture-key"
    runner = DialecticRunner(
        ctx=_ctx(str(src)),
        gateway=ScriptGateway(handler),
        substrate=substrate,
        evidence_root=tmp_path / "ev",
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4),
        champion_mutmut=False,
        hmac_key=key,
    )
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "no-verified-candidate"
    assert len(result.branch_refs) == 4
    assert result.scores_summary == {}
    assert result.veto_log == []
    evidence = Path(result.evidence_dir)
    events = _read_events(evidence)

    by_title = {
        event["payload"].get("title"): event["node_id"]
        for event in events
        if event["kind"] == "NODE_PROPOSED"
    }
    bad_id = by_title["strategy-3"]

    # Failing branch pruned with gate evidence (pytest failed, ruff/mypy clean).
    bad_ver = _verifier_failed(events, bad_id)
    assert bad_ver is not None and bad_ver["passed"] is False
    assert "stc_pytest" in bad_ver["stderr"]
    assert _score_of(events, bad_id) is None

    # Fail-closed verifying records: signed dossier consumes cleanly.
    assert (evidence / "store.db").is_file()
    assert (evidence / "result.json").is_file()
    assert (evidence / "selection_outcome.json").is_file()
    assert (evidence / "dossier_digests.json").is_file()
    assert result.linked_record_digests
    assert result.dossier_signature
    ok, findings = verify_dossier(evidence, key)
    assert ok, findings


# NOTE (SST cand-02 handoff): test_fixture_wiring_stub_substrate retired —
# same unreachable veto-then-reselect-to-synthesis shape as
# test_veto_reselects_and_receipts_synthesis under honest SST scores.


def test_mock_gateway_search_smoke(tmp_path: Path) -> None:
    """Mock-harness gateway search completes with a typed outcome + store."""
    pytest.importorskip("prompt_kit")
    from sst.gateway.contracts import (
        GatewayRequest,
        ModelCatalog,
        ProviderKind,
        ProviderProfile,
    )

    from stc.integration.cli_gateway import CLIGatewayBackend, CLIModelGateway
    from stc.schemas.models import GateReport, JudiciaryVerdict

    if shutil.which("git") is None:
        pytest.skip("git required for P01 candidate identity")

    def fail_receipt(task_id: str) -> ExecutionReceipt:
        def gate(name: str) -> GateReport:
            return GateReport(
                gate_name=name,
                exit_code=1,
                duration_seconds=0.1,
                violations_count=1,
                raw_output_snippet="mock prose is not code",
            )

        return ExecutionReceipt(
            receipt_id="rc-mock",
            task_id=task_id,
            epoch_index=1,
            commit_hash="abc",
            timestamp_utc="2026-09-13T00:00:00Z",
            python_version="3.11",
            os_platform="linux",
            gate_ruff=gate("ruff"),
            gate_mypy=gate("mypy"),
            gate_pytest=gate("pytest"),
            gate_mutmut=gate("mutmut"),
            sha256_signature="stub",
        )

    class FailAllSubstrate:
        def execute_gates(
            self,
            worktree_path: Path,
            task_id: str,
            epoch_index: int = 1,
            correlation_id: str | None = None,
            causation_id: str | None = None,
            pytest_target: str | None = None,
            **kwargs: Any,
        ) -> ExecutionReceipt:
            _ = (worktree_path, epoch_index, correlation_id, causation_id, pytest_target, kwargs)
            return fail_receipt(task_id)

        def verify_receipt(self, receipt: ExecutionReceipt) -> bool:
            _ = receipt
            return True

    class StubAuditor:
        with_codex = False

        def audit_diff(
            self, diff_text: str, bundle: TaskBundle, receipt: ExecutionReceipt
        ) -> JudiciaryVerdict:
            _ = (diff_text, bundle, receipt)
            return JudiciaryVerdict(
                task_id="P04-MOCK",
                status="APPROVED",
                findings=[],
                summary_rationale="stub",
            )

    from stc.integration.harness_worker import SpendLedger

    src = _git_source(tmp_path)
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    backend = CLIGatewayBackend("mock", project_root=tmp_path, ledger=ledger)
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
    probe = gateway.invoke(GatewayRequest(messages=[{"role": "user", "content": "mock probe"}]))
    assert "Mock response" in probe.content
    runner = DialecticRunner(
        ctx=_ctx(str(src)),
        gateway=gateway,
        substrate=FailAllSubstrate(),  # type: ignore[arg-type]
        evidence_root=tmp_path / "ev",
        policy=SearchPolicy(max_iterations=2, max_depth=2, branching_factor=2),
        auditor=StubAuditor(),  # type: ignore[arg-type]
    )
    result = runner.run(_bundle("P04-MOCK"))
    assert isinstance(result, NoChampionResult)
    assert result.reason == "no-verified-candidate"
    assert len(result.branch_refs) >= 1
    assert (Path(result.evidence_dir) / "store.db").is_file()


@requires_gate_tools
def test_mutmut_once_on_champion(tmp_path: Path) -> None:
    """Tiny-fixture champion mutmut fails closed with verifying records (R2b).

    P04-era contract conversion (packet decision 2; P1-ADDENDUM item 1):
    the tiny lease cannot host the ratified §5.2 mandatory set, so no
    candidate verifies, no merge runs, and mutmut-on-champion never
    executes — NoChampion (``no-verified-candidate``) with a signed
    dossier is the contract-correct outcome. The node id is kept stable
    for the 15-list; the once-counting rule itself is proven by the
    counting unit tests plus the ACCEPT P2 merge. The old
    requires_mutmut gate is dropped (this proof needs real gates, not a
    mutmut install — keeping it would skip the proof where mutmut is
    absent).
    """
    src = _git_source(tmp_path)
    (src / "pyproject.toml").write_text(
        '[tool.mutmut]\npaths_to_mutate = ["mod.py"]\ntests_dir = ["."]\nrunner = "pytest"\n',
        encoding="utf-8",
    )
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
            "mutmut config",
        ],
        check=True,
    )
    substrate = SubstrateRunner(timeout_per_gate=300.0, run_mutmut=True)
    handler = _make_handler([_full_diff(GOOD_MOD)], synth_diff=_full_diff(SYNTH_MOD))
    key = b"r2b-fixture-key"
    runner = DialecticRunner(
        ctx=_ctx(str(src)),
        gateway=ScriptGateway(handler),
        substrate=substrate,
        evidence_root=tmp_path / "ev",
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=1),
        champion_mutmut=True,
        hmac_key=key,
    )
    result = runner.run(_bundle("P04-MUTMUT"))
    assert isinstance(result, NoChampionResult)
    assert result.reason == "no-verified-candidate"
    assert len(result.branch_refs) == 1
    evidence = Path(result.evidence_dir)
    assert (evidence / "store.db").is_file()
    assert (evidence / "result.json").is_file()
    assert (evidence / "selection_outcome.json").is_file()
    assert (evidence / "dossier_digests.json").is_file()
    assert result.linked_record_digests
    assert result.dossier_signature
    ok, findings = verify_dossier(evidence, key)
    assert ok, findings


def _seed_codex_home() -> Path | None:
    """Writable CODEX_HOME seeded from the operator login (caller deletes)."""
    src = Path.home() / ".codex"
    auth, config = src / "auth.json", src / "config.toml"
    if not auth.is_file():
        return None
    home = Path(tempfile.mkdtemp(prefix="p04-codex-home-"))
    shutil.copy(auth, home / "auth.json")
    (home / "auth.json").chmod(0o600)
    if config.is_file():
        shutil.copy(config, home / "config.toml")
    return home


@live
@requires_gate_tools
def test_live_cli_node(tmp_path: Path) -> None:
    """One live CLI node: codex text → proposal → real substrate verify."""
    from sst.gateway.contracts import (
        GatewayRequest,
        ModelCatalog,
        ProviderKind,
        ProviderProfile,
    )

    from stc.integration.cli_gateway import CLIGatewayBackend, CLIModelGateway
    from stc.integration.harness_worker import SpendLedger

    codex_home = _seed_codex_home()
    if codex_home is None:
        pytest.skip("operator codex login unavailable")
    try:
        src = _git_source(tmp_path)
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
            GatewayRequest(messages=[{"role": "user", "content": "Reply with only: P04-LIVE-OK"}])
        )
        assert "P04-LIVE-OK" in response.content
        packet = TaskPacket(
            task_id="P04-LIVE",
            goal="live node verify",
            source_repo_root=str(src),
            base_commit="abc",
            snapshot_hash="snap",
            allowed_paths=["mod.py", "live_node.txt"],
            acceptance_commands=["true"],
        )
        proposal = CandidateProposal(
            candidate_id="live-node-1",
            tree_id="live-tree",
            role="DIVERGE",
            title="live node",
            rationale="live generation",
            target_paths=["live_node.txt"],
            patch_diff="",
            file_operations=[
                {
                    "action": "write",
                    "path": "live_node.txt",
                    "content": "P04-LIVE-OK\n",
                }
            ],
        )
        wrapper = STCCustodyWrapper(
            CandidateCustodyManager(base_worktree_dir=tmp_path / "custody"),
            SubstrateRunner(timeout_per_gate=180.0, run_mutmut=False),
            leases_root=tmp_path / "leases",
        )
        result = wrapper.verify_candidate_proposal(packet, proposal, src)
        assert result.passed is True
        assert "live-node-1" in wrapper.receipts
        rows = [
            json.loads(line)
            for line in (tmp_path / "spend.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 1
        assert rows[0]["channel"] == "gateway" and rows[0]["ok"] is True
    finally:
        shutil.rmtree(codex_home, ignore_errors=True)


_STC_ROOT = Path(__file__).resolve().parents[2]
if _STC_ROOT.name == "mutants" and (_STC_ROOT.parent / "pyproject.toml").is_file():
    # Under mutmut stats this file lives in mutmut's scratch copy whose
    # mutated sources are trampoline-instrumented (not lint-clean); prove
    # the green path on the pre-mutation tree instead (nested gates lint
    # real bytes). Mirrors skip mutmut scratch by _MIRROR_SKIP_DIRS.
    _STC_ROOT = _STC_ROOT.parent

_GREEN_DIFF = """--- a/src/stc/__init__.py
+++ b/src/stc/__init__.py
@@ -1,3 +1,4 @@
 \"\"\"STC - Biomimetic Spec-To-Code Autonomous Engineering Engine.\"\"\"

 __version__ = "0.1.0"
+# R2b green-path marker (comment-only, behavior-neutral).
"""
#: Version-agnostic new-file form (no context lines): applies to 0.1.0,
#: 0.2.0, and trampoline-instrumented trees alike. The P1 modify-form
#: pinned 0.1.0 bytes and collided with the acceptance candidate.
_GREEN_DIFF_NF = """--- /dev/null
+++ b/src/stc/r2b_greenpath_probe.py
@@ -0,0 +1 @@
+\"\"\"R2b green-path probe (comment-only, behavior-neutral).\"\"\"
"""

#: P1-pinned lease env digest (requalification tripwire; update deliberately
#: only when the suite interpreter/toolchain legitimately changes).
_GREEN_ENV_DIGEST = "b43db3e480ba8997fd9d0525b93407d3d0766abd42c93f015071b75ea3de2062"


@requires_gate_tools
def test_stc_source_real_gates_green_path(tmp_path: Path) -> None:
    """STC-source per-node verify passes real gates (R2b green-path proof).

    P1-driver shape (fix-2 P1 GREEN), version-agnostic new-file form: a
    comment-only STC-tree candidate through scoped per-node gates —
    ruff/mypy/pytest exit 0, 0 skipped,
    receipt signature verifies, mutmut absent per-node (E1), a scoped
    pytest target observed, selection + custody records consume cleanly,
    and the lease env digest requalifies. This is the maintained proof
    that the §5.2 green path works on STC sources; the P04 tiny
    fixtures above prove the fail-closed instead. Never pass
    file_operations alongside patch_diff (P1 driver-caution: SST
    custody applies file_operations first and would blank the target).
    """
    head = subprocess.run(
        ["git", "-C", str(_STC_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    packet = TaskPacket(
        task_id="R2B-GREEN",
        goal="R2b: comment-only STC-tree candidate through scoped per-node gates",
        source_repo_root=str(_STC_ROOT),
        base_commit=head,
        snapshot_hash="r2b-green",
        allowed_paths=["src/stc/r2b_greenpath_probe.py"],
        forbidden_paths=[],
        acceptance_commands=["true"],
        evidence_references={"stc.epoch_index": "1"},
    )
    proposal = CandidateProposal(
        candidate_id="R2B-GREEN-1",
        tree_id="r2b-green",
        role="DIVERGE",
        title="R2b comment-only candidate",
        rationale="green-path proof",
        target_paths=["src/stc/r2b_greenpath_probe.py"],
        patch_diff=_GREEN_DIFF_NF,
        file_operations=[],
    )
    key = b"r2b-greenpath-key"
    substrate = SubstrateRunner(timeout_per_gate=600.0, run_mutmut=False)
    wrapper = STCCustodyWrapper(
        CandidateCustodyManager(base_worktree_dir=str(tmp_path / "custody")),
        substrate,
        leases_root=str(tmp_path / "leases"),
        hmac_key=key,
    )
    result = wrapper.verify_candidate_proposal(packet, proposal, _STC_ROOT)
    assert result.passed is True, result.stderr[:2000]
    receipt = wrapper.receipts["R2B-GREEN-1"]
    for gate in (receipt.gate_ruff, receipt.gate_mypy, receipt.gate_pytest):
        assert gate.exit_code == 0, gate.raw_output_snippet[:1500]
    assert "0 skipped" in receipt.gate_pytest.raw_output_snippet
    assert substrate.verify_receipt(receipt) is True
    assert count_mutmut_runs(receipt) == 0
    pytest_argv = substrate.last_gate_argv.get("pytest", [])
    assert any("::" in str(a) or str(a).endswith(".py") for cmd in pytest_argv for a in cmd), (
        pytest_argv
    )
    config = load_selection_config()
    sel = wrapper.selections["R2B-GREEN-1"]
    assert verify_selection_record(sel, key, config=config) == []
    inta = wrapper.intakes["R2B-GREEN-1"]
    assert verify_custody_intake(inta, key) == []
    assert env_digest_of(wrapper.env_fingerprints["R2B-GREEN-1"]) == _GREEN_ENV_DIGEST
