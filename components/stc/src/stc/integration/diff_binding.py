"""Exact merge diff-binding (D-gamma, section 5.6).

Base, result, and policy are FROZEN here:

- base = the merge lease's baseline tree (``base_commit`` tree +
  baseline manifest, committed as the lease's baseline commit);
- result = the merge scratch-ref tree;
- policy = ``git diff --no-ext-diff --unified=3 <base> <result>``
  with default whitespace handling (NO ignore-whitespace).

One shared transport-only :func:`normalize_diff`, used at render (the
merge-block binding render) AND audit (the live/bundle recompute),
canonicalizes transport only: LF endings, trailing newline at EOF,
exact hunk headers. It MUST NOT reorder hunks or touch in-line
whitespace — hunk-header and content lines pass through byte-exact
apart from the line-ending fold.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final

from stc.integration.identity import IntegrationError

__all__ = [
    "DIFF_POLICY_ARGV",
    "DiffBindingError",
    "normalize_diff",
    "normalize_diff_bytes",
    "recount_patch_hunk_headers",
    "recount_patch_hunk_headers_bytes",
    "render_binding_diff",
    "restore_patch_trailing_newline",
    "restore_patch_trailing_newline_bytes",
    "write_scratch_bundle",
]

#: Frozen diff policy argv fragment (section 5.6): no ext diff, unified=3,
#: default whitespace handling. The two SHAs are appended by the caller.
DIFF_POLICY_ARGV: Final[tuple[str, ...]] = ("diff", "--no-ext-diff", "--unified=3")

_GIT_TIMEOUT_S: Final[int] = 120


class DiffBindingError(IntegrationError):
    """Binding render/recompute failed (fail-closed: no diff, no verdict)."""


def normalize_diff_bytes(data: bytes) -> bytes:
    """Canonical transport-only normalization over diff bytes.

    CRLF/CR fold to LF; a missing trailing newline at EOF is added.
    Empty input stays empty. Hunk order, hunk headers, and in-line
    whitespace are preserved byte-exact.
    """
    if not data:
        return b""
    text = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if not text.endswith(b"\n"):
        text += b"\n"
    return text


def normalize_diff(text: str) -> str:
    """The ONE shared transport-only normalizer (render AND audit).

    Same canonicalization as :func:`normalize_diff_bytes`, over text.
    Idempotent: normalizing twice is a byte-identical no-op.
    """
    if not text:
        return ""
    return normalize_diff_bytes(text.encode("utf-8")).decode("utf-8")


def restore_patch_trailing_newline_bytes(data: bytes) -> bytes:
    """Transport repair: restore ONE trailing LF stripped upstream (P04).

    The SST controller strips the trailing newline of every
    ``proposed_changes``, which makes ``git apply`` fail with "corrupt
    patch". Appends exactly one ``b"\\n"`` iff ``data`` is non-empty and
    lacks a trailing LF. Every other byte is preserved — notably NO
    CRLF/CR folding (unlike :func:`normalize_diff_bytes`). Empty input
    stays empty. Idempotent: ``f(f(x)) == f(x)``.
    """
    if not data:
        return b""
    if data.endswith(b"\n"):
        return data
    return data + b"\n"


def restore_patch_trailing_newline(text: str) -> str:
    """Str form of :func:`restore_patch_trailing_newline_bytes`.

    Same contract: append one ``"\\n"`` iff ``text`` is non-empty and
    lacks a trailing LF; all other characters preserved; idempotent.
    """
    if not text:
        return ""
    if text.endswith("\n"):
        return text
    return text + "\n"


_HUNK_HEADER_RE: Final = re.compile(
    r"^@@ -(?P<a>\d+)(?:,(?P<b>\d+))? "
    r"\+(?P<c>\d+)(?:,(?P<d>\d+))? @@(?P<section>.*)$"
)

_FILE_BOUNDARY_PREFIXES: Final = (
    "diff --git ",
    "--- ",
    "+++ ",
    "Index: ",
    "Binary ",
    "*** ",
)


def _recounted_header(line: str, old_count: int, new_count: int) -> str:
    """Rebuilds one hunk header with recomputed counts (starts kept)."""
    match = _HUNK_HEADER_RE.match(line)
    assert match is not None  # caller only passes matching headers
    return f"@@ -{match['a']},{old_count} +{match['c']},{new_count} @@{match['section']}"


def recount_patch_hunk_headers(text: str) -> str:
    """Transport repair (Option 2): recompute ``@@`` hunk line counts.

    Model-emitted diffs routinely carry wrong ``oldcount``/``newcount``
    while context lines are verbatim-correct; ``git apply`` then fails
    with "corrupt patch" before content is even considered (observed:
    15/15 candidate rejections across two construction runs, both
    rescued by ``git apply --recount``). This repair rewrites ONLY the
    counts: starts, section text, and every body line pass through
    byte-exact, so ``git apply`` still judges the actual content.

    Contract (total, idempotent, conservative, minimal):

    - total: never raises on any input; unparseable headers, empty
      hunks, and non-diff text pass through unchanged;
    - idempotent: recounting twice is a byte-identical no-op;
    - conservative: a hunk whose body holds a line outside the
      ``' '``/``'-'``/``'+'``/``'\\\\'``/empty alphabet keeps its
      original header (fails downstream honestly, as today);
    - minimal: headers whose counts are already correct are left
      byte-exact (implicit ``,1`` counts included);
    - ``'\\\\ No newline at end of file'`` markers are preserved and
      never counted.
    """
    if not text or "@@" not in text:
        return text
    lines = text.split("\n")
    # A trailing LF produces a structural "" that is not a content line;
    # mid-body "" entries stay (genuine blank context lines).
    trailing_lf = False
    if lines and lines[-1] == "":
        lines.pop()
        trailing_lf = True
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        match = _HUNK_HEADER_RE.match(line)
        if match is None:
            out.append(line)
            i += 1
            continue
        # Collect the hunk body: until the next header, a file
        # boundary, or EOF.
        body: list[str] = []
        j = i + 1
        while j < n:
            nxt = lines[j]
            if _HUNK_HEADER_RE.match(nxt) is not None:
                break
            if nxt.startswith(_FILE_BOUNDARY_PREFIXES):
                break
            body.append(nxt)
            j += 1
        old_count = 0
        new_count = 0
        clean = True
        for bline in body:
            if bline == "" or bline.startswith(" "):
                old_count += 1
                new_count += 1
            elif bline.startswith("-"):
                old_count += 1
            elif bline.startswith("+"):
                new_count += 1
            elif bline.startswith("\\"):
                continue  # marker line: preserved, never counted
            else:
                clean = False  # unexpected alphabet: keep header as-is
                break
        if not clean:
            out.append(line)
            out.extend(body)
            i = j
            continue
        want_b = int(match["b"]) if match["b"] is not None else 1
        want_d = int(match["d"]) if match["d"] is not None else 1
        if want_b == old_count and want_d == new_count:
            out.append(line)  # already correct: byte-exact
        else:
            out.append(_recounted_header(line, old_count, new_count))
        out.extend(body)
        i = j
    result = "\n".join(out)
    if trailing_lf:
        result += "\n"
    return result


def recount_patch_hunk_headers_bytes(data: bytes) -> bytes:
    """Bytes form of :func:`recount_patch_hunk_headers`.

    Same contract; empty input stays empty; idempotent.
    """
    if not data:
        return b""
    return recount_patch_hunk_headers(data.decode("utf-8")).encode("utf-8")


def render_binding_diff(repo: Path, base_sha: str, result_sha: str) -> bytes:
    """Renders the frozen-policy diff ``base -> result`` (normalized bytes).

    Runs ``git diff --no-ext-diff --unified=3 <base> <result>`` inside
    ``repo`` and normalizes the raw stdout bytes. Any git failure raises
    :class:`DiffBindingError` (fail-closed).
    """
    try:
        proc = subprocess.run(
            ["git", *DIFF_POLICY_ARGV, base_sha, result_sha],
            cwd=str(repo),
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiffBindingError(f"binding diff render failed: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise DiffBindingError(f"binding diff render failed: {detail}")
    return normalize_diff_bytes(proc.stdout)


def write_scratch_bundle(repo: Path, scratch_ref: str, dest: Path) -> Path:
    """Writes a ``git bundle`` of the scratch ref (evidence durability).

    The bundle + the rendered diff bytes in the evidence dir let
    verification recompute bundle-against-rendered forever, after the
    lease is deleted. ``dest`` must live OUTSIDE the lease.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "bundle", "create", str(dest), scratch_ref],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiffBindingError(f"bundle creation failed: {exc}") from exc
    if proc.returncode != 0 or not dest.is_file():
        raise DiffBindingError(f"bundle creation failed: {(proc.stderr or '').strip()[:300]}")
    return dest
