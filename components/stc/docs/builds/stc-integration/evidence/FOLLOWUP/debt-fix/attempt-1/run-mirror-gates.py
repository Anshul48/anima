"""Item-3 lease-faithful mirror via the REAL mirror_source_tree (post-fix tree)."""
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path("<workspace-root>")
sys.path.insert(0, str(WS / "stc" / "src"))
sys.path.insert(0, str(WS / "sst" / "src"))

from stc.integration.dialectic_runner import mirror_source_tree  # noqa: E402

SRC = WS / "stc"
DST = Path("/tmp/debtfix-lease-gates")

if DST.exists():
    shutil.rmtree(DST)
mirror_source_tree(SRC, DST)

# Lease-faithfulness assertions (code-as-contract: .git in, skip-set out).
head = subprocess.run(
    ["git", "-C", str(DST), "rev-parse", "HEAD"],
    capture_output=True, text=True, check=True, timeout=30,
).stdout.strip()
assert head == "edf5389873e4d4a2a4752ee0aa2159289398495e", head
assert (DST / "pyproject.toml").is_file()
assert "docs/builds/stc-integration/evidence" in (DST / "pyproject.toml").read_text()
assert (DST / "docs/builds/stc-integration/evidence/FOLLOWUP/h1-prep/ctx-package.txt").is_file()
assert (DST / "docs/builds/stc-integration/evidence/FOLLOWUP/live-exp/attempt-1/liveexp-probe.py").is_file()
assert ".gitignore" in {(DST / ".gitignore").name} and "worktrees" in (DST / ".gitignore").read_text()
assert not (DST / ".venv").exists(), "skip-set must exclude .venv"
assert not list(DST.rglob("__pycache__")), "skip-set must exclude __pycache__"
assert not (DST / ".pytest_cache").exists(), "skip-set must exclude .pytest_cache"
print(f"mirror ready: {DST} HEAD={head[:7]} whole-tree evidence intact")
