# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Propose → assess → retain → reuse loop over real task work (M4).

A recipe is a retained check profile (family + version + predicate
set + budget) with assessed evidence. Flow, all through consumer
surfaces with explicit state dirs:

- propose: file a proposal (shape-checked only, so invalid
  proposals reach assessment) bound to a filed prereg entry hash.
- assess: run mechanical predicates P0–P3 plus an independent
  re-hash on real files; verdict POSITIVE / NEGATIVE / VOID.
- retain: record the decision (`retain` needs POSITIVE,
  `retain-negative` needs NEGATIVE; VOID is unretainable).
- reuse: run a retained (non-negative) recipe on a new task through
  its family world; report verdict + measured cost.
- baseline: from-scratch direct check (no recipe machinery) with
  counted operator interventions.
- compare: report reuse-vs-baseline (verdict agreement, costs,
  interventions) with superiority_claimed=false, after re-hashing
  the prereg entry (a changed prereg voids the comparison).

D-005 signal classes (one per predicate, never conflated):
prediction discrepancy, explicit requirement/preference correction,
independent-check failure, evaluator defect, comparative workflow
advantage. No record claims generality beyond the tasks it ran.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

from anima_substrate.host import api
from anima_substrate.host.minihost import atomic_write_bytes, atomic_write_text
from anima_substrate.participants.relcheck.checker import (
    RelcheckError,
    hash_tree,
    load_manifest,
    run_check,
    verify_identity,
)

SIG_PREDICTION_DISCREPANCY = "prediction discrepancy"
SIG_REQUIREMENT_CORRECTION = "explicit requirement/preference correction"
SIG_INDEPENDENT_CHECK_FAILURE = "independent-check failure"
SIG_EVALUATOR_DEFECT = "evaluator defect"
SIG_COMPARATIVE_ADVANTAGE = "comparative workflow advantage"

SIGNAL_CLASSES = (
    SIG_PREDICTION_DISCREPANCY,
    SIG_REQUIREMENT_CORRECTION,
    SIG_INDEPENDENT_CHECK_FAILURE,
    SIG_EVALUATOR_DEFECT,
    SIG_COMPARATIVE_ADVANTAGE,
)

DECISIONS = ("retain", "retain-negative")

# P0 evaluator self-test fixture (fixed bytes, no randomness).
P0_FILES = {"alpha.txt": "alpha-1\n", "beta/gamma.txt": "gamma-2\n"}


def _recipe_dir(state_dir: Path, name: str) -> Path:
    return Path(state_dir) / "recipes" / name


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _independent_hash_tree(tree_root: str | Path) -> dict[str, str]:
    """Re-hash a tree WITHOUT the checker (independent code path).

    Plain os.walk + hashlib; any disagreement with the checker's
    hashes is an evaluator defect, not a verdict.
    """
    root = Path(tree_root)
    out: dict[str, str] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            full = Path(dirpath) / filename
            if full.is_symlink() or not full.is_file():
                raise RelcheckError(
                    f"tree member is not a regular file: {full}",
                    "verify trees of regular files only",
                )
            rel = full.relative_to(root).as_posix()
            digest = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    digest.update(chunk)
            out[rel] = digest.hexdigest()
    return out


def _p0_self_test(scratch: Path) -> tuple[bool, str]:
    """Run the fixed fixture through the checker; must come back VALID."""
    tree = scratch / "p0-tree"
    for rel, body in P0_FILES.items():
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(dest, body)
    pins = {
        rel: hashlib.sha256(body.encode()).hexdigest()
        for rel, body in sorted(P0_FILES.items())
    }
    manifest_path = scratch / "p0-manifest.json"
    atomic_write_text(
        manifest_path,
        json.dumps(
            {"manifest_version": 1, "release": "p0-fixture", "files": pins},
            indent=2,
            sort_keys=True,
        ),
    )
    try:
        report, _ = run_check("relcheck", "v1", "P0", manifest_path, tree)
    except RelcheckError as exc:
        return False, f"checker raised on the fixed fixture: {exc.cause}"
    if not report["valid"]:
        return False, f"checker verdict on the fixed fixture: {report}"
    return True, "fixed fixture verifies VALID"


def _verdict(predicates: dict[str, dict]) -> str:
    if not predicates["P0"]["passed"]:
        return "VOID"
    if all(predicates[p]["passed"] for p in ("P1", "P2", "P3")):
        return "POSITIVE"
    return "NEGATIVE"


