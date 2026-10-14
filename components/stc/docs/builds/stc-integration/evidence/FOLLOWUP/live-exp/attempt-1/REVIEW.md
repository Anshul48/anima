# FOLLOWUP live-exp — Builder delivery (attempt-1): WINNER P2-H3a

Record type: builder delivery
Author role and date: live-experiment-builder / 2026-09-14
Packet: STC follow-up tranche, live-experiment stage.
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (all 8 hashes re-verified byte-exact at start: F1-owned
`harness_worker ced79ed5…7867`, `cli_gateway f9dda17e…07b8a`,
`test_integration_harness_worker e96db8d0…70b45`; fix-owned `dialectic_runner
19a2e448…8283b`, `test_dialectic 6e059f08…f1019`, `__init__ 10571421…bac40`;
tracked `cli.py 33476f34…124bb` 576/0, `dispatch.py dc75c56e…13c7` 333/7;
HEAD move 4544190→edf5389 proven evidence-only). Pins: sst
`079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after every leg),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`.
Environment: joint `trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`, shims
present, no recreation); `PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`.
Zero competing processes at start; codex-cli `0.154.0`.

## Delivery section

- Behavior/artifact changed and why: NOTHING changed in product code — this
  stage is pure live experimentation. Result: **WINNER P2-H3a** — the FIRST
  H3 variation (reasoning `max`→`medium`, ZERO prompt-byte change) yielded a
  valid diverge proposal through the real confined gateway in 56.66 s.
  Experimenting STOPPED per the brief's WIN rule; H4/H1/H2 never ran (0 calls
  spent there). No SST/prompt-kit/trace edit (read-only throughout);
  `trace-lite/` never listed, read, or written. R1 stayed deferred (no
  blocking evidence).
- Files or outputs changed: evidence ONLY, all under
  `evidence/FOLLOWUP/live-exp/` (`readiness.md`, `attempt-1/` with driver
  copy, SST stage file, 3 probe dirs, `spend.jsonl`, this REVIEW). No STATE.md
  write; no commits; no tracked-file modification (see Identity).
- Material implementation decisions: hypothesis order H0→H3→H4→H1→H2 per B1
  (H3 first among variations: purest isolation — identical shaped bytes —
  and strongest hang-signature fit). H3's lever rides the existing
  scratch-CODEX_HOME seeding pattern (P05 precedent): the driver copies
  `auth.json` + `config.toml` and flips one line
  (`model_reasoning_effort`), so argv stays byte-identical confined and the
  header confesses the lever. A winning variant of this shape becomes a real
  STC-owned profile/config change at acceptance — proposed exactly below.
