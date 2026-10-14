"""Role-specific manual-payload templates + pre-submission validation (Fix 4).

The manual harness accepts operator/agent payloads for four SST roles whose
JSON shapes DIFFER (controller.py): diverge reads ``branches[].proposed_changes``,
refine/synthesize read ``executable_content``, critique reads the flat
``value_score`` / ``verdict`` / ``rationale`` object or the capsule-path
``evaluations[0]`` object. A payload in the wrong shape parses to an empty
patch or a defaulted score and the failure masquerades as candidate quality.
This module makes packaging mistakes fail fast with actionable errors.
"""

from __future__ import annotations

import json
from typing import Any, Final

DIVERGE_ROLE: Final[str] = "diverge"
REFINE_ROLE: Final[str] = "refine"
SYNTHESIZE_ROLE: Final[str] = "synthesize"
CRITIQUE_ROLE: Final[str] = "critique"

MANUAL_ROLES: Final[tuple[str, ...]] = (
    DIVERGE_ROLE,
    REFINE_ROLE,
    SYNTHESIZE_ROLE,
    CRITIQUE_ROLE,
)

CRITIQUE_VERDICTS: Final[tuple[str, ...]] = ("APPROVE", "PRUNE", "ESCALATE_HUMAN")
CORTEX_CRITIQUE_VERDICTS: Final[tuple[str, ...]] = (
    "APPROVE",
    "PRUNE",
    "SYNTHESIZE",
    "ESCALATE_HUMAN",
)


def _looks_like_diff(text: str) -> bool:
    stripped = text.strip()
    return (
        stripped.startswith("--- ")
        or stripped.startswith("diff --git")
        or stripped.startswith("@@ ")
        or "\n@@ " in text
    )


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_diverge(obj: dict[str, Any]) -> list[str]:
    """Errors for a diverge payload (empty == valid)."""
    errors: list[str] = []
    branches = obj.get("branches")
    if not isinstance(branches, list) or not branches:
        return ["missing non-empty 'branches' list"]
    for index, branch in enumerate(branches):
        where = f"branches[{index}]"
        if not isinstance(branch, dict):
            errors.append(f"{where} must be an object")
            continue
        if not _is_nonempty_str(branch.get("strategy_title")):
            errors.append(f"{where} needs non-empty 'strategy_title'")
        if not _is_nonempty_str(branch.get("hypothesis_or_rationale")):
            errors.append(f"{where} needs non-empty 'hypothesis_or_rationale'")
        changes = branch.get("proposed_changes")
        if not _is_nonempty_str(changes):
            errors.append(f"{where} needs non-empty 'proposed_changes'")
        elif not _looks_like_diff(str(changes)):
            errors.append(
                f"{where}.proposed_changes must be a unified diff "
                "('diff --git'/'---'/'@@' hunks), not prose or patch markers"
            )
    return errors


def _validate_executable(obj: dict[str, Any], title_key: str, notes_key: str) -> list[str]:
    errors: list[str] = []
    if not _is_nonempty_str(obj.get(title_key)):
        errors.append(f"missing non-empty '{title_key}'")
    if not _is_nonempty_str(obj.get(notes_key)):
        errors.append(f"missing non-empty '{notes_key}'")
    content = obj.get("executable_content")
    if not _is_nonempty_str(content):
        errors.append("missing non-empty 'executable_content'")
    elif not _looks_like_diff(str(content)):
        errors.append(
            "'executable_content' must be a unified diff "
            "('diff --git'/'---'/'@@' hunks), not prose or patch markers"
        )
    # Cross-shape tripwire: a diverge payload here parses to an empty patch.
    if "branches" in obj:
        errors.append(
            "looks like a DIVERGE payload ('branches' key); this role needs "
            "'executable_content' — see: stc manual-template refine"
        )
    return errors


def validate_refine(obj: dict[str, Any]) -> list[str]:
    """Errors for a refine payload (empty == valid)."""
    return _validate_executable(obj, "refined_title", "refactoring_notes")


def validate_synthesize(obj: dict[str, Any]) -> list[str]:
    """Errors for a synthesize payload (empty == valid)."""
    return _validate_executable(obj, "synthesized_title", "synthesis_rationale")


def _score_ok(score: object) -> bool:
    return (
        not isinstance(score, bool)
        and isinstance(score, (int, float))
        and 0.0 <= float(score) <= 1.0
    )


def validate_critique(obj: dict[str, Any]) -> list[str]:
    """Errors for a critique payload (empty == valid).

    Accepts BOTH controller shapes: the flat ``value_score``/``verdict``/
    ``rationale`` object (non-capsule prompt) and the capsule-path cortex
    ``evaluations[0]`` object (``value_score``/``verdict``/``critique``,
    verdicts per the cortex schema). Mirrors the controller's shape
    preference: a non-empty ``evaluations`` list governs.
    """
    evals = obj.get("evaluations")
    if isinstance(evals, list) and evals:
        first = evals[0]
        if not isinstance(first, dict):
            return ["'evaluations[0]' must be an object"]
        errors: list[str] = []
        if not _score_ok(first.get("value_score")):
            errors.append("'evaluations[0].value_score' must be a number in [0, 1]")
        if first.get("verdict") not in CORTEX_CRITIQUE_VERDICTS:
            errors.append(
                "'evaluations[0].verdict' must be one of " + ", ".join(CORTEX_CRITIQUE_VERDICTS)
            )
        if not _is_nonempty_str(first.get("critique")):
            errors.append("missing non-empty 'evaluations[0].critique'")
        return errors
    errors = []
    if not _score_ok(obj.get("value_score")):
        errors.append("'value_score' must be a number in [0, 1]")
    verdict = obj.get("verdict")
    if verdict not in CRITIQUE_VERDICTS:
        errors.append(f"'verdict' must be one of {', '.join(CRITIQUE_VERDICTS)}")
    if not _is_nonempty_str(obj.get("rationale")):
        errors.append("missing non-empty 'rationale'")
    return errors


