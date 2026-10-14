"""Round-3 runner smoke test (no model): one stub-consumer cell end-to-end.

Covers runner-qualification R1-R6 repairs: real helper API wiring,
structured confinement audit, item-id dedupe, per-turn usage arrays,
and grading-script integrity. Uses frozen cases read-only; all trial
output goes to tmp_path. Never calls a model, never touches live
capture/store.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "evidence" / "muse-20261011" / "tools" / "trial_runner.py"
CASES_DIR = ROOT / "evidence" / "muse-20261011" / "cases"

sys.path.insert(0, str(ROOT / "scripts"))

from pilot.trial import ConsumerOutput, TrialError  # noqa: E402


def _load_runner():
    spec = importlib.util.spec_from_file_location("trial_runner_smoke", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


def _stub_backend(prompt: str, workdir: Path, trace_path: Path) -> ConsumerOutput:
    """No-model consumer: archives a minimal honest trace, changes nothing."""
    trace_path.write_text(
        '{"type": "turn.started"}\n'
        '{"type": "item.started", "item": {"id": "item_1", '
        '"type": "command_execution", "command": "ls", "status": "in_progress"}}\n'
        '{"type": "item.completed", "item": {"id": "item_1", '
        '"type": "command_execution", "command": "ls", "exit_code": 0, '
        '"status": "completed"}}\n'
        '{"type": "turn.completed", "usage": {"input_tokens": 10, '
        '"output_tokens": 3}}\n',
        encoding="utf-8",
    )
    return ConsumerOutput(
        output_text="stub consumer (no model): no changes made",
        recovery_actions=[],
        costs={"stub": True},
        notes="smoke",
    )


def test_smoke_cell_format_doc(runner, tmp_path):
    """W-A1/C0 runs end-to-end; starting state fails (V1), nothing invalid."""
    rec = runner.run_case_condition(
        CASES_DIR, tmp_path, "W-A1", "C0", consumer_backend=_stub_backend)
    assert rec["invalid_reason"] is None
    assert rec["success"] is False  # frozen starting state must fail V1
    assert rec["verifier_result"]["verifier"] == "format-doc"
    assert rec["condition_id"] == "C0"
    assert rec["consumer_identity"] == runner.CONSUMER_IDENTITY
    cell_dir = tmp_path / rec["tag"].replace(":", "_")
    for name in ("context.txt", "context-meta.json", "prompt.txt",
                 "consumer-trace.jsonl", "trace-stats.json", "trial.json"):
        assert (cell_dir / name).is_file(), name
    stats = json.loads((cell_dir / "trace-stats.json").read_text(encoding="utf-8"))
    assert stats["parsed_recovery_actions"] == 1  # item_1 deduped
    assert stats["usage_turns"] == [{"input_tokens": 10, "output_tokens": 3}]


def test_smoke_cell_suite_green_with_integrity_gate(runner, tmp_path):
    """I-A1/C0 runs the suite-green path incl. R6 integrity re-hash."""
    rec = runner.run_case_condition(
        CASES_DIR, tmp_path, "I-A1", "C0", consumer_backend=_stub_backend)
    assert rec["invalid_reason"] is None
    assert rec["success"] is False  # starting state fails V1
    assert rec["verifier_result"]["verifier"] == "suite-green"
    assert rec["verifier_result"]["grading_integrity"] == "ok"


def test_parse_trace_dedupes_updated_completed(runner):
    """R3: one action emitting updated+completed counts once (id-less)."""
    trace = (
        '{"type": "item.updated", "item": {"type": "command_execution", '
        '"command": "ls", "status": "running"}}\n'
        '{"type": "item.completed", "item": {"type": "command_execution", '
        '"command": "ls", "exit_code": 0, "status": "completed"}}\n'
    )
    path = Path("/tmp") / "smoke-double-count.jsonl"
    path.write_text(trace, encoding="utf-8")
    try:
        stats = runner.parse_trace(path)
    finally:
        path.unlink(missing_ok=True)
    assert stats["exec_calls"] == 1
    assert stats["parsed_recovery_actions"] == 1
    assert "verified_recovery_actions" not in stats


def test_parse_trace_dedupes_by_item_id(runner):
    """R3: started+completed with the same id count once."""
    trace = (
        '{"type": "item.started", "item": {"id": "item_7", '
        '"type": "command_execution", "command": "x", "status": "in_progress"}}\n'
        '{"type": "item.completed", "item": {"id": "item_7", '
        '"type": "command_execution", "command": "x", "exit_code": 0, '
        '"status": "completed"}}\n'
    )
    path = Path("/tmp") / "smoke-item-id.jsonl"
    path.write_text(trace, encoding="utf-8")
    try:
        stats = runner.parse_trace(path)
    finally:
        path.unlink(missing_ok=True)
    assert stats["exec_calls"] == 1


def test_parse_trace_keeps_per_turn_usage(runner):
    """R4: every turn.completed.usage is preserved in order."""
    trace = (
        '{"type": "turn.completed", "usage": {"input_tokens": 5, '
        '"output_tokens": 2}}\n'
        '{"type": "turn.completed", "usage": {"input_tokens": 9, '
        '"output_tokens": 4}}\n'
    )
    path = Path("/tmp") / "smoke-usage.jsonl"
    path.write_text(trace, encoding="utf-8")
    try:
        stats = runner.parse_trace(path)
    finally:
        path.unlink(missing_ok=True)
    assert stats["usage_turns"] == [{"input_tokens": 5, "output_tokens": 2},
                                    {"input_tokens": 9, "output_tokens": 4}]
    assert stats["usage"] == {"input_tokens": 9, "output_tokens": 4}
    assert stats["usage_semantics"] == "unresolved-U1"


def test_audit_trace_flags_direct_and_relative_escapes(runner, tmp_path):
    """R2: direct absolute path + relative .. in command both flagged."""
    trace = (
        '{"type": "turn.started"}\n'
        '{"type": "item.completed", "item": {"type": "file_change", '
        '"path": "/etc/passwd"}}\n'
        '{"type": "item.completed", "item": {"type": "command_execution", '
        '"command": "cat ../../outside.txt", "exit_code": 0, '
        '"status": "completed"}}\n'
        '{"type": "turn.completed", "usage": {"input_tokens": 5, '
        '"output_tokens": 7}}\n'
    )
    trace_path = tmp_path / "gap.jsonl"
    trace_path.write_text(trace, encoding="utf-8")
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    stats = runner.parse_trace(trace_path)
    assert runner.audit_trace(stats, str(workdir)) is not None


def test_parse_trace_collects_file_change_paths(runner, tmp_path):
    """F1: observed file_change shape carries paths in changes[] ({path,
    kind}); each must appear in path_mentions so R2 confinement audits it."""
    trace = (
        '{"type": "item.completed", "item": {"id": "fc_1", '
        '"type": "file_change", "status": "completed", "changes": ['
        '{"path": "/etc/shadow", "kind": "modification"}, '
        '{"path": "notes.txt", "kind": "addition"}]}}\n'
    )
    trace_path = tmp_path / "changes.jsonl"
    trace_path.write_text(trace, encoding="utf-8")
    stats = runner.parse_trace(trace_path)
    assert stats["write_calls"] == 1
    values = [m["value"] for m in stats["path_mentions"]]
    assert "/etc/shadow" in values
    assert "notes.txt" in values
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    assert runner.audit_trace(stats, str(workdir)) is not None


def test_audit_trace_allows_inside_paths(runner, tmp_path):
    """R2: in-workdir absolute + relative paths are not flagged."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    trace = (
        '{"type": "item.completed", "item": {"id": "a", '
        '"type": "command_execution", '
        f'"command": "cat {workdir}/hello.txt sub/dir/x.py", '
        '"exit_code": 0, "status": "completed"}}\n'
    )
    trace_path = tmp_path / "ok.jsonl"
    trace_path.write_text(trace, encoding="utf-8")
    stats = runner.parse_trace(trace_path)
    assert runner.audit_trace(stats, str(workdir)) is None