- Known limitations and checks not run: patch CORRECTNESS (whether the 4338 B
  diff verifies/greens) is NOT judged here — acceptance's job; only the §2
  parse contract was proven (with SST's own types). Single WIN observation
  (n=1; no replicate — the WIN rule stops experimenting). H4/H1/H2
  unexplored live (moot after the win, but their mechanisms are neither
  proven nor disproven). Worker-stage harnesses never reached live (same
  evidential boundary as M1/P05-fix).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Required full reads | read all 5 records in full | INSPECTION H0–H4 + §2 contract; F1 PASS gate; P05-fix live shapes; FIX-B5 NOT-READY baseline | predecessor records | Read, not re-executed |
| Candidate + drift gate | rev-parse, 8 full-sha recomputes, numstat, inter-HEAD diff stat | HEAD `edf5389`; 8/8 hashes exact; numstat 576/0 + 333/7; HEAD move evidence-only (zero non-`docs/builds/` paths) | this REVIEW; readiness Gates 1–2 | Hash-bound |
| B-small re-confirm (P0-H0a) | own driver `/tmp/liveexp-probe.py`: B1 string byte-exact, baseline frame, 120 s | OK 25.27 s, 662 B valid JSON (2 branches); shaped stdin `2eb53399…` = B1 disk bytes EXACT; header luna/max/read-only/scratch; confined 9/9; tracked identical; sst clean | `attempt-1/P0-H0a/` (22 files) | 1 CLI call; small-shape only |
| B-real short check (P1-H0b) | same driver: M1 4364 B verbatim, baseline frame, 150 s | SERVED TIMEOUT exit 124 @150 s, 0 B (hang reproduces past 60 s on current candidate); shaped `3339af29…` = diag bytes EXACT; stderr/exit hashes IDENTICAL to diag-retry placeholders (`7aa02fee…`/`ca2ebdf9…`); F1 sidecar 1 record; confined; sst clean | `attempt-1/P1-H0b/` (23 files) | 1 CLI call; H0-transient-only ruled out |
| **WINNER (P2-H3a)** | same driver + ONE lever: `model_reasoning_effort medium` in scratch config; bytes+argv+model identical; 180 s | **OK 56.66 s, 4996 B, `s2_branches_valid=true`**: JSON `{"branches":[...]}` (1 branch, `branch_index 0`, title `Custody Tripwire Matrix`, rationale present, `proposed_changes` 4338 B unified diff for `tests/unit/test_integration_runner_pins.py`, 191 lines, 3 pin tests with exact `merge-apply-failed` / `reselect-reconstruction-failed` / `RT-08`); header confesses `reasoning effort: medium` (leg NOT void); shaped `3339af29…` identical to baseline; argv confined 9/9 (no `--model` flag); tracked identical; sst clean; pins exact | `attempt-1/P2-H3a/` (23 files) | 1 CLI call; n=1; §2-parse win (correctness = acceptance) |
| §2 end-to-end proof (0 calls) | SST's own `_parse_json_dict` + `_clean_code` + `CandidateProposal` over P2 stdout bytes (controller.py:444-467 replay) | Valid `CandidateProposal` constructs: DIVERGE, title, rationale, target pins module, 4338-char `patch_diff`, `model_id` | this REVIEW (replay output quoted in session) | Parse contract only |
| Confinement (all 3 legs) | per-leg argv shape asserts + scratch-cwd assert + pre/post tracked+full + sst clean + header capture | 3/3 `confined:true` (9/9 checks); tracked IDENTICAL every leg (guard `d1edad82…` = FIX-B5 value); full deltas = own `live-exp/` writes only; sst clean 6/6; scratch homes verified deleted | per-probe `argv/cwd/status-*/sst-*` | Gateway legs only |
| One-lever discipline | EXPECT_SHAPED pins (P0 `2eb53399…`, P1/P2 `3339af29…`) + `stdin_matches_precomputed` + verbatim guards, all enforced pre-call | P0/P1/P2 all `stdin_matches_precomputed:true`; P2 prompt bytes bit-identical to P1 (only the config line differs) | `outcome.json`, `shaped-sha256.txt`, `config-toml.txt` | Driver-enforced |
| Sidecar diagnosis (F1) | per-probe `spend-ledger.failures.jsonl` | P1: 1 record (30-char timeout note; agent stderr unrecoverable by construction — served-hang, recorded not diagnosed); P0/P2 success → no sidecar (correct) | `attempt-1/P1-H0b/spend-ledger.failures.jsonl` | F1 working as VERIFIED |
| Spend | `spend.jsonl` row audit (1 row/probe) | **3 CLI calls / 14** (P0 ok, P1 timeout, P2 WIN); $0.00 metered; 6-call reserve NEVER touched; 11 experiment calls unspent | `attempt-1/spend.jsonl` (3 rows) | CLI-session budget only |
| Scope/hygiene | full/tracked status after last write; sst status; driver hash | tracked = exactly the 2 pre-existing mods; untracked = pre-existing loose set + `FOLLOWUP/`; sst clean; `/tmp` driver == preserved copy (`136a054e…`); no product edits; no commits; no STATE.md | git output; Identity block | Tree left + this record |

## Diagnosis (what the evidence establishes)

- **H3 CONFIRMED as the hang breaker (n=1, clean isolation).** Identical 5044 B
  shaped stdin hangs served at reasoning-max (P1 @150 s; plus B2/retry @280 s
  history) and emits a valid §2 proposal at reasoning-medium in 56.66 s (P2).
  The only differing byte in the universe of the two legs is the scratch
  config's `model_reasoning_effort` line (proven by `config-toml.txt` pair +
  header pair `max` vs `medium` + identical `prompt.txt` hashes). Mechanism
  (inferred, consistent): at `max`, gpt-5.6-luna spends the whole budget in
  unobserved reasoning (`reasoning summaries: none`) over the enormous
  single-artifact demand and never converges to emission; at `medium` it
  emits. H0-transient-only is ruled out (P0 fast-ok vs P1 served-hang back
  to back); H4/H1/H2 are MOOT for the win (unprobed, undisproven).
