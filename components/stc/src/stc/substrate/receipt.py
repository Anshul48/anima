"""Cryptographic HMAC-SHA256 and SHA-256 execution receipt engine.

Handles canonical serialization, cryptographic signing, tamper detection,
and persistent storage of substrate ExecutionReceipt structures.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stc.schemas.models import ExecutionReceipt, GateReport


def serialize_canonical_payload(
    task_id: str,
    commit_hash: str,
    timestamp_utc: str,
    gate_ruff: GateReport,
    gate_mypy: GateReport,
    gate_pytest: GateReport,
    gate_mutmut: GateReport,
    correlation_id: str,
    causation_id: str | None = None,
    epoch_index: int = 1,
    python_version: str = "",
    os_platform: str = "",
    receipt_id: str = "",
) -> bytes:
    """Format canonical JSON byte stream for hashing and signing.

    Ensures bit-exact repeatability by sorting dictionary keys and
    using compact separators without extraneous whitespace.
    Includes all fields and environment metadata per 01_INVARIANTS.md §5.1.
    """
    canonical: dict[str, Any] = {
        "causation_id": causation_id,
        "commit_hash": commit_hash,
        "correlation_id": correlation_id,
        "epoch_index": epoch_index,
        "gate_mutmut": gate_mutmut.model_dump(),
        "gate_mypy": gate_mypy.model_dump(),
        "gate_pytest": gate_pytest.model_dump(),
        "gate_ruff": gate_ruff.model_dump(),
        "os_platform": os_platform,
        "python_version": python_version,
        "receipt_id": receipt_id,
        "task_id": task_id,
        "timestamp_utc": timestamp_utc,
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_receipt_signature(
    task_id: str,
    commit_hash: str,
    timestamp_utc: str,
    gate_ruff: GateReport,
    gate_mypy: GateReport,
    gate_pytest: GateReport,
    gate_mutmut: GateReport,
    correlation_id: str,
    causation_id: str | None = None,
    epoch_index: int = 1,
    python_version: str | None = None,
    os_platform: str | None = None,
    receipt_id: str | None = None,
    key: bytes | str | None = None,
) -> str:
    """Compute deterministic HMAC-SHA256 or SHA-256 signature over receipt fields.

    If a non-empty key is provided, computes an HMAC-SHA256 digest.
    If key is omitted or empty, computes a canonical SHA-256 digest.
    """
    raw_bytes = serialize_canonical_payload(
        task_id=task_id,
        commit_hash=commit_hash,
        timestamp_utc=timestamp_utc,
        gate_ruff=gate_ruff,
        gate_mypy=gate_mypy,
        gate_pytest=gate_pytest,
        gate_mutmut=gate_mutmut,
        correlation_id=correlation_id,
        causation_id=causation_id,
        epoch_index=epoch_index,
        python_version=python_version or "",
        os_platform=os_platform or "",
        receipt_id=receipt_id or "",
    )
    if key:
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        return hmac.new(key_bytes, raw_bytes, hashlib.sha256).hexdigest()
    return hashlib.sha256(raw_bytes).hexdigest()


def compute_receipt_signature_for_model(
    receipt: ExecutionReceipt,
    key: bytes | str | None = None,
) -> str:
    """Compute expected signature for an existing ExecutionReceipt instance."""
    return compute_receipt_signature(
        task_id=receipt.task_id,
        commit_hash=receipt.commit_hash,
        timestamp_utc=receipt.timestamp_utc,
        gate_ruff=receipt.gate_ruff,
        gate_mypy=receipt.gate_mypy,
        gate_pytest=receipt.gate_pytest,
        gate_mutmut=receipt.gate_mutmut,
        correlation_id=receipt.correlation_id,
        causation_id=receipt.causation_id,
        epoch_index=receipt.epoch_index,
        python_version=receipt.python_version,
        os_platform=receipt.os_platform,
        receipt_id=receipt.receipt_id,
        key=key,
    )


def create_receipt(
    task_id: str,
    commit_hash: str,
    gate_ruff: GateReport,
    gate_mypy: GateReport,
    gate_pytest: GateReport,
    gate_mutmut: GateReport,
    epoch_index: int = 1,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    receipt_id: str | None = None,
    timestamp_utc: str | None = None,
    python_version: str | None = None,
    os_platform: str | None = None,
    key: bytes | str | None = None,
) -> ExecutionReceipt:
    """Aggregate gate reports into a signed, tamper-evident ExecutionReceipt."""
    active_corr_id = correlation_id or f"corr_{uuid.uuid4().hex[:12]}"
    active_timestamp = timestamp_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    active_py_ver = python_version or platform.python_version()
    active_os = os_platform or platform.system()
    active_receipt_id = receipt_id or f"rcpt_{uuid.uuid4().hex[:12]}"

    signature = compute_receipt_signature(
        task_id=task_id,
        commit_hash=commit_hash,
        timestamp_utc=active_timestamp,
        gate_ruff=gate_ruff,
        gate_mypy=gate_mypy,
        gate_pytest=gate_pytest,
        gate_mutmut=gate_mutmut,
        correlation_id=active_corr_id,
        causation_id=causation_id,
        epoch_index=epoch_index,
        python_version=active_py_ver,
        os_platform=active_os,
        receipt_id=active_receipt_id,
        key=key,
    )

    return ExecutionReceipt(
        receipt_id=active_receipt_id,
        task_id=task_id,
        epoch_index=epoch_index,
        commit_hash=commit_hash,
        timestamp_utc=active_timestamp,
        python_version=active_py_ver,
        os_platform=active_os,
        gate_ruff=gate_ruff,
        gate_mypy=gate_mypy,
        gate_pytest=gate_pytest,
        gate_mutmut=gate_mutmut,
        sha256_signature=signature,
        correlation_id=active_corr_id,
        causation_id=causation_id,
    )


def verify_receipt(
    receipt: ExecutionReceipt,
    key: bytes | str | None = None,
) -> bool:
    """Verify cryptographic signature against canonical receipt content.

    Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
    Returns True if and only if the signature matches bit-for-bit.
    """
    expected_sig = compute_receipt_signature_for_model(receipt, key=key)
    return hmac.compare_digest(expected_sig, receipt.sha256_signature)


def save_receipt(
    receipt: ExecutionReceipt,
    output_dir: Path | None = None,
    filename: str | None = None,
) -> Path:
    """Serialize and persist the signed execution receipt to disk as JSON with LF newlines."""
    target_dir = output_dir or Path(os.environ.get("STC_RECEIPTS_DIR", "artifacts/receipts"))
    target_dir.mkdir(parents=True, exist_ok=True)
    target_filename = filename or f"{receipt.receipt_id}.json"
    target_path = target_dir / target_filename
    target_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path


def load_receipt(path: Path) -> ExecutionReceipt:
    """Load and deserialize an ExecutionReceipt from a JSON file on disk."""
    content = path.read_text(encoding="utf-8")
    return ExecutionReceipt.model_validate_json(content)


class ReceiptSigner:
    """Cryptographic receipt signer and verifier supporting HMAC-SHA256."""

    def __init__(self, key: bytes | str | None = None) -> None:
        self.key = key

    def compute_signature(
        self,
        task_id: str,
        commit_hash: str,
        timestamp_utc: str,
        gate_ruff: GateReport,
        gate_mypy: GateReport,
        gate_pytest: GateReport,
        gate_mutmut: GateReport,
        correlation_id: str,
        causation_id: str | None = None,
        epoch_index: int = 1,
        python_version: str | None = None,
        os_platform: str | None = None,
        receipt_id: str | None = None,
    ) -> str:
        """Compute signature using the configured HMAC key."""
        return compute_receipt_signature(
            task_id=task_id,
            commit_hash=commit_hash,
            timestamp_utc=timestamp_utc,
            gate_ruff=gate_ruff,
            gate_mypy=gate_mypy,
            gate_pytest=gate_pytest,
            gate_mutmut=gate_mutmut,
            correlation_id=correlation_id,
            causation_id=causation_id,
            epoch_index=epoch_index,
            python_version=python_version,
            os_platform=os_platform,
            receipt_id=receipt_id,
            key=self.key,
        )

    def create_receipt(
        self,
        task_id: str,
        commit_hash: str,
        gate_ruff: GateReport,
        gate_mypy: GateReport,
        gate_pytest: GateReport,
        gate_mutmut: GateReport,
        epoch_index: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        receipt_id: str | None = None,
        timestamp_utc: str | None = None,
        python_version: str | None = None,
        os_platform: str | None = None,
    ) -> ExecutionReceipt:
        """Create and sign a receipt with the configured key."""
        return create_receipt(
            task_id=task_id,
            commit_hash=commit_hash,
            gate_ruff=gate_ruff,
            gate_mypy=gate_mypy,
            gate_pytest=gate_pytest,
            gate_mutmut=gate_mutmut,
            epoch_index=epoch_index,
            correlation_id=correlation_id,
            causation_id=causation_id,
            receipt_id=receipt_id,
            timestamp_utc=timestamp_utc,
            python_version=python_version,
            os_platform=os_platform,
            key=self.key,
        )

    def verify(self, receipt: ExecutionReceipt) -> bool:
        """Verify the receipt signature against the configured key."""
        return verify_receipt(receipt, key=self.key)


__all__ = [
    "ReceiptSigner",
    "compute_receipt_signature",
    "compute_receipt_signature_for_model",
    "create_receipt",
    "load_receipt",
    "save_receipt",
    "serialize_canonical_payload",
    "verify_receipt",
]