def test_grading_integrity_flags_tamper(runner, tmp_path):
    """R6: modified/removed grading scripts + added conftest fail closed."""
    case_dir = CASES_DIR / "I-A1"
    pristine = tmp_path / "pristine"
    shutil.copytree(case_dir / "workdir", pristine)
    assert runner.check_grading_integrity(case_dir, pristine) is None

    modified = tmp_path / "modified"
    shutil.copytree(case_dir / "workdir", modified)
    script = modified / "run_tests.sh"
    script.write_text(script.read_text(encoding="utf-8") + "\n# tamper\n",
                      encoding="utf-8")
    assert "modified" in runner.check_grading_integrity(case_dir, modified)

    added = tmp_path / "added"
    shutil.copytree(case_dir / "workdir", added)
    (added / "conftest.py").write_text("collect_ignore = []\n", encoding="utf-8")
    assert "added" in runner.check_grading_integrity(case_dir, added)


def test_empty_probe_cell_uses_empty_context(runner, tmp_path):
    """R8 batch-2 cell shape: same template slots, empty memory context."""
    rec = runner.run_case_condition(
        CASES_DIR, tmp_path, "W-A1", runner.EMPTY_CONDITION,
        consumer_backend=_stub_backend)
    assert rec["invalid_reason"] is None
    cell_dir = tmp_path / rec["tag"].replace(":", "_")
    assert (cell_dir / "context.txt").read_text(encoding="utf-8") == ""
    meta = json.loads((cell_dir / "context-meta.json").read_text(encoding="utf-8"))
    assert meta["empty_probe"] is True
    assert "MEMORY CONTEXT" in (cell_dir / "prompt.txt").read_text(encoding="utf-8")


