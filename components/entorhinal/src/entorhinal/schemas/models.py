"""Core Pydantic data schemas, classification taxonomy, and epistemic models for Entorhinal.

Invariants preserved:
1. Epistemic separation: Evidence != Derived Facts != Hypotheses != ContextSnapshots != User Corrections.
2. Immutability: EvidenceRecord, DerivedFact, Hypothesis, ContextSnapshot, and UserCorrection models are frozen.
3. Provenance & Hash Chaining: SHA-256 hash chains with UUIDv7 monotonic identifiers.
4. Fail-Closed & Zero Action Authority: Purely observational data structures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ==============================================================================
# Helper Functions: Monotonic UUIDv7 & Cryptographic Hashing
# ==============================================================================

def generate_uuidv7(timestamp_ms: Optional[int] = None) -> str:
    """Generate an RFC 9562 compliant UUIDv7 string.

    UUIDv7 format:
    - 48 bits: Unix timestamp in milliseconds
    - 4 bits: Version 7 (0b0111)
    - 12 bits: Random data (rand_a)
    - 2 bits: Variant 10 (RFC 4122 / RFC 9562)
    - 62 bits: Random data (rand_b)
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    rand_bytes = os.urandom(10)
    ts_bytes = timestamp_ms.to_bytes(6, byteorder="big")

    uuid_bytes = bytearray(16)
    uuid_bytes[0:6] = ts_bytes
    # Byte 6: 0x70 (version 7) | (4 bits of random)
    uuid_bytes[6] = 0x70 | (rand_bytes[0] & 0x0F)
    # Byte 7: 8 bits of random
    uuid_bytes[7] = rand_bytes[1]
    # Byte 8: 0x80 (variant 10) | (6 bits of random)
    uuid_bytes[8] = 0x80 | (rand_bytes[2] & 0x3F)
    # Bytes 9-15: 56 bits of random
    uuid_bytes[9:16] = rand_bytes[3:10]

    return str(uuid.UUID(bytes=bytes(uuid_bytes)))


def compute_sha256(content: Any) -> str:
    """Compute deterministic SHA-256 hex digest for any payload or string."""
    if isinstance(content, bytes):
        content_bytes = content
    elif isinstance(content, str):
        content_bytes = content.encode("utf-8")
    elif isinstance(content, dict):
        content_bytes = json.dumps(content, sort_keys=True, default=str).encode("utf-8")
    elif isinstance(content, list):
        content_bytes = json.dumps(content, sort_keys=True, default=str).encode("utf-8")
    else:
        content_bytes = str(content).encode("utf-8")

    return hashlib.sha256(content_bytes).hexdigest()


def compute_record_hash(previous_record_hash: str, record_dict: Dict[str, Any]) -> str:
    """Compute the tamper-evident SHA-256 hash for a chained EvidenceRecord.

    Excludes volatile/computed hash fields during digest computation.
    """
    clean_dict = {
        k: v for k, v in record_dict.items()
        if k not in ("provenance_hash",)
    }
    canonical_str = f"{previous_record_hash}:{json.dumps(clean_dict, sort_keys=True, default=str)}"
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


# ==============================================================================
# Stable semantic identity (F10): deterministic fact/cluster/edge references
# ==============================================================================

#: Algorithm versions for stable identity derivation. Disclosed in health
#: detail and repair evidence; bumped only with a deliberate migration.
FACT_ID_ALGORITHM = "fact-id/1"
CLUSTER_ID_ALGORITHM = "cluster-id/1"
EDGE_ID_ALGORITHM = "edge-id/1"


