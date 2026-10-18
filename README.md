# ANIMA

[![CI](https://github.com/Anshul48/anima/actions/workflows/ci.yml/badge.svg)](https://github.com/Anshul48/anima/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

![ANIMA component overview: five cards for substrate, SST, STC, entorhinal, and reflex](assets/anima-overview.svg)

> **Research preview.** ANIMA is experimental research shared early for
> feedback. It is not a production runtime, not a hosted service, and
> not a benchmark champion — just working code with measured numbers.

## ANIMA in 30 seconds

**What:** Superintelligence will not come from a bigger model alone.
ANIMA externalizes intelligence into the environment: persistent
project worlds, heuristic search, spec-to-code construction, advisory
memory, and computer-use perception — durable scaffolds around models
so cognition lives in the system, not in a single prompt.

**Who it helps:** agent builders who need attributable, budgeted local
execution across many models — [who it is for](#who-it-is-for).

**Proof:** a frozen 10M-token memory build (TRACE seam12a) organizes
**10,003,381 tokens** into **13,081 docs** and **63,441 atoms** with
**recall@10 0.7367 (all) / 0.4883 (leave-schema-out)**, repairs
**5,847 defects to 0 in 6 iterations**, in **9,494.9 s (~2.6 h)** at
**~8.5 GB peak RAM** (parent-process peak 8489.1 MB, rss-hwm), freeze
sha `8d3bbb6b`. [TRACE section](#trace-the-memory-layer) ·
[benchmarks](#benchmarks-frozen-seam12a-o94-scale10m) ·
[live explorer](https://anshul48.github.io/trace/explorer/) ·
[run it](#quickstart).

## The dream (Vision — direction, not shipped)

Everything in this section is direction, not a claim about what exists.
The composition it describes is a proposal today, not shipped wiring.

The dream is a dynamic substrate that rewires itself while it runs:
worlds that split, merge, and quarantine organizations the way cells
divide and immune systems isolate; software that literally evolves
like biology — variation under search, selection under deterministic
gates, inheritance through versioned genomes of verified code.

A cost cascade keeps that evolution affordable. A frontier model acts
as architect and decides rarely; a coordinator schedules and budgets;
Spark swarms of cheap models do the abundant work. Each layer is
budgeted separately, so intelligence scales by spending wisely rather
than by renting the largest model for every step.

Cognition is offloaded to deterministic scaffolds that do not forget:
a hippocampus-inspired retrieval layer, a prefrontal-inspired
constraint and planning system, and a basal-ganglia-inspired gate that
only lets verified work through. Memory itself is TRACE: the layer
that supplies schema priors from everything seen before, plus negative
knowledge — what was tried, what failed, and what must never ship.

## What exists today

Five independently installable research components plus a thin alias
namespace. There is no shared server, no cross-component wiring, and
no hosted service here. Shared background and proposals live in
[docs/anima/](docs/anima/).

### Modules

| Component | Distribution | Status (repo wording) | Guide |
|---|---|---|---|
| [substrate](components/substrate/) | `anima-substrate` 0.1.1 | Alpha research artifact, not a production runtime; stdlib-only; suite 207 passed, 11 skipped | [Component README](components/substrate/README.md) |
| [sst](components/sst/) | `sst-engine` 0.1.0 | Heuristic dialectic-MCTS search; repo check 161 passed, exact parity with the CUT1 pin record; model rollouts need caller-configured backends | [Component README](components/sst/README.md) |
| [stc](components/stc/) | `stc` 0.1.0 | Component description: production-grade, distributed autonomous engineering engine; badges 209 tests passing and Mutmut kill rate >= 85%; repo re-verified the schemas smoke (37 passed), full suite not re-run | [Component README](components/stc/README.md) |
| [entorhinal](components/entorhinal/) | `entorhinal` 0.1.0 | Local-first advisory temporal context under strictly advisory authority (zero autonomous mutation authority); smoke `test_fact_identity.py` 9 passed | [Component README](components/entorhinal/README.md) |
| [reflex](components/reflex/) | `reflex` 0.1.0 | Research/seed stage: model names, latency figures, and complexity claims in its `ARCHITECTURE.md` are hypotheses to measure, not release commitments; smoke `test_privacy_redactor.py` 14 passed; four upstream pass-only test files excluded, not claimed as passing | [Component README](components/reflex/README.md) |

Component READMEs are the authoritative per-component guides. Native
imports (`import anima_substrate`, `import sst`, ...) are primary;
`anima.<component>` modules are same-object convenience aliases.

> **Note on PyPI name collision**: The native import name `reflex` collides with the unrelated Reflex web framework on PyPI. Do not install both into the same Python environment.

### Status

What is verified today (see [TEST-REPORT.md](TEST-REPORT.md), staged
2026-10-14, CPython 3.12.3): root alias imports 8 passed; substrate
207 passed, 11 skipped; SST 161 passed, exact parity with the CUT1 pin
record (frozen-lock env); STC schemas 37 passed; entorhinal
fact-identity 9 passed plus conformance/truth 29 passed, 2 skipped;
reflex privacy-redactor 14 passed plus 11 subtests; every CLI responds;
and the substrate journey below ends with `ANIMA quickstart OK`.
Component validation covers bounded unit, smoke, and conformance
invariants within isolated test suites and local test harnesses; it
does not constitute general production or turn-key guarantees.

### Constraints

Every component runs alone: each has its own install, its own test
suite, and its own caller-selected state directory, with no shared
server and no cross-component imports. Work is bounded before it runs:
substrate pins participants and delegates explicit budgets, STC
compiles task bundles under a strict 25 KB ceiling and passes every
worker through deterministic gates (Ruff, Mypy strict, Pytest, Mutmut)
plus blind judiciary review and a human promotion gate, and SST refuses
to promote unless the verifier passed on the exact logged bytes.
Memory stays advisory: entorhinal records evidence and serves context
snapshots but has zero autonomous mutation authority, and every
correction, consent grant, deletion, and access is audit-logged under
user control.

## Quickstart

To run from a fresh checkout in an isolated virtual environment:

```bash
git clone https://github.com/Anshul48/anima.git
cd anima

# Create and activate an isolated Python 3.12 virtual environment:
python3.12 -m venv .venv
source .venv/bin/activate

# Or using uv:
# uv venv .venv --python 3.12 --seed && source .venv/bin/activate

# Install the root alias package and the stdlib-only substrate component:
pip install -e . -e components/substrate

# Execute the verified substrate journey (participant run, byte-identical close/reopen):
python examples/quickstart.py   # ends with: ANIMA quickstart OK
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit
together, [docs/CODE-TOUR.md](docs/CODE-TOUR.md) for where to start
reading each component, and [docs/ABOUT.md](docs/ABOUT.md) for the
proposed GitHub About text and topics.

### Deep dive

How each piece works lives behind these links: [substrate
guide](components/substrate/README.md), [SST
guide](components/sst/README.md), [STC
guide](components/stc/README.md), [entorhinal
guide](components/entorhinal/README.md), [reflex
guide](components/reflex/README.md), [architecture
guide](docs/ARCHITECTURE.md), [code
tour](docs/CODE-TOUR.md), and background proposals in
[docs/anima/](docs/anima/).

## Who it is for

- **Agent builders** who want worlds with explicit custody: pinned
  participants, delegated budgets, and crash-atomic state instead of
  hidden global state. Built for local, attributable execution — use
  substrate to explore it.
- **Multi-model orchestrators** who want search, construction, and
  memory budgeted as separate concerns: SST for heuristic search with
  deterministic promotion gates, STC for bounded spec-to-code bundles,
  entorhinal for advisory context that can never mutate on its own.
- **Cost-conscious teams**: budgets are explicit before work runs
  (substrate delegates them, STC caps bundles at 25 KB, SST verifies
  on the exact logged bytes), so model spend is attributable per
  participant and per task.

## TRACE: the memory layer

TRACE is the memory layer for this ecosystem: an experimental
retrieval architecture that organizes continuous document streams into
an overlapping multi-tier DAG without global clustering
recomputation. The frozen build below is measured, not projected.

Freeze identity (pinned): **seam12a**, tarball sha256
`8d3bbb6bf53e1731811065a9de156a9997be740d598cd1dfa0a3d946928dbf64`,
run **o94-scale10m**, probes `b332d62d...`, harness `9f78479a...`,
final commits `164195`. The freeze holds 253 files (`frozen_ok=true`).

Measured headline: 10,003,381 tokens, 13,081 docs, 63,441 atoms;
guided recall@10 0.7367 all / 0.4883 leave-schema-out; self-repair
5,847 to 0 over 6 iterations; wall 9,494.9 s (~2.6 h); peak RAM
~8.5 GB (parent-process peak 8489.1 MB, rss-hwm). Live explorer:
[live explorer](https://anshul48.github.io/trace/explorer/).
Source: [github.com/Anshul48/trace](https://github.com/Anshul48/trace).

What exists is a Python package plus the `tools/product_pilot.py`
CLI — no SDK, no API, and no hosted endpoint is claimed. Built for
memory-over-streams research; use it to explore schema priors and
negative knowledge (what failed, and what must never ship) on your
own corpora at small scale.

### Benchmarks (frozen seam12a, o94-scale10m)

| Benchmark | Score |
|---|---|
| Guided recall@10, all sources (120 probes: chunk/noisy/cross) | 0.7367 |
| Guided recall@10, leave-schema-out | 0.4883 |
| Flat recall@10, all sources (baseline, same probes) | 0.055 |
| Flat recall@10, leave-schema-out (baseline, same probes) | 0.0017 |
| Self-repair debt over 6 iterations | 5847 to 0, 0 pending |
| Query-complete latency p50/p95 (n=33, all within 5 s) | 96.8/115.5 ms |
| Append ack-to-query | 0.114 s |
| Reader load, 2 threads, 27796 requests, p50 | 74.7 ms |

No broad-benchmark claim is made: this is the project team's
prototype evaluation protocol, nothing more.

### Reproduce the benchmark

From inside the extracted seam12a dir, with the environment kept
inside that dir:

```bash
uv venv .venv --python /usr/bin/python3
uv pip install --python .venv/bin/python numpy==2.5.4 blake3==1.0.11
SUP_PYTHON=$PWD/.venv/bin/python bash runtime.sh tools/product_pilot.py --help
PYTHONPATH=$PWD/fork/tl-sys:$PWD/tools:$PWD/tests $PWD/.venv/bin/python -B -m unittest tests.test_integration
PYTHONPATH=$PWD/fork/tl-sys $PWD/.venv/bin/python -B fork/tl-sys/tests/test_o93_repair_columnar.py
```

Expected: `--help` exits 0, integration 6/6 OK, repair-columnar
221 checks PASS. A 10k-token synthetic pilot with the same flags
exits 0 with `status=PASS, claim=measured`:

```bash
SUP_PYTHON=$PWD/.venv/bin/python bash runtime.sh tools/product_pilot.py --tokens 10000 --profile local --source-root $PWD --data-dir ./synth-data --out ./out-pilot --drain-attribution --drain-census --holon-descriptor-columnar --overrides-columnar --descriptor-matrix-all --per-view-sharing --cold-scan-chunk 4096 --repair-columnar --candidate-source hnsw --drain-bounded-k 32 --candidate-shadow-audit 8
```

`./synth-data` must hold `docs-100m.jsonl` (one JSON object per line,
fields `doc_id` + `text`) plus `emb_cache/` in `tl-gpu-embcache-v1`
layout (`meta.json`, `index.jsonl`, FP32 `shard_NNNNNN.f32` files).
Non-VM runs are capped at 1M tokens via `--profile local`.

A full 10M-token reproduction is blocked by two facts, and there is
no one-click 10M repro today: (a) the external corpus
`docs-100m.jsonl` plus its embedding cache is absent — the 1.2 MB
freeze tarball is source-only and ships no dataset; (b) the
`--profile vm` path exits unless the hostname is `trace-build500`
(`VM profile requires existing trace-build500; local runs capped at
1M TOK`). Behind that gate the corpus is absent too, so the 10M
numbers above stay receipt-labeled, not re-measured here. Scaling to
100M+ tokens is roadmap, not a claim.

## Architecture

![ANIMA repository architecture: the anima alias package over five independent distributions](assets/anima-architecture.svg)

The [`anima` alias package](src/anima/) re-exports the five native
distributions as same-object convenience aliases (`anima.substrate`,
`anima.sst`, ...). Native imports (`import anima_substrate`, `import sst`,
...) are primary; the diagram arrows are import aliases, not data flow.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architecture guide and [docs/anima/architecture/](docs/anima/architecture/) for background proposals.

## Verification & Testing

Every component includes dedicated unit and conformance test suites (requires `pytest`, installed via `pip install pytest` or your test environment):

```bash
# Run root namespace import smoke tests:
pytest tests/ -q

# Run substrate component test suite (stdlib-only):
pytest components/substrate/tests/ -q

# Run root quickstart verification:
python examples/quickstart.py
```

CI workflows run automatically on push and pull requests as defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Maturity & Component Scope

ANIMA components are modular research systems exploring attributable local execution, heuristic code synthesis, and computer use. Component validation covers bounded unit, smoke, and conformance invariants within isolated test suites and local test harnesses; it does not constitute general production or turn-key guarantees. Model-driven rollouts and perception pipelines require caller-selected and caller-configured model backends.

## Scope & Boundaries

This repository ships the five research components, the alias namespace package, tests, and curated background documentation:
- **No shared runtime**: There is no overarching daemon, monolithic server, or implicit inter-component coupling.
- **Offline / mock demonstrations**: Demonstrated CLI snippets and example scripts run via offline, stdlib, or mock execution paths. Model-driven capabilities (e.g., MCTS tree search rollouts or vision escalation) require caller-configured local runners (e.g., Ollama) or remote provider credentials, and may incur external provider charges.
- **Sanitized publication record**: Test fixtures are synthetic and push-protection safe; see the dated [SECRET-SCAN.md](SECRET-SCAN.md) (2026-10-14) for the bounded publication check.
- **No autoplay media**: this README ships no animated or auto-playing content.

## Roadmap

Labeled outlook only — none of this is claimed as shipped:

- **TRACE scale-up (100M+ tokens)**: the frozen seam12a build above is
  a 10M-token measurement; larger corpora need a fetchable dataset and
  a reproducible large-machine path.
- **Composed worlds**: running substrate worlds with SST search, STC
  construction, entorhinal memory, and TRACE retrieval under one
  budgeted arrangement is the stated direction in
  [docs/anima/](docs/anima/), not a qualified integration today.
- **Cost accounting**: per-participant budgets exist in substrate now;
  extending that accounting across coordinator scheduling and model
  calls is future work.
- **Interfaces**: any hosted or graphical interface is in development
  at most — nothing dated, nothing promised.

## Contributing & Security

- **Contributing**: Contributions and workflow guidelines are documented in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security**: Security posture, disclosure procedures, and authority boundaries are documented in [SECURITY.md](SECURITY.md) and [components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md](components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md).
- **Code Tour & Architecture**: See [docs/CODE-TOUR.md](docs/CODE-TOUR.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for navigation guides.


## Provenance

Staged 2026-10-14 from user-owned sources (see [MANIFEST.md](MANIFEST.md)):

| Component | Source revision staged |
|---|---|
| substrate | worktree HEAD `755b0d1` (2026-10-11) |
| sst | frozen `search.sst@df78f428` (2026-10-04 release) |
| stc | frozen `construction.stc@1f93f15c` (2026-10-06) |
| entorhinal | worktree HEAD `0be71d8` (2026-10-11) |
| reflex | worktree HEAD `8b44867` (2026-10-14; source dir spelled `relfex`) |
| docs/anima | curated subset of ANIMA (2026-10-14) |

Upstream remotes: `anima-substrate`, `entorhinal`, `relfex`, `utilities-sst` (all `github.com/Anshul48/...`); `stc` has no remote configured. Per-file history stays in those sources; this repo starts fresh.


## License

This repository is licensed under the [Apache License, Version 2.0](LICENSE)
(`SPDX-License-Identifier: Apache-2.0`), covering the root files,
[`src/anima/`](src/anima/), [`docs/anima/`](docs/anima/), and every
component directory — including `sst`, `entorhinal`, and `reflex`, which
carried no license text upstream. Each component directory contains its own
`LICENSE` copy with identical terms:

| Path | License file | Terms |
|---|---|---|
| repo root / `src/anima/` / docs | [`LICENSE`](LICENSE) | Apache-2.0 |
| `components/substrate/` | [`LICENSE`](components/substrate/LICENSE) | Apache-2.0 (as carried upstream) |
| `components/stc/` | [`LICENSE`](components/stc/LICENSE) | Apache-2.0 (as carried upstream) |
| `components/sst/` | [`LICENSE`](components/sst/LICENSE) | Apache-2.0 (added at publication; pyproject already stated it) |
| `components/entorhinal/` | [`LICENSE`](components/entorhinal/LICENSE) | Apache-2.0 (added at publication) |
| `components/reflex/` | [`LICENSE`](components/reflex/LICENSE) | Apache-2.0 (added at publication) |

Apache-2.0 here covers this project's code; it does not relicense
third-party material. Third-party code, data, and model terms shipped
inside components keep their own licenses, copyright notices, and
attribution exactly as found, as documented in the component READMEs;
no license text or copyright notice was removed from any directory.