PROFILE_ONLY_LAUNCH = (
    ROOT / "evidence" / "muse-20261011" / "consumer-isolation"
    / "parent-native-live" / "profile-only" / "LAUNCH.json"
)


def test_consumer_filesystem_rule_exact_shape(runner):
    """Profile rule byte-shape: deny root, minimal read, bin read,
    dependency-runtime read (feasibility amendment 2026-10-12), cell write."""
    rule = runner.consumer_filesystem_rule(
        "/opt/codex/bin", "/tmp/cell-1", "/repo/.venv-linux")
    assert rule == (
        '{":root" = "deny", ":minimal" = "read", '
        '"/opt/codex/bin" = "read", "/tmp/cell-1" = "write", '
        '"/repo/.venv-linux" = "read"}'
    )


def test_build_consumer_argv_matches_qualified_launch(runner, tmp_path):
    """Amendments 2026-10-11/12: argv is byte-identical to the qualified
    profile-only LAUNCH.json modulo workdir/bin-dir/dep-runtime/prompt
    substitution; no -s/--sandbox/workspace-write anywhere. The feasibility
    amendment adds exactly one rule pair (dep runtime read); the qualified
    baseline's flag order and all other pairs are unchanged."""
    workdir = tmp_path / "cell"
    workdir.mkdir()
    workdir_abs = str(workdir.resolve())
    bin_dir = "/opt/codex/bin-test"
    dep_dir = "/repo/.venv-linux"
    prompt = "TEST-PROMPT"
    argv = runner.build_consumer_argv(
        prompt, workdir, codex_bin_dir=bin_dir, dep_runtime_dir=dep_dir)
    assert "-s" not in argv
    assert not any("sandbox" in token for token in argv)
    assert not any("workspace-write" in token for token in argv)

    qualified = json.loads(PROFILE_ONLY_LAUNCH.read_text(encoding="utf-8"))["argv"]
    expected = list(qualified)
    expected[expected.index("-C") + 1] = workdir_abs
    for pos, token in enumerate(expected):
        if token.startswith("permissions."):
            expected[pos] = (
                "permissions.consumer-trial.filesystem="
                + runner.consumer_filesystem_rule(
                    bin_dir, workdir_abs, dep_dir)
            )
    expected[-1] = prompt
    assert argv == expected

    # The rule is the qualified baseline shape (same bin/workdir pairs)
    # plus exactly one appended dep-runtime read pair: no reordered,
    # removed, or weakened pairs.
    baseline_shaped = (
        '{":root" = "deny", ":minimal" = "read", '
        f'"{bin_dir}" = "read", "{workdir_abs}" = "write"}}'
    )
    new_rule = next(
        t.split("=", 1)[1] for t in argv if t.startswith("permissions."))
    assert new_rule == baseline_shaped[:-1] + f', "{dep_dir}" = "read"}}'
    assert new_rule.count('" = "read"') == 3
    assert new_rule.count('" = "write"') == 1
    assert new_rule.count('" = "deny"') == 1