def _canonical_json(value: Any) -> str:
    """Canonical JSON for stable hashing (sorted keys, compact separators)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def derive_stable_id(*, namespace: str, parts: Dict[str, Any], length: int = 32) -> str:
    """Derive a deterministic `namespace-hex` id from canonical parts.

    Identical parts always yield the identical id, in any process. Parts
    must themselves be deterministic (sorted id lists, ISO datetimes).
    """
    digest = hashlib.sha256(f"{namespace}:".encode("utf-8") + _canonical_json(parts).encode("utf-8")).hexdigest()
    return f"{namespace}{digest[:length]}"


def derive_fact_id(
    *,
    entity_uri: str,
    attribute: str,
    value: Any,
    valid_from: Any,
    valid_to: Any,
    evidence_ids: List[str],
    derived_by: str,
) -> str:
    """Derive the stable semantic id for a fact (``FACT_ID_ALGORITHM``).

    The id binds (entity, attribute, value, validity, evidence-set,
    derivation). Validity instants must come from evidence timestamps, never
    wall-clock processing time, so identical evidence replays identically.
    ``revision_id`` remains the separate monotonic revision counter.
    """
    return derive_stable_id(
        namespace="fact-v1-",
        parts={
            "algorithm": FACT_ID_ALGORITHM,
            "entity_uri": entity_uri,
            "attribute": attribute,
            "value": json.loads(_canonical_json(value)),
            "valid_from": valid_from.isoformat() if isinstance(valid_from, datetime) else str(valid_from),
            "valid_to": valid_to.isoformat() if isinstance(valid_to, datetime) else (None if valid_to is None else str(valid_to)),
            "evidence_ids": sorted(evidence_ids),
            "derived_by": derived_by,
        },
    )


def derive_cluster_id(
    *,
    evidence_ids: List[str],
    start_time: Any,
    end_time: Any,
    title: str,
) -> str:
    """Derive the stable id for a session cluster (``CLUSTER_ID_ALGORITHM``)."""
    start = start_time.isoformat() if isinstance(start_time, datetime) else str(start_time)
    end = end_time.isoformat() if isinstance(end_time, datetime) else str(end_time)
    return derive_stable_id(
        namespace="cluster-v1-",
        parts={
            "algorithm": CLUSTER_ID_ALGORITHM,
            "evidence_ids": sorted(evidence_ids),
            "start_time": start,
            "end_time": end,
            "title": title,
        },
    )


def derive_edge_id(*, source_uri: str, relation_type: str, target_uri: str) -> str:
    """Derive the stable id for a graph edge (``EDGE_ID_ALGORITHM``)."""
    return derive_stable_id(
        namespace="edge-v1-",
        parts={
            "algorithm": EDGE_ID_ALGORITHM,
            "source_uri": source_uri,
            "relation_type": relation_type,
            "target_uri": target_uri,
        },
    )


# ==============================================================================
# Exact default-deny scope matching (F4)
# ==============================================================================

#: Record source-type -> scope class. Every fact derived from a record carries
#: the record's class scope.
SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE = {
    "browser": "scope:browser",
    "terminal_pty": "scope:terminal",
    "os_window": "scope:workspace",
    "os_accessibility": "scope:workspace",
    "document": "scope:workspace",
    "calendar": "scope:developer",
    "user_input": "scope:developer",
}

#: Entity-URI scheme -> scope class fallback. Applied when a fact carries no
#: explicit stored tag for a scheme; unknown schemes match nothing
#: (default-deny). Document http(s) URLs resolve to scope:browser, all other
#: document URIs to scope:workspace (see fallback_tags_for_uri).
ENTITY_SCHEME_SCOPE_TABLE = {
    "project:": "scope:workspace",
    "workspace:": "scope:workspace",
    "goal:": "scope:workspace",
    "artifact:": "scope:workspace",
    "session:": "scope:workspace",
    "topic:arxiv:": "scope:browser",
    "topic:git-branch:": "scope:terminal",
    "topic:test-execution:": "scope:terminal",
}


@lru_cache(maxsize=4096)
def scope_class(scope: str) -> Optional[str]:
    """Return the scope class (``scope:<name>``) for a requested scope pattern.

    ``scope:workspace.active_project`` -> ``scope:workspace``;
    ``scope:browser.*`` -> ``scope:browser``; anything else -> None.
    """
    text = (scope or "").strip()
    if not text.startswith("scope:"):
        return None
    rest = text[len("scope:"):]
    name = rest.split(".", 1)[0].rstrip("*").rstrip(".")
    if not name:
        return None
    return f"scope:{name}"


def source_scope_for_source_id(source_id: str) -> str:
    """Canonical source scope tag for a configured source id."""
    return f"scope:source:{source_id}"


@lru_cache(maxsize=16384)
def fallback_tags_for_uri(entity_uri: str) -> List[str]:
    """Fixed prefix-table scope tags for an entity URI (default-deny).

    Unknown URI schemes yield no tags. This fallback keeps hand-constructed
    and legacy facts matchable under the exact matcher; graph-derived facts
    additionally carry explicit stored tags (record class + entity kind).
    Callers must not mutate the returned list (it is cached).
    """
    uri = (entity_uri or "").strip()
    for prefix, tag in ENTITY_SCHEME_SCOPE_TABLE.items():
        if uri.startswith(prefix):
            return [tag]
    if uri.startswith("document:"):
        lowered = uri.lower()
        if "https://" in lowered or "http://" in lowered:
            return ["scope:browser"]
        return ["scope:workspace"]
    if uri.startswith("topic:"):
        return ["scope:browser"]
    return []


def effective_fact_tags(entity_uri: str, stored_scopes: List[str]) -> List[str]:
    """Explicit stored scopes, or the URI fallback table when untagged.

    Stored tags are ground truth (tagged from the raw record at derivation
    time) and take precedence: the fallback is a heuristic for legacy and
    hand-constructed facts and must never override explicit tags (entity
    URIs are slugified, so the heuristic can misread schemes -- e.g. a
    slugified ``document:https_//...`` URI -- and union semantics would
    disclose across scopes). Sorted for determinism.
    """
    stored = sorted({s.strip() for s in (stored_scopes or []) if s and s.strip()})
    if stored:
        return stored
    return sorted(set(fallback_tags_for_uri(entity_uri)))


def fact_matches_scope(entity_uri: str, stored_scopes: List[str], pattern: str) -> bool:
    """Exact scope-pattern match for one fact (default-deny).

    Match iff the pattern is the explicit wildcard ``"*"`` (honored only when
    explicitly granted, and then only for facts carrying at least one
    effective tag), equals the entity URI exactly, or its scope class is one
    of the fact's effective tags. No substring or prefix implication.
    """
    pat = (pattern or "").strip()
    if not pat:
        return False
    if pat == entity_uri:
        return True
    tags = effective_fact_tags(entity_uri, stored_scopes)
    if pat == "*":
        return bool(tags)
    wanted = scope_class(pat)
    if wanted is None:
        return False
    return wanted in tags


def scope_covers_record_class(pattern: str, record_class: Optional[str]) -> bool:
    """Whether one requested scope pattern covers a record's scope class.

    Used for aggregate (session) gating: explicit ``"*"`` covers any known
    class; otherwise the pattern's scope class must equal the record's
    class. Unknown classes are never covered (fail-closed).
    """
    pat = (pattern or "").strip()
    if not pat or not record_class:
        return False
    if pat == "*":
        return True
    return scope_class(pat) == record_class


def fact_tier_rank(entity_uri: str, attribute: str, confidence: float) -> int:
    """Deterministic budget-priority tier rank (lower packs first).

    Mirrors the documented 4-tier compression: Tier 1 corrections/workspace
    identifiers first, Tier 2 focus/session next, Tier 3 relations/goals/
    artifacts next, Tier 4 (everything else) last.
    """
    uri = (entity_uri or "").lower()
    attr = (attribute or "").lower()
    if "workspace" in uri or "project" in uri or "user_correction" in uri:
        return 1
    if ("session" in uri or "immediate" in uri or "focus" in uri) and confidence >= 0.85:
        return 2
    if "relation" in attr or "goal" in uri or "artifact" in uri:
        return 3
    return 4


# ==============================================================================
# Enumerations
# ==============================================================================

class SourceType(str, Enum):
    """Permitted source signal categories."""
    BROWSER = "browser"
    OS_WINDOW = "os_window"
    OS_ACCESSIBILITY = "os_accessibility"
    TERMINAL_PTY = "terminal_pty"
    DOCUMENT = "document"
    CALENDAR = "calendar"
    USER_INPUT = "user_input"


class ClassificationLevel(str, Enum):
    """Data classification taxonomy."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PROHIBITED = "prohibited"


