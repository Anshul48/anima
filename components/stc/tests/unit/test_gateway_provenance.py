"""Unit tests for critique provenance recording (Fix 2)."""

import json
from pathlib import Path
from typing import Any

import pytest
from sst.gateway.contracts import ProviderGatewayError

from stc.integration.cli_gateway import CLIGatewayBackend
from stc.integration.harness_worker import SpendLedger

VALID_CRITIQUE = json.dumps(
    {"value_score": 0.9, "verdict": "APPROVE", "rationale": "covers all clauses"}
)


class _StubResult:
    def __init__(self, content: str, ok: bool = True, error: str | None = None) -> None:
        self.content = content
        self.exit_code = 0 if ok else 1
        self.error = error
        self._ok = ok

    @property
    def is_success(self) -> bool:
        return self._ok


class _StubHarness:
    def __init__(self, results: list[_StubResult]) -> None:
        self._results = list(results)
        self.roles: list[str] = []

    def execute(
        self,
        prompt: str,
        role: str = "general",
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> _StubResult:
        self.roles.append(role)
        return self._results.pop(0)


def _backend(tmp_path: Path, harness: _StubHarness) -> CLIGatewayBackend:
    return CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        ledger=SpendLedger(tmp_path / "spend.jsonl"),
        harness=harness,
    )


def test_valid_critique_records_valid_witness(tmp_path: Path) -> None:
    backend = _backend(tmp_path, _StubHarness([_StubResult(VALID_CRITIQUE)]))
    assert backend.generate("p", sst_role="critique") == VALID_CRITIQUE
    (witness,) = backend.critique_provenance
    assert (witness.seq, witness.valid, witness.ledger_row) == (0, True, 0)
    assert witness.detail == "ok"


CORTEX_CRITIQUE = json.dumps(
    {
        "evaluations": [
            {
                "node_id": "n1",
                "verdict": "APPROVE",
                "value_score": 0.92,
                "architectural_fit": 0.9,
                "critique": "solid layering, full invariant coverage",
                "synthesis_hints": [],
            }
        ],
        "best_node_id": "n1",
        "synthesis_opportunity": "",
    }
)


def test_fenced_critique_records_valid_witness(tmp_path: Path) -> None:
    """Fenced JSON validates: the controller strips fences before parsing."""
    fenced = "```json\n" + VALID_CRITIQUE + "\n```"
    backend = _backend(tmp_path, _StubHarness([_StubResult(fenced)]))
    assert backend.generate("p", sst_role="critique") == fenced
    (witness,) = backend.critique_provenance
    assert witness.valid is True


def test_cortex_evaluations_critique_records_valid_witness(tmp_path: Path) -> None:
    """Capsule-path cortex shape (evaluations[0]/critique) validates."""
    backend = _backend(tmp_path, _StubHarness([_StubResult(CORTEX_CRITIQUE)]))
    assert backend.generate("p", sst_role="critique") == CORTEX_CRITIQUE
    (witness,) = backend.critique_provenance
    assert witness.valid is True


def test_cortex_synthesize_verdict_valid(tmp_path: Path) -> None:
    """SYNTHESIZE is a genuine cortex verdict, not a packaging failure."""
    content = json.dumps(
        {"evaluations": [{"verdict": "SYNTHESIZE", "value_score": 0.8, "critique": "merge a+b"}]}
    )
    backend = _backend(tmp_path, _StubHarness([_StubResult(content)]))
    backend.generate("p", sst_role="critique")
    (witness,) = backend.critique_provenance
    assert witness.valid is True


def test_cortex_missing_critique_key_invalid(tmp_path: Path) -> None:
    """evaluations[0] without 'critique' is not an explicit review."""
    content = json.dumps({"evaluations": [{"verdict": "APPROVE", "value_score": 0.9}]})
    backend = _backend(tmp_path, _StubHarness([_StubResult(content)]))
    backend.generate("p", sst_role="critique")
    (witness,) = backend.critique_provenance
    assert witness.valid is False


def test_garbage_critique_records_invalid_witness(tmp_path: Path) -> None:
    backend = _backend(tmp_path, _StubHarness([_StubResult("not json{{{")]))
    assert backend.generate("p", sst_role="critique") == "not json{{{"
    (witness,) = backend.critique_provenance
    assert witness.valid is False
    assert "unparseable" in witness.detail


def test_implicit_verdict_records_invalid_witness(tmp_path: Path) -> None:
    """A score without an explicit verdict must not validate (Path C)."""
    content = json.dumps({"value_score": 0.9, "rationale": "no verdict key"})
    backend = _backend(tmp_path, _StubHarness([_StubResult(content)]))
    assert backend.generate("p", sst_role="critique") == content
    (witness,) = backend.critique_provenance
    assert witness.valid is False


def test_failed_critique_records_invalid_and_raises(tmp_path: Path) -> None:
    harness = _StubHarness([_StubResult("", ok=False, error="boom")])
    backend = _backend(tmp_path, harness)
    with pytest.raises(ProviderGatewayError):
        backend.generate("p", sst_role="critique")
    (witness,) = backend.critique_provenance
    assert witness.valid is False
    assert "boom" in witness.detail


def test_non_critique_roles_not_recorded(tmp_path: Path) -> None:
    harness = _StubHarness([_StubResult("x"), _StubResult("y")])
    backend = _backend(tmp_path, harness)
    backend.generate("p", sst_role="diverge")
    backend.generate("p")
    assert backend.critique_provenance == ()


def test_sst_role_threaded_to_harness(tmp_path: Path) -> None:
    harness = _StubHarness([_StubResult("x")])
    backend = _backend(tmp_path, harness)
    backend.generate("p", sst_role="refine")
    assert harness.roles == ["refine"]


def test_ledger_row_index_counts_all_calls(tmp_path: Path) -> None:
    harness = _StubHarness([_StubResult("x"), _StubResult(VALID_CRITIQUE), _StubResult("z")])
    backend = _backend(tmp_path, harness)
    backend.generate("p", sst_role="diverge")
    backend.generate("p", sst_role="critique")
    backend.generate("p", sst_role="diverge")
    (witness,) = backend.critique_provenance
    assert witness.ledger_row == 1
