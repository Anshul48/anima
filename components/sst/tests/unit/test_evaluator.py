"""Tests for SSTDeterministicEvaluator isolated workspace copying and patching.

SYNTHETIC PROVENANCE: API_KEY values set here are the "[REDACTED]"
placeholder via monkeypatch, never real credentials.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sst.core.models import (
    DomainMode,
    NodeRole,
    PayloadType,
    SSTNode,
)
from sst.sandbox.evaluator import SSTDeterministicEvaluator


def test_evaluator_code_patching_and_testing() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir) / "project"
        ws.mkdir()

        # Base math module
        math_file = ws / "calc.py"
        math_file.write_text("def add(a, b):\n    return 0\n")

        # Test file
        test_file = ws / "test_calc.py"
        test_file.write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")

        evaluator = SSTDeterministicEvaluator()

        # Failing node
        failing_node = SSTNode(
            node_id="n_fail",
            tree_id="t_001",
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.ASD_EXPLOITER,
            title="Broken Add",
            payload_type=PayloadType.CODE_DIFF,
            content="def add(a, b):\n    return a - b\n",
            metadata={"target_file": "calc.py"},
        )

        fail_res = evaluator.evaluate_code(
            failing_node,
            workspace_dir=ws,
            test_command="python -m pytest test_calc.py",
        )
        assert fail_res.passed is False
        assert fail_res.exit_code != 0

        # Passing node
        passing_node = SSTNode(
            node_id="n_pass",
            tree_id="t_001",
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.ASD_EXPLOITER,
            title="Correct Add",
            payload_type=PayloadType.CODE_DIFF,
            content="def add(a, b):\n    return a + b\n",
            metadata={"target_file": "calc.py"},
        )

        pass_res = evaluator.evaluate_code(
            passing_node,
            workspace_dir=ws,
            test_command="python -m pytest test_calc.py",
        )
        assert pass_res.passed is True
        assert pass_res.exit_code == 0
        assert pass_res.tests_passed >= 1


def test_evaluator_path_traversal_rejection() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir) / "project"
        ws.mkdir()

        evaluator = SSTDeterministicEvaluator()
        traversal_node = SSTNode(
            node_id="n_traversal",
            tree_id="t_001",
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.ASD_EXPLOITER,
            title="Traversal Attack",
            payload_type=PayloadType.CODE_DIFF,
            content="print('escaped')",
            metadata={"target_file": "../../etc/passwd"},
        )

        res = evaluator.evaluate_code(
            traversal_node,
            workspace_dir=ws,
            test_command="python -c 'pass'",
        )
        assert res.passed is False
        assert "Path Traversal Violation" in (res.failure_reason or "")


def test_evaluator_secret_scrubbing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret12345678901234567890")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "awssecret12345")
    monkeypatch.setenv("MY_SAFE_VAR", "safe_value")

    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir) / "project"
        ws.mkdir()

        check_file = ws / "check_env.py"
        check_file.write_text(
            "import os\n"
            "assert 'OPENAI_API_KEY' not in os.environ\n"
            "assert 'AWS_SECRET_ACCESS_KEY' not in os.environ\n"
            "assert os.environ.get('MY_SAFE_VAR') == 'safe_value'\n"
            "assert os.environ.get('AUTO_SANDBOX') == '1' or os.environ.get('SST_SANDBOX') == '1'\n"
        )

        evaluator = SSTDeterministicEvaluator()
        node = SSTNode(
            node_id="n_env",
            tree_id="t_001",
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.ASD_EXPLOITER,
            title="Check Env",
            payload_type=PayloadType.CODE_DIFF,
            content="pass\n",
            metadata={"target_file": "dummy.py"},
        )

        res = evaluator.evaluate_code(
            node,
            workspace_dir=ws,
            test_command="python check_env.py",
        )
        assert res.passed is True
        assert res.exit_code == 0