class CorrectionAction(str, Enum):
    """User override action directives."""
    OVERWRITE = "overwrite"
    EXCLUDE = "exclude"
    DELETE = "delete"


# ==============================================================================
# Epistemic Layer 1: Raw Signal Event (Volatile RAM Buffer)
# ==============================================================================

class RawSignalEvent(BaseModel):
    """Ephemeral, unnormalized signal emitted by a permitted source adapter.

    Lives strictly in volatile RAM before policy evaluation and journal persistence.
    """
    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 signal ID")
    source_type: SourceType = Field(..., description="Source category")
    adapter_id: str = Field(..., min_length=1, description="Identifier of the source adapter")
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when signal was observed"
    )
    device_id: str = Field(default="local-device", min_length=1, description="Origin device ID")
    app_identifier: str = Field(..., min_length=1, description="Application identifier/process name")
    window_title: Optional[str] = Field(default=None, description="Active window title")
    target_uri: Optional[str] = Field(default=None, description="Target URI or file path")
    raw_payload: Dict[str, Any] = Field(default_factory=dict, description="Raw unnormalized payload")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional capture metadata")


# ==============================================================================
# Epistemic Layer 2: Evidence Record (Immutable Durable Journal)
# ==============================================================================

class EvidenceRecord(BaseModel):
    """Immutable, policy-sanitized, provenance-bearing record persisted to the local journal."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 deterministic record ID")
    schema_version: str = Field(default="1.0.0", description="Contract version")
    persisted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC persistence timestamp"
    )
    source_type: SourceType = Field(..., description="Source category")
    app_identifier: str = Field(..., min_length=1, description="Normalized application identifier")
    window_title: Optional[str] = Field(default=None, description="Sanitized window title")
    target_uri: Optional[str] = Field(default=None, description="Sanitized target URI")
    sanitized_payload: Dict[str, Any] = Field(default_factory=dict, description="Policy-redacted payload")
    classification: ClassificationLevel = Field(
        default=ClassificationLevel.INTERNAL,
        description="Assigned data classification"
    )
    provenance_hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 hash of record content")
    previous_record_hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 hash of prior journal entry")
    is_tombstone: bool = Field(default=False, description="Tombstone marker for revoked/erased records")
    tombstone_reason: Optional[str] = Field(default=None, description="Reason for cryptographic tombstoning")

    @classmethod
    def create(
        cls,
        source_type: SourceType,
        app_identifier: str,
        sanitized_payload: Dict[str, Any],
        previous_record_hash: str,
        window_title: Optional[str] = None,
        target_uri: Optional[str] = None,
        classification: ClassificationLevel = ClassificationLevel.INTERNAL,
        record_id: Optional[str] = None,
        persisted_at: Optional[datetime] = None,
        is_tombstone: bool = False,
        tombstone_reason: Optional[str] = None,
    ) -> EvidenceRecord:
        """Factory method to construct an EvidenceRecord with an automatically computed provenance hash."""
        rid = record_id or generate_uuidv7()
        ts = persisted_at or datetime.now(timezone.utc)

        data_for_hash = {
            "record_id": rid,
            "schema_version": "1.0.0",
            "persisted_at": ts.isoformat(),
            "source_type": source_type.value,
            "app_identifier": app_identifier,
            "window_title": window_title,
            "target_uri": target_uri,
            "sanitized_payload": sanitized_payload,
            "classification": classification.value,
            "previous_record_hash": previous_record_hash,
            "is_tombstone": is_tombstone,
            "tombstone_reason": tombstone_reason,
        }
        prov_hash = compute_record_hash(previous_record_hash, data_for_hash)

        return cls(
            record_id=rid,
            schema_version="1.0.0",
            persisted_at=ts,
            source_type=source_type,
            app_identifier=app_identifier,
            window_title=window_title,
            target_uri=target_uri,
            sanitized_payload=sanitized_payload,
            classification=classification,
            provenance_hash=prov_hash,
            previous_record_hash=previous_record_hash,
            is_tombstone=is_tombstone,
            tombstone_reason=tombstone_reason,
        )


# ==============================================================================
# Epistemic Layer 3: Derived Fact (Normalized Semantic Assertion)
# ==============================================================================

class DerivedFact(BaseModel):
    """Normalized, verified semantic assertion extracted from one or more Evidence Records."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 fact ID")
    schema_version: str = Field(default="1.0.0", description="Contract version")
    entity_uri: str = Field(..., min_length=1, description="URI of the entity this fact describes")
    attribute: str = Field(..., min_length=1, description="Semantic attribute key")
    value: Any = Field(..., description="Fact value (primitive, dict, or list)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Normalized confidence score [0.0, 1.0]")
    valid_from: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC validity start timestamp"
    )
    valid_to: Optional[datetime] = Field(default=None, description="UTC validity end timestamp")
    supporting_evidence_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of EvidenceRecord UUIDs grounding this fact"
    )
    derived_by: str = Field(..., min_length=1, description="Compiler or rule ID producing this fact")
    revision_id: int = Field(default=1, ge=1, description="Monotonic revision counter")
    scopes: List[str] = Field(
        default_factory=list,
        description="Explicit scope tags authorizing disclosure (default-deny when empty)",
    )


