"""H1 emitter context: pinned read-only source package in the frame (CONTEXT.md)."""

import hashlib
from pathlib import Path

from stc.integration.cli_gateway import (
    H1_CONTEXT_PACKAGE,
    SST_PROMPT_BEGIN,
    SST_PROMPT_END,
    shape_gateway_prompt,
)

_REPO = Path(__file__).resolve().parents[2]
_PACKAGE_ARTIFACT = _REPO / "docs/builds/stc-integration/evidence/FOLLOWUP/h1-prep/ctx-package.txt"
_RUNNER = _REPO / "src/stc/integration/dialectic_runner.py"
_DIALECTIC_TEST = _REPO / "tests/unit/test_integration_dialectic.py"
_AUDITOR = _REPO / "src/stc/judiciary/auditor.py"

PACKAGE_BYTES = 4061
PACKAGE_SHA256 = "383c474f48699907cc1348631caef07012329b92f08b6f67e3055302938af5fc"
PACKAGE_BUDGET = 4096
FRAME_OVERHEAD_BUDGET = 8192

_PIN_LINES = (
    "If the JSON carries proposed code changes, emit that patch string",
    "'@@' hunks only. NEVER emit codex apply_patch markers: no patch line",
    "may begin with '***' ('*** Begin Patch' / '*** Add File:' / '*** End Patch').",
)
_EMIT_LAST = "Now emit exactly one JSON document satisfying the SST prompt above,"

#: CONTEXT.md §3 range assembly (1-based inclusive spans), re-pinned 2026-09-25
#: to track the same semantic anchors after the operator-release tranche
#: shifted sources (Fix 2 provenance imports + veto rules, Fix 3 worker
#: constraints, new veto tests); re-pinned 2026-10-04 after the
#: finalization tranche shifted dialectic_runner.py (+1 import, +26 mirror
#: docstring); re-pinned again for the SST cand-02 adoption (+6 veto
#: rule, rule comment bytes changed); re-pinned once more when the
#: honest-budget helper gained an explicit time_budget_seconds
#: parameter (+1 line above §4; veto comment shortened in place);
#: re-pinned again for the walkthrough mirror-parity fix (+1 lease_git
#: import, +2 mirror skip-set block → spans <382 shift +1, spans ≥382
#: shift +3; content verified identical span-by-span against HEAD);
#: re-pinned again for the R4B top-level-only mirror fix (+4 skip-set
#: comment, +2 _mirror_into signature/docstring → spans ≥455 shift +6;
#: content verified identical span-by-span against HEAD).
#: Payload is rebuilt mechanically from these spans, never
#: hand-edited. Section 5 carries the two indented `# L…:` tags.
_SECTIONS: tuple[tuple[str, Path, tuple[tuple[int, int], ...]], ...] = (
    (
        "--- 1 test_integration_dialectic.py:21-22,24-26,28-29,33-55",
        _DIALECTIC_TEST,
        ((21, 22), (24, 26), (28, 29), (33, 55)),
    ),
    (
        "--- 2 dialectic_runner.py:127-128,199-200,204-211",
        _RUNNER,
        ((127, 128), (199, 200), (204, 211)),
    ),
    ("--- 3 dialectic_runner.py:747-758,777-778", _RUNNER, ((747, 758), (777, 778))),
    ("--- 4 test_integration_dialectic.py:817-829", _DIALECTIC_TEST, ((817, 829),)),
)


def _reassemble_from_sources() -> str:
    """Rebuild the package from the pinned source ranges (staleness tripwire)."""
    runner = _RUNNER.read_text(encoding="utf-8").splitlines()
    test = _DIALECTIC_TEST.read_text(encoding="utf-8").splitlines()
    audit = _AUDITOR.read_text(encoding="utf-8").splitlines()

    def pick(lines: list[str], spans: tuple[tuple[int, int], ...]) -> list[str]:
        out: list[str] = []
        for start, end in spans:
            out.extend(lines[start - 1 : end])
        return out

    by_path = {_RUNNER: runner, _DIALECTIC_TEST: test, _AUDITOR: audit}
    rebuilt = ["[H1-CTX/pinned] read-only source context (NOT a patch target)"]
    for tag, path, spans in _SECTIONS:
        rebuilt.append(tag)
        rebuilt.extend(pick(by_path[path], spans))
    rebuilt.append("--- 5 dialectic_runner.py:921-923,932,876,887,893-897")
    rebuilt.extend(pick(runner, ((921, 923),)))
    rebuilt.append("    # L932:")
    rebuilt.extend(pick(runner, ((932, 932),)))
    rebuilt.append("    # L876/L887/L893-897:")
    rebuilt.extend(pick(runner, ((876, 876), (887, 887), (893, 897))))
    rebuilt.append("--- 6 auditor.py:91-96,189-194 + dialectic_runner.py:1030-1039")
    rebuilt.extend(pick(audit, ((91, 96), (189, 194))))
    rebuilt.extend(pick(runner, ((1030, 1039),)))
    return "\n".join(rebuilt) + "\n"