- **No SST contract change is indicated.** The SST §2 contract parsed the
  winner with SST's own code paths; the fix is STC-side profile/config.
- **F1 corroborated live.** The P1 timeout wrote exactly the designed sidecar
  record; success legs wrote none. (Timeout agent-stderr remains
  unrecoverable by construction — no gap, just physics.)

## WINNER + exact reproduction (for the acceptance stage, serialized later)

- WINNER: **P2-H3a** — real M1 diverge bytes (4364 B, `3154b3bb…`) + baseline
  STC frame + codex 0.154.0 + model gpt-5.6-luna + **`model_reasoning_effort =
  "medium"`** + 180 s budget (answered in 56.66 s).
- Reproduction (exact): joint env, cwd `ws/stc`,
  `LIVEXP_OUT=<probe-dir> LIVEXP_PROBE=<id>
  LIVEXP_SST_SRC=<ws>/stc/docs/builds/stc-integration/evidence/P05/attempt-1/trial-timeout/p05-diverge-prompt.md
  LIVEXP_FRAME=baseline LIVEXP_TIMEOUT=180 LIVEXP_MODEL=default
  LIVEXP_REASONING=medium LIVEXP_EXPECT_SHAPED_SHA256=3339af290a80e1d88f2ff57f8f5bd829f9f2bafd665e8a14775256893c227fe4
  PYTHONDONTWRITEBYTECODE=1
  PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit
  trace/.venv-linux/bin/python /tmp/liveexp-probe.py`
  (driver preserved at `evidence/FOLLOWUP/live-exp/attempt-1/liveexp-probe.py`,
  `136a054e…`). Expect: exit 0, `s2_branches_valid:true`, header `reasoning
  effort: medium`.
- Proposed STC-owned acceptance change (NOT made here — no product edits in
  this stage): teach the live-run CODEX_HOME seeding (`cli.py:
  _seed_codex_home`, the P05 pattern this probe already follows) to write
  `model_reasoning_effort = "medium"` into the seeded `config.toml` for the
  gateway role (one-line, STC-owned, confined argv untouched, SST bytes
  untouched). Acceptance then re-runs the P05 live shape on that profile
  within the 6-call reserve. Alternative within existing access: `-c
  model_reasoning_effort='"medium"'` codex flag — but that alters the fixed
  argv builder (product change + re-verify); the seeded-config route alters
  no argv bytes and is already the established pattern.
- Caveat for acceptance: the winner's diff imports `stc_gateway.dialectic…`
  (model-guessed module path; real tree uses `stc.integration…`) — the §2
  parse win does not promise verify-green. If the medium-profile acceptance
  proposal fails verify on wiring (not shape), H1-context (append real API
  signatures in-frame) is the evidence-backed next lever, with 11 experiment
  calls still unspent should the coordinator release them.

## Verdict, reviewer only

**WIN — valid diverge proposal via an STC-owned variation (P2-H3a).**

- Criteria established: H0 controls green (P0 ok 25 s, P1 served-hang 150 s);
  first H3 variation wins (P2 ok 56.66 s, §2-valid via SST's own parse +
  `CandidateProposal` construction); one-lever discipline driver-enforced
  (identical prompt bytes P1≡P2); confinement 3/3; sst/prompt-kit/trace
  read-only + clean; spend 3/14, reserve intact; everything preserved.
- Unmet criteria or missing evidence: patch correctness/verify-green (out of
  this stage by design — acceptance's verdict); WIN replicate n=1 (WIN rule
  forbids further spend); H4/H1/H2 live status unknown (moot, not disproven).
- Baseline failures versus new regressions: zero regressions (no product
  code touched). The P1 hang matches the recorded baseline shape exactly.
