# STC Integration — Design review (A3)

Date: 2026-09-13. Scope reviewed: contract INT-2026-09-13.1 (all plan files)
against STC/SST/prompt-kit sources at pinned checkouts.
Reviewers: 3 red teams + 1 blue team (parallel subagent audits, 64 findings),
adjudicated by the planning agent with independent source verification.
Conclusion: **REVISE** — executed in this pass; contract re-issued as
INT-2026-09-13.2. Scope actually reviewed: full M1 tranche + governing kit.

Conventions: dispositions are FIXED (.2 location) / ACCEPTED (recorded limit) /
DEFERRED (post-M1 + trigger) / OPERATOR (decided by user).
Dedup: BT-01=RT-01, BT-03=RT-07, BT-05=F7(R2), BT-19b=F1b — disposed once.

## BLOCKS_EXECUTION (12 unique) — all FIXED or OPERATOR-decided

| ID | Finding | Disposition |
| --- | --- | --- |
| F1a (R1) | Bundle↔packet "lossless ==" unachievable (correlation_id/compiled_at + 8 dropped fields regenerate) | FIXED: P01 acceptance is now named-field projection equality + per-field disposition table; "lossless" claim removed |
| F1b (R1) | Inverse signature contradicts call site (phantom ctx) | FIXED: `task_packet_to_bundle(packet, ctx)` with typed `AdapterContext`; ctx-recovered fields labeled non-round-tripped |
| F1c (R1) | Blanket-raise vs by-design drops dilemma | FIXED: blanket-raise replaced by the disposition table; raise only on undisposed fields |
| F2a (R1) | No NOT-RUN state; deferred mutmut bit-identical to pass | FIXED: deferred reports fingerprinted (exit-0 + duration-0.0 + snippet class); per-node hard_gates OMIT the mutmut key with documented vocabulary |
| F2b (R1) | hard_gates write-only; search runs on reward+verdict which P01 never maps | FIXED: P01 now defines coarse deterministic reward (hard-gate fraction) + verdict rule; acceptance re-pointed at champion/frontier behavior. Verified: controller.py:96 (-1.0 init), :265-270 selection on reward |
| F3a (R1) | P00 status-text digest is content-blind; contradicts ARCH identity formula | FIXED: single formula — HEAD + `git diff HEAD` bytes + untracked hashes + env digests; P00 rewritten |
| F1 (R2) | Confinement watches 2 dirs only; /tmp, $HOME, siblings unwatched | FIXED: claims narrowed to monitored dirs (tripwire, not sandbox); quarantine-via-wrapper; OS-sandbox DEFERRED post-M1. Verified: dispatch.py:83-134 |
| F7 (R2) | `lease_root` ctx key ignored; agent runs in coordinator cwd | FIXED: `project_root=str(lease_root)` mandated + cwd assertion test. Verified: account_harness.py:504,564 |
| RT-01 | Controller+evaluator seam does not exist (mutually exclusive stacks) | FIXED: A2 seam choice — controller stack + STC-side `verify_candidate_proposal` wrapper (D7-legal, no SST edits). Verified: controller.py:36-52,190,342; zero EvaluatorProtocol consumers |
| RT-02 | HarnessWorker has no socket in either SST entry point | FIXED: worker socket is a prompt-kit-harness-backed ModelGateway backend (new P03/P04 scope); fixes BT-04 jointly |
| RT-07 | P05 `compile` collides with existing command | OPERATOR: extend existing `run SPEC_PATH` instead (verified run composes lease→worker→gates, cli.py:994). P05 rewritten |
| BT-02 | P00 push of sst/prompt-kit contradicts read-only auth | FIXED: P00 commits+pushes STC only; read-only identities for sst/prompt-kit/trace; trace-lite ABSENT per operator (BT-09) |

## MAJOR — red 1 (adapters/identity)

| ID | Finding | Disposition |
| --- | --- | --- |
| F1d | Merge irreversible; forbidden_paths denylist dropped (scope widening) | FIXED: merge/split escaping specified; denylist enforced at lease-allocation (P04), tested |
| F2c | Two hard_gates vocabularies, no shared contract | FIXED: P01 mandates native `verifier_passed` key + `stc_*` extension keys; P04 bound to it. Verified native producer controller.py:720,735 |
| F2d | ctx unschemaed yet safety-critical | FIXED: typed `AdapterContext` + non-empty acceptance validation in P01 |
| F3b | Ignored inputs (venv/interpreter) invisible to identity | FIXED: pip-freeze digest + python/OS in identity table; fixed glob list replaces "relevant" judgment |
| F3c | No 3-repo digest composition; wrong-tree pin risk (prompt-kit/ vs trace/docs/prompt-kit/) | FIXED: 5-path pin table (stc, sst, prompt-kit PKG, trace KIT, + TL absent-note); JSON map composition; import path asserted in P03 B1 |
| F3d | snapshot_hash/prompt_template_hash never wired | FIXED: forward mapping assigns snapshot_hash ← candidate_identity; template hash records adapter version |
| F4a | P01∥P02 both create `__init__.py` — parallel claim false | FIXED: tranche serialized (P01→P02); parallelism dropped per D6 quality focus. Kills BT-15 jointly |