def test_package_hash_pin() -> None:
    """The embedded package is exactly the 4061 B pinned payload."""
    raw = H1_CONTEXT_PACKAGE.encode("utf-8")
    assert len(raw) == PACKAGE_BYTES
    assert hashlib.sha256(raw).hexdigest() == PACKAGE_SHA256


def test_package_matches_pinned_artifact() -> None:
    """The embedded package equals the h1-prep artifact byte-for-byte."""
    artifact = _PACKAGE_ARTIFACT.read_bytes()
    assert len(artifact) == PACKAGE_BYTES
    assert hashlib.sha256(artifact).hexdigest() == PACKAGE_SHA256
    assert H1_CONTEXT_PACKAGE.encode("utf-8") == artifact


def test_package_sections_verbatim_against_sources() -> None:
    """Every payload section equals its current source-range bytes (staleness)."""
    assert _reassemble_from_sources() == H1_CONTEXT_PACKAGE


def test_package_head_marks_read_only() -> None:
    """The scope guard survives: read-only, not a patch target."""
    head = H1_CONTEXT_PACKAGE.splitlines()[0]
    assert head == "[H1-CTX/pinned] read-only source context (NOT a patch target)"


def test_placement_after_sst_before_pin_emit_last() -> None:
    """Closing-block placement: SST block → context → A3 pin → emit-last."""
    sst = "SST-BYTES"
    shaped = shape_gateway_prompt(sst)
    assert shaped.count(sst) == 1
    assert shaped.count(H1_CONTEXT_PACKAGE) == 1
    end = shaped.index(SST_PROMPT_END)
    ctx = shaped.index(H1_CONTEXT_PACKAGE)
    pins = [shaped.index(line) for line in _PIN_LINES]
    emit = shaped.index(_EMIT_LAST)
    assert end < ctx < pins[0]
    assert pins == sorted(pins)
    assert pins[-1] < emit
    assert shaped.rstrip().endswith("and nothing else.")


def test_sst_bytes_verbatim_with_context_present() -> None:
    """D15/D7 intact: SST bytes (even marker-bearing) pass through unedited."""
    sst = "*** Begin Patch\n*** Add File: x.py\n+code\n*** End Patch\n"
    shaped = shape_gateway_prompt(sst)
    assert shaped.count(sst) == 1
    assert shaped.index(SST_PROMPT_BEGIN) < shaped.index(sst) < shaped.index(SST_PROMPT_END)


def test_no_allowed_paths_widening() -> None:
    """The package grants no write scope: no target/paths directive inside."""
    lowered = H1_CONTEXT_PACKAGE.lower()
    assert "allowed_paths" not in lowered
    assert "write to" not in lowered


def test_frame_budget_sizing() -> None:
    """Package within its 4096 B budget; total frame overhead bounded.

    Frame-budget note (CONTEXT.md §5): the package roughly doubles emission
    input — attempt-4 keeps the reasoning-medium profile and treats any
    stall as a prompt-size signal, not a content signal.
    """
    assert len(H1_CONTEXT_PACKAGE.encode("utf-8")) <= PACKAGE_BUDGET
    shaped = shape_gateway_prompt("SST-BYTES")
    assert len(shaped) - len("SST-BYTES") <= FRAME_OVERHEAD_BUDGET


def test_frame_introduces_no_marker_lines_with_context() -> None:
    """No STC frame line (context block included) starts with `***`."""
    shaped = shape_gateway_prompt("SST")
    before, _, after_block = shaped.partition(SST_PROMPT_BEGIN)
    _, _, after = after_block.partition(SST_PROMPT_END)
    frame_lines = before.splitlines() + after.splitlines()
    assert frame_lines
    assert not any(line.startswith("***") for line in frame_lines)