# ==============================================================================
# Epistemic Layer 4: Hypothesis (Uncertain Semantic Proposal)
# ==============================================================================

class Hypothesis(BaseModel):
    """Uncertain, probabilistic semantic proposal or intent classification.

    Invariant: `is_hypothesis` must ALWAYS be True and cannot be mutated.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 hypothesis ID")
    proposed_intent: str = Field(..., min_length=1, description="Proposed semantic intent or label")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence [0.0, 1.0]")
    candidate_evidence_ids: List[str] = Field(
        default_factory=list,
        description="Candidate EvidenceRecord IDs considered"
    )
    uncertainty_reasons: List[str] = Field(
        default_factory=list,
        description="Explicit ambiguity or uncertainty factors"
    )
    expires_at: datetime = Field(..., description="UTC expiration timestamp for TTL bounding")
    is_hypothesis: bool = Field(default=True, frozen=True, description="Strict epistemic marker")

    @field_validator("is_hypothesis")
    @classmethod
    def validate_is_hypothesis(cls, v: bool) -> bool:
        if not v:
            raise ValueError("is_hypothesis invariant violated: must always be True")
        return True


# ==============================================================================
# Epistemic Layer 5: Context Request & Context Snapshot (Advisory Bounded Context)
# ==============================================================================

class ContextRequest(BaseModel):
    """Bounded query from an approved consumer."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_uri: Optional[str] = Field(default=None, alias="$schema", description="JSON schema URI")
    request_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 request ID")
    schema_version: str = Field(default="1.0.0", description="Contract version")
    consumer_id: str = Field(..., min_length=1, description="Consumer identity/role")
    stated_purpose: str = Field(..., min_length=1, description="Explicit stated purpose for query")
    requested_scopes: List[str] = Field(..., min_length=1, description="Target scopes requested")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC request timestamp"
    )
    max_freshness_seconds: int = Field(default=300, ge=1, description="Maximum age of acceptable facts in seconds")
    token_or_size_budget: int = Field(default=2048, ge=1, description="Maximum token or size budget for context payload")
    correlation_id: Optional[str] = Field(default=None, description="Optional upstream correlation ID")


