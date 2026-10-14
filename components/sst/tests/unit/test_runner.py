"""Tests for SSTBuildRunner integration."""

import tempfile
from pathlib import Path

from sst.cli.runner import SSTBuildRunner
from sst.core.models import DomainMode


def test_sst_build_runner_code_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        runner = SSTBuildRunner(
            workspace_dir=ws,
            mock_mode=True,
        )

        tree = runner.execute_build_goal(
            goal="Implement lock-free threadsafe queue",
            target_files=["queue_impl.py"],
            max_iterations=2,
        )

        assert tree.domain == DomainMode.AUTOBUILD
        assert len(tree.nodes) >= 3

        # Verify champion applied to workspace
        target_path = ws / "queue_impl.py"
        assert target_path.exists()
        content = target_path.read_text(encoding="utf-8")
        assert "RingBuffer" in content
