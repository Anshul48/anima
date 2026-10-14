"""Signed linked records + verification-consumption checks (D-zeta).

Four signed linked records (section 5.2/5.3/T2-T7):

- ``CustodyIntake`` (T2): the candidate's birth certificate —
  ``(candidate_id, base_commit ref, scratch_ref_SHA,
  candidate_content_digest, baseline receipt ref, target env_digest)``.
- ``SelectionRecord`` (T3, per node): mandatory-set digest (bound to
  the selection-config revision), affected-computation inputs,
  broadenings, plausibly-affected-but-unrun tests with reasons, the
  ACTUAL gate argv executed alongside ``contract_rev``, and the
  safeguard declaration.
- ``SelectionOutcomeRecord`` (T4): ``(verified set, tainted map, scores
  summary, selected node OR no-champion reason)``.
- ``MergeRecord`` (T5/T6): pins exactly ``(merge_scratch_ref,
  selection_outcome_ref, env_digest, merged_diff_sha256)``; the mutmut
  disposition rides ``ChampionResult``, and the ExecutionReceipt stays
  frozen (no new fields there).

Verification MUST consume every record (existence, signature auth,
digest links, cross-identity agreement); a tampered or substituted
record MUST fail verification (preflight N6). The final dossier is
HMAC'd over the digest list of all four records
(:func:`dossier_digest_list` + ``dossier_signature``).

Signatures follow receipt semantics: HMAC-SHA256 when a key is
configured, canonical SHA-256 when omitted (``sig_mode`` recorded
explicitly on every record — never inferred).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Final, Self

from pydantic import BaseModel, ConfigDict, model_validator

from stc.integration.diff_binding import normalize_diff_bytes, render_binding_diff
from stc.integration.identity import IntegrationError
from stc.integration.selection import mandatory_set_digest

__all__ = [
    "CONTRACT_REV",
    "CustodyIntake",
    "MergeRecord",
    "RecordVerificationError",
    "SelectionOutcomeRecord",
    "SelectionRecord",
    "candidate_content_digest",
    "digest_of",
    "dossier_digest_list",
    "dossier_signature",
    "load_record",
    "save_record",
    "sign_payload",
    "verify_custody_intake",
    "verify_dossier",
    "verify_merge_record",
    "verify_payload_signature",
    "verify_selection_outcome",
    "verify_selection_record",
]

#: Contract revision naming the ratified section 5 implementation intent.
#: Recorded ALONGSIDE the actual argv (what ran beats what varies — a
#: revision names intent, not execution).
CONTRACT_REV: Final[str] = "ADR-INT-02/1"

_BUNDLE_NAME: Final[str] = "scratch.bundle"
_BINDING_NAME: Final[str] = "binding.diff"


class RecordVerificationError(IntegrationError):
    """Linked-record verification failure (fail-closed)."""


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_of(payload: dict[str, Any]) -> str:
    """Content digest of a record payload (unsigned fields only)."""
    return hashlib.sha256(_canonical(payload)).hexdigest()


def sign_payload(payload: dict[str, Any], key: str | bytes | None) -> tuple[str, str]:
    """Signs a record payload; returns ``(sig_mode, signature)``."""
    raw = _canonical(payload)
    if key:
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        return "hmac-sha256", hmac.new(key_bytes, raw, hashlib.sha256).hexdigest()
    return "sha256-plain", hashlib.sha256(raw).hexdigest()


def verify_payload_signature(
    payload: dict[str, Any], sig_mode: str, signature: str, key: str | bytes | None
) -> bool:
    """Recomputes and constant-time-compares a record signature."""
    expected_mode, expected = sign_payload(payload, key)
    if sig_mode != expected_mode:
        return False
    return hmac.compare_digest(expected, signature)


def candidate_content_digest(
    scratch_ref_sha: str, untracked_manifest: dict[str, str], normalized_diff: bytes
) -> str:
    """Per-candidate bytes digest: scratch SHA + manifest + norm diff."""
    payload = {
        "scratch_ref_sha": scratch_ref_sha,
        "untracked": dict(sorted(untracked_manifest.items())),
        "diff_sha256": hashlib.sha256(normalize_diff_bytes(normalized_diff)).hexdigest(),
    }
    return digest_of(payload)


class _SignedRecord(BaseModel):
    """Shared signed-record envelope (frozen; signature over payload)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sig_mode: str = ""
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        """Unsigned payload (everything except the signature envelope)."""
        dumped = self.model_dump(mode="json")
        dumped.pop("sig_mode", None)
        dumped.pop("signature", None)
        return dumped

    def digest(self) -> str:
        """Digest link for this record (over the unsigned payload)."""
        return digest_of(self.payload())

    def signed(self, key: str | bytes | None) -> Self:
        """Returns a copy carrying the signature over the payload."""
        mode, sig = sign_payload(self.payload(), key)
        return self.model_copy(update={"sig_mode": mode, "signature": sig})

    def verify_signature(self, key: str | bytes | None) -> bool:
        """Signature-auth check (existence + recompute + compare)."""
        if not self.signature or not self.sig_mode:
            return False
        return verify_payload_signature(self.payload(), self.sig_mode, self.signature, key)


