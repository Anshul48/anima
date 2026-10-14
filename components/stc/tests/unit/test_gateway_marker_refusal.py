"""Gateway marker refusal: column-0 `***` responses refused pre-dispatch (MARKERS §5)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from sst.gateway.contracts import ProviderGatewayError

from stc.integration.cli_gateway import (
    MARKER_REFUSAL_RULE,
    SST_PROMPT_BEGIN,
    SST_PROMPT_END,
    CLIGatewayBackend,
    marker_refusal_reason,
    shape_gateway_prompt,
)
from stc.integration.harness_worker import SpendLedger

_REPO = Path(__file__).resolve().parents[2]
_FOLLOWUP = _REPO / "docs/builds/stc-integration/evidence/FOLLOWUP"
_A1_EVENTS = _FOLLOWUP / "accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/events.json"
_A2_EVENTS = _FOLLOWUP / "accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/events.json"
_A3_EVENTS = _FOLLOWUP / "accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/events.json"
_P2_STDOUT = _FOLLOWUP / "live-exp/attempt-1/P2-H3a/stdout.txt"

#: Guard pins: exact live payload sizes + shas (drift fails loudly, never silently).
_LIVE_PINS = {
    "a1": (3685, "1e8ddb6f3d0f2c5e5c1fd22c3b49a727a384f79d00f9e3ff3e5f69a23e3b9ece"),
    "a2c0": (5182, "44a77e3048d6ce0ee9c5571912d41f1cac5de6a617ceb4793a291d0c90509a11"),
    "a2c1": (3929, "0c7052d6bc37e6e7d26a7037842244228c75b38fb3bc6f6b6d72567a03db2fe3"),
    "a3c0": (5534, "24ea36b2a447f804f3100a5cd08526ac3cd735ca7381a35d31f39056220ced28"),
    "a3c1": (4299, "a6c8f1d39c0e50da08ee21d0892c1cbd7527b2cbf31869ae8cae7fb5264e670b"),
}
_P2_STDOUT_PIN = (
    4997,
    "30283c5880d8e1fd912eac46e14cefa579feea39b6edd0c8a82a2c52bc4b0d37",
)


def _patch_diff(events_path: Path, index: int, pin_key: str) -> str:
    """Load the exact live `patch_diff` payload with size+sha guard pins."""
    events = json.loads(events_path.read_text(encoding="utf-8"))
    proposed = [e for e in events if e.get("kind") == "NODE_PROPOSED"]
    patch = str(proposed[index]["payload"]["patch_diff"])
    raw = patch.encode("utf-8")
    size, sha = _LIVE_PINS[pin_key]
    assert len(raw) == size, f"{pin_key} size drift"
    assert hashlib.sha256(raw).hexdigest() == sha, f"{pin_key} byte drift"
    return patch


def _branches_envelope(patch: str) -> str:
    """Wrap exact patch bytes in a §2 branches response (SST parse shape)."""
    return json.dumps({"branches": [{"branch_index": 0, "proposed_changes": patch}]})


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
    """Minimal HarnessT-satisfying stub serving one scripted response."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def execute(
        self,
        prompt: str,
        role: str = "general",
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> _StubResult:
        self.calls.append({"prompt": prompt, "role": role, "model": model, "context": context})
        return _StubResult(self.content)


def _backend(tmp_path: Path, content: str) -> tuple[CLIGatewayBackend, _StubHarness]:
    harness = _StubHarness(content)
    backend = CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        ledger=SpendLedger(tmp_path / "spend" / "test.jsonl"),
        harness=harness,
    )
    return backend, harness