def test_build_consumer_argv_rejects_relative_workdir(runner):
    """Fail closed: relative workdirs never reach the consumer."""
    with pytest.raises(TrialError, match="not absolute"):
        runner.build_consumer_argv(
            "p", Path("relative/cell"), codex_bin_dir="/opt/codex/bin",
            dep_runtime_dir="/repo/.venv-linux")


def test_build_consumer_argv_rejects_bad_dep_runtime(runner, tmp_path):
    """Fail closed: relative or /home dep runtimes never reach the consumer."""
    workdir = tmp_path / "cell"
    workdir.mkdir()
    with pytest.raises(TrialError, match="not absolute"):
        runner.build_consumer_argv(
            "p", workdir, codex_bin_dir="/opt/codex/bin",
            dep_runtime_dir="relative/.venv-linux")
    with pytest.raises(TrialError, match="/home"):
        runner.build_consumer_argv(
            "p", workdir, codex_bin_dir="/opt/codex/bin",
            dep_runtime_dir="/home/someone/.venv-linux")


def test_check_codex_version_fail_closed(runner, monkeypatch):
    """Fail closed unless `codex --version` stdout is exactly pinned."""
    calls = []

    class _Proc:
        def __init__(self, stdout, returncode=0):
            self.stdout = stdout
            self.returncode = returncode

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Proc("codex-cli 0.999.9\n")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    with pytest.raises(TrialError, match="pinned"):
        runner.check_codex_version()
    assert calls and calls[0][:2] == ["codex", "--version"]

    def _fake_run_ok(cmd, **kwargs):
        return _Proc(runner.PINNED_CODEX_VERSION + "\n")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run_ok)
    assert runner.check_codex_version() == runner.PINNED_CODEX_VERSION


def test_codex_binary_dir_fail_closed(runner, monkeypatch):
    """Fail closed when no codex binary is on PATH."""
    monkeypatch.setattr(runner.shutil, "which", lambda _name: None)
    with pytest.raises(TrialError, match="not found on PATH"):
        runner.codex_binary_dir()


def test_dependency_runtime_dir_markers(runner, monkeypatch, tmp_path):
    """Fail closed unless the anchored runtime carries both markers."""
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(TrialError, match="runtime missing"):
        runner.dependency_runtime_dir()
    venv = tmp_path / ".venv-linux"
    (venv / "bin").mkdir(parents=True)
    with pytest.raises(TrialError, match="marker missing"):
        runner.dependency_runtime_dir()
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    with pytest.raises(TrialError, match="marker missing"):
        runner.dependency_runtime_dir()
    (venv / "bin" / "python-trial").write_text("#!/bin/x\n", encoding="utf-8")
    assert runner.dependency_runtime_dir() == str(venv.resolve())


def test_dependency_runtime_dir_live_markers(runner):
    """The real repo runtime resolves and carries both markers."""
    resolved = runner.dependency_runtime_dir()
    assert resolved == str((ROOT / ".venv-linux").resolve())
    assert "/home/" not in resolved


