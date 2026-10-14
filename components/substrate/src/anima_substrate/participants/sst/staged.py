# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""SST consumption over a caller-staged checkout (stdlib-only here).

Consumption contract (see `docs/SST-STAGING.md`):
- The caller stages an SST checkout at the pinned commit and points
  `SUBSTRATE_SST_ROOT` at it. NOTHING SST is vendored in this
  package: only the pinned manifest (relpaths + sha256, no bytes).
- PYTHONPATH points at `<root>/src` (the staged bytes), TEST
  fixtures, $0. The child refuses unless `sst` resolves inside the
  staged dir with no shadowing copy anywhere else on sys.path.
- `verify_snapshot()` runs BEFORE every SST import and AFTER every
  SST consumption: ANY drift raises SSTBoundary naming the files.
- venv interpreter with pinned pydantic==2.13.5 (default
  `<root>/.venv/bin/python`, override via SUBSTRATE_SST_VENV_PY). A
  different pydantic version aborts the leg (re-qualification
  required).
- NEVER write into the staged tree (pre/post verification proves it).

Label: SUBSTRATE-QUALIFIED SNAPSHOT — NO SST-OWNER RELEASE ACCEPTANCE.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from ...host.minihost import atomic_write_text
from .manifest import (
    CONSTRUCTION,
    EXPECTED_FILE_COUNT,
    PINNED_MANIFEST,
    PINNED_PYDANTIC,
    PINNED_SNAPSHOT_HASH,
    PINNED_SST_COMMIT,
    file_manifest,
    snapshot_hash,
)

__all__ = [
    "SSTBoundary",
    "probe",
    "run_sst_test_search",
    "verify_snapshot",
    "CONSTRUCTION",
    "ENVELOPE_KEYS",
    "EXPECTED_FILE_COUNT",
    "PINNED_MANIFEST",
    "PINNED_PYDANTIC",
    "PINNED_SNAPSHOT_HASH",
    "PINNED_SST_COMMIT",
    "default_snapshot_src",
    "default_venv_py",
]

ENVELOPE_KEYS = {
    "tree_id",
    "termination_reason",
    "champion",
    "alternatives",
    "budget_consumed",
    "provider_errors",
    "gateway_bindings",
    "event_log_ref",
}


class SSTBoundary(Exception):
    """Exact consumption boundary: what failed, where, with what evidence."""


def default_snapshot_src(sst_root: str | Path | None = None) -> Path:
    root = sst_root or os.environ.get("SUBSTRATE_SST_ROOT", "")
    if not root:
        raise SSTBoundary(
            "SST boundary: no staged SST checkout (set SUBSTRATE_SST_ROOT "
            "to an SST checkout at the pinned commit; see "
            "docs/SST-STAGING.md)"
        )
    return Path(root) / "src"


def default_venv_py(sst_root: str | Path | None = None) -> Path:
    override = os.environ.get("SUBSTRATE_SST_VENV_PY", "").strip()
    if override:
        return Path(override)
    root = sst_root or os.environ.get("SUBSTRATE_SST_ROOT", "")
    if not root:
        raise SSTBoundary(
            "SST boundary: no staged SST checkout (set SUBSTRATE_SST_ROOT "
            "or SUBSTRATE_SST_VENV_PY; see docs/SST-STAGING.md)"
        )
    return Path(root) / ".venv" / "bin" / "python"


def load_manifest(manifest_path: Path = PINNED_MANIFEST) -> dict:
    try:
        doc = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise SSTBoundary(
            f"SST boundary: cannot read snapshot manifest {manifest_path}: {exc}"
        )
    except ValueError as exc:
        raise SSTBoundary(
            f"SST boundary: snapshot manifest is not valid JSON "
            f"({manifest_path}): {exc}"
        )
    if doc.get("construction") != CONSTRUCTION:
        raise SSTBoundary(
            f"SST boundary: manifest construction {doc.get('construction')!r} "
            f"!= {CONSTRUCTION!r} ({manifest_path}); refusing to guess "
            f"the hash algorithm"
        )
    if not isinstance(doc.get("files"), list):
        raise SSTBoundary(f"SST boundary: manifest has no file list ({manifest_path})")
    return doc