def _ledger_rows(tmp_path: Path) -> list[dict[str, Any]]:
    text = (tmp_path / "spend" / "test.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --- Refuse matrix: exact live marker-bearing bytes ---------------------------


def test_refuses_p2_winner_stdout_exact() -> None:
    """The exact P2 served §2 response (trailer-only) is refused."""
    raw = _P2_STDOUT.read_bytes()
    size, sha = _P2_STDOUT_PIN
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha
    assert marker_refusal_reason(raw.decode("utf-8")) == "*** End Patch"


@pytest.mark.parametrize(
    ("events_path", "index", "pin_key"),
    [(_A2_EVENTS, 0, "a2c0"), (_A3_EVENTS, 0, "a3c0")],
)
def test_refuses_trailer_legs_exact(events_path: Path, index: int, pin_key: str) -> None:
    """Exact a2c0/a3c0 unified+trailer payloads are refused on the End line."""
    patch = _patch_diff(events_path, index, pin_key)
    assert marker_refusal_reason(_branches_envelope(patch)) == "*** End Patch"


@pytest.mark.parametrize(
    ("events_path", "index", "pin_key"),
    [(_A1_EVENTS, 0, "a1"), (_A2_EVENTS, 1, "a2c1")],
)
def test_refuses_apply_patch_envelopes_exact(events_path: Path, index: int, pin_key: str) -> None:
    """Exact a1/a2c1 pure apply_patch payloads are refused on the Begin line."""
    patch = _patch_diff(events_path, index, pin_key)
    assert marker_refusal_reason(_branches_envelope(patch)) == "*** Begin Patch"


def test_refuses_unified_plus_trailer_synthetic() -> None:
    """Well-formed unified diff + lone trailing End is refused."""
    patch = "--- /dev/null\n+++ tests/unit/test_x.py\n@@ -0,0 +1 @@\n+x = 1\n*** End Patch"
    assert marker_refusal_reason(_branches_envelope(patch)) == "*** End Patch"


def test_refuses_raw_fallback_with_markers() -> None:
    """Non-JSON raw code with a marker line is refused (whole-content scan)."""
    assert marker_refusal_reason("x = 1\n*** End Patch\n") == "*** End Patch"


def test_refuses_unparseable_json_with_markers() -> None:
    """Unparseable JSON falls back to whole-content scan and is refused."""
    assert marker_refusal_reason('{"branches": [\n*** End Patch') == "*** End Patch"


def test_refusal_truncates_long_offending_line() -> None:
    """The offending line is truncated to 80 chars (full bytes stay in sidecar)."""
    long_line = "*** " + "x" * 200
    assert marker_refusal_reason(long_line + "\n") == long_line[:80]


def test_branches_selection_semantics_exact() -> None:
    """Non-empty branches scan proposed_changes only; empty scans whole content."""
    envelope = json.dumps(
        {"branches": [{"strategy_title": "*** End Patch", "proposed_changes": "clean = 1\n"}]}
    )
    assert marker_refusal_reason(envelope) is None
    second_dirty = json.dumps(
        {
            "branches": [
                {"proposed_changes": "clean = 1\n"},
                {"proposed_changes": "x = 1\n*** End Patch\n"},
            ]
        }
    )
    assert marker_refusal_reason(second_dirty) == "*** End Patch"
    assert marker_refusal_reason('{"branches": []}\n*** End Patch\n') == "*** End Patch"


# --- Admit matrix --------------------------------------------------------------


def test_admits_pin_held_a3c1_exact() -> None:
    """The exact pin-held a3c1 marker-free payload is admitted."""
    patch = _patch_diff(_A3_EVENTS, 1, "a3c1")
    assert "***" not in patch
    assert marker_refusal_reason(_branches_envelope(patch)) is None


def test_admits_known_good_diff_shape() -> None:
    """A marker-free unified diff (PATH-REVIEW §2 shape) is admitted."""
    patch = (
        "diff --git a/tests/unit/test_pins.py b/tests/unit/test_pins.py\n"
        "--- /dev/null\n"
        "+++ b/tests/unit/test_pins.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+from stc.integration.dialectic_runner import DialecticRunner\n"
        "+def test_entry() -> None:\n"
        "+    assert hasattr(DialecticRunner, 'run_async')\n"
    )
    assert marker_refusal_reason(_branches_envelope(patch)) is None


def test_admits_indented_and_bold_markers() -> None:
    """Non-column-0 `***` (indented, markdown-bold) stays admissible."""
    content = "text\n   *** End Patch\n ***bold*** and `***code***`\n"
    assert marker_refusal_reason(content) is None
    assert marker_refusal_reason(_branches_envelope(content)) is None


def test_admits_marker_free_raw_code() -> None:
    """Marker-free raw code is admitted."""
    assert marker_refusal_reason("def f() -> int:\n    return 42\n") is None


# --- Ledger honesty + forensic preservation (generate-level) -------------------


def test_generate_refuses_with_honest_ledger_and_sidecar(tmp_path: Path) -> None:
    """Refusal: ok=True row + refusal note + sidecar round-trips exact bytes."""
    patch = _patch_diff(_A3_EVENTS, 0, "a3c0")
    served = _branches_envelope(patch)
    backend, harness = _backend(tmp_path, served)
    with pytest.raises(ProviderGatewayError) as excinfo:
        backend.generate("SST-PROMPT", profile="cli")
    assert len(harness.calls) == 1  # no gateway-internal retry
    err = excinfo.value
    assert err.category == "stc_marker_refusal"
    assert "no bytes forwarded to SST" in str(err.message)
    assert "*** End Patch" in str(err.message)
    assert served not in str(err.message)  # never the full bytes
    assert err.profile == "cli"

    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["ok"] is True  # harness truth: it served
    assert row["note"].startswith(f"stc-refused: {MARKER_REFUSAL_RULE} (")
    assert ".refusals.jsonl#" in row["note"]
    assert "failure_evidence" not in row  # note-only pointer, not the F1 key

    sidecar = tmp_path / "spend" / "test.refusals.jsonl"
    assert sidecar.is_file()
    record = json.loads(sidecar.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["rule"] == MARKER_REFUSAL_RULE
    assert record["offending_line"] == "*** End Patch"
    assert record["refused_bytes"] == served
    assert record["refused_sha256"] == hashlib.sha256(served.encode("utf-8")).hexdigest()
    assert record["profile"] == "cli"
    assert not (tmp_path / "spend" / "test.failures.jsonl").exists()  # not the F1 sidecar


def test_generate_admits_clean_response_byte_identical(tmp_path: Path) -> None:
    """Admitted payloads travel byte-identically; no refusal artifacts."""
    patch = _patch_diff(_A3_EVENTS, 1, "a3c1")
    served = _branches_envelope(patch)
    backend, harness = _backend(tmp_path, served)
    assert backend.generate("SST-PROMPT", profile="cli") == served
    assert len(harness.calls) == 1
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["ok"] is True and rows[0]["note"] == ""
    assert not (tmp_path / "spend" / "test.refusals.jsonl").exists()


# --- Frame interaction (D15/D7) -------------------------------------------------


def test_sst_bytes_verbatim_through_frame_with_markers() -> None:
    """D15/D7 intact post-refusal: even marker-bearing SST bytes pass unedited."""
    sst = "*** Begin Patch\n*** Add File: x.py\n+code\n*** End Patch\n"
    shaped = shape_gateway_prompt(sst)
    assert shaped.count(sst) == 1
    assert shaped.index(SST_PROMPT_BEGIN) < shaped.index(sst) < shaped.index(SST_PROMPT_END)
