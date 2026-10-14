# UI State Hash — Canonical Platform-Neutral Spec (v1)

Status: normative. Implements the CHECK-A leg-(iii) structural fix
(`compute_ui_state_hash` mixed the adapter platform label into core memory
identity, so a transition recorded on Windows was unretrievable for the same
canonical state on Linux).

## 1. Scope

`reflex.episodes.bridge.compute_ui_state_hash(obs)` maps an
`ObservationRecord` to a 16-character lowercase hex identity for the *observed
UI content*. The hash MUST depend only on the canonical UI graph. It MUST NOT
depend on: adapter name, platform label, platform metadata, observation/snapshot
IDs, timestamps, screenshot bytes, quality literals, or error messages.

## 2. Layer 1 — evidence fingerprint (delegated)

The v1 hash is derived from `CanonicalUIGraph.compute_evidence_hash()`, which
returns a 64-character lowercase hex SHA-256 digest over this exact payload:

- Serialization: `json.dumps(payload, sort_keys=True, separators=(", ", ": "), ensure_ascii=True)`.
- Field order: alphabetical by key at every object level (`sort_keys=True`).
  Top-level keys: `focused_node_id`, `nodes`, `url`, `window`.
- Nodes: array sorted ascending by `node_id`; per-node keys alphabetical:
  `attributes`, `bounds`, `children_ids`, `id`, `is_clickable`, `is_editable`,
  `is_enabled`, `is_focused`, `label`, `parent_id`, `role`, `source`, `value`.
- `children_ids` sorted ascending; `bounds` as `[x1, y1, x2, y2]` integers.
- Encoding: the JSON text is encoded UTF-8, then SHA-256, hex digest.
- None rule: `None` serializes as JSON `null` (applies to `parent_id`,
  `focused_node_id`, `url`, `window`, nullable attribute values).
- Float rule: floats serialize with shortest round-trip `repr` (CPython `json`
  default; applies only inside `attributes` — all other hashed fields are
  strings, integers, booleans, or null).
- Non-JSON-native attribute values serialize via `str()` (`default=str`).
- Excluded from identity by design: `timestamp_ms`, `viewport_size`,
  per-node `confidence`, and every `ObservationRecord` envelope field.

## 3. Layer 2 — versioned UI-state identity (this spec)

- Version marker: the literal tag `reflex-ui-state/v1`, embedded in the hash
  preimage (not in the output; the 16-char output format is unchanged).
- Preimage: the ASCII string `reflex-ui-state/v1:<layer-1-hex>` where
  `<layer-1-hex>` is the 64-char digest from §2.
- Encoding: preimage encoded UTF-8, then SHA-256.
- Output: first 16 characters of the lowercase hex digest.

Reference:

```python
raw = f"reflex-ui-state/v1:{obs.graph.compute_evidence_hash()}"
digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

## 4. Worked test vector

Graph: one node `wifi_toggle` (role `toggle`, label `Wi-Fi Enable`,
value `off`, bounds `[50, 100, 130, 132]`, clickable, focused, editable false,
enabled, source `dom`, no parent/children/attributes),
`active_window_title="Settings"`, `timestamp_ms=50000.0`,
all other graph fields default/empty.

- Layer-1 evidence digest:
  `5a233714a6b73ed2730d6e5b1f1406453ee76a5df12d35ab2c900a10297b56ac`
- v1 UI-state hash: `3a757f998594459e`
- Legacy (v0, platform `linux`) hash of the same graph: `2c852d9da9a834fb`
  (differs from v1 by construction; see §5).

## 5. Legacy hashes (v0, platform-qualified)

Hashes computed by the pre-fix formula
`sha256(f"{platform}:{evidence_hex}")[:16]` are labeled
`legacy/v0-platform-qualified`. They remain readable wherever stored, but:

- they MUST be labeled legacy at every read/compare site that handles them;
- they MUST NEVER be recomputed, backfilled, or rewritten in place;
- cross-generation comparison (v0 vs v1) is meaningless and MUST NOT be used
  for retrieval, matching, or skill-precondition fallback.

The expression `compute_ui_state_hash_legacy` exists solely for forensic
comparison and regression tests; new code MUST NOT call it.

## 6. Conformance

An implementation conforms iff, for any two observations sharing one canonical
graph but differing in envelope (platform, adapter, metadata, IDs, timestamps,
screenshots, quality): both v1 hashes are equal; both equal the §3 reference
recomputation; the output matches `[0-9a-f]{16}`; and flipping any node value
changes the hash. Regression tests: `tests/test_ui_state_hash_platform_neutral.py`.
