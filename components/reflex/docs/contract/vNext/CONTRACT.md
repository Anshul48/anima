# Entorhinal-to-Reflex Contract vNext

## 1. Versioning and Compatibility
- **Status**: vNext (Major revision). The previous v1 contract is now designated as legacy regression material.
- **Route/Schema**: All endpoints will use the `vNext` prefix or header `X-Contract-Version: vNext`.
- **Breaking vs Additive**: This is a breaking change. Any v1 support is temporary and strictly for backward compatibility testing, not for production use.
- **Deprecation**: V1 adapter will be refused after S8.
- **Cache**: Initially disabled. No global fallback.

## 2. Field Ownership and Validation

### 2.1 Context Request
- **Producer**: Reflex
- **Validator**: Entorhinal
- **Content**:
  - `request_id` (UUIDv4)
  - `consumer_identity` (String)
  - `purpose` (Enum: EVALUATION, SHADOW, ASSISTED)
  - `scopes` (List[String], Non-empty)
  - `deadline_ms` (Int)
  - `freshness_ms` (Int)
  - `budget_tokens` (Int)
- **Rules**: Must not derive purpose/scope from arbitrary query strings.

### 2.2 Context Result
- **Producer**: Entorhinal
- **Validator**: Reflex
- **Content**:
  - `status` (Enum - see Result State Table)
  - `payload` (Optional[ContextSnapshot], only if AVAILABLE)
  - `redacted_diagnostics` (Map[String, String])

### 2.3 Context Snapshot
- **Producer**: Entorhinal
- **Validator**: Reflex
- **Content**:
  - `snapshot_id` (UUIDv4)
  - `provider` (String)
  - `contract_revision` (String)
  - `issued_at` (ISO8601)
  - `expires_at` (ISO8601)
  - `granted_purpose` (Enum)
  - `granted_scopes` (List[String])
  - `facts` (List[Fact])

### 2.4 Fact/Hypothesis
- **Producer**: Entorhinal
- **Content**:
  - `fact_id` (String)
  - `epistemic_category` (Enum: CONFIRMED, HYPOTHESIS)
  - `confidence` (Float 0.0-1.0)
  - `validity` (Enum: VALID, REVOKED, CORRECTED)
  - `provenance_ref` (String)

### 2.5 Receipt
- **Producer**: Reflex
- **Content**:
  - `request_id` (UUIDv4)
  - `decision` (Enum: ACCEPTED, REJECTED)
  - `timing_ms` (Int)
  - `disclosure_summary` (String)
- **Rules**: No raw secret payload.

### 2.6 Error
- **Producer**: Either
- **Content**:
  - `code` (String)
  - `safe_message` (String)
  - `retryable` (Boolean)
  - `audit_correlation_id` (UUIDv4)

## 3. Result State Table

| Status | Payload | Planner Behavior | Receipt Behavior | Cache/Retry | Advisory Input |
|---|---|---|---|---|---|
| AVAILABLE | Yes | Incorporate | Log summary | Cacheable | Yes |
| NO_CONTEXT | No | Fallback | Log summary | Cacheable | No |
| DENIED | No | Terminal | Log rejection | No retry | No |
| TIMEOUT | No | Fallback | Log failure | Retryable | No |
| UNAVAILABLE | No | Fallback | Log failure | Retryable | No |
| STALE | No | Reject | Log rejection | Evict | No |
| REVOKED | No | Reject | Log rejection | Evict | No |
| MALFORMED | No | Reject | Log error | No retry | No |
| OVERSIZE | No | Reject | Log error | No retry | No |
| UNSUPPORTED_VERSION | No | Terminal | Log error | No retry | No |

## 4. Advisory-Use Policy
- **Allowed**: Low-risk semantic context (e.g., user-confirmed project identity).
- **Confirmation-Required**: Information changing user-visible content/forms.
- **Prohibited**: Credentials, auth artifacts, executable instructions, command fragments, selectors, coordinates, navigation URLs, capabilities, leases, policy overrides, verifier instructions.
- **Precedence**: Fresh UI Observation > Reflex Policy > Bounded Advisory Context. Untrusted text must be strictly escaped and never interpreted as instructional.
