# Ratification packet (DRAFT — for contract review, not ratified)

Redline rev: D-α…D-ζ + E1–E4 applied per HANDOFF-NEXT.md
(R-ENV/R-HEAD/R-DIFF/R-TRIP/R-SEL/R-LINK/R-ED); reconstruction flags
carried in AUTHORIZATION.md. Still DRAFT — nothing here is ratified.

Packet for: `01_INVARIANTS.md` §5 amendment + ADR-INT-01 amendment +
new D-rules D-CT1–D-CT7 (proposed vehicle: new ADR-INT-02; rationale
below). Approval basis: rev-2 focused-session approval (Q1 Yes genuine
isolation / Q2 Yes STC-owned 3.12 preferred, no install / Q3 keep
12-incl-6, topology-derived cap later) + the three in-session details.
Companion: `WALKTHROUGH.md` (same dir) — the walkthrough is the
normative prose; this packet is the exact text surgery. No-waiver rule:
rejected text returns to draft or to honest NOT-READY — never to waiver;
any waiver/downgrade/carve-out needs its own explicit approval.

## Delta S5-1 — Gate-2 argv (correct the text to the implementation)

CURRENT (`01_INVARIANTS.md:91`):

> | **Gate 2: Static Type Soundness** | Mypy | `uv run mypy --strict src/` | Exit Code == 0 (0 type errors, 0 Any leaks) |

PROPOSED:

> | **Gate 2: Static Type Soundness** | Mypy | `mypy --strict src tests` (src-or-dot when `src/` absent; `tests/` appended when present) | Exit Code == 0 (0 type errors, 0 Any leaks) |

Ground: the implementation appends both dirs when present
(`runner.py:363-369`), and ALL evidence ran `src tests` (close-out
`gates-real-tree.log` byte `00e27712…`). The rejected alternative —
narrowing the implementation to §5-literal `mypy src` — would un-gate
15 test-file errors and contradict every evidence log.

## Delta S5-2 — Gate-3 argv (correct the text to the implementation + D13)

CURRENT (`01_INVARIANTS.md:92`):

> | **Gate 3: Deterministic Test Suite** | Pytest | `uv run pytest -v --tb=short` | Exit Code == 0 (100% pass, 0 failed, 0 skipped) |

PROPOSED:

> | **Gate 3: Deterministic Test Suite** | Pytest | `pytest -v --tb=short -m "not live"` (+ `pytest_target` scoping per §5.1–§5.2) | Exit Code == 0 (100% pass, 0 failed, 0 skipped; live-marked deselected per D13) |

Ground: code runs `-m "not live"` with optional target
(`runner.py:430-432`); ADR-INT-01:31 records the D13 deselect; the
0-skipped invariant is UNCHANGED (D-CT4: no manifest, no carve-out).

## Delta S5-3 — Invocation clarification (bundled, minor)

§5 commands are written `uv run <tool>`; the substrate executes
`<authoritative-interp> -m <tool>` (`runner.py:291-292,363,430,635`).
PROPOSED §5 note (one sentence, appended to the §5 table caption):

> Gate commands resolve to the authoritative environment's interpreter;
> `uv run` is satisfied wherever it selects that interpreter.

This changes no behavior; it records what every evidence log already
shows. Disposition together with S5-1/S5-2 (no separate exchange).

## Delta S5-4 — New §5 subsections (the redesigned contract)

PROPOSED §5.1 — Evaluation cadences (three classes; D-CT1/D-CT5):

> Baseline checks run whole-tree Gates 1–3 once per
> `(base_commit, baseline_content_digest, env_digest, gate_argv)` and
> their receipt is reused as immutable input. Per-node candidate checks
> run Gates 1–2 whole-tree and Gate-3 candidate-scoped per §5.2, fresh
> per candidate; candidate evidence is never reused across candidates.
> Integration checks run whole-tree Gates 1–3 unscoped plus Gate-4
> exactly once at champion/merge cadence, re-run on every merge.
> Whole-tree interaction coverage moved cadence; it was not deleted.