# --- Muse/F1 backend (A5/r6; codex tests above unchanged) ---

F1_EXEC = ROOT / "evidence" / "muse-20261011" / "codexfree-f1-20261012" / "f1_exec.sh"


def _msp_line(payload_type, payload):
    return json.dumps({"schema_version": 1, "id": "x", "stream": {},
                       "sequence": 1, "recorded_at": 1,
                       "record_type": "event", "durability": "durable",
                       "causation_id": "y", "payload_type": payload_type,
                       "payload_schema_version": 1, "payload": payload})


def _tool_result(call_id, tool_name, outcome, text):
    return _msp_line("tool.result", {
        "call_id": call_id, "command_id": "c",
        "correlation_facts": {"outcome": outcome, "tool_name": tool_name},
        "kind": "tool_result", "run_stream": {}, "text": text})


_MSP_IDENTITY = _msp_line("run.model.configured", {
    "command_id": "c", "kind": "run_model_configured",
    "model_id": "muse-spark-1.3", "profile_id": "tbh",
    "provider_id": "meta", "run_stream": {}, "source": "startup"})


def test_muse_argv_exact_shape(runner, tmp_path, monkeypatch):
    """A5.1: f1 + workdir + frozen inner tuple; --workspace == workdir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TMPDIR", raising=False)
    workdir = tmp_path / "cell"
    workdir.mkdir()
    prompt_file = workdir / "p.txt"
    prompt_file.write_text("PROMPT", encoding="utf-8")
    argv = runner.build_muse_argv(
        prompt_file, workdir, f1_exec=str(F1_EXEC))
    assert argv[0] == str(F1_EXEC.resolve())
    assert argv[1] == str(workdir.resolve())
    inner = argv[2:]
    assert inner[0] == "exec" and inner[1] == "--json"
    assert inner[inner.index("--provider") + 1] == "meta"
    assert inner[inner.index("--model") + 1] == "muse-spark-1.3"
    assert inner[inner.index("--reasoning-effort") + 1] == "high"
    assert inner[inner.index("--prompt-file") + 1] == str(prompt_file.resolve())
    assert inner[inner.index("--workspace") + 1] == str(workdir.resolve())
    assert inner[inner.index("--sandbox-network") + 1] == "restricted"
    for flag in ("--disable-web-tools", "--disable-reminders",
                 "--no-foreign-personal-context", "--no-session-log",
                 "--disable-approval"):
        assert flag in inner
    for token in inner:
        assert token not in runner.MUSE_FORBIDDEN_EXACT
        assert not token.startswith(runner.MUSE_FORBIDDEN_PREFIX)


def test_muse_argv_rejects_bad_placement(runner, tmp_path, monkeypatch):
    """Fail closed: relative, non-$HOME, or $TMPDIR workdirs."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    prompt_file = tmp_path / "p.txt"
    prompt_file.write_text("P", encoding="utf-8")
    with pytest.raises(TrialError, match="not absolute"):
        runner.build_muse_argv(
            prompt_file, Path("relative/cell"), f1_exec=str(F1_EXEC))
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(TrialError, match=r"not under \$HOME"):
        runner.build_muse_argv(
            prompt_file, outside, f1_exec=str(F1_EXEC))
    under_tmp = tmp_path / "tmp" / "cell"
    under_tmp.mkdir(parents=True)
    # under_tmp is outside $HOME too; make a HOME+TMPDIR overlap case:
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(TrialError, match=r"under \$TMPDIR"):
        runner.build_muse_argv(
            prompt_file, under_tmp, f1_exec=str(F1_EXEC))


