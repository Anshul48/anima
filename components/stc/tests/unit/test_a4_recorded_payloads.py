"""Attempt-4 recorded legs: patch parsing + refusal on exact live bytes.

Fixtures are byte-exact copies of attempt-4/attempt-1 recorded payloads:
leg-001 served content (5691 B, admitted) and the leg-002 refused bytes
(5580 B, marker refusal; leg-002 forwarded zero bytes to SST by
construction). Provenance: evidence/BUILD/attempt-4/attempt-1/{legs/,
spend.refusals.jsonl#250226322290}. Scripted only: stub harnesses serve
the bytes in-process; no model calls, no network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from sst.core.contracts import CandidateProposal
from sst.gateway.contracts import ProviderGatewayError
from sst.search.controller import SSTSearchController

from stc.integration.adapters import proposal_to_filetargets
from stc.integration.cli_gateway import (
    MARKER_REFUSAL_RULE,
    CLIGatewayBackend,
    marker_refusal_reason,
)
from stc.integration.harness_worker import SpendLedger

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_LEG_001 = _FIXTURES / "a4-leg-001-content.txt"
_LEG_002_REFUSED = _FIXTURES / "a4-leg-002-refused.txt"

#: Guard pins: exact recorded sizes + shas (drift fails loudly).
_LEG_001_PIN = (
    5691,
    "9ed668b920ead436b6045a5d28b62df7388882be298129ed6a219c53ecb2740c",
)
_LEG_002_PIN = (
    5580,
    "0c93b2cc06b3f2c9a9bbf1bababfd82cc4261e4336f7551b49ca9d06224ae252",
)

_TARGET = "tests/unit/test_integration_runner_pins.py"


def _pinned_text(path: Path, pin: tuple[int, str]) -> str:
    raw = path.read_bytes()
    size, sha = pin
    assert len(raw) == size, f"{path.name} size drift"
    assert hashlib.sha256(raw).hexdigest() == sha, f"{path.name} byte drift"
    return raw.decode("utf-8")


def _proposal_for(patch_diff: str) -> CandidateProposal:
    return CandidateProposal(
        candidate_id="cand-a4",
        tree_id="ATTEMPT-4-PINS",
        parent_ids=["root"],
        role="DIVERGE",
        title="Evidence-Carrying Fault Injection",
        rationale="recorded",
        target_paths=[_TARGET],
        patch_diff=patch_diff,
        model_id="scripted-test-double",
    )


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


def test_leg_001_admitted_and_parses_to_create_target() -> None:
    """Recorded leg-001: admitted, one branch, create-target patch."""
    served = _pinned_text(_LEG_001, _LEG_001_PIN)
    assert marker_refusal_reason(served) is None
    branches = SSTSearchController._parse_json_dict(served)["branches"]
    assert isinstance(branches, list) and len(branches) == 1
    patch = str(branches[0]["proposed_changes"])
    assert patch.startswith("--- /dev/null\n")
    targets = proposal_to_filetargets(_proposal_for(patch))
    assert [(t.path, t.action) for t in targets] == [(_TARGET, "create")]


def test_leg_002_refused_on_recorded_end_line() -> None:
    """Recorded leg-002 refused bytes trip the live offending line."""
    refused = _pinned_text(_LEG_002_REFUSED, _LEG_002_PIN)
    assert marker_refusal_reason(refused) == "*** End Patch"


def test_leg_002_generate_refuses_with_honest_ledger(tmp_path: Path) -> None:
    """Serving the recorded leg-002 bytes refuses pre-dispatch, honestly logged."""
    refused = _pinned_text(_LEG_002_REFUSED, _LEG_002_PIN)
    harness = _StubHarness(refused)
    backend = CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        ledger=SpendLedger(tmp_path / "spend" / "test.jsonl"),
        harness=harness,
    )
    with pytest.raises(ProviderGatewayError) as excinfo:
        backend.generate("SST-PROMPT", profile="cli")
    assert len(harness.calls) == 1  # no gateway-internal retry
    err = excinfo.value
    assert err.category == "stc_marker_refusal"
    assert "no bytes forwarded to SST" in str(err.message)
    assert refused not in str(err.message)

    rows = [
        json.loads(line)
        for line in (tmp_path / "spend" / "test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["ok"] is True  # harness truth: it served
    assert rows[0]["note"].startswith(f"stc-refused: {MARKER_REFUSAL_RULE} (")
    sidecar = tmp_path / "spend" / "test.refusals.jsonl"
    record = json.loads(sidecar.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["refused_bytes"] == refused
    assert record["refused_sha256"] == _LEG_002_PIN[1]