PROPOSED §5.2 — Trusted test selection (D-CT5 + approval correction):

> Affected coverage is computed by trusted orchestration from candidate
> bytes through the versioned owning-suite map; the mandatory set
> always runs, frozen in ONE versioned selection-config data file
> (config revision + exact node IDs + M3 file paths with per-file node
> counts + owning-suite map revision): M1
> `tests/unit/test_integration_identity.py::test_record_shape_and_env_keys`
> (node-level); M2
> `tests/unit/test_integration_harness_worker.py::test_f3c_prompt_kit_import_resolves_to_pinned_tree`
> + `...::test_fix_shape_gateway_prompt_preserves_real_diverge_bytes`
> (node-level); M3 `tests/unit/test_a3_patch_format.py` +
> `tests/unit/test_gateway_marker_refusal.py` (file-level, both files
> whole; per-file node counts pinned as a tripwire — count change =
> finding). Missing files or node IDs fail closed. Unresolvable paths
> broaden scope, never narrow it; plausibly-affected-but-unrun tests
> are named with reasons in the signed per-node SelectionRecord;
> generated proposals may suggest additional tests and may satisfy
> none — a suggested test never displaces mandatory or affected
> coverage. The SelectionRecord carries the mandatory-set digest
> (bound to the selection-config revision), affected-computation
> inputs, broadenings, the safeguard declaration, and the ACTUAL gate
> argv executed alongside `contract_rev`. Verification MUST consume
> the SelectionRecord (existence, signature auth, digest links,
> cross-identity agreement; tampered/substituted records MUST fail
> verification — preflight N6).
> Safeguard coverage is decided by the production call sites, which
> pass explicit `run_mutmut` bools (precedence per
> `runner.py:212-215`; the `runner.py:212-219` trap takes effect ONLY
> without an explicit kwarg): per-node runs declare safeguards
> `[ruff, mypy, scoped-pytest]` with mutmut excluded by ADR-INT-01;
> merge runs forbid `pytest_target` so the safeguard set stays
> whole-tree + mutmut by construction. The precedence invariant is
> recorded as a code comment at the trap AND call sites, and a
> behavioral check at the execution boundary proves safeguard
> selection survives the production call path (behavioral assertions,
> never AST). Dropped safeguards are explicit, named, and separately
> approved.

PROPOSED §5.3 — Candidate identity and scratch-ref protocol (D-CT1/D-CT2):

> Every evaluated byte is bound to `candidate_content_digest` (scratch
> ref SHA + untracked-input manifest + normalized diff) with the
> baseline receipt referenced, never merged: the baseline receipt binds
> `baseline_content_digest` under
> `(base_commit, baseline_content_digest, env_digest, gate_argv)`.
> Custody opens the signed CustodyIntake linked record
> (`candidate_id`, `base_commit` ref, scratch-ref SHA,
> `candidate_content_digest`, baseline receipt ref, target
> `env_digest`); intake checks apply-clean + tree-hash equality AND
> re-hashes the baseline manifest (`--locked` semantics — drift fails
> closed, re-pin T0, never proceed). The lease mirror excludes the
> FOLLOWUP-a1-fix dst-subtree (the lease never mirrors its own
> destination path; NOT Delta A1).
> Integration-cadence E2E leases branch from a candidate-inclusive
> scratch ref (`refs/scratch/<candidate_id>`) committed in the lease's
> disposable git, never `main`. Ref propagation AND head assert are
> BOTH required on EVERY lease: primary leases check out the scratch
> ref at intake and assert `HEAD == SHA` at gate time; nested leases
> receive the exact `(lease_git_path, scratch_ref_SHA)` pair,
> materialize that SHA, and assert `HEAD == SHA` before running.
> Safety never depends on the `main` default: silent fallback to
> `main` fails closed, and every branch point is re-specified.
> Verification MUST consume the CustodyIntake (existence, signature
> auth, digest links, cross-identity agreement with the gate
> receipts; tampered/substituted records MUST fail verification —
> preflight N6). Lease git isolation is by construction — sanitized
> mirror copies (remotes removed, copied worktree admin dropped),
> independent clones for scratch-ref leases, no `worktree add`
> against the original repository, whole-delete cleanup — and is
> proven per run by original-repo ref/worktree identity before and
> after. Push controls are not cited as isolation evidence.