def test_muse_argv_rejects_f1_drift_and_overrides(runner, tmp_path, monkeypatch):
    """Fail closed: f1 sha drift, missing prompt, F1_* env overrides."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TMPDIR", raising=False)
    workdir = tmp_path / "cell"
    workdir.mkdir()
    prompt_file = workdir / "p.txt"
    prompt_file.write_text("P", encoding="utf-8")
    stray = tmp_path / "stray.txt"
    stray.write_text("P", encoding="utf-8")
    with pytest.raises(TrialError, match="outside cell workdir"):
        runner.build_muse_argv(
            stray, workdir, f1_exec=str(F1_EXEC))
    drifted = tmp_path / "f1_exec.sh"
    drifted.write_bytes(F1_EXEC.read_bytes() + b"# drift\n")
    with pytest.raises(TrialError, match="sha drift"):
        runner.build_muse_argv(
            prompt_file, workdir, f1_exec=str(drifted))
    with pytest.raises(TrialError, match="prompt file missing"):
        runner.build_muse_argv(
            workdir / "absent.txt", workdir, f1_exec=str(F1_EXEC))
    monkeypatch.setenv("F1_VENV_DIR", "/tmp/evil-venv")
    with pytest.raises(TrialError, match="F1_VENV_DIR"):
        runner.build_muse_argv(
            prompt_file, workdir, f1_exec=str(F1_EXEC))


def test_check_muse_version_fail_closed(runner, monkeypatch):
    """Fail closed unless `muse --version` stdout is exactly pinned."""

    class _Proc:
        def __init__(self, stdout, returncode=0):
            self.stdout = stdout
            self.returncode = returncode

    def _fake_run(cmd, **kwargs):
        assert cmd[:2] == ["muse", "--version"]
        return _Proc("Muse Code 9.9.9\n")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    with pytest.raises(TrialError, match="pinned"):
        runner.check_muse_version()

    def _fake_run_ok(cmd, **kwargs):
        return _Proc(runner.PINNED_MUSE_VERSION + "\n")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run_ok)
    assert runner.check_muse_version() == runner.PINNED_MUSE_VERSION


def test_check_muse_version_live_pin(runner):
    """The ambient binary reports exactly the pinned client string."""
    assert runner.check_muse_version() == "Muse Code 1.4.7 (1.4.7-R6101.1)"


def _muse_sample_trace(workdir: Path) -> str:
    bash_text = json.dumps({
        "chunk_id": "exec-1-1", "command": "cat hello.txt sub/x.py",
        "description": "d", "exit_code": 0, "terminal_status": "completed",
        "output": "hi", "original_output_bytes": 2,
        "original_output_tokens": 1, "truncated": False})
    denial = ("tool failed: No such file or directory (os error 2); "
              'requested absolute path "/etc/passwd"; '
              'resolved candidate "/etc/passwd"; Active Workspace Root '
              f'"{workdir}".')
    return "\n".join([
        "NOT-JSON (banner line)",
        _MSP_IDENTITY,
        _msp_line("task.lifecycle.proposed", {
            "command_id": "c", "kind": "task_lifecycle",
            "event": {"kind": "proposed", "task_id": "t1",
                      "task_kind": "tool:bash"},
            "run_stream": {}, "task_id": "t1", "task_stream": {}}),
        _msp_line("turn.input.user", {
            "command_id": "c", "kind": "turn_input_user",
            "prompt": "ignore /etc/shadow-honeypot (prose never mined)"}),
        _tool_result("call_1", "bash", "success", bash_text),
        _tool_result("call_1", "bash", "success", bash_text),  # dup: dedupe
        _tool_result("call_2", "read_file", "failure", denial),
        _tool_result("call_3", "write_file", "success",
                     f"wrote 6 bytes to {workdir}/hello.txt"),
        _tool_result("call_4", "edit_file", "success",
                     "edited\nchanged lines: line 1\n"),
        _msp_line("run.output.delta", {
            "command_id": "c", "kind": "run_output_delta",
            "run_stream": {}, "text": "prose mentions /etc/prose (never mined)"}),
    ]) + "\n"


def test_parse_muse_trace_mapping(runner, tmp_path):
    """A5.3: SHELL/WRITE/READ sets, call_id dedupe, honest empty usage."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(_muse_sample_trace(workdir), encoding="utf-8")
    stats = runner.parse_muse_trace(trace_path)
    assert stats["trace_lines"] == 10  # banner line counted, skipped
    assert stats["trace_missing"] is False
    assert stats["usage"] == {} and stats["usage_turns"] == []
    assert stats["usage_semantics"] == runner.MUSE_USAGE_SEMANTICS
    assert stats["model"] == "muse-spark-1.3"
    assert stats["exec_calls"] == 1  # call_1 deduped
    assert stats["write_calls"] == 2  # write_file + edit_file
    assert stats["read_calls"] == 1
    assert stats["parsed_recovery_actions"] == 3
    assert stats["action_labels"][0] == "exec:cat hello.txt sub/x.py"
    values = [m["value"] for m in stats["path_mentions"]]
    assert "/etc/passwd" in values
    assert f"{workdir}/hello.txt" in values
    assert "cat hello.txt sub/x.py" in values
    # Prose/prompt echoes are never mined.
    assert not any("honeypot" in v or "prose" in v for v in values)


