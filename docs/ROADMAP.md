# ANIMA roadmap and maturity (moved from README)

This page holds the outlook, maturity, and scope notes that used to live
in full inside `README.md`. The README keeps short pointers here.

Related: [Architecture](ARCHITECTURE.md) · [Code tour](CODE-TOUR.md) ·
[TRACE reproduction](TRACE-REPRODUCE.md) · [Root quickstart](../README.md#quickstart)
· [Component guides](../components/substrate/README.md).

## Architecture (summary)

The [`anima` alias package](../src/anima/) re-exports the five native
distributions as same-object convenience aliases (`anima.substrate`,
`anima.sst`, ...). Native imports (`import anima_substrate`, `import sst`,
...) are primary; diagram arrows are import aliases, not data flow.
Full guide: [docs/ARCHITECTURE.md](ARCHITECTURE.md). Component guides:
[substrate](../components/substrate/README.md),
[SST](../components/sst/README.md),
[STC](../components/stc/README.md),
[entorhinal](../components/entorhinal/README.md),
[reflex](../components/reflex/README.md).

## Maturity and component scope

ANIMA components are modular research systems exploring attributable local
execution, heuristic code synthesis, and computer use. Component validation
covers bounded unit, smoke, and conformance invariants within isolated test
suites and local test harnesses; it does not constitute general production
or turn-key guarantees. Model-driven rollouts and perception pipelines
require caller-selected and caller-configured model backends.

What is verified today (see [TEST-REPORT.md](../TEST-REPORT.md), staged
2026-10-14, CPython 3.12.3): root alias imports 8 passed; substrate
207 passed, 11 skipped; SST 161 passed, exact parity with the CUT1 pin
record (frozen-lock env); STC schemas 37 passed; entorhinal
fact-identity 9 passed plus conformance/truth 29 passed, 2 skipped;
reflex privacy-redactor 14 passed plus 11 subtests; every CLI responds;
and the substrate journey below ends with `ANIMA quickstart OK`.

## Scope and boundaries

This repository ships the five research components, the alias namespace
package, tests, and curated background documentation:

- **No shared runtime**: There is no overarching daemon, monolithic server,
  or implicit inter-component coupling.
- **Offline / mock demonstrations**: Demonstrated CLI snippets and example
  scripts run via offline, stdlib, or mock execution paths. Model-driven
  capabilities (e.g., MCTS tree search rollouts or vision escalation)
  require caller-configured local runners (e.g., Ollama) or remote
  provider credentials, and may incur external provider charges.
- **Sanitized publication record**: Test fixtures are synthetic and
  push-protection safe; see the dated [SECRET-SCAN.md](../SECRET-SCAN.md)
  (2026-10-14) for the bounded publication check.
- **No autoplay media**: this README ships no animated or auto-playing content.

## Roadmap

Labeled outlook only — none of this is claimed as shipped:

- **TRACE scale-up (100M+ tokens)**: the frozen seam12a build
  ([TRACE reproduction](TRACE-REPRODUCE.md)) is a 10M-token measurement;
  larger corpora need a fetchable dataset and a reproducible
  large-machine path.
- **Composed worlds**: running substrate worlds with SST search, STC
  construction, entorhinal memory, and TRACE retrieval under one
  budgeted arrangement is the stated direction in
  [docs/anima/](anima/), not a qualified integration today.
- **Cost accounting**: per-participant budgets exist in substrate now;
  extending that accounting across coordinator scheduling and model
  calls is future work.
- **Interfaces**: any hosted or graphical interface is in development
  at most — nothing dated, nothing promised.

## Provenance

Staged 2026-10-14 from user-owned sources (see [MANIFEST.md](../MANIFEST.md)):

| Component | Source revision staged |
|---|---|
| substrate | worktree HEAD `755b0d1` (2026-10-11) |
| sst | frozen `search.sst@df78f428` (2026-10-04 release) |
| stc | frozen `construction.stc@1f93f15c` (2026-10-06) |
| entorhinal | worktree HEAD `0be71d8` (2026-10-11) |
| reflex | worktree HEAD `8b44867` (2026-10-14; source dir spelled `relfex`) |
| docs/anima | curated subset of ANIMA (2026-10-14) |

Upstream remotes: `anima-substrate`, `entorhinal`, `relfex`,
`utilities-sst` (all `github.com/Anshul48/...`); `stc` has no remote
configured. Per-file history stays in those sources; this repo starts fresh.
