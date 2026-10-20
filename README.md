# ANIMA

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)


![ANIMA component overview: five cards for substrate, SST, STC, entorhinal, and reflex](assets/anima-overview.svg)

> **Research preview.** ANIMA is experimental research shared early for
> feedback. It is not a production runtime, not a hosted service, and
> not a benchmark champion — just working code with measured numbers.


**Superintelligence won't come from a bigger model alone. ANIMA externalizes intelligence into the environment — persistent worlds, heuristic search, spec-to-code construction, advisory memory, computer-use perception — running locally, budgeted, and attributable today.**

**New here? [Watch the overview film](https://anshul48.github.io/anima/)** — then run the quickstart below and end with `ANIMA quickstart OK`.

[Watch it](#watch-it) · [Try it](#quickstart) · [Proof](#proof-one-line) · [Components](#what-exists-today) · [Deep dive](#deep-dive)

## What you can do with it today

- **Run a persistent world** — the stdlib-only substrate pins participants, delegates explicit budgets, and reopens crash-atomic state byte-identically. One script, `ANIMA quickstart OK` at the end.
- **Search before you spend** — SST runs heuristic dialectic-MCTS and refuses to promote unless the verifier passed on the exact logged bytes.
- **Turn specs into gated code** — STC compiles task bundles under a strict 25 KB ceiling through deterministic gates plus blind judiciary review and a human promotion gate.
- **Remember without risk** — entorhinal serves advisory context snapshots with zero autonomous mutation authority; everything is audit-logged under your control.
- **See and click** — reflex works toward computer-use perception (seed stage: its figures are hypotheses to measure, not commitments).
- **Browse the live pages** — [overview](https://anshul48.github.io/anima/) · [substrate](https://anshul48.github.io/anima/substrate.html) · [sst](https://anshul48.github.io/anima/sst.html) · [stc](https://anshul48.github.io/anima/stc.html) · [entorhinal](https://anshul48.github.io/anima/entorhinal.html) · [reflex](https://anshul48.github.io/anima/reflex.html) — each with its film and live interactive twin.

## Watch it

- 🎬 **[Overview film](https://anshul48.github.io/anima/)** — what ANIMA is and what each component does, in about a minute. Video file `docs/assets/anima.mp4` (720p H.264, captions + transcript on the page; voice is synthetic).
- 🎬 **Component films** — one per page: `substrate`, `sst`, `stc`, `entorhinal`, `reflex` under `docs/assets/`, embedded with live interactive twins above the fold.
- 🖱️ **Live interactive twins** — every page pairs its film with something you can click: the substrate journey, search traces, gate pipelines, advisory snapshots.

## Proof (one line)

Five local-first components, every suite green, on a frozen 10M-token memory — receipts in [TEST-REPORT.md](TEST-REPORT.md) and [docs/TRACE-REPRODUCE.md](docs/TRACE-REPRODUCE.md).

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

> **Note on PyPI name collision**: The native import name `reflex` collides with the unrelated Reflex web framework on PyPI. Do not install both into the same Python environment.


All suites green on CPython 3.12.3 — full counts in [TEST-REPORT.md](TEST-REPORT.md); per-component guides are authoritative. Verify it yourself:

```bash
# Run root namespace import smoke tests:
pytest tests/ -q

# Run substrate component test suite (stdlib-only):
pytest components/substrate/tests/ -q

# Run root quickstart verification:
python examples/quickstart.py
```

CI workflows run automatically on push and pull requests as defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Who it is for

- **Agent builders** who want worlds with explicit custody: pinned
  participants, delegated budgets, and crash-atomic state instead of
  hidden global state. Built for local, attributable execution — use
  substrate to explore it.
- **Multi-model orchestrators** who want search, construction, and
  memory budgeted as separate concerns: SST for heuristic search with
  deterministic promotion gates, STC for bounded spec-to-code bundles,
  entorhinal for advisory context that can never mutate on its own.
- **Cost-conscious teams**: budgets are explicit before work runs, so
  model spend is attributable per participant and per task.

## TRACE: the memory layer

TRACE is ANIMA's memory layer: one frozen, receipt-backed 10M-token build (seam12a, run o94-scale10m) — 10M tokens, ~8.5 GB peak, self-repairing. Numbers live in [docs/TRACE-REPRODUCE.md](docs/TRACE-REPRODUCE.md); the system lives at [github.com/Anshul48/trace](https://github.com/Anshul48/trace) with its [live explorer](https://anshul48.github.io/trace/explorer/).

## Vision (direction — not shipped)

> The dream is a dynamic substrate that rewires itself while it runs:
> worlds that split, merge, and quarantine organizations the way cells
> divide and immune systems isolate; software that literally evolves
> like biology — variation under search, selection under deterministic
> gates, inheritance through versioned genomes of verified code. A cost
> cascade keeps that evolution affordable: a frontier model decides
> rarely, a coordinator budgets, swarms of cheap models do the abundant
> work. Everything in this section is direction, not a claim about what
> exists — the composition it describes is a proposal today, not shipped
> wiring.

## Deep dive

How each piece works lives behind these links: [substrate
guide](components/substrate/README.md), [SST
guide](components/sst/README.md), [STC
guide](components/stc/README.md), [entorhinal
guide](components/entorhinal/README.md), [reflex
guide](components/reflex/README.md), [architecture
guide](docs/ARCHITECTURE.md), [code
tour](docs/CODE-TOUR.md), and background proposals in
[docs/anima/](docs/anima/).

Maturity, scope, roadmap outlook, and provenance live in [docs/ROADMAP.md](docs/ROADMAP.md); the GitHub About text in [docs/ABOUT.md](docs/ABOUT.md); illustration prompts in [docs/image-prompts.md](docs/image-prompts.md). Shared tokens:
[docs/assets/design.css](docs/assets/design.css),
[docs/assets/motion.js](docs/assets/motion.js).

## Contributing & Security

- **Contributing**: Contributions and workflow guidelines are documented in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security**: Security posture, disclosure procedures, and authority boundaries are documented in [SECURITY.md](SECURITY.md) and [components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md](components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md).
- **Code Tour & Architecture**: See [docs/CODE-TOUR.md](docs/CODE-TOUR.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for navigation guides.

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