def propose(
    state_dir: str | Path,
    name: str,
    family: str,
    family_version: str,
    manifest_path: str | Path,
    prereg_entry_path: str | Path,
    reason: str,
    proposer: str = "operator",
) -> dict:
    """File a recipe proposal bound to a filed prereg entry.

    Shape-checked only: an unreadable manifest does NOT refuse here
    (it fails P2 at assessment — invalid proposals are assessed
    too). Records the prereg entry hash; `compare` re-hashes it.
    """
    root = Path(state_dir)
    if not name or not isinstance(name, str) or "/" in name:
        raise ValueError("propose refused: name must be a non-empty plain id")
    if not family or not family_version:
        raise ValueError("propose refused: family and family_version required")
    rdir = _recipe_dir(root, name)
    if (rdir / "proposal.json").exists():
        raise ValueError(f"propose refused: recipe {name!r} already proposed")
    entry_path = Path(prereg_entry_path)
    if not entry_path.is_file():
        raise ValueError(
            f"propose refused: prereg entry missing: {entry_path} "
            f"(file the prereg BEFORE proposing)"
        )
    prereg_hash = _sha_file(entry_path)
    try:
        raw = Path(manifest_path).read_bytes()
        manifest_sha = hashlib.sha256(raw).hexdigest()
        stage_error = None
    except OSError:
        raw, manifest_sha, stage_error = None, None, f"unreadable: {manifest_path}"
    rdir.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        atomic_write_bytes(rdir / "staged-manifest.json", raw)
    proposal = {
        "name": name,
        "family": family,
        "family_version": family_version,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "stage_error": stage_error,
        "prereg_entry": str(entry_path),
        "prereg_entry_sha256": prereg_hash,
        "proposer": proposer,
        "reason": reason,
        "status": "proposed",
    }
    atomic_write_text(
        rdir / "proposal.json",
        json.dumps(proposal, indent=2, sort_keys=True) + "\n",
    )
    host, _ = api.open_run(root)
    host.append(
        "recipe",
        {"op": "propose", "name": name, "prereg_entry_sha256": prereg_hash},
        actor="host",
    )
    return proposal


def assess(
    state_dir: str | Path,
    name: str,
    tree_root: str | Path,
    task_id: str,
    budget_s: float = 60.0,
) -> dict:
    """Assess a proposed recipe on real files (predicates P0–P3)."""
    root = Path(state_dir)
    rdir = _recipe_dir(root, name)
    proposal_path = rdir / "proposal.json"
    if not proposal_path.is_file():
        raise ValueError(f"assess refused: unknown recipe {name!r}")
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    out_path = rdir / "assessments" / f"{task_id}.json"
    if out_path.exists():
        raise ValueError(
            f"assess refused: {name}/{task_id} already assessed "
            f"(assessment ids never reused)"
        )
    predicates: dict[str, dict] = {}
    scratch = rdir / "assess-scratch" / task_id
    p0_ok, p0_detail = _p0_self_test(scratch)
    predicates["P0"] = {
        "name": "P0 evaluator self-test",
        "signal_class": SIG_EVALUATOR_DEFECT,
        "passed": p0_ok,
        "detail": p0_detail,
    }
    staged = rdir / "staged-manifest.json"
    manifest = None
    if staged.is_file():
        try:
            manifest, _, _ = load_manifest(staged)
        except RelcheckError as exc:
            manifest = None
            p2_detail = f"staged manifest invalid: {exc.cause}"
        else:
            p2_detail = "staged manifest shape valid"
    else:
        p2_detail = (
            f"no staged manifest ({proposal.get('stage_error')}); requirements unmet"
        )
    predicates["P2"] = {
        "name": "P2 stated requirements met",
        "signal_class": SIG_REQUIREMENT_CORRECTION,
        "passed": manifest is not None,
        "detail": p2_detail,
    }
    t0 = time.time()
    p1_detail: str
    p1_passed = False
    if manifest is None:
        p1_detail = "skipped: no valid manifest (see P2)"
    else:
        try:
            primary = hash_tree(tree_root)
            independent = _independent_hash_tree(tree_root)
        except RelcheckError as exc:
            p1_detail = f"hashing failed: {exc.cause}"
        else:
            if primary != independent:
                predicates["P0"] = {
                    "name": "P0 evaluator self-test",
                    "signal_class": SIG_EVALUATOR_DEFECT,
                    "passed": False,
                    "detail": (
                        "checker hashes disagree with the independent "
                        "re-hash; the evaluator is at fault, not the tree"
                    ),
                }
                p1_detail = "skipped: evaluator defect (see P0)"
            else:
                identity = verify_identity(manifest, primary)
                p1_passed = bool(identity["valid"])
                p1_detail = (
                    f"checked={identity['checked']} "
                    f"missing={identity['missing']} "
                    f"extra={identity['extra']} "
                    f"mismatched={identity['mismatched']}"
                )
    elapsed = time.time() - t0
    predicates["P1"] = {
        "name": "P1 pins reproduce on the tree",
        "signal_class": SIG_INDEPENDENT_CHECK_FAILURE,
        "passed": p1_passed,
        "detail": p1_detail,
    }
    predicates["P3"] = {
        "name": "P3 measured cost within budget",
        "signal_class": SIG_PREDICTION_DISCREPANCY,
        "passed": elapsed <= budget_s,
        "detail": f"elapsed_s={round(elapsed, 3)} budget_s={budget_s}",
    }
    verdict = _verdict(predicates)
    assessment = {
        "name": name,
        "assessment_id": task_id,
        "tree_root": str(tree_root),
        "budget_s": budget_s,
        "elapsed_s": round(elapsed, 3),
        "predicates": predicates,
        "verdict": verdict,
        "prereg_entry_sha256": proposal["prereg_entry_sha256"],
    }
    atomic_write_text(out_path, json.dumps(assessment, indent=2, sort_keys=True) + "\n")
    host, _ = api.open_run(root)
    host.append(
        "recipe",
        {"op": "assess", "name": name, "assessment_id": task_id, "verdict": verdict},
        actor="host",
    )
    return assessment