## MAJOR — red 2 (memory/worker)

| ID | Finding | Disposition |
| --- | --- | --- |
| F2 | .git excluded from snapshots (hooks/refs/worktrees mutable, undetected); CLIChaperoneWorker is the real pipeline class | FIXED: hash-snapshot .git/{refs,hooks,config,worktrees}; P03 names CLIChaperoneWorker as composed base. Verified cli.py:869-883,1144 |
| F3 | mtime-equality miss (utime reset, coarse FS, dir-create-delete) | FIXED: (mtime_ns,size) + flag-on-size-change; residual TOCTOU ACCEPTED as recorded limit |
| F4 | Outer suppress() aborts audit loop on first walk error | FIXED: remove outer suppress; collect errors; fail closed on any error |
| F5 | "Preserved as evidence" false — rogue files unlinked before raise | FIXED: move-to-quarantine + bytes/hashes into violation record instead of unlink |
| F6 | ChaperoneWorker never quarantines; P04 path has no quarantiner | FIXED: HarnessWorker wrapper owns quarantine call; breach test asserts .quarantined.json |
| F8 | worker_fn has no timeout; is_success unchecked → partial attested as success | FIXED: dispatch-level timeout + mandatory is_success raise in harness_worker_fn |
| F9 | Citation loss ([:100] cut, silent prune) + [Trace]→invariant promotion contradicts "index, never decide"; no freshness | FIXED: `[source:path]`-first convention + renderer preservation test + HEAD/as-of stamps on entries. Verified bundler.py:126,256-276 |
| F10 | Membrane threading unspecified; [] passes vacuously; symlink stubs spoof | FIXED: membrane files as __init__ param, non-empty required, content-marker checks; spoof + real-shape tests. Protocol signature untouched (init-level config) |
| F11 | Spend log integrity + R10 unenforced + API/command-smuggling via registry | FIXED: try/finally per-subprocess rows; pre-dispatch cap check; CLI-only harness allowlist; {prompt}/command templates forbidden; log outside leases append-only |
| F12 | Mock/live divergence; "skips honestly" contradicts ARCH READY gate | FIXED: live test required for READY (skip only in declared degraded-manual mode); live checklist in acceptance; ARCH contradiction removed |
| F13 | "*" match-all parity unspecified; literal impl drops all general inhibitors | FIXED: "*"/empty = match-all + parity test vs TraceClient. Verified trace_client.py:270-280, bundler.py:238-249 |

## MAJOR — red 3 (runner/acceptance)

| ID | Finding | Disposition |
| --- | --- | --- |
| RT-03 | Per-node fail-closed has no D7-clean mechanism; event-scrape is fragile | FIXED: restated as champion-veto with named mechanism + garbage-critique experiment; subclass D7-exception DEFERRED (trigger: veto proves insufficient) |
| RT-04 | Lease-per-evaluate lifecycle/concurrency; test_command ignored; receipt→score caller unnamed | FIXED: one lease per node-id + release policy; test_command declared ignored; caller named (runner maps receipt→score). Concurrency experiment kept in P04 |
| RT-05 | Mutmut-once uncountable; pytest auto-disable trap; retry scope undefined | FIXED: counting rule (duration>0 ∧ snippet class) + pytest_target forbidden in that test + retry policy + post-merge receipt. Verified runner.py:212-220,615-621 |
| RT-06 | Winner-take-all contradicts built-in colimit synthesis; silent partial-loss | FIXED: synthesis embraced — synthesis receipt defined; loss-ledger for collapsed partials. Verified controller.py:273-393, policy.py temperatures-only |
| RT-08 | Dry-run counter misses gateway + codex paths (2 of 3) | FIXED: composite counter (gateway.invoke wrap + harness.execute wrap + with_codex=False assert). Verified 3rd path auditor.py:106-155, default False |
| RT-09 | Escalation criterion gameable; SST escalation fire-and-forget | FIXED: chain criterion — real ambiguity ≥τ → recorded choice → locked invariant → branch effect in Q&A log |
| RT-10 | No-champion type must be invented; P05 contradicts itself on artifacts | FIXED: `NoChampionResult` named in P04; P05 partial-dossier criterion added. Verified bare-None controller.py:58,412 |

## MAJOR — blue (compliance/cross-cutting)