def verify_snapshot(
    snapshot_dir: str | Path, manifest_path: str | Path = PINNED_MANIFEST
) -> dict:
    """Verify staged SST bytes against the pinned manifest.

    Raises SSTBoundary naming every offending file on any drift.
    """
    snapshot_dir = Path(snapshot_dir)
    manifest_path = Path(manifest_path)
    if not (snapshot_dir / "sst").is_dir():
        raise SSTBoundary(
            f"SST boundary: staged tree missing: {snapshot_dir / 'sst'} "
            f"(stage an SST checkout at {PINNED_SST_COMMIT[:7]}; see "
            f"docs/SST-STAGING.md)"
        )
    doc = load_manifest(manifest_path)
    pinned = {e["relpath"]: e["sha256"] for e in doc["files"]}
    live = {e["relpath"]: e["sha256"] for e in file_manifest(snapshot_dir)}
    missing = sorted(set(pinned) - set(live))
    extra = sorted(set(live) - set(pinned))
    changed = sorted(r for r in set(pinned) & set(live) if pinned[r] != live[r])
    problems = []
    if missing:
        problems.append(f"missing files ({len(missing)}): " + ", ".join(missing))
    if extra:
        problems.append(f"extra files ({len(extra)}): " + ", ".join(extra))
    if changed:
        problems.append(f"changed bytes ({len(changed)}): " + ", ".join(changed))
    if doc.get("file_count") != len(live):
        problems.append(
            f"file count drift: manifest {doc.get('file_count')} vs live {len(live)}"
        )
    live_hash = snapshot_hash(file_manifest(snapshot_dir))
    if live_hash != doc.get("snapshot_hash"):
        problems.append(
            f"snapshot_hash drift: manifest {doc.get('snapshot_hash')} "
            f"vs live {live_hash}"
        )
    if problems:
        raise SSTBoundary(
            f"SST boundary: staged SST drifted from the pinned snapshot "
            f"({snapshot_dir}): " + "; ".join(problems)
        )
    return {
        "construction": CONSTRUCTION,
        "file_count": len(live),
        "snapshot_hash": live_hash,
        "verdict": "MATCH",
    }


