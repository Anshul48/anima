# Research archive — curation plan

What publishes with substrate 0.1.0 vs what stays local, and the
scrub rules for anything that ships. Authority: `prototype/
programme-20261004/LICENSE-AUDIT.md` (§§2–3, items T1–T7).
The coordinator owns LICENSE/NOTICE filing and the T2 option choice;
this file plans the curation only.

## Publishes (lawful, claim-supporting)

- Substrate-original code/docs/fixtures/accept packs in all
  successor/lane trees (T1: GO) — carry chains documented in-tree
  (`VENDORING.md` + `PROVENANCE.md` per tree; `minihost.py` lineage
  reuse-demo-001 → successor-006).
- P1-adapters code (substrate-original; ships zero STC bytes — T3: GO
  as-is, hashes/prose only).
- ANIMA citations by locator (`../ANIMA/context/…`, D-001–D-017,
  `IDEA-MAP:NN`) — T4: GO as citations; never copy packet content
  (ANIMA has no license file).
- SST snapshot bytes: ONLY per coordinator's T2 decision —
  Option A (preferred): EXCLUDE all five `vendor/sst-snapshot/` dirs,
  document fetch-by-pin (`VENDORING.md` procedure: clean `df78f42` +
  `verify_snapshot.py`); Option B: ship ONE deduplicated copy +
  Apache-2.0 LICENSE text + NOTICE entry + `vendor/PROVENANCE.md` as
  the §4(b) changes statement, and ask the SST owner to add a LICENSE
  file (grant currently rests on a pyproject declaration only).
- Publication docs: `CONTRIBUTING.md`, `CHANGELOG.md`, `CITATION.cff`
  (after placeholders filled), `docs/ROADMAP.md`,
  `docs/TECHNICAL-REPORT.md`, this file. (`README.md`, `docs/api/`,
  `ARCHITECTURE.md` land after the build.)

## Stays local (never ships)

- `runs/` evidence dirs (ledgers, EVIDENCE.json) — T6: project-
  generated but embed absolute username paths; EXCLUDE (or scrub —
  exclusion preferred, evidence is not package code).
- `.venv/` trees (root + `prototype/w1/.venv`), `__pycache__/`,
  `*.db` run artifacts, `*.log` — T5: mixed third-party /
  regenerable; already git-ignored.
- SST-leg staging outside the snapshot (`../sst/.delivery/cand-02`
  references, `sst-work/`, `search-work/` runtime artifacts).
- Throwaway/validation state, blind-rating work dirs beyond filed
  records, auditor `/tmp` logs.

## Scrub rules (before anything ships)

1. **Username paths (privacy, not license).** The OS username in
   absolute paths (`/mnt/c/Users/<user>/…`, `C:\Users\<user>\…`) is a
   path artifact, NOT authorship (LICENSE-AUDIT A7 VERIFIED) — and
   must never be presented as an author. Generalize to `$U/substrate`-
   style placeholders. Known carriers (T6/T7): `REPRODUCE-ALL.md`,
   `docs/SUBSTRATE-DIRECTION.md`, `vendor/PROVENANCE.md` copy-time
   paths, run `EVIDENCE.json` `solution_ref`s,
   `docs/PENDING-B1-B2-REVIEW-2026-10-05.md` (Windows path form).
2. **Audit command (run at curation time, from root):**
   `grep -rn -E "(Users|users)[/\\\\][^\"'/\\\\<]" --include="*" -l . --exclude-dir=.venv`
   must return zero shippable files (functional code defaults and synthetic
   test vectors excepted — see carrier list; `<user>` placeholders do not
   match). Re-check after every doc edit.
3. **No owner invention.** M1 (copyright owner name/year) and M2
   (agent-byte assignment) stay `OWNER-YEAR`-style placeholders until
   the human answers; the single human name+email in-tree
   (`STC-548615a-ASSESSMENT.md:12`) is an STC observation, not
   substrate authorship (A4).
4. **Preserve honesty artifacts.** Negatives, VOID legs, superseded
   records, rater/auditor warts (e.g. U-execute `12:00:00Z`
   placeholder timestamps, S5-A10 environmental reds), and interim
   notes ship WITH their causes named — scrubbing paths must never
   scrub findings.
5. **Curation gate.** Coordinator verifies: LICENSE/NOTICE filed
   (M1/M2 closed), T2 option executed, scrub audit clean, then tags.
   No tag without all three.