| ID | Finding | Disposition |
| --- | --- | --- |
| BT-04 | ModelGateway channel unowned/unbudgeted/API-implicated; no CLI backend | FIXED jointly with RT-02: CLI-backed gateway backend in scope; gateway calls counted in budgets + spend log |
| BT-06 | A3 skipped; A4 self-checks show no evidence | FIXED: this document is the A3; contract re-issued .2 before Wave 0 |
| BT-07 | No B5 launch; builder-authored B5 record violates separation | FIXED: B5 record removed from P05 scope; exact post-VERIFIED B5/coordinator launch added to EXECUTION.md |
| BT-08 | Honest-skip vs code-enforced zero-skip Gate 3 | FIXED: `@pytest.mark.live` opt-in policy, deselected in gate runs. Verified runner.py:457-460 |
| BT-09 | TL writes required but unauthorized | OPERATOR: trace-lite ABSENT from M1 (not read, not written); P05 self-hosted on STC; LLM+shim is the TRACE substitute. R3 amended |
| BT-10 | recommended/PARKED/degraded/terminal semantics undefined | FIXED: dispositions defined per packet; honest-partial terminal stop added; exhaustion options enumerated; A2-revisit session pre-authorized |
| BT-11 | Unowned seams: inhibitor wiring, bundle→packet call site, deferred __init__, membrane_files dep | FIXED: (a)+(b) assigned to P04; (c) dropped (serialization kills deferral); (d) declared in P05 inputs |
| BT-12 | STATE spend rows unmaintainable; two writers | FIXED: every packet emits spend record (zeros ok); budget table in STATE; builders report, coordinator writes |
| BT-13 | P01 B1 lacks contract-shape re-verification | FIXED: P01 B1 asserts live SST field sets match mapping tables |
| BT-14 | normalized_reward undefined (degenerates MCTS) | FIXED jointly with F2b: coarse deterministic derivation in P01 contract |
| BT-15 | P01∥P02 isolation unspecified; installs unauthorized | FIXED: serialized; shared venv established read-only in P00; installs pre-authorized nowhere (B1 must use existing env) |
| BT-16 | Pin set incomplete (kit + STC-base moves unpinned) | FIXED: 5-path pin table + extended re-readiness rule |
| BT-17 | P04 implements amendment while ADR only "recommended" | FIXED: ADR-INT-01 authorship moved to P00 (ratification already happened at grill) |

## MINOR (batched) — all FIXED

- F1e: proposal→filetargets unspecified → inference rules specified in P01 (patch_diff hunk headers primary; op-dicts validated, unknown ops raise).
- F4b/F4c: LAYOUT-note ownership + rollback blast radius → moot under serialization; rollback narrowed to owned filenames regardless.
- F14: case-alias/hardlink experiment → kept as bounded P03 experiment, non-blocking (U5).
- F15: transient create-exfiltrate-delete → folded into F1/F3 fix acceptance.
- RT-11: store/tree-id unnamed → DialecticRunner owns store under evidence/P04, generates tree_id, preserves DB.
- RT-12: lease mapping unconstrained → candidate-suffixed task-id + release/quarantine policy (covered by RT-04 experiment).
- BT-18: wrong source paths (missing src/) → mechanical correction pass applied to all packets.
- BT-19: signature contradictions → ctx param added; baseline_metrics renamed.
- BT-20: revision unnamed in boot, session miscount, repair-session rule, R10 overrides → each corrected (count recomputed 1+6+6+1 B5 = 14 with B5 dedicated).
- BT-21: async bridging, store path, vacuous persistence claim → B1 notes + store path fixed; claim dropped.

## Positive findings retained

- Proposal-returning `execute_search` exists and never writes source (custody uses tempfile dirs).
- task_id/goal mapping, custody single-command characterization accurate.
- PACKET.md section structure complete on all six packets; coordinator boot 7-step compliant by reference.
- Shared-file edit claims hold (P03 dispatch.py hunk source-compatible; P04 transitively imports only).
- Socratic/memory paths model-free → dry-run purity achievable.

## Unresolved (carried, non-blocking)

- U-F1e/U-F2d: closed by dispositions above (rules specified).
- U-conftest: moot under serialization (single builder at a time; coordinator orders fixture edits).
- Blue U1 (TL auth intent): closed by operator (absent).
- Blue U2 (run_cmd composition): closed by operator (extend run).
- Blue U3 (live-harness availability): properly left to P03 B1 handshake.
- Q1 (CLI caps): R10 defaults apply until operator sets.
- F14 experiment + RT-04 concurrency experiment: run in P03/P04 B1/B2, non-blocking.

## A3 conclusion

REVISE executed. All 12 BLOCKS resolved (10 FIXED, 2 OPERATOR-decided with
compatible fixes). All 38 MAJORs disposed. All 14 MINORs fixed. No finding
left without a disposition. Contract INT-2026-09-13.2 re-issued; Wave 0
may proceed when the operator says go.