PROPOSED §5.4 — Lease external-dependency discipline (D-CT2):

> Leases are self-contained; the only external reachability is the
> closed pinned read-only set (prompt-kit pin, trace prompt-kit path
> pin, sst read-only API surface — additions are contract amendments).
> Tests resolve the workspace via `STC_WORKSPACE_ROOT` when set, else
> the legacy inference for real-tree runs only. Before gates, each
> lease proves import integrity: `stc.__file__` under the lease,
> lease-first `sys.path` order, pinned externals spot-hashed. Any other
> reachability through the override is a finding; a lease failing the
> proof fails closed.
> Each lease ALSO carries a full-manifest tripwire: every enumerated
> file hashed at lease open, pre-gates, and close; content deltas and
> additions/deletions fail the run. The guarantee is
> detection-with-fail-closed, never "read-only" (chmod prevention is
> dropped as theater on Windows/OneDrive): persistent change ⇒ run
> fails; transient write-then-restore inside one hash interval is a
> RESIDUAL RISK accepted explicitly by the authorization. Prevention
> awaits container read-only mounts (future, not built).

PROPOSED §5.5 — Authoritative environment: floor, fingerprint, requalification (D-CT3):

> COMPATIBILITY (floor): the product supports Python ≥3.12 with
> ruff/mypy/pytest/mutmut present + app deps installed. Fail closed
> ONLY on floor violation or missing tool. (RULED D-α, operator
> 2026-09-19: FLOOR + amend the F4 test to a `>= (3, 12)` check as
> implementation scope; narrow-the-contract-to-3.12.x REJECTED.)
> The floor establishes eligibility only: each actual env is
> qualified individually — no blanket certification of future
> releases.
> PROVENANCE (fingerprint): every check records its EXACT env
> fingerprint (`env_digest`: interpreter string, tool `--version`s,
> lockfile content hash, `os_platform`). Patch drift is a different
> fingerprint, recorded always — never a silent same.
> REUSE (requalification policy): same (major, minor) + same
> tools-present set + same lockfile content hash ⇒ the ENV side
> requalifies; reuse ALSO requires the full T0 key match
> (`base_commit`, `baseline_content_digest`, `gate_argv`) — the
> lockfile content hash records dependency intent and is necessary,
> NEVER sufficient by itself. ANY lockfile content change or
> minor-version change ⇒ requalify the baseline (re-run T0).
> Windows↔Linux results comparable with separate identities each.
> CONSTRUCTION: STC `pyproject.toml` + `uv.lock` via
> `uv sync --locked` (full gate toolchain, no additions). No pip venv
> (split-brain), no TRACE-owned env. If the 3.12 interpreter or sync
> inputs are unavailable: stop, report, no fallback.
> Python 3.11 legs are advisory only and never receipted as
> authoritative.

PROPOSED §5.6 — Merge binding and evidence durability (NEW subsection, D-γ):

> The merged diff is bound EXACTLY: base = the merge lease's baseline
> tree (`base_commit` tree + baseline manifest); result = the merge
> scratch-ref tree; policy =
> `git diff --no-ext-diff --unified=3 <base> <result>` with default
> whitespace handling (NO ignore-whitespace). One shared
> `normalize_diff()` helper, used at render AND audit, canonicalizes
> transport only (LF endings, trailing newline at EOF, exact hunk
> headers) — it MUST NOT reorder hunks or touch in-line whitespace.
> Base + policy are frozen by this redline. The auditor recomputes
> the diff from the merge scratch ref: live path passes `merged_dir`
> to `_audit` (live-against-rendered now); evidence path stores a
> `git bundle` of the scratch ref + the rendered diff bytes in the
> evidence dir (bundle-against-rendered later — verification survives
> lease deletion forever). Mismatch fails closed either way.
> Binding is established by the verified receipt-and-linked-record
> ensemble, not the receipt alone. The linked merge record pins
> exactly (`merge_scratch_ref`, `selection_outcome_ref`,
> `env_digest`, `merged_diff_sha256`) — not the frozen
> ExecutionReceipt; the mutmut disposition rides `ChampionResult`.
> The dossier is HMAC'd over the digest list of the linked
> CustodyIntake + per-node SelectionRecords + selection-outcome
> record + merge record.