class SnapshotBudget(BaseModel):
    """Truthful accounting of the delivered snapshot serialization.

    Counts refer to the canonical compact-JSON consumer serialization,
    measured with the identified tokenizer. ``overflow`` is True iff any
    content was pruned to fit the declared budget.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    budget_tokens: int = Field(..., ge=1, description="Effective token budget applied")
    used_tokens: int = Field(..., ge=0, description="Tokens in the delivered serialization")
    used_chars: int = Field(..., ge=0, description="Characters in the delivered serialization")
    tokenizer: str = Field(..., min_length=1, description="Identified counter, e.g. tiktoken/o200k_base")
    overflow: bool = Field(default=False, description="True iff content was pruned for budget")
    omitted_facts: int = Field(default=0, ge=0, description="Facts dropped for budget")
    omitted_hypotheses: int = Field(default=0, ge=0, description="Hypotheses dropped for budget")


class ContextSnapshot(BaseModel):
    """Bounded, purpose-scoped, time-to-live limited advisory context payload delivered to consumer."""
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_uri: Optional[str] = Field(default=None, alias="$schema", description="JSON schema URI")
    snapshot_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 snapshot ID")
    schema_version: str = Field(default="1.0.0", description="Contract version")
    request_id: Optional[str] = Field(default=None, description="Originating ContextRequest ID")
    issued_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC issuance timestamp"
    )
    expires_at: datetime = Field(..., description="UTC expiration timestamp")
    purpose_granted: str = Field(..., min_length=1, description="Authorized purpose")
    scope_granted: List[str] = Field(default_factory=list, description="Authorized scopes included")
    active_facts: List[DerivedFact] = Field(default_factory=list, description="Active facts matching scope")
    active_hypotheses: List[Hypothesis] = Field(default_factory=list, description="Active hypotheses included")
    evidence_provenance_refs: List[str] = Field(
        default_factory=list,
        description="SHA-256 or record UUID references for provenance"
    )
    redaction_manifest: List[str] = Field(
        default_factory=list,
        description="List of fields/patterns redacted before delivery"
    )
    disclaimer: str = Field(
        default="ADVISORY ONLY. Direct user instruction and fresh observation take precedence.",
        description="Mandatory epistemic warning"
    )
    overflow: bool = Field(default=False, description="True iff budget pruning dropped content")
    budget: Optional[SnapshotBudget] = Field(
        default=None, description="Truthful delivered-serialization accounting when enforced"
    )


# ==============================================================================
# Epistemic Layer 6: User Correction & Tombstone (Human Primacy)
# ==============================================================================

class UserCorrection(BaseModel):
    """Explicit human override, exclusion, annotation, or deletion command.

    Invariant: Takes absolute priority over all historical evidence, facts, and hypotheses.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    correction_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 correction ID")
    target_entity_or_fact_id: str = Field(..., min_length=1, description="Target entity URI or fact ID")
    override_action: CorrectionAction = Field(..., description="Correction action type")
    corrected_value: Optional[Any] = Field(default=None, description="Replacement value if OVERWRITE")
    user_comment: Optional[str] = Field(default=None, description="Optional user annotation")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of user command"
    )