def _git_head(sst_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(sst_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _venv_pydantic(venv_py: Path) -> str:
    try:
        proc = subprocess.run(
            [str(venv_py), "-c", "import pydantic; print(pydantic.VERSION)"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SSTBoundary(f"SST boundary: cannot run SST interpreter {venv_py}: {exc}")
    if proc.returncode != 0:
        raise SSTBoundary(
            f"SST boundary: SST interpreter {venv_py} cannot report "
            f"pydantic: {proc.stderr[-1000:]}"
        )
    return proc.stdout.strip()


def probe(
    sst_root: str | Path | None = None,
    venv_py: str | Path | None = None,
) -> dict:
    """Compat probe: is the staged SST checkout consumable?

    Checks, in order: root present, snapshot MATCH (byte pin), git pin
    when a `.git` checkout is staged (byte pin stays authoritative
    for exports without `.git`), interpreter present, pydantic pin.
    Returns the evidence dict; raises SSTBoundary naming the first
    failure.
    """
    raw = sst_root or os.environ.get("SUBSTRATE_SST_ROOT", "")
    if not raw or not Path(raw).is_dir():
        raise SSTBoundary(
            "SST boundary: no staged SST checkout "
            f"({raw or 'SUBSTRATE_SST_ROOT unset'}); see docs/SST-STAGING.md"
        )
    root = Path(raw)
    src = root / "src"
    checked = verify_snapshot(src)
    head = _git_head(root)
    if (root / ".git").exists():
        if head != PINNED_SST_COMMIT:
            raise SSTBoundary(
                f"SST boundary: staged checkout HEAD {head} != pinned "
                f"{PINNED_SST_COMMIT} (re-stage at the pin; see "
                f"docs/SST-STAGING.md)"
            )
        git_pin = {"present": True, "head": head, "pinned": True}
    else:
        git_pin = {
            "present": False,
            "head": head,
            "pinned": head == PINNED_SST_COMMIT if head else None,
            "note": "no .git in staged tree; the snapshot byte pin is authoritative",
        }
    venv = Path(venv_py) if venv_py else default_venv_py(root)
    if not venv.exists():
        raise SSTBoundary(
            f"SST boundary: SST interpreter missing: {venv} "
            f"(override with SUBSTRATE_SST_VENV_PY)"
        )
    pydantic_version = _venv_pydantic(venv)
    if pydantic_version != PINNED_PYDANTIC:
        raise SSTBoundary(
            f"SST boundary: pydantic {pydantic_version} != pinned "
            f"{PINNED_PYDANTIC} (re-qualification required)"
        )
    return {
        "verdict": "MATCH",
        "sst_root": str(root),
        "snapshot_src": str(src),
        "snapshot_check": checked,
        "git": git_pin,
        "venv_py": str(venv),
        "pydantic_version": pydantic_version,
    }


# ------------------------------------------------------- TEST consumption

CHILD_SCRIPT = '''"""SST-TEST child: run_search against the staged snapshot ONLY.

Modeled on the snapshot tests/unit/test_controller.py pattern (TEST
fixture gateway + deterministic code return), calling the frozen
run_search envelope. All disk writes go under RUNDIR (argv[1]); the
staged tree is read-only. Argv[2] is the staged snapshot src dir.
"""
import asyncio
import json
import sys
from pathlib import Path

RUNDIR = Path(sys.argv[1])
SNAPSHOT_SRC = Path(sys.argv[2]).resolve()

import sst  # noqa: E402  (import AFTER sys.argv read, on purpose)
SST_FILE = Path(sst.__file__).resolve()
try:
    SST_FILE.relative_to(SNAPSHOT_SRC)
except ValueError:
    raise AssertionError(
        f"SST boundary violated: sst imported from {SST_FILE}, "
        f"not from the staged snapshot {SNAPSHOT_SRC}")
# Shadowing guard: no OTHER sys.path entry may provide an sst package.
for entry in sys.path:
    if not entry:
        continue
    cand = (Path(entry).resolve() / "sst" / "__init__.py")
    if cand.exists() and cand != SNAPSHOT_SRC / "sst" / "__init__.py":
        raise AssertionError(
            f"SST boundary violated: shadowing sst package at {cand}")

import pydantic  # noqa: E402
from sst.core.contracts import TaskPacket  # noqa: E402
from sst.gateway.contracts import (GatewayResponse, ModelCatalog,  # noqa: E402
    ModelCatalogEntry, ProviderKind, ProviderProfile)
from sst.gateway.gateway import ModelGateway  # noqa: E402
from sst.sandbox.custody import CandidateCustodyManager  # noqa: E402
from sst.search.controller import SSTSearchController  # noqa: E402
from sst.search.policy import SearchPolicy  # noqa: E402
from sst.storage.store import SQLiteSSTStore  # noqa: E402


class TestGateway(ModelGateway):
    def __init__(self) -> None:
        super().__init__()
        prof = ProviderProfile(
            name="test-prof", kind=ProviderKind.TEST, api_base="test://",
            catalog=ModelCatalog(models=[ModelCatalogEntry(
                id="fake-model", display_label="Fake")]))
        self.register_profile(prof)
        self.set_route("diverge", "test-prof", "fake-model")
        self.set_route("critique", "test-prof", "fake-model")

    def invoke(self, request):  # deterministic TEST fixture return
        if request.role == "critique":
            content = ('{"value_score": 0.95, "verdict": "APPROVE", '
                       '"rationale": "High quality solution"}')
        else:
            content = "def mul(a, b): return a * b\\n"
        return GatewayResponse(
            content=content, profile="test-prof", model="fake-model",
            prompt_tokens=50, completion_tokens=50, total_tokens=100)


def main() -> None:
    work = RUNDIR / "sst-work"
    repo = work / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "math_mod.py").write_text(
        "def mul(a, b): return a + b\\n", encoding="utf-8")
    (repo / "test_math.py").write_text(
        "from math_mod import mul\\nassert mul(3, 4) == 12\\n",
        encoding="utf-8")
    task = TaskPacket(
        task_id="t_successor_sst", goal="Implement correct multiplication",
        source_repo_root=str(repo), base_commit="c1", snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"])
    store = SQLiteSSTStore(work / "events.db")
    custody = CandidateCustodyManager(
        base_worktree_dir=work / "worktrees")
    ctl = SSTSearchController(
        task=task, gateway=TestGateway(), store=store,
        custody_manager=custody,
        policy=SearchPolicy(
            max_iterations=2, branching_factor=1, max_depth=3))
    res = asyncio.run(ctl.run_search("tree_successor_sst"))
    out = {
        "sst_file": str(SST_FILE),
        "pydantic_version": pydantic.VERSION,
        "provider_kind": "TEST",
        "envelope": res.model_dump(),
    }
    (RUNDIR / "sst-result.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, default=str),
        encoding="utf-8")
    print(json.dumps({"termination_reason": str(res.termination_reason),
                      "champion": (res.champion.candidate_id
                                   if res.champion else None),
                      "cost_usd": res.budget_consumed.estimated_cost_usd,
                      "sst_file": str(SST_FILE)}))


if __name__ == "__main__":
    main()
'''


def run_sst_test_search(
    rundir: str | Path,
    snapshot_src: str | Path | None = None,
    venv_py: str | Path | None = None,
    timeout_s: int = 300,
) -> dict:
    """Verify the staged snapshot, then run the TEST search in a child."""
    rundir = Path(rundir)
    rundir.mkdir(parents=True, exist_ok=True)
    src = Path(snapshot_src) if snapshot_src else default_snapshot_src()
    venv = Path(venv_py) if venv_py else default_venv_py()
    # Gate 1 (BEFORE any SST import): exact-snapshot verification.
    pre = verify_snapshot(src)
    atomic_write_text(
        rundir / "SNAPSHOT-CHECK.json",
        json.dumps(pre, indent=2, sort_keys=True),
    )
    if not venv.exists():
        raise SSTBoundary(
            f"SST boundary: SST interpreter missing: {venv} "
            f"(override with SUBSTRATE_SST_VENV_PY)"
        )
    child = rundir / "sst_child_test.py"
    atomic_write_text(child, CHILD_SCRIPT)
    env = {
        "PYTHONPATH": str(src),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "HOME": os.environ.get("HOME", ""),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    try:
        proc = subprocess.run(
            [str(venv), str(child), str(rundir), str(src)],
            cwd=str(rundir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        raise SSTBoundary(f"SST boundary: cannot start SST python: {exc}")
    if proc.returncode != 0:
        raise SSTBoundary(
            f"SST boundary: staged TEST child failed rc={proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr[-4000:]}"
        )
    res_path = rundir / "sst-result.json"
    if not res_path.exists():
        raise SSTBoundary(
            "SST boundary: child exited 0 but wrote no "
            f"sst-result.json\nstdout:\n{proc.stdout}"
        )
    result = json.loads(res_path.read_text(encoding="utf-8"))
    envelope = result["envelope"]
    missing = ENVELOPE_KEYS - set(envelope)
    if missing:
        raise SSTBoundary(f"SST boundary: envelope keys missing: {missing}")
    if result.get("provider_kind") != "TEST":
        raise SSTBoundary("SST boundary: provider_kind is not TEST")
    kinds = {b.get("kind") for b in envelope["gateway_bindings"]}
    if kinds != {"TEST"}:
        raise SSTBoundary(f"SST boundary: gateway bindings not all TEST: {kinds}")
    cost = envelope["budget_consumed"]["estimated_cost_usd"]
    if cost != 0.0:
        raise SSTBoundary(f"SST boundary: non-$0 TEST run: cost {cost}")
    if result.get("pydantic_version") != PINNED_PYDANTIC:
        raise SSTBoundary(
            f"SST boundary: pydantic {result.get('pydantic_version')} != "
            f"pinned {PINNED_PYDANTIC} (re-qualification required)"
        )
    # Gate 2 (AFTER consumption): the staged tree must be byte-identical.
    post = verify_snapshot(src)
    if post["snapshot_hash"] != pre["snapshot_hash"]:
        raise SSTBoundary(
            "SST boundary: staged tree changed during "
            "consumption (writes into the staged tree are forbidden)"
        )
    return {
        "snapshot_check": post["verdict"],
        "check_file": str(rundir / "SNAPSHOT-CHECK.json"),
        "snapshot_hash": post["snapshot_hash"],
        "termination_reason": str(envelope["termination_reason"]),
        "champion": (
            envelope["champion"]["candidate_id"] if envelope["champion"] else None
        ),
        "cost_usd": cost,
        "envelope_keys": sorted(envelope),
        "sst_file": result["sst_file"],
        "pydantic_version": result["pydantic_version"],
        "snapshot_unchanged": True,
        "child_stdout_tail": (
            proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        ),
    }