def test_parse_muse_trace_schema_identical(runner, tmp_path):
    """trace-stats.json keys are EXACTLY the current schema (scorer-safe)."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(_muse_sample_trace(workdir), encoding="utf-8")
    muse_keys = set(runner.parse_muse_trace(trace_path).keys())
    codex_path = tmp_path / "codex.jsonl"
    codex_path.write_text('{"type": "turn.completed", "usage": {}}\n',
                          encoding="utf-8")
    assert muse_keys == set(runner.parse_trace(codex_path).keys())
    assert muse_keys == set(runner.empty_trace_stats().keys())


def test_muse_audit_flags_outside_and_triggers(runner, tmp_path):
    """A2-analog + A5.4: outside tokens and subagent/web tasks are invalid."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(_muse_sample_trace(workdir), encoding="utf-8")
    stats = runner.parse_muse_trace(trace_path)
    assert runner.audit_trace(stats, str(workdir)) is not None  # /etc/passwd

    clean = "\n".join([
        _MSP_IDENTITY,
        _tool_result("c1", "bash", "success", json.dumps({
            "chunk_id": "e", "command": "./run_tests.sh",
            "description": "d", "exit_code": 0,
            "terminal_status": "completed", "output": "ok",
            "original_output_bytes": 2, "original_output_tokens": 1,
            "truncated": False})),
        _tool_result("c2", "write_file", "success",
                     f"wrote 3 bytes to {workdir}/a.txt"),
    ]) + "\n"
    clean_path = tmp_path / "clean.jsonl"
    clean_path.write_text(clean, encoding="utf-8")
    assert runner.audit_trace(
        runner.parse_muse_trace(clean_path), str(workdir)) is None

    evil = "\n".join([
        _MSP_IDENTITY,
        _msp_line("task.lifecycle.proposed", {
            "command_id": "c", "kind": "task_lifecycle",
            "event": {"kind": "proposed", "task_id": "t9",
                      "task_kind": "tool:subagent_spawn"},
            "run_stream": {}, "task_id": "t9", "task_stream": {}}),
        _tool_result("c9", "web_search", "failure", "disabled"),
    ]) + "\n"
    evil_path = tmp_path / "evil.jsonl"
    evil_path.write_text(evil, encoding="utf-8")
    reason = runner.audit_trace(
        runner.parse_muse_trace(evil_path), str(workdir))
    assert reason is not None and "prohibited tool task" in reason