## Delta A1 — ADR-INT-01 amendment (per-node scoping + integration cadence)

CURRENT (`ADR-INT-01.md:28-34`): per-node Gates 1–3 with Gate-3 as the
full deterministic suite; Gate-4 champion-only.

PROPOSED amendment (appended section "Amendment A1 — scoped per-node
Gate-3 (date of ratification)"):

> Per-node Gate-3 runs candidate-scoped per §5.2 (mandatory +
> orchestrator-computed affected + broadenings + suggested additions),
> still with `-m "not live"` and 0 skipped. The full-suite Gate-3
> including the committed-E2E tests runs at champion/merge cadence per
> §5.1/§5.3 (unscoped, scratch-ref-propagated). Gate-4 remains
> champion-only, exactly once, kill rate ≥ 85%; the reversion condition
> is unchanged and now ALSO triggers if scoped per-node selection is
> shown to let mock-gaming suites reach champion routinely.

D13 (live deselect, ADR-INT-01:31) is unchanged. Note: D13's operative
text lives ONLY in ADR-INT-01 — `DESIGN_REVIEW.md` was found to contain
no D9–D15 rule text (grep 2026-09-19; the file holds RT-row review
notes). No D13 edit is proposed or needed.

## Delta D1 — New D-rules D-CT1–D-CT7 (recording vehicle)

The seven contract decisions (three-class split + scratch-ref protocol;
lease-aware resolution + import proof; floor + fingerprint +
requalification; absolute 0-skipped; cadence/evidence-reuse + trusted
selection; §5 text correction; sequencing gate) are recorded VERBATIM
as decided at ratification. RULED VEHICLE (operator 2026-09-19): new
`ADR-INT-02` (integration lease/gate contract), because the putative
register (`DESIGN_REVIEW.md`) holds no D-rule text today and grafting
seven rules onto review notes invites the same text/code split this
packet closes. (The DESIGN_REVIEW-append alternative was available at
draft; the operator confirmed ADR-INT-02.)

## Disposition table (for the contract-review discussion)

| ID | Text | Disposition | Routing on reject |
| --- | --- | --- | --- |
| S5-1 | Gate-2 `src tests` | Approve / Revise / Reject | Re-discuss or honest NOT-READY (no-waiver) |
| S5-2 | Gate-3 `-m "not live"` + scoping | Approve / Revise / Reject | Same |
| S5-3 | Invocation note | Bundled with S5-1/S5-2 | Same |
| S5-4 §5.1 | Cadences | Approve / Revise / Reject | Same |
| S5-4 §5.2 | Trusted selection (exact M1–M3 IDs + versioned config + count tripwire) + SelectionRecord + actual argv + E1 coverage rule | Approve / amend list / Reject | Same; list amendment needs no re-draft of the rule |
| S5-4 §5.3 | Identity + scratch-ref + propagation-and-assert + CustodyIntake + intake re-hash + a1-fix mirror line | Approve / Revise / Reject | Same; `main`-fallback variant is NOT an available revision (F3-impossible, proven) |
| S5-4 §5.4 | Lease-dep discipline + import proof + full-manifest tripwire (detection-only) | Approve / Revise / Reject | Same |
| S5-4 §5.5 | Floor + fingerprint + requalification + `uv sync --locked` construction (D-α RULED floor; narrow REJECTED) | Approve / Revise / Reject | Same; 3.11-primary needs its own downgrade amendment, never a fallback |
| S5-4 §5.6 | Merge binding (base/policy frozen) + bundle durability + linked merge record (NEW) | Approve / Revise / Reject | Same |
| A1 | ADR-INT-01 scoping amendment | Approve / Revise / Reject | Same |
| D1 | D-CT1–D-CT7 text + vehicle (RULED ADR-INT-02) | Approve / Revise / Reject | Same |

## Post-approval preflight SPEC (specified here, executed later — never in this session)

Runs AFTER the dispositions are implemented, on the PRODUCTION pipeline
(real call path, implemented code — spec simulation is not preflight).
Zero live calls (Q3). All legs sequential; outputs staged in `/tmp`,
copied to evidence/ only after completion.

- P1 Green actual-path per-node run: one candidate through
  creation→custody→scoped-gates on the real path; assert exit-0,
  0 skipped, HMACs verify, SelectionRecord valid per §5.2
  (mandatory-set digest binds the config revision; actual argv
  recorded; safeguard declaration matches observed gate execution —
  the E1 behavioral proof rides this assertion), CustodyIntake
  consumption checks pass.
- P2 Green actual-path integration run: same candidate through
  selection→merge→judiciary→dossier; assert E2E tests evaluated the
  scratch-ref bytes (byte-identity proof), mutmut counted-once per
  merge evaluation, 0 skipped, chain resolves unbroken,
  live-against-rendered AND bundle-against-rendered diff checks pass.
- P3 Dry-run + collect: `--collect-only` bare and `-m "not live"`
  counts recorded (baseline: 533 bare / 527 + 6 per close-out logs);
  any delta owned and explained.
- N1 (negative — scoping load-bearing): per-node Gate-3 UNSCOPED on a
  tree with F3-active E2E MUST FAIL with the committed-bytes signature
  (proves scoping removes a real block, not a phantom).
- N2 (negative — ref propagation load-bearing): integration run with
  the scratch ref OMITTED (branch from `main`) MUST evaluate `main`
  bytes and fail the candidate assertion (proves the E2E verdict comes
  from the ref, not the machinery).
- N3 (negative — override load-bearing): the two F2-named tests in a
  lease WITHOUT the override MUST skip (original symptom); WITH the
  override MUST run with 0 skips (proves the override, not luck).
- N4 (negative — env binding load-bearing): the F4 assert under 3.11
  MUST fail and under the authoritative 3.12 MUST pass (proves the
  verdict binds the env).
- N5 (negative — isolation proof): original-repo ref advertisement +
  worktree list byte-identical before and after P1+P2 (proves no
  original mutation; ANY delta fails the preflight, not the run).
- N6 (negative — linked-record tamper control): a tampered or
  substituted CustodyIntake / SelectionRecord / selection-outcome
  record / merge record (bad signature, broken digest link,
  cross-identity mismatch against the gate receipts) MUST fail
  verification (proves the linked records are consumed, not
  decorative).
- ACCEPTANCE BAR: P1–P3 green + N1–N6 all showing the REQUIRED
  red/green polarity + receipt chain resolves unbroken + N5 identity
  byte-identical + SelectionRecord validity (config revision bound,
  actual argv recorded, safeguard declaration matches observed
  execution). A negative control showing the wrong polarity fails
  the preflight (the claim it guards is unproven). The readiness
  ruling is a SEPARATE decision on this evidence — this spec does
  not pre-rule it.

## Packet honesty block

- Every CURRENT quote above was transcribed from the file + line cited
  on 2026-09-19; verify by diff before ratifying.
- This packet contains zero readiness assertions and zero production
  predictions. It specifies WHAT will be true after implementation and
  HOW the preflight will check — it does not claim any of it now.
- Budget-box restatement (corrected, unchanged): 12 CLI remaining
  INCLUDING the protected 6-call verification reserve; $0 installs in
  this session; env construction post-approval under separate
  authorization.