_VALIDATORS: Final[dict[str, Any]] = {
    DIVERGE_ROLE: validate_diverge,
    REFINE_ROLE: validate_refine,
    SYNTHESIZE_ROLE: validate_synthesize,
    CRITIQUE_ROLE: validate_critique,
}


def strip_json_fences(text: str) -> str:
    """Unwrap ```json / ``` fences exactly as SST ``_parse_json_dict`` does.

    The controller applies this to every role response before ``json.loads``,
    so validation must accept fenced payloads SST would accept.
    """
    stripped = text.strip()
    if "```json" in stripped:
        return stripped.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in stripped:
        return stripped.split("```", 1)[1].split("```", 1)[0].strip()
    return stripped


def parse_critique_content(content: str) -> dict[str, Any] | None:
    """Parse gateway critique bytes exactly as the SST controller would.

    Mirrors SST ``_parse_json_dict``: fence-strip, ``json.loads``, dict
    check. Returns None when SST would fall back to defaults (Fix 2).
    """
    try:
        obj = json.loads(strip_json_fences(content))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def detect_role_shape(obj: dict[str, Any]) -> str | None:
    """Best-guess role from payload keys (None when unrecognized)."""
    if "value_score" in obj or "evaluations" in obj:
        return CRITIQUE_ROLE
    if "executable_content" in obj:
        if "synthesized_title" in obj:
            return SYNTHESIZE_ROLE
        return REFINE_ROLE
    if "branches" in obj:
        return DIVERGE_ROLE
    return None


def validate_payload_text(
    text: str, *, expected_role: str | None, source: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse + role-check one payload; returns (obj, errors).

    ``source`` names the origin for actionable messages (filename or
    "pasted payload"). ``expected_role`` None means accept any
    recognized shape (detected role is NOT returned; callers that need
    it use detect_role_shape on the parsed object).
    """
    try:
        obj = json.loads(strip_json_fences(text))
    except json.JSONDecodeError as exc:
        return None, [f"{source}: invalid JSON at {exc.pos}: {exc.msg}"]
    if not isinstance(obj, dict):
        return None, [f"{source}: top level must be a JSON object"]
    if expected_role is None:
        detected = detect_role_shape(obj)
        if detected is None:
            return None, [
                f"{source}: unrecognized shape; expected one of: diverge "
                "('branches'), refine/synthesize ('executable_content'), "
                "critique ('value_score'/'evaluations') — see: stc manual-template <role>"
            ]
        problems = _VALIDATORS[detected](obj)
        return obj, [f"{source}: {problem}" for problem in problems]
    if expected_role not in _VALIDATORS:
        return None, [f"{source}: unknown role {expected_role!r}"]
    problems = _VALIDATORS[expected_role](obj)
    if problems:
        detected = detect_role_shape(obj)
        if detected is not None and detected != expected_role:
            problems = [
                f"shape mismatch: payload looks like {detected.upper()}, "
                f"expected {expected_role.upper()} "
                f"(see: stc manual-template {expected_role})",
                *problems,
            ]
    return obj, [f"{source}: {problem}" for problem in problems]


def role_from_filename(name: str) -> str | None:
    """Role suffix from a fixture filename stem (NN-<role>.*)."""
    stem = name.rsplit(".", 1)[0]
    suffix = stem.rsplit("-", 1)[-1].strip().lower() if "-" in stem else ""
    return suffix if suffix in _VALIDATORS else None


TEMPLATES: Final[dict[str, dict[str, Any]]] = {
    DIVERGE_ROLE: {
        "branches": [
            {
                "strategy_title": "<short plan title>",
                "hypothesis_or_rationale": "<why this change fixes the goal>",
                "proposed_changes": "<ONE pure unified diff vs source root>",
            }
        ]
    },
    REFINE_ROLE: {
        "refined_title": "<short improvement title>",
        "refactoring_notes": "<what changed vs the parent and why>",
        "executable_content": "<ONE pure unified diff vs source root>",
    },
    SYNTHESIZE_ROLE: {
        "synthesized_title": "<short merge title>",
        "synthesis_rationale": "<how the parents combine>",
        "executable_content": "<ONE pure unified diff vs source root>",
    },
    CRITIQUE_ROLE: {
        "value_score": 0.0,
        "verdict": "APPROVE",
        "rationale": "<per-requirement judgment with diff-line cites>",
    },
}


def render_template(role: str) -> str:
    """Canonical template JSON for a role (KeyError on unknown role)."""
    return json.dumps(TEMPLATES[role], indent=2) + "\n"