def retain(
    state_dir: str | Path,
    name: str,
    assessment_id: str,
    decision: str,
    reason: str,
) -> dict:
    """Retain an assessed recipe with lineage + measured cost."""
    root = Path(state_dir)
    rdir = _recipe_dir(root, name)
    assessment_path = rdir / "assessments" / f"{assessment_id}.json"
    if not assessment_path.is_file():
        raise ValueError(f"retain refused: unknown assessment {name}/{assessment_id}")
    if decision not in DECISIONS:
        raise ValueError(
            f"retain refused: decision {decision!r} not in {list(DECISIONS)}"
        )
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    verdict = assessment["verdict"]
    if verdict == "VOID":
        raise ValueError(
            "retain refused: VOID assessments are unretainable (fix "
            "the evaluator, then re-assess)"
        )
    if decision == "retain" and verdict != "POSITIVE":
        raise ValueError(
            f"retain refused: assessment is {verdict}, not POSITIVE "
            f"(use retain-negative for NEGATIVE assessments)"
        )
    if decision == "retain-negative" and verdict != "NEGATIVE":
        raise ValueError(
            f"retain refused: assessment is {verdict}, not NEGATIVE "
            f"(use retain for POSITIVE assessments)"
        )
    if (rdir / "retention.json").exists():
        raise ValueError(f"retain refused: {name!r} already retained")
    proposal = json.loads((rdir / "proposal.json").read_text(encoding="utf-8"))
    retention = {
        "name": name,
        "assessment_id": assessment_id,
        "decision": decision,
        "verdict": verdict,
        "lineage": {
            "proposer": proposal["proposer"],
            "reason": proposal["reason"],
            "manifest_sha256": proposal["manifest_sha256"],
            "prereg_entry_sha256": proposal["prereg_entry_sha256"],
        },
        "measured_cost": {
            "elapsed_s": assessment["elapsed_s"],
            "budget_s": assessment["budget_s"],
        },
        "reason": reason,
    }
    atomic_write_text(
        rdir / "retention.json",
        json.dumps(retention, indent=2, sort_keys=True) + "\n",
    )
    host, _ = api.open_run(root)
    host.append(
        "recipe",
        {
            "op": "retain",
            "name": name,
            "assessment_id": assessment_id,
            "decision": decision,
        },
        actor="host",
    )
    return retention


def reuse(
    state_dir: str | Path,
    name: str,
    world_id: str,
    tree_root: str | Path,
    manifest_path: str | Path,
    task_id: str,
) -> dict:
    """Reuse a retained recipe on a new task through its family world."""
    root = Path(state_dir)
    rdir = _recipe_dir(root, name)
    retention_path = rdir / "retention.json"
    if not retention_path.is_file():
        raise ValueError(f"reuse refused: recipe {name!r} is not retained")
    retention = json.loads(retention_path.read_text(encoding="utf-8"))
    if retention["decision"] != "retain":
        raise ValueError(
            f"reuse refused: recipe {name!r} is retained-negative "
            f"(assessment {retention['assessment_id']} was NEGATIVE); "
            f"negatives are evidence, not executables"
        )
    out_path = rdir / "reuses" / f"{task_id}.json"
    if out_path.exists():
        raise ValueError(
            f"reuse refused: {name}/{task_id} already recorded (reuse ids never reused)"
        )
    proposal = json.loads((rdir / "proposal.json").read_text(encoding="utf-8"))
    from anima_substrate.participants import get_family

    family = get_family(proposal["family"], proposal["family_version"])
    host, _ = api.open_run(root)
    if world_id not in host.worlds:
        family.create(root, world_id, {}, f"reuse of recipe {name}")
    rep = family.run(
        root,
        world_id,
        {
            "task_id": task_id,
            "manifest_path": str(manifest_path),
            "tree_root": str(tree_root),
        },
    )
    record = {
        "name": name,
        "reuse_id": task_id,
        "world_id": world_id,
        "tree_root": str(tree_root),
        "manifest_path": str(manifest_path),
        "manifest_sha256": rep.get("manifest_sha256"),
        "valid": rep.get("valid"),
        "measured_cost": rep.get("measured_cost"),
        "elapsed_s": rep.get("elapsed_s"),
        "report_ref": rep.get("report_ref"),
        "retention": {
            "assessment_id": retention["assessment_id"],
            "prereg_entry_sha256": retention["lineage"]["prereg_entry_sha256"],
        },
    }
    atomic_write_text(out_path, json.dumps(record, indent=2, sort_keys=True) + "\n")
    host, _ = api.open_run(root)
    host.append(
        "recipe",
        {"op": "reuse", "name": name, "reuse_id": task_id, "valid": rep.get("valid")},
        actor="host",
    )
    return record


