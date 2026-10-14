# MANIFEST.md — ANIMA review manifest

Written: 2026-10-14T10:14Z. Author: W3 (ANIMA worker).
Fix pass: 2026-10-14 (focused fixer): removed operational records, repaired
entry READMEs + all doc links, excluded gutted reflex tests, added the
entorhinal corpus skip-guard, redacted machine-local paths, added the STC
staging-hash note, corrected TEST-REPORT row 7. No algorithm edits.

## Candidate

- Remote: `github.com/Anshul48/anima`, branch `main`.
- Remote old SHA: **none (empty repository)** — verified at clone; no
  commits, no remote work to preserve. Push (when approved) seeds `main`
  with a normal fast-forward of the first commit.
- This repository is published as ONE sanitized initial commit with no
  parents (operational records never reachable in published history).
  Exact commit/tree SHAs are pinned in the out-of-tree publication REPORT
  (channel `anima-fixes/`); verify locally with `git rev-parse HEAD`,
  `git rev-parse HEAD^{tree}`, `git ls-files | wc -l` (= 1289).
- Superseded staging history (`2205440`, `3a27d7c`, which contained the
  operational records) is preserved on a local-only quarantine branch and
  in a private quarantine copy. It is not pushed, tagged, or reachable
  from the published commit.

## Shipped files (1289, all newly tracked in the initial commit)

| Area | Files | Contents |
|---|---|---|
| `components/substrate/` | 87 | src, tests, examples, docs, legal/notes (worktree HEAD) |
| `components/sst/` | 106 | src, tests, docs (minus evidence), ops files, frozen `uv.lock` |
| `components/stc/` | 564 | src, tests, specs, examples, docs + FOLLOWUP fixtures, `dsh-plugin-*` minus evidence, frozen `uv.lock`, `.env.example` |
| `components/entorhinal/` | 151 | src (minus consented corpus), tests, boundary + spec docs |
| `components/reflex/` | 261 | src, tests (minus 4 pass-only files), scripts/evals, contract docs, entry points |
| `docs/anima/` | 105 | README/START-HERE/AGENTS, proposals, syntheses, reading room, catalogue + freeze pins + staging-hash note (minus operational records) |
| `src/anima/` | 7 | `__init__` + 5 alias modules + `py.typed` |
| root | 8 | README, TEST-REPORT, SECRET-SCAN, MANIFEST, pyproject, .gitignore, tests/, requirements/ |

Full list: `git ls-files` at the candidate commit. (The superseded manifest
said "root 7 / 1301 files"; the true superseded count was 1302 — root paths
are 8. This manifest counts the final tree: 1289.)

## Provenance (read-only sources, worktrees untouched)

| Staged | Source | Method |
|---|---|---|
| substrate | `Utilities/substrate` HEAD `755b0d1` (2026-10-11, clean) | curated worktree copy |
| sst | `Utilities/sst` frozen `search.sst@df78f428` (2026-10-04) | `git archive` (pruned, see below) |
| stc | `Utilities/stc` frozen `construction.stc@1f93f15c` (2026-10-06) | `git archive` (pruned, see below) |
| entorhinal | `Utilities/entorhinal` HEAD `0be71d8` (2026-10-11) | curated worktree copy |
| reflex | `Utilities/relfex` HEAD `8b44867` (2026-10-14; note source spelling) | curated worktree copy |
| docs/anima | `Utilities/ANIMA` (2026-10-14) | curated docs subset |

Upstream remotes (unchanged): anima-substrate, entorhinal, relfex,
utilities-sst under `github.com/Anshul48/`; stc has no remote.
Post-staging HEAD check: sst `85611d2`, stc `d78cd4e` (unchanged).

## Excluded (deliberate, not shipped)

- Operational records: `docs/anima/architecture/notes/`
  `2026-10-09-LINUX-AGY-RESEARCH-AUTOMATION/` (9 files: event streams,
  logs, result/summary, prompt, unaccepted worker report, evidence ledger)
  — removed from the public tree in the fix pass; original sources
  untouched, private quarantine copy + local quarantine branch preserved.
  Never reachable in published history (sanitized initial commit).
- Pass-only tests: reflex `clear_failing_tests.py` + 4 test files whose
  bodies were `pass`-only upstream (see TEST-REPORT scope). Quarantine
  copies preserved privately; no qualification claimed.
- Secrets/creds: all `.env` (never read); only stc's clean `.env.example`
  ships. No `*.pem`/`*.key`/tokens (see SECRET-SCAN.md).
- Private/user data: entorhinal `evidence/`, `run/`, `artifacts/`,
  `src/…/fixtures/consented_trace/`; relfex `artifacts/`, logs, harnesses,
  `windows-exchange-staging/`; sst `experiments/`, `.delivery/`,
  `docs/evidence`; stc `artifacts/`, `mutants/`, `trace/`, `worktrees/`,
  `.durable/`, `operator-console/`, `docs/{builds minus FOLLOWUP+2md,
  plans,progress_logs,prototype-dsh-workspace}`, `dsh-plugin-*/evidence`.
