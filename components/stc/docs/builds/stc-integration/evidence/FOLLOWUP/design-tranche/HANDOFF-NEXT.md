# Handoff — verdict synthesis + next-session prompts (design tranche, post-review)

Status: VERDICT SYNTHESIZED, NOT RATIFIED. Nothing here approves
implementation. Next step is reconciliation redlines + one final coherent
authorization, brought back for operator/Sovereign approval. This file
supersedes HANDOFF-TEMP.md for the next session (leave HANDOFF-TEMP.md
for deletion at tranche close per its own instruction). Prior session
goal shows blocked/terminal; work below proceeds under direct instruction.

## Source map (what "the verdict" is)

Two pasted texts, both operator-provided 2026-09-19, processed together:

- Review A ("verdict"): conditional approve of the consistency review's
  findings — accept blockers 2, 3(goal), 5 and E1–E4 as specified;
  modify 1 (env reframing: provenance-not-identity, floor+record,
  `uv sync` construction, strike pip venv), 4 (tripwire-only), 6
  (linked records, no receipt bloat). Code-reading-settled, no red/blue
  teams.
- Review B (meta-critique, constrains A — "would not approve it
  verbatim"): 6 corrections + budget-terminology question. B explicitly
  did NOT confirm repo citations; the Verified Facts section below does
  that work now, so the next session inherits zero unverified claims.

Reconciliation rule used: accept A's simplifications where B doesn't
object; where they conflict, B's correction governs unless a tree fact
overrules it. Each point below records A/B/reconciled explicitly.

## Verified tree facts (probed 2026-09-19, read-only, this session)

- V1 Floor: `pyproject.toml:10` requires-python `>=3.12`. Contract
  `01_INVARIANTS.md:5` says 3.12+. Both are floors. (A correct.)
- V2 Lockfile: `stc/uv.lock` committed (194972 B); Makefile `sync`
  target runs `uv sync --frozen --all-groups`. (A correct.)
- V3 CI: `.github/workflows/ci.yml` matrix runs ubuntu-latest +
  windows-latest — cross-env comparison is routine. (A correct; kills
  any "no receipt spans envs" absolute.)
- V4 F4 assert: `test_integration_identity.py:111`
  `startswith("3.12.")` — accepts 3.12.x ONLY, rejects 3.13. It is a
  minor-series pin, NOT a floor. (B correct; A's "encodes a floor"
  is factually wrong. Floor-vs-pin is therefore a REAL open decision:
  contract+pyproject say floor, the test says pin.)
- V5 uv flags (installed uv `--help`): `--locked` asserts the lockfile
  stays unchanged; `--frozen` merely syncs without updating it.
  (B correct: construction needs `--locked`, or an explicit lock
  check before `--frozen`.)
- V6 Toolchain in lock: uv.lock + pyproject BOTH contain ruff, mypy,
  pytest, mutmut. `uv sync --locked` reproduces the FULL gate
  toolchain — no dependency additions needed for construction.
- V7 Tripwire precedent exists: `dispatch.py:127` ("Outer dirs under
  tripwire watch"). (A correct.)
- V8 Receipt frozen: `ExecutionReceipt` (`models.py:212-228`)
  `frozen=True, extra="forbid"`; fields include `commit_hash`,
  `python_version`, `os_platform`, 4 gates, HMAC — NO argv, NO tool
  versions, NO digests. (A correct on substance; line is 212 not 200.)
- V9 Budget term: R5 (`PROJECT.md:41`) = "CLI-session budget" for
  builders = CLI-AGENT (model-backed) spend, distinct from API-key
  spend; every evidence log counts agent sessions only. "Six CLI
  sessions" = six model-backed agent sessions; local deterministic
  commands are uncounted (but logged). (Answers B's terminology Q
  from repo text.)

## Reconciled positions (what the next session implements in redlines)

### R-ENV (blocker 1 + §5.5 — the one that matters)

A says: floor + 3-line check (≥3.12, tools present, versions recorded);
patch drift recorded never deviation; build via uv sync; strike pip venv.
B corrects: keep compatibility/provenance/reuse DISTINCT; patch change ⇒
different fingerprint with explicit requalification policy; --locked not
--frozen; env must include app deps + mutmut tooling, not just 3 tools.
RECONCILED (all three kept):

- COMPATIBILITY (floor): product supports Python ≥3.12 + ruff/mypy/
  pytest/mutmut present + app deps installed. Fail closed ONLY on
  floor violation or missing tool. N4 stays as the floor-polarity test.
- PROVENANCE (fingerprint): every check records its EXACT env
  fingerprint (interpreter string, tool `--version`s, lockfile content
  hash, `os_platform`). 3.12.3 vs 3.12.10 = different fingerprints,
  recorded always — never a silent same.
- REUSE (requalification policy — NEW, explicit): same
  (major,minor) + same tools-present set + same lockfile content hash
  ⇒ baseline receipts reusable without re-approval. ANY lockfile
  content change or minor-version change ⇒ requalify the baseline
  (re-run T0). Windows↔Linux results comparable with separate
  identities each (V3 precedent). Patch drift needs no approval AND
  leaves an exact trail — portability and evidence identity coexist.
- CONSTRUCTION: STC pyproject+uv.lock via `uv sync --locked`
  (V5/V6 — full toolchain, no additions). No pip venv (split-brain),
  no TRACE-owned env (Q2 intent preserved structurally). If the 3.12
  interpreter or sync inputs are unavailable: stop, report, no fallback.
- OPEN DECISION D-α: the F4 test pins 3.12.x (V4) while contract+
  pyproject say floor. RECOMMEND floor (portability instruction rules)
  + amend the test to a `>= (3, 12)` check as implementation scope.
  Operator confirms in the authorization; the alternative (narrow
  contract to 3.12.x) needs its own amendment, never a silent keep.

### R-HEAD (blocker 2 — propagation AND assertion)

A says: assert suffices; re-specifying the `main` default is optional.
B corrects: assert-without-propagation is safe but unusable — nested
leases still need to be TOLD the right ref.
RECONCILED (B governs): BOTH, as originally drafted (T2/Q1): explicit
`(lease_git_path, scratch_ref_SHA)` propagation into every nested lease
(usability) + `HEAD == scratch SHA` assert before gates on EVERY lease
(safety; one `git rev-parse` comparison, zero API change). A's narrow
point stands: safety never depends on the default. Primary leases get
the checkout rule my drafts left implicit: scratch ref checked out at
intake, assert at gate time.

### R-DIFF (blocker 3 — precise durable binding)

A says: auditor recomputes diff from merge scratch ref; shared
`normalize_diff()` at render (`dialectic_runner.py:850`) + audit;
pass `merged_dir` to `_audit`; `merged_diff_sha256` field only if
needed. B corrects: commit alone doesn't fix base/policy; objects must
survive lease deletion; unspecified normalization could erase meaning;
field-vs-linked-record is a wash, neither is "five lines."
RECONCILED:

- DEFINITION (exact): base = merge lease's baseline tree
  (base_commit tree + baseline manifest); result = merge scratch-ref
  tree; policy = `git diff --no-ext-diff --unified=3 <base> <result>`
  with default whitespace handling (NO ignore-whitespace); the shared
  helper canonicalizes transport only (LF endings, trailing newline
  at EOF, exact hunk headers) — it MUST NOT reorder hunks or touch
  in-line whitespace. Base+policy frozen in the redline.
- DURABILITY: live path passes `merged_dir` to `_audit` (A's note,
  accepted); evidence path stores a `git bundle` of the scratch ref +
  the rendered diff bytes in the evidence dir, so verification survives
  lease deletion forever. Auditor checks live-against-rendered now,
  bundle-against-rendered later; mismatch fails closed either way.
- FIELD QUESTION folds into R-LINK: carry `merged_diff_sha256` in the
  linked merge record (below), not as a new ExecutionReceipt field.

### R-TRIP (blocker 4 — full-manifest tripwire, detection scoped honestly)

A says: tripwire only, drop chmod (theater on Windows/OneDrive).
B corrects: tripwires DETECT, don't prevent; need FULL manifest
(additions+deletions, not spot checks); approve detection-only
explicitly if acceptable; write-then-restore is invisible to hashing.
RECONCILED: tripwire-only (A's chmod point uncontested) + FULL
manifest hashed at lease open, pre-gates, and close (every enumerated
file; additions/deletions fail, not just content deltas) + the
guarantee LABELED detection-with-fail-closed, never "read-only":
persistent change ⇒ run fails; transient write-then-restore is a
RESIDUAL RISK the authorization accepts explicitly. Prevention awaits
container read-only mounts — noted as future, not built. Matches the
`dispatch.py:127` precedent (V7).

### R-SEL (blocker 5 — versioned selection config)

Agreed by A+B: node-level M1 (`test_record_shape_and_env_keys`) + M2
(two F2 tests, verified `:78` + `:1025`) + file-level M3 (both files),
frozen in ONE versioned data file (selection config / owning-suite-map
revision — never prose, where the IDs already went missing once), with
the selection record's mandatory-set digest binding it automatically.
B's qualifications adopted: missing files/node IDs fail closed;
file-level is NOT literally rename-proof (a move OUT of the file
escapes it) ⇒ config ALSO pins per-file node counts as a tripwire
(count change = finding). Tiny fixed layer + adaptive breadth stands.

### R-LINK (blocker 6 — linked records with teeth + actual argv)

A says: separate signed CustodyIntake + SelectionRecord (SLSA/in-toto),
dossier HMAC'd over the digest list; static argv needs no per-run
binding (contract_rev + gate_name suffice). B corrects: linked records
only count if VERIFICATION consumes them (existence, auth, digest
links, cross-identity agreement, tampered fixtures rejected); a
revision names intent, not execution — RETAIN actual argv (cheap).
RECONCILED: linked direction accepted (ExecutionReceipt stays frozen,
V8) + ALL of B's consumption checks become explicit preflight
assertions (add N6: tampered/substituted linked record MUST fail
verification) + record ACTUAL argv per run in the linked record
alongside contract_rev (B governs: what ran beats what varies).
"Five lines" claimed by neither side in this file.

### R-ED (editorials E1–E4 — all accepted with B's upgrade)

E1 trap rationale: rewrite on coverage grounds (explicit kwarg
precedence verified: `runner.py:212-215` beats the trap when callers
pass bools, which both production sites do) + invariant as code
comment at the trap AND call sites (A) + a small BEHAVIORAL check at
the execution boundary proving safeguard selection survives the
production call path (B — behavior test, never AST assertions).
E2 A1-mirror line, E3 per-merge-evaluation qualification, E4 intake
re-hash (≈`--locked` semantics on the baseline manifest, ~10 lines):
accepted as specified.

## Redline list (exact amendments to WALKTHROUGH/RATIFICATION pre-signing)

- D-α §5.5 rewrite → R-ENV (floor + fingerprint + requalification
  policy + `uv sync --locked` construction). §5.5 as drafted MUST NOT
  sign (pin + new-identity-on-any-change + pip venv).
- D-β §5.3/T2: primary-lease checkout rule (R-HEAD).
- D-γ T6/dossier: diff-binding definition + bundle durability (R-DIFF).
- D-δ §5.4: full-manifest tripwire + detection-only scope (R-TRIP).
- D-ε §5.2: exact mandatory IDs + versioned config + count tripwire,
  missing-fails-closed (R-SEL).
- D-ζ dossier/receipts: linked CustodyIntake + SelectionRecord with
  consumption checks + actual argv + N6 tamper control (R-LINK).
- E1–E4 as specified above.
Untouched: S5-1, S5-2, S5-3, §5.1, A1 body, D1 (vehicle ADR-INT-02).

## Final-authorization skeleton (next session finalizes; NOT approved)

One coherent authorization (per B: no competing descriptions): scope =
D-α…D-ζ + E1–E4 implemented; installation = `uv sync --locked` box per
R-ENV (stop if interpreter/inputs unavailable); env acceptance =
checklist (floor ✓, tools ✓, fingerprint recorded, F4 passes, Gates
1–2 green on pinned baseline) with pre-approval iff exact-pass and
explicit re-approval on ANY deviation; acceptance = P1–P3 green +
N1–N6 required polarity + chain + N5 identity + selection-record
validity; stops = wrong polarity, HMAC/auth failure, N5 delta,
foreign-path write, floor/tool violation, any live-call attempt
(hard abort), CLI cap; accounting = 0 live gateway calls (hard),
≤6 model-backed CLI sessions (V9 wording — local deterministic
commands uncounted but logged), 6-call verification reserve untouched,
cap-hit stops with a report.

## Open decisions for operator/Sovereign (in the authorization, nowhere else)

1. D-α: floor + F4-test amendment (recommended) vs narrow-to-3.12.x.
2. Detection-only externals accepted explicitly (R-TRIP residual risk).
3. Linked-record field list + N6 (R-LINK/R-DIFF details as drafted).
4. Vehicle confirmed ADR-INT-02 (recommended, D1 unchanged).

## Prompts

### P1 — next-session bootstrap (paste first)

```text
STC integration design tranche, post-verdict. Read, in order:
stc/docs/builds/stc-integration/evidence/FOLLOWUP/design-tranche/HANDOFF-NEXT.md
(verdict synthesis — your instructions), then PLAN.md, WALKTHROUGH.md,
RATIFICATION.md (same dir), then STATE.md. Cold re-probe before any other
work: HEAD==ea1ca30, 28/28 loose hashes (manifest in
/tmp/loose-manifest.sha256 if present, else debt-fix verify-1 REVIEW.md
Identity block), pins sst 079f4de6/prompt-kit 4f442a6c/trace a24a9370,
sst clean, numstat 1114+/14- on the 10 tracked product files. Report
PASS/FAIL with counts. Then await P2. Records-only until the
authorization below is approved: no product edits, installs, or live calls.
```

### P2 — reconcile, redline, authorize (paste after P1 passes)

```text
Using HANDOFF-NEXT.md reconciled positions R-ENV/R-HEAD/R-DIFF/R-TRIP/
R-SEL/R-LINK/R-ED as binding: (1) apply redlines D-α…D-ζ + E1–E4 to
WALKTHROUGH.md and RATIFICATION.md (records-only edits, exact text —
flag any redline you cannot apply cleanly instead of improvising);
(2) draft the ONE final coherent implementation/preflight authorization
(scope, installation, env-acceptance checklist + gate, P1–P3/N1–N6
acceptance, stop conditions, call accounting per the skeleton) with the
four open decisions called out for operator ruling; (3) re-run the
honesty audit (zero readiness claims) and the no-drift guard. STOP and
present the redlined deltas + authorization for approval. No
implementation, installs, or live calls under this prompt.
```

## Hygiene note

This session is closed; do not return to it. Its context held the full
plan, both drafts, the review, and both verdicts — everything durable
is now in design-tranche/ + STATE.md. Next session starts cold per P1.
