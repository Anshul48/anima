"""Unit tests for manual-payload templates + validation (Fix 4)."""

import json

import pytest

from stc.integration.manual_payloads import (
    MANUAL_ROLES,
    detect_role_shape,
    render_template,
    role_from_filename,
    validate_critique,
    validate_diverge,
    validate_payload_text,
    validate_refine,
    validate_synthesize,
)

GOOD_DIFF = (
    "diff --git a/mod.py b/mod.py\n"
    "--- a/mod.py\n"
    "+++ b/mod.py\n"
    "@@ -1 +1 @@\n"
    "-return a\n"
    "+return a + b\n"
)


def test_role_validators_accept_good_shapes() -> None:
    assert (
        validate_diverge(
            {
                "branches": [
                    {
                        "strategy_title": "t",
                        "hypothesis_or_rationale": "r",
                        "proposed_changes": GOOD_DIFF,
                    }
                ]
            }
        )
        == []
    )
    assert (
        validate_refine(
            {
                "refined_title": "t",
                "refactoring_notes": "n",
                "executable_content": GOOD_DIFF,
            }
        )
        == []
    )
    assert (
        validate_synthesize(
            {
                "synthesized_title": "t",
                "synthesis_rationale": "n",
                "executable_content": GOOD_DIFF,
            }
        )
        == []
    )
    assert validate_critique({"value_score": 0.9, "verdict": "APPROVE", "rationale": "r"}) == []


def test_diverge_rejects_prose_and_missing_keys() -> None:
    assert validate_diverge({}) == ["missing non-empty 'branches' list"]
    problems = validate_diverge(
        {"branches": [{"strategy_title": "", "proposed_changes": "just prose"}]}
    )
    assert any("strategy_title" in p for p in problems)
    assert any("hypothesis_or_rationale" in p for p in problems)
    assert any("unified diff" in p for p in problems)


def test_refine_flags_diverge_shape() -> None:
    problems = validate_refine(
        {
            "branches": [
                {
                    "strategy_title": "t",
                    "hypothesis_or_rationale": "r",
                    "proposed_changes": GOOD_DIFF,
                }
            ]
        }
    )
    assert any("DIVERGE payload" in p for p in problems)
    assert any("executable_content" in p for p in problems)


def test_critique_rejects_bad_score_and_verdict() -> None:
    assert validate_critique({}) != []
    assert any(
        "value_score" in p
        for p in validate_critique({"value_score": "high", "verdict": "APPROVE", "rationale": "r"})
    )
    assert any(
        "value_score" in p
        for p in validate_critique({"value_score": 1.5, "verdict": "APPROVE", "rationale": "r"})
    )
    assert any(
        "verdict" in p
        for p in validate_critique({"value_score": 0.5, "verdict": "MAYBE", "rationale": "r"})
    )
    assert any(
        "rationale" in p for p in validate_critique({"value_score": 0.5, "verdict": "PRUNE"})
    )


def test_critique_accepts_cortex_evaluations_shape() -> None:
    obj = {"evaluations": [{"verdict": "APPROVE", "value_score": 0.9, "critique": "r"}]}
    assert validate_critique(obj) == []
    obj = {"evaluations": [{"verdict": "SYNTHESIZE", "value_score": 0.8, "critique": "r"}]}
    assert validate_critique(obj) == []
    assert validate_critique({"evaluations": [{"verdict": "APPROVE", "value_score": 0.9}]}) != []
    assert validate_critique({"evaluations": []}) != []
    assert validate_critique({"evaluations": ["x"]}) != []


def test_validate_payload_text_strips_fences_like_controller() -> None:
    text = "```json\n" + json.dumps({"value_score": 0.5, "verdict": "PRUNE", "rationale": "r"})
    text += "\n```"
    obj, problems = validate_payload_text(text, expected_role="critique", source="paste")
    assert obj is not None and problems == []
    obj, problems = validate_payload_text(
        "```\n" + json.dumps({"value_score": 0.5, "verdict": "PRUNE", "rationale": "r"}) + "\n```",
        expected_role=None,
        source="paste",
    )
    assert obj is not None and problems == []


def test_validate_payload_text_reports_json_errors() -> None:
    obj, problems = validate_payload_text(
        '{"branches": [', expected_role="diverge", source="f.json"
    )
    assert obj is None
    assert len(problems) == 1 and problems[0].startswith("f.json: invalid JSON")
    obj, problems = validate_payload_text("[1, 2]", expected_role="diverge", source="f.json")
    assert obj is None and "JSON object" in problems[0]


def test_validate_payload_text_flags_shape_mismatch() -> None:
    text = json.dumps(
        {
            "branches": [
                {
                    "strategy_title": "t",
                    "hypothesis_or_rationale": "r",
                    "proposed_changes": GOOD_DIFF,
                }
            ]
        }
    )
    obj, problems = validate_payload_text(text, expected_role="refine", source="03-refine.json")
    assert obj is not None
    assert any("DIVERGE" in p and "REFINE" in p for p in problems)
    assert any("manual-template refine" in p for p in problems)


def test_validate_payload_text_detects_without_role() -> None:
    obj, problems = validate_payload_text(
        json.dumps({"value_score": 0.5, "verdict": "PRUNE", "rationale": "r"}),
        expected_role=None,
        source="paste",
    )
    assert obj is not None and problems == []
    _, problems = validate_payload_text(
        json.dumps({"whatever": 1}), expected_role=None, source="paste"
    )
    assert any("unrecognized shape" in p for p in problems)


def test_detect_role_shape() -> None:
    assert detect_role_shape({"branches": []}) == "diverge"
    assert detect_role_shape({"executable_content": "x", "refined_title": "t"}) == "refine"
    assert detect_role_shape({"executable_content": "x", "synthesized_title": "t"}) == "synthesize"
    assert detect_role_shape({"value_score": 0.5}) == "critique"
    assert detect_role_shape({"evaluations": []}) == "critique"
    assert detect_role_shape({"whatever": 1}) is None


def test_role_from_filename() -> None:
    assert role_from_filename("01-diverge.json") == "diverge"
    assert role_from_filename("04-critique.json") == "critique"
    assert role_from_filename("03-refine.json") == "refine"
    assert role_from_filename("payload.json") is None
    assert role_from_filename("no-role-here.json") is None


def test_templates_parse_and_cover_roles() -> None:
    assert set(MANUAL_ROLES) == {"diverge", "refine", "synthesize", "critique"}
    for role in MANUAL_ROLES:
        template = render_template(role)
        obj = json.loads(template)
        if role == "diverge":
            assert "branches" in obj
        elif role == "critique":
            assert set(obj) == {"value_score", "verdict", "rationale"}
        else:
            assert "executable_content" in obj
    with pytest.raises(KeyError):
        render_template("nope")