class CustodyIntake(_SignedRecord):
    """T2 signed birth certificate for one candidate."""

    candidate_id: str
    base_commit: str
    scratch_ref: str
    scratch_ref_sha: str
    candidate_content_digest: str
    untracked_manifest: dict[str, str] = {}
    baseline_receipt_ref: dict[str, str] = {}
    target_env_digest: str
    lease_mode: str = ""


class SelectionRecord(_SignedRecord):
    """T3 signed per-node coverage record for one candidate."""

    candidate_id: str
    intake_ref: str
    config_revision: str
    mandatory_digest: str
    affected_inputs: dict[str, Any] = {}
    broadenings: list[str] = []
    unrun_with_reasons: list[dict[str, str]] = []
    suggested_tests: list[str] = []
    actual_gate_argv: dict[str, Any] = {}
    argv_provenance: str = ""
    contract_rev: str = CONTRACT_REV
    safeguard_declaration: list[str] = []
    safeguards_dropped: list[str] = []
    env_digest: str


class SelectionOutcomeRecord(_SignedRecord):
    """T4 signed outcome across candidates (selected OR no-champion)."""

    tree_id: str
    run_id: str
    verified: list[str] = []
    tainted: dict[str, str] = {}
    scores_summary: dict[str, float] = {}
    selected_node: str | None = None
    no_champion_reason: str | None = None
    per_node_refs: dict[str, str] = {}

    @model_validator(mode="after")
    def _exactly_one_outcome(self) -> SelectionOutcomeRecord:
        if (self.selected_node is None) == (self.no_champion_reason is None):
            raise ValueError("exactly one of selected_node / no_champion_reason must be set")
        return self


class MergeRecord(_SignedRecord):
    """T5/T6 signed merge record (pins exactly the four fields).

    ``merged_diff_sha256`` is the sha256 of the rendered BINDING diff
    bytes (``binding.diff``: the section 5.6 base/result/policy render),
    not of the ``merged.diff`` judiciary scan text.
    """

    merge_scratch_ref: str
    selection_outcome_ref: str
    env_digest: str
    merged_diff_sha256: str


def save_record(path: str | Path, record: _SignedRecord) -> Path:
    """Persists a signed record as sorted-key JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def load_record(path: str | Path, model: type[Any]) -> Any:
    """Loads a signed record (missing/corrupt file raises)."""
    target = Path(path)
    if not target.is_file():
        raise RecordVerificationError(f"linked record missing: {target}")
    try:
        return model.model_validate_json(target.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RecordVerificationError(f"linked record corrupt: {target}: {exc}") from exc


def verify_custody_intake(record: CustodyIntake, key: str | bytes | None) -> list[str]:
    """Consumption checks: signature auth + digest-link recompute + shape."""
    findings: list[str] = []
    if not record.verify_signature(key):
        findings.append(f"custody {record.candidate_id}: signature auth failed")
    if len(record.scratch_ref_sha) != 40:
        findings.append(f"custody {record.candidate_id}: scratch_ref_sha not 40-hex")
    for field in ("base_commit", "candidate_content_digest", "target_env_digest"):
        if not getattr(record, field):
            findings.append(f"custody {record.candidate_id}: empty {field}")
    for field in ("base_commit", "baseline_content_digest", "env_digest"):
        if field not in record.baseline_receipt_ref:
            findings.append(f"custody {record.candidate_id}: baseline ref missing {field}")
    return findings


def verify_selection_record(
    record: SelectionRecord,
    key: str | bytes | None,
    *,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Consumption checks: signature + config binding + argv + declaration."""
    findings: list[str] = []
    if not record.verify_signature(key):
        findings.append(f"selection {record.candidate_id}: signature auth failed")
    if config is not None:
        if record.config_revision != config.get("config_revision"):
            findings.append(
                f"selection {record.candidate_id}: config revision "
                f"{record.config_revision} != live {config.get('config_revision')}"
            )
        elif record.mandatory_digest != mandatory_set_digest(config):
            findings.append(
                f"selection {record.candidate_id}: mandatory digest mismatch "
                "(config content drifted under a bound revision)"
            )
    if record.contract_rev != CONTRACT_REV:
        findings.append(f"selection {record.candidate_id}: contract_rev {record.contract_rev}")
    if not record.actual_gate_argv:
        findings.append(f"selection {record.candidate_id}: actual gate argv missing")
    if not record.argv_provenance:
        findings.append(f"selection {record.candidate_id}: argv provenance missing")
    if not record.safeguard_declaration:
        findings.append(f"selection {record.candidate_id}: safeguard declaration missing")
    if not record.env_digest or not record.intake_ref:
        findings.append(f"selection {record.candidate_id}: env/intake link missing")
    return findings