class TombstoneRecord(BaseModel):
    """Cryptographic tombstone record replacing revoked/deleted evidence in the journal."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    tombstone_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 tombstone ID")
    original_record_id: str = Field(..., min_length=1, description="ID of the overwritten evidence record")
    revocation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC revocation timestamp"
    )
    revocation_reason: str = Field(..., min_length=1, description="Reason for deletion/revocation")
    previous_record_hash: str = Field(..., min_length=64, max_length=64, description="Prior hash in chain")
    tombstone_hash: str = Field(..., min_length=64, max_length=64, description="Sealed tombstone hash")

    @classmethod
    def create(
        cls,
        original_record_id: str,
        previous_record_hash: str,
        revocation_reason: str = "User deletion request",
        tombstone_id: Optional[str] = None,
        revocation_timestamp: Optional[datetime] = None,
    ) -> TombstoneRecord:
        tid = tombstone_id or generate_uuidv7()
        ts = revocation_timestamp or datetime.now(timezone.utc)
        payload = {
            "tombstone_id": tid,
            "original_record_id": original_record_id,
            "revocation_timestamp": ts.isoformat(),
            "revocation_reason": revocation_reason,
            "previous_record_hash": previous_record_hash,
            "is_tombstone": True,
        }
        thash = compute_record_hash(previous_record_hash, payload)
        return cls(
            tombstone_id=tid,
            original_record_id=original_record_id,
            revocation_timestamp=ts,
            revocation_reason=revocation_reason,
            previous_record_hash=previous_record_hash,
            tombstone_hash=thash,
        )


# ==============================================================================
# Governance & Explanations
# ==============================================================================

class FactExplanation(BaseModel):
    """Detailed audit explanation of why and how a fact was derived."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(..., description="Target fact ID")
    entity_uri: str = Field(..., description="Target entity URI")
    attribute: str = Field(..., description="Attribute key")
    value: Any = Field(..., description="Fact value")
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    derived_by: str = Field(...)
    reasoning_summary: str = Field(...)
    valid_from: datetime = Field(...)
    valid_to: Optional[datetime] = None
    derivation_rule: Optional[str] = Field(default=None, description="Rule or compiler descriptor")
    supporting_evidence: List[EvidenceRecord] = Field(default_factory=list, description="Sanitized EvidenceRecords grounding this fact")
    active_hypotheses: List[Dict[str, Any]] = Field(default_factory=list, description="Candidate hypotheses associated with this fact")
    uncertainty_reasons: List[str] = Field(default_factory=list, description="Uncertainty factors if any")
    user_override_active: bool = Field(default=False, description="Whether an active user correction overrides this fact")


class PolicyDecision(BaseModel):
    """Result of policy evaluation against a raw signal or query request."""
    model_config = ConfigDict(extra="forbid")

    permitted: bool = Field(..., description="Whether signal/request is permitted")
    classification: ClassificationLevel = Field(..., description="Assigned classification level")
    redacted_payload: Optional[Dict[str, Any]] = Field(default=None, description="Sanitized payload")
    sanitized_window_title: Optional[str] = Field(default=None, description="Redacted window title if present")
    sanitized_target_uri: Optional[str] = Field(default=None, description="Sanitized target URI if present")
    violations: List[str] = Field(default_factory=list, description="List of policy violations or match reasons")
    redacted_fields: List[str] = Field(default_factory=list, description="Fields modified during redaction")
    audit_event_id: str = Field(default_factory=generate_uuidv7, description="Audit event identifier")