- Operational/workspace records: ANIMA `coordination/`, `progress_logs/`,
  `context/{conversations,provenance-excerpts,*.jsonl}`,
  `integrations/*/preserved`, `SESSION-STEER-*`; all `AGENTS.md` /
  `ANIMA-CONTEXT.md` router notes; `anima-ecosystem/session-handoff.md`.
  Doc links to excluded records are plaintext historical references with a
  per-file curation notice (original identities preserved).
- Machine-local paths redacted to `<workspace-root>` / `<research-archives>`
  / `<codex-sessions>` / `<user>` placeholders across docs, evidence logs,
  and test path constants (functional product defaults and synthetic test
  vectors excepted). Frozen STC contract docs ship byte-identical to the
  pin, including historical absolute links in `STC-DSH-RECORD.md` (frozen
  evidence, disclosed in the staging-hash note).
- Non-Python sidecars: entorhinal browser/editor extensions, stc
  `node_modules`; JS `dsh-plugin-*` sources kept only where frozen-contract
  (`DSH_PIN`, cordis) — pilot evidence pruned.
- Machine residue: `.git/`, `.venv*/`, `__pycache__`, `*.pyc`,
  caches, `dist/`, `build/`, `*.egg-info`, substrate `prototype/` (186MB
  frozen research) + `runs/`, entorhinal/relfex `uv.lock` (current-tree
  only; pin locks kept), relfex `S3_MANIFEST.json` (run verdict).

## Verification (exact commands + exits — see TEST-REPORT.md)

- `pip install -r requirements/components-all.txt` from clean state: exit 0
  (6 dists built: anima, anima-substrate, sst-engine, stc, entorhinal,
  reflex; run from repo root with real pip 26.2.1).
- Root import-map tests: 8 passed (clean venv, re-verified) / 4 passed+4
  skipped (substrate-only venv). All five native + `anima.*` imports OK.
- substrate quickstart 7/7; substrate suite 207 passed/11 skipped;
  sst@pin suite **161/161** (frozen-lock env + localhost proxy bypass;
  matches CUT1 record; latest-dep run was 158+3failed with pytest exit 1,
  previously misrecorded as 0 — see TEST-REPORT row 7); stc schemas 37
  passed (re-verified); entorhinal fact-identity 9 passed; entorhinal
  track1/track2 guard 1 skipped; conformance/truth/fact 29+2skip; reflex
  redactor 14 passed; all five CLIs `--help` OK (reflex via `main.py`).
- Link check: 0 broken relative links across 245 `*.md` (132 repaired to
  shipped targets; excluded-target links converted to plaintext refs).
- Pin check: sst contract+policy MATCH; stc 5/6 contract docs + TaskBundle
  model MATCH; stc `04_DATA_CONTRACTS_AND_SCHEMAS.md` differs (pin holds
  pre-commit working-tree hash — historical value preserved, staging hash
  recorded in `docs/anima/catalogue/pins/STAGING-HASH-NOTE.md`). No pin
  JSON edited.
- Secret scan P1–P7 over final tree: clean; all pattern hits synthetic
  redaction vectors with in-tree labels (9 new + 2 pre-existing) or
  demonstrated false positives; 3 masked-byte spans forensically resolved
  (numeric-filler fakes) with hashes for auditor confirmation.

## License/authorship posture (no changes made)

- Root `pyproject.toml` carries NO license/authors fields (A7 fix).
- No LICENSE text added anywhere; no author emails introduced.
- Per-component status preserved exactly; see README license table
  (substrate + stc: Apache-2.0; sst/entorhinal/reflex + root staging
  files: unlicensed as found — owner to confirm before/after push).

## Diff summary

New repository: one sanitized initial commit adds 1289 files. No rebase or
merge; no push performed (hard gate: awaiting REVIEW-APPROVED.md naming
repo + candidate commit). Superseded staging commits exist only on the
local quarantine branch (not published); empty remote, so no force-push
and no previous published history.

## Addendum 2026-10-14 — professional publication pass (on public `5cf1708`)

Normal descendant of the public commit
`5cf1708a1587caa6fd3b248071f0f384216b5e56`; documentation, licensing,
metadata, images, community files, and CI only:

- Root Apache-2.0 `LICENSE` (byte copy of the `components/substrate/LICENSE`
  already in the tree, appendix included); identical copies added to
  `components/sst/`, `components/entorhinal/`, `components/reflex/`
  (`substrate`/`stc` already carried Apache-2.0). All six
  `pyproject.toml` files (root + five components) declare Apache-2.0.
  Third-party/data/model material keeps its own terms and notices.
- Root README: capabilities table, quickstart, architecture and code-tour
  links (`docs/ARCHITECTURE.md`, `docs/CODE-TOUR.md`), hero/architecture
  SVGs under `assets/`, shortened scope paragraph pointing here.
- New: `examples/quickstart.py`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CHANGELOG.md`, `CITATION.cff`, `.github/workflows/ci.yml`.
- No component source, fixture, or dependency edits. In particular the
  two public-safe synthetic fixture files from `5cf1708`
  (`components/entorhinal/src/entorhinal/fixtures/golden.py`,
  `components/entorhinal/tests/test_integration_security_and_failure.py`)
  are byte-identical to `5cf1708`, and every file tracked at `5cf1708`
  is still present (verification in `TEST-REPORT.md`).