def verify_selection_outcome(record: SelectionOutcomeRecord, key: str | bytes | None) -> list[str]:
    """Consumption checks: signature + outcome coherence + ref coverage."""
    findings: list[str] = []
    if not record.verify_signature(key):
        findings.append("selection-outcome: signature auth failed")
    if record.selected_node is not None:
        if record.selected_node not in record.verified:
            findings.append("selection-outcome: selected node not in verified set")
        if record.selected_node in record.tainted:
            findings.append("selection-outcome: selected node is tainted")
    for node in record.verified:
        if node not in record.per_node_refs:
            findings.append(f"selection-outcome: verified node {node} has no per-node ref")
    return findings


def _fetch_bundle_tmp(bundle: Path, ref: str) -> Path:
    """Fetches the bundle's scratch ref (+ full history) into a fresh repo.

    A plain clone does not fetch non-``heads`` refs, so the scratch ref
    is fetched explicitly by name.
    """
    tmp = Path(tempfile.mkdtemp(prefix="stc-bundle-verify-"))
    repo = tmp / "repo"
    if shutil.which("git") is None:
        raise RecordVerificationError("bundle verification needs git on PATH")
    init = subprocess.run(
        ["git", "init", "-q", str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    if init.returncode != 0:
        raise RecordVerificationError("bundle verify repo init failed")
    fetch = subprocess.run(
        ["git", "fetch", "-q", str(bundle), f"{ref}:{ref}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    if fetch.returncode != 0:
        raise RecordVerificationError(f"bundle fetch of {ref} failed: {fetch.stderr.strip()[:300]}")
    return repo


def verify_merge_record(
    record: MergeRecord,
    key: str | bytes | None,
    *,
    evidence_dir: str | Path,
    outcome_digest: str | None = None,
) -> list[str]:
    """Consumption checks: signature + outcome link + bundle-against-rendered."""
    findings: list[str] = []
    if not record.verify_signature(key):
        findings.append("merge: signature auth failed")
    if outcome_digest is not None and record.selection_outcome_ref != outcome_digest:
        findings.append("merge: selection-outcome ref mismatch")
    ev = Path(evidence_dir)
    rendered_path = ev / _BINDING_NAME
    bundle_path = ev / _BUNDLE_NAME
    if not rendered_path.is_file():
        findings.append("merge: rendered diff bytes missing from evidence dir")
        return findings
    if not bundle_path.is_file():
        findings.append("merge: scratch bundle missing from evidence dir")
        return findings
    rendered = rendered_path.read_bytes()
    if hashlib.sha256(normalize_diff_bytes(rendered)).hexdigest() != record.merged_diff_sha256:
        findings.append("merge: merged_diff_sha256 mismatch (rendered bytes tampered?)")
        return findings
    # Bundle-against-rendered: the lease history is linear
    # (baseline commit -> scratch commit), so the scratch ref's parent
    # is the base; recompute the policy diff from the bundle alone.
    # (A clone does not preserve custom ref names, so the SHA comes
    # from `git bundle list-heads`, matched to the pinned ref.)
    verify_proc = subprocess.run(
        ["git", "bundle", "verify", str(bundle_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    if verify_proc.returncode != 0:
        findings.append("merge: bundle fails git bundle verify")
        return findings
    heads_proc = subprocess.run(
        ["git", "bundle", "list-heads", str(bundle_path), record.merge_scratch_ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    heads = (heads_proc.stdout or "").split()
    if heads_proc.returncode != 0 or len(heads) < 2 or heads[1] != record.merge_scratch_ref:
        findings.append("merge: scratch ref unresolvable from bundle")
        return findings
    scratch_sha = heads[0]
    clone = _fetch_bundle_tmp(bundle_path, record.merge_scratch_ref)
    try:
        base_proc = subprocess.run(
            ["git", "rev-parse", f"{scratch_sha}^"],
            cwd=str(clone),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
        if base_proc.returncode != 0 or not (base_proc.stdout or "").strip():
            findings.append("merge: base (scratch^) unresolvable from bundle")
            return findings
        recomputed = render_binding_diff(clone, base_proc.stdout.strip(), scratch_sha)
        if normalize_diff_bytes(recomputed) != normalize_diff_bytes(rendered):
            findings.append("merge: bundle-against-rendered mismatch (fail-closed)")
    finally:
        shutil.rmtree(clone.parent, ignore_errors=True)
    return findings


def dossier_digest_list(
    custody: dict[str, str],
    selection: dict[str, str],
    outcome: str | None,
    merge: str | None,
) -> dict[str, str]:
    """Digest list covering all four linked records (flat key -> digest)."""
    flat: dict[str, str] = {}
    for cid in sorted(custody):
        flat[f"custody:{cid}"] = custody[cid]
    for cid in sorted(selection):
        flat[f"selection:{cid}"] = selection[cid]
    if outcome is not None:
        flat["selection_outcome"] = outcome
    if merge is not None:
        flat["merge"] = merge
    return flat


def dossier_signature(digests: dict[str, str], key: str | bytes | None) -> str:
    """HMAC (or plain sha256 when keyless) over the digest list."""
    _, sig = sign_payload(dict(sorted(digests.items())), key)
    return sig


def verify_dossier(
    run_dir: str | Path,
    key: str | bytes | None,
    *,
    config: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Full verification-consumption over a run evidence dir.

    Existence + signature auth + digest links + cross-identity agreement
    for CustodyIntake, per-node SelectionRecords, the selection-outcome
    record, and (champion runs) the merge record. Any tampered or
    substituted record fails (N6 control). Returns ``(ok, findings)``.
    """
    rd = Path(run_dir)
    findings: list[str] = []
    custody: dict[str, CustodyIntake] = {}
    selection: dict[str, SelectionRecord] = {}
    for path in sorted(rd.glob("custody_*.json")):
        try:
            record = load_record(path, CustodyIntake)
        except RecordVerificationError as exc:
            findings.append(str(exc))
            continue
        custody[record.candidate_id] = record
        findings.extend(verify_custody_intake(record, key))
    for path in sorted(rd.glob("selection_*.json")):
        if path.name == "selection_outcome.json":
            continue
        try:
            record = load_record(path, SelectionRecord)
        except RecordVerificationError as exc:
            findings.append(str(exc))
            continue
        selection[record.candidate_id] = record
        findings.extend(verify_selection_record(record, key, config=config))
    outcome: SelectionOutcomeRecord | None = None
    outcome_path = rd / "selection_outcome.json"
    if not outcome_path.is_file():
        findings.append("selection-outcome record missing")
    else:
        try:
            outcome = load_record(outcome_path, SelectionOutcomeRecord)
            findings.extend(verify_selection_outcome(outcome, key))
        except RecordVerificationError as exc:
            findings.append(str(exc))
    merge: MergeRecord | None = None
    merge_path = rd / "merge_record.json"
    if merge_path.is_file():
        try:
            merge = load_record(merge_path, MergeRecord)
            findings.extend(
                verify_merge_record(
                    merge,
                    key,
                    evidence_dir=rd,
                    outcome_digest=outcome.digest() if outcome else None,
                )
            )
        except RecordVerificationError as exc:
            findings.append(str(exc))
    # Cross-identity agreement.
    for cid, record in selection.items():
        intake = custody.get(cid)
        if intake is None:
            findings.append(f"selection {cid}: no custody intake for candidate")
        elif record.intake_ref != intake.digest():
            findings.append(f"selection {cid}: intake ref mismatch (substituted?)")
        if intake is not None and record.env_digest != intake.target_env_digest:
            findings.append(f"selection {cid}: env digest disagrees with intake")
    if outcome is not None:
        for cid, ref in outcome.per_node_refs.items():
            sel = selection.get(cid)
            if sel is None:
                findings.append(f"outcome: per-node ref {cid} has no selection record")
            elif sel.digest() != ref:
                findings.append(f"outcome: per-node ref {cid} mismatch (substituted?)")
    # Dossier digest list agreement.
    digests_path = rd / "dossier_digests.json"
    if not digests_path.is_file():
        findings.append("dossier digest list missing")
    else:
        try:
            stored = json.loads(digests_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            findings.append(f"dossier digest list corrupt: {exc}")
            stored = None
        if stored is not None:
            expected = dossier_digest_list(
                {cid: rec.digest() for cid, rec in custody.items()},
                {cid: rec.digest() for cid, rec in selection.items()},
                outcome.digest() if outcome else None,
                merge.digest() if merge else None,
            )
            if dict(stored.get("digests", {})) != expected:
                findings.append("dossier digest list mismatch (substituted record?)")
            if stored.get("dossier_signature") != dossier_signature(expected, key):
                findings.append("dossier signature mismatch")
    return len(findings) == 0, findings
