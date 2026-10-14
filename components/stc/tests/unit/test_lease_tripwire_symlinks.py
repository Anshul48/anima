"""Tripwire manifest: symlink-cycle safety + node_modules exclusion.

Regression tests for the ELOOP failure where hash_tree_manifest
descended into package-manager symlink cycles (node_modules) via
rglob. Directory symlinks are recorded as links, never descended.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from stc.integration.lease_git import hash_tree_manifest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_dir_symlink_cycles_complete_without_descending(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    (tmp_path / "ext").mkdir()
    _write(tmp_path / "ext" / "foreign.py", "y = 2\n")
    (tmp_path / "src" / "loop").symlink_to(tmp_path / "src", target_is_directory=True)
    (tmp_path / "src" / "out").symlink_to(tmp_path / "ext", target_is_directory=True)
    manifest = hash_tree_manifest(tmp_path)
    assert "src/a.py" in manifest
    assert "ext/foreign.py" in manifest
    # Foreign bytes never hash under local names.
    assert "src/out/foreign.py" not in manifest
    assert "src/loop/a.py" not in manifest
    # Links themselves are recorded (retargeting trips the wire).
    assert (
        manifest["src/out"]
        == hashlib.sha256(f"DIR-SYMLINK:{tmp_path / 'ext'}".encode()).hexdigest()
    )


def test_node_modules_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    before = hash_tree_manifest(tmp_path)
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "z = 3\n")
    (tmp_path / "node_modules" / "cycle").symlink_to(
        tmp_path / "node_modules", target_is_directory=True
    )
    after = hash_tree_manifest(tmp_path)
    assert after == before


def test_backend_runtime_outputs_excluded(tmp_path: Path) -> None:
    """dossier/.durable/worktrees never hash (walkthrough regression).

    Backend runtime outputs live under the source root; hashing them
    wedges the T0 walk on multi-GB trees and self-trips the close
    check when the run writes its own dossier records.
    """
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    before = hash_tree_manifest(tmp_path)
    _write(tmp_path / "dossier" / "qa_log.json", "{}\n")
    _write(tmp_path / "dossier" / "runs" / "r1" / "result.json", "{}\n")
    _write(tmp_path / ".durable" / "dsh" / "big.bin", "0" * 1000)
    _write(tmp_path / "worktrees" / "lease-1" / "src" / "a.py", "x = 1\n")
    _write(tmp_path / "artifacts" / "notebooklm" / "media.bin", "0" * 1000)
    after = hash_tree_manifest(tmp_path)
    assert after == before


def test_dir_symlink_retarget_trips(tmp_path: Path) -> None:
    (tmp_path / "t1").mkdir()
    (tmp_path / "t2").mkdir()
    link = tmp_path / "linked"
    link.symlink_to(tmp_path / "t1", target_is_directory=True)
    before = hash_tree_manifest(tmp_path)
    link.unlink()
    link.symlink_to(tmp_path / "t2", target_is_directory=True)
    after = hash_tree_manifest(tmp_path)
    assert after != before


def test_foreign_content_change_invisible(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "ext").mkdir()
    target = tmp_path / "ext" / "f.py"
    _write(target, "v1\n")
    (root / "out").symlink_to(tmp_path / "ext", target_is_directory=True)
    before = hash_tree_manifest(root)
    _write(target, "v2\n")
    after = hash_tree_manifest(root)
    assert after == before


def test_file_symlink_hashes_target_bytes_and_broken_recorded(tmp_path: Path) -> None:
    _write(tmp_path / "real.txt", "hello\n")
    (tmp_path / "alias.txt").symlink_to(tmp_path / "real.txt")
    (tmp_path / "dangling.txt").symlink_to(tmp_path / "missing.txt")
    manifest = hash_tree_manifest(tmp_path)
    assert manifest["alias.txt"] == manifest["real.txt"]
    assert manifest["dangling.txt"] == "BROKEN-SYMLINK"