def test_muse_consumer_spawns_pinned_cell(runner, tmp_path, monkeypatch):
    """muse_consumer: hashed prompt file, pinned argv, identity fail-closed."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TMPDIR", raising=False)
    workdir = tmp_path / "cell"
    workdir.mkdir()
    trace_path = tmp_path / "consumer-trace.jsonl"
    seen = {}

    class _Proc:
        returncode = 0
        stderr = ""

    def _fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["cwd"] = kwargs.get("cwd")
        kwargs["stdout"].write(_muse_sample_trace(workdir))
        return _Proc()

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    monkeypatch.setattr(runner, "check_muse_version",
                        lambda: runner.PINNED_MUSE_VERSION)
    out = runner.muse_consumer("PROMPT-BYTES", workdir, trace_path)
    assert seen["cmd"][0] == str(F1_EXEC.resolve())
    assert seen["cwd"] == str(workdir.resolve())
    prompt_file = workdir / runner.MUSE_PROMPT_FILE_NAME
    assert prompt_file.read_text(encoding="utf-8") == "PROMPT-BYTES"
    assert out.costs["consumer_prompt_sha256"] == runner._sha256_file(prompt_file)
    assert out.costs["trace_model"] == "muse-spark-1.3"
    assert out.costs["trace_provider"] == "meta"
    assert out.costs["trace_profile"] == "tbh"
    assert out.costs["wall_seconds"] >= 0
    assert out.costs["consumer_f1_exec_sha256"] == runner.PINNED_F1_EXEC_SHA
    assert "parsed_recovery_actions=3" in out.notes

    def _fake_run_drift(cmd, **kwargs):
        kwargs["stdout"].write(_msp_line("run.model.configured", {
            "command_id": "c", "kind": "run_model_configured",
            "model_id": "other-model", "profile_id": "tbh",
            "provider_id": "meta", "run_stream": {}, "source": "startup"}))
        return _Proc()

    monkeypatch.setattr(runner.subprocess, "run", _fake_run_drift)
    with pytest.raises(TrialError, match="trace identity"):
        runner.muse_consumer("P", workdir, tmp_path / "drift.jsonl")


def _muse_stub_backend(prompt: str, workdir: Path, trace_path: Path):
    """No-model muse cell: archives a minimal honest MSP trace."""
    trace_path.write_text("\n".join([
        _MSP_IDENTITY,
        _tool_result("s1", "bash", "success", json.dumps({
            "chunk_id": "e", "command": "ls",
            "description": "d", "exit_code": 0,
            "terminal_status": "completed", "output": "",
            "original_output_bytes": 0, "original_output_tokens": 0,
            "truncated": False})),
    ]) + "\n", encoding="utf-8")
    return ConsumerOutput(
        output_text="muse stub (no model): no changes made",
        recovery_actions=[],
        costs={"stub": True},
        notes="smoke",
    )


_muse_stub_backend.is_muse_backend = True
_muse_stub_backend.backend_identity = "muse-f1-spark-1.3"


def test_muse_cell_wiring_uses_muse_parser(runner, tmp_path):
    """run_case_condition with a muse backend: muse identity + parser."""
    rec = runner.run_case_condition(
        CASES_DIR, tmp_path, "W-A1", "C0",
        consumer_backend=_muse_stub_backend)
    assert rec["invalid_reason"] is None
    assert rec["success"] is False
    assert rec["consumer_identity"] == runner.MUSE_CONSUMER_IDENTITY
    cell_dir = tmp_path / rec["tag"].replace(":", "_")
    stats = json.loads((cell_dir / "trace-stats.json").read_text(encoding="utf-8"))
    assert stats["usage_semantics"] == runner.MUSE_USAGE_SEMANTICS
    assert stats["parsed_recovery_actions"] == 1
    assert stats["model"] == "muse-spark-1.3"


def test_qual_parseable_shape_preserved(runner):
    """R7: PROMPT_TEMPLATE literal regex + 7-name BATCHES parity intact."""
    import re as _re
    text = RUNNER_PATH.read_text(encoding="utf-8")
    matches = _re.findall(
        r"PROMPT_TEMPLATE\s*=\s*\"\"\"(.*?)\"\"\"", text, _re.DOTALL)
    assert len(matches) == 1
    assert matches[0].startswith("You are resuming a paused software task.")
    assert runner.BATCHES == ["primary", "sensitivity", "edge", "m2",
                              "empty-probes", "discordant", "stability"]