def baseline(tree_root: str | Path, work_dir: str | Path, task_id: str) -> dict:
    """From-scratch direct check: hash, write pins, verify (3 steps).

    The competent baseline: real file hashing + real pins + a real
    verification, with each operator step counted as one
    intervention. No recipe machinery, no ledger, no lineage.
    """
    root = Path(tree_root)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    interventions = 0
    t0 = time.time()
    hashes = hash_tree(root)  # step 1: hash the tree
    interventions += 1
    manifest = {
        "manifest_version": 1,
        "release": f"baseline-{task_id}",
        "files": {k: hashes[k] for k in sorted(hashes)},
    }
    manifest_path = work / "baseline-manifest.json"
    atomic_write_text(
        manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    interventions += 1  # step 2: write the pins
    loaded, manifest_sha, _ = load_manifest(manifest_path)
    identity = verify_identity(loaded, _independent_hash_tree(root))
    interventions += 1  # step 3: verify against an independent re-hash
    elapsed = time.time() - t0
    return {
        "task_id": task_id,
        "tree_root": str(root),
        "manifest_sha256": manifest_sha,
        "valid": bool(identity["valid"]),
        "checked": identity["checked"],
        "elapsed_s": round(elapsed, 3),
        "interventions": interventions,
    }


def compare(
    state_dir: str | Path,
    name: str,
    reuse_id: str,
    baseline_report: dict,
    prereg_entry_path: str | Path,
) -> dict:
    """Report reuse-vs-baseline WITHOUT comparative claims (P4).

    Refuses when the prereg entry changed since filing (hash
    mismatch voids the comparison). The record carries
    superiority_claimed=false: costs are REPORTED, never ranked.
    """
    root = Path(state_dir)
    rdir = _recipe_dir(root, name)
    reuse_path = rdir / "reuses" / f"{reuse_id}.json"
    if not reuse_path.is_file():
        raise ValueError(f"compare refused: unknown reuse {name}/{reuse_id}")
    proposal = json.loads((rdir / "proposal.json").read_text(encoding="utf-8"))
    live_hash = _sha_file(Path(prereg_entry_path))
    if live_hash != proposal["prereg_entry_sha256"]:
        raise ValueError(
            "compare refused: prereg entry changed since filing "
            f"(filed {proposal['prereg_entry_sha256'][:16]}..., live "
            f"{live_hash[:16]}...); the comparison is VOID — re-file "
            f"and re-run"
        )
    reuse_rec = json.loads(reuse_path.read_text(encoding="utf-8"))
    record = {
        "name": name,
        "reuse_id": reuse_id,
        "signal_class": SIG_COMPARATIVE_ADVANTAGE,
        "verdict_agreement": bool(reuse_rec["valid"]) == bool(baseline_report["valid"]),
        "reuse": {
            "valid": reuse_rec["valid"],
            "elapsed_s": reuse_rec.get("elapsed_s"),
            "measured_cost": reuse_rec.get("measured_cost"),
            "interventions": 1,
        },
        "baseline": {
            "valid": baseline_report["valid"],
            "elapsed_s": baseline_report.get("elapsed_s"),
            "interventions": baseline_report.get("interventions"),
        },
        "superiority_claimed": False,
        "prereg_entry_sha256": live_hash,
    }
    out_path = rdir / "comparisons" / f"{reuse_id}.json"
    if out_path.exists():
        raise ValueError(f"compare refused: {name}/{reuse_id} already compared")
    atomic_write_text(out_path, json.dumps(record, indent=2, sort_keys=True) + "\n")
    host, _ = api.open_run(root)
    host.append(
        "recipe",
        {
            "op": "compare",
            "name": name,
            "reuse_id": reuse_id,
            "superiority_claimed": False,
        },
        actor="host",
    )
    return record