- Exact scope of independent execution/inspection: everything in the Evidence
  table was executed by me in this session: 5 required full reads; candidate
  + 8 hashes + 3 pins at open (+ per-leg sst/pins); HEAD-move evidence-only
  proof; driver authorship (+3 pre-call 0-spend fixes: syntax, render-prefix,
  delimiter guard); 3 live legs through the real confined gateway (P0/P1/P2)
  with full per-probe captures; SST-own-types §2 replay; status-after-last-write.
- Next action: coordinator schedules the serialized acceptance stage (NOT
  mine): implement the one-line seeded-config change above (or rule an
  equivalent), then run acceptance + verification inside the 6-call reserve.
  Live-exp spends no more.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no tranche defects; P1 hang is the recorded baseline shape, not a finding) | — | — | — | Acceptance judges patch correctness |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — this stage touched zero product files; tracked numstat is exactly the
# 2 pre-existing loose-set mods, both still matching the tasked hashes:
#  src/stc/cli.py 576/0 33476f34c50ed726f699990102783fc507333e0bc165b033b0ded96eb8b124bb
#  src/stc/orchestrator/dispatch.py 333/7 dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
111b9a584af682cb6aec28fa42ff3c716a22491989a217464e8b0080f8dcceac  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/argv.txt
e2c27098f2b7d9d65a88a741b3b7cee2fae6dfb48f623dd4142e0703a44a9e72  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/byte-counts.txt
dbe7218fd3953d71eac340668b850fe4b57278326a462a0cf0ad506efbf8b02e  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/config-reasoning.txt
75109b679e85516c282106650dcfc1cee224505cdd0f526e8e349a4abcbbd759  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/config-toml.txt
5ba94a8ae513d37c7d5dae6a5d9f04342be20c298d623348f58e19cd0b58bae4  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/cwd.txt
9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/exit.txt
2362cf0d88635abdfa321de85b016e766dce5ac28c5e64fd3e5d523801c0da78  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/header.txt
36020c6ffafcc0bfb7b4346b00ca6bb78390e7af1c37eda65d961ee4ce4af74e  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/outcome.json
ecc6904088419834114672ce05b2093c6aebfa5b8b9fb8eae9bb4059e1851136  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/prompt-src-sha256.txt
2eb53399f7729145f23e9271d2ac0a031959d56e31320f6d4aaf80e0c251aafc  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/prompt.txt
04b7964bab509c44412090775c3d93b4b808d39256de2f8ebd8611564ee5419d  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/shaped-sha256.txt
2eb98ed274961913654856b75c319ef56e815da3fd1d41e320c0646710a2a2e6  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/spend-ledger.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/sst-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/sst-before.txt
a99abb3ac4f67c61d2e05d46e40a4f378298782edaf3cc82ebe3a265310454f0  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/sst-source.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/status-after-tracked.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/status-before-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/status-before-tracked.txt
edcac2390fb9c07a324a315b2732f93d1e319fefede87d0a4207abfc130ed4c8  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/stderr.txt
4d0d8cf58f91e265496562bde2ee26c5e6b464f0fb236c6500892ae2a670bf85  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/stdout.txt
664e62949445847a19765c5e31bcc5d841f4227d1663b52f90266daea3135eff  evidence/FOLLOWUP/live-exp/attempt-1/P0-H0a/variation.json
74792322ee97f42ce45695827ddd9d7d6f5ba64928c0bd5ca0d9997c728ba592  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/argv.txt
8474acf7d9fd1945ceec71d916a5bda23b2533f415476822ff249411d4ae8b6f  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/byte-counts.txt
dbe7218fd3953d71eac340668b850fe4b57278326a462a0cf0ad506efbf8b02e  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/config-reasoning.txt
75109b679e85516c282106650dcfc1cee224505cdd0f526e8e349a4abcbbd759  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/config-toml.txt
1dca7d2fcd9f6a9e578d8b53b8cb84eb78f0113718673fe060ae1d31c650296c  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/cwd.txt
ca2ebdf97d7469496b1f4b78958f9dc8447efdcb623953fee7b6996b762f6fff  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/exit.txt
7be04ace70f2618760947875ba800230354d8703e18697852e0d086126d7c0ee  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/outcome.json
6ad3329b93970c9758b2d5a1905a778023e38f8c5594ea9a499062458f946687  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/prompt-src-sha256.txt
3339af290a80e1d88f2ff57f8f5bd829f9f2bafd665e8a14775256893c227fe4  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/prompt.txt
afc91de4e0dcc4b38fc2fe78b02ca96cc9cca0dd172ae50edbec8c4c4c7b308e  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/shaped-sha256.txt
c9e6f41e0e20b41e7145cfa648b356d212ef48a4584e34b668d85a92e73b6a9f  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/spend-ledger.failures.jsonl
9984a0a27a048aaabb6e0ade8211c13f5fb800503dd3a9acb2b9d4fa008565de  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/spend-ledger.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/sst-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/sst-before.txt
f10a2f602b089fc4c947931d96220d127e6ffa98f110f926e93dc9a2877c42ba  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/sst-source.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/status-after-tracked.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/status-before-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/status-before-tracked.txt
7aa02feee4464594b291a848f00fffadcf65f6641909114be50a66f560935bb4  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/stderr.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/stdout.txt
fb7482a4e116ac56df4e3ecd2550024bc6d0194872bdbe2c8f64c91bc1fca645  evidence/FOLLOWUP/live-exp/attempt-1/P1-H0b/variation.json
f3e6cf2f0f13ab7517c803c5a5f37a5b7edb886bcbd59dd9f47941fe46122131  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/argv.txt
467e473727973012390d81a0f8f91c97a0c073345086300750688e896da3c1c8  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/byte-counts.txt
98330f6ff24a545a7929586bacb4b29a227ad92955339361d198c61a97c444ad  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/config-reasoning.txt
a30c90e0efe635f03ea196d2aca43ce1b8b3e92fb0ba6a481c01e3fec8e21061  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/config-toml.txt
3de12f881d71c98a28c4ae5d3fa454e960cdc25e3392cf47cc8c7ff714466d5d  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/cwd.txt
9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/exit.txt
d7733de3e1f483accb30312330b4d77491963f6c5bdf2f4ea3843e25bc98626d  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/header.txt
efbdda4e2c53f832072d3adf4ea105068bdc33504bb393a6278b0121026552d4  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/outcome.json
6ad3329b93970c9758b2d5a1905a778023e38f8c5594ea9a499062458f946687  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/prompt-src-sha256.txt
3339af290a80e1d88f2ff57f8f5bd829f9f2bafd665e8a14775256893c227fe4  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/prompt.txt
afc91de4e0dcc4b38fc2fe78b02ca96cc9cca0dd172ae50edbec8c4c4c7b308e  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/shaped-sha256.txt
31486b0ad06eb952e1ce8f2c642f2fd0b33e60ae04fbddad7c18b5b2b2e85762  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/spend-ledger.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/sst-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/live-exp/attempt-1/P2-H0b/sst-before.txt
f10a2f602b089fc4c947931d96220d127e6ffa98f110f926e93dc9a2877c42ba  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/sst-source.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/status-after-tracked.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/status-before-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/status-before-tracked.txt
7ee0d1dd528933d35f479ecf74d0cf3c71339ad81f038967cad439b62aa99dd7  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/stderr.txt
30283c5880d8e1fd912eac46e14cefa579feea39b6edd0c8a82a2c52bc4b0d37  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/stdout.txt
aa859c1575d71cdfb428d2968a4552b18b64da94dcef2de55a5e5b86b06d52f6  evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/variation.json
136a054e0086c726f69ed62f322db9a97a57a2ddb48560dc27b1706b79a1a047  evidence/FOLLOWUP/live-exp/attempt-1/liveexp-probe.py
ca11dd3b589ff5a3753601b9585da37f6b0b07e4aa6dedad7b0e39b2a28e61bd  evidence/FOLLOWUP/live-exp/attempt-1/p0-small-sst.txt
4e3a56aac7720b226a4ebe424611d711bbe8f8a686443d229dbde8b11f5d9552  evidence/FOLLOWUP/live-exp/attempt-1/spend.jsonl
9538afd1a76a47c444f12ced4efd993b7b54a4aae3779a197919e04cdbd15d81  evidence/FOLLOWUP/live-exp/readiness.md
```

`git diff` tracked hunks belonging to this stage: NONE (no tracked file created
or modified; `git diff --numstat` shows only the 2 pre-existing loose-set mods).
