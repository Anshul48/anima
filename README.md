# ANIMA — the map of a mind

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)


![ANIMA component overview: five cards for substrate, SST, STC, entorhinal, and reflex](assets/anima-overview.svg)

> **Research preview.** ANIMA is experimental research shared early for
> feedback. It is a map, not a machine: it shows how five working parts fit
> together, and it is honest about what runs and what is still drawn.

**One wrong total. One morning to fix it. Five helpers — and every step keeps its receipt.**

Maya's bakery till rings $14 as $41. The fix travels the map: **remember** how the total was built, **argue** two fixes until one survives, **build** in a workspace that survives force-quit, **check** until a signed proof is issued, and one day — **act**, with eyes that verify every click. That last stop is a seed: drawn, not built.

**New here? [Watch the story](https://anshul48.github.io/anima/)** (two short films, plain words) — then run the quickstart below and end with `ANIMA quickstart OK`.

[Watch it](#watch-it) · [Try it](#quickstart) · [Proof](#proof-one-line) · [Helpers](#what-exists-today) · [Deep dive](#deep-dive)

## What you can do with it today

- **Survive the crash** — substrate workspaces reopen with every byte intact after a real force-quit (the harshest kill — no goodbyes), then merge, split, or move. One script, `ANIMA quickstart OK` at the end.
- **Let drafts argue** — SST debates candidate fixes against strict checks; losers stay visible and the survivor becomes the fix.
- **Demand the receipt** — STC packs work into small capped packages, runs four strict checks plus an independent audit, and merges only when the signed proof verifies.
- **Get briefed, not watched** — entorhinal whispers short expiring briefs with a receipt per line; it can change nothing and keeps an audit trail.
- **Glimpse the seed** — reflex aims for cheap-eyes-first computer use (early build: its speed figures are hopes to measure, not commitments).
- **Browse the live pages** — [story](https://anshul48.github.io/anima/) · [substrate](https://anshul48.github.io/anima/substrate.html) · [sst](https://anshul48.github.io/anima/sst.html) · [stc](https://anshul48.github.io/anima/stc.html) · [entorhinal](https://anshul48.github.io/anima/entorhinal.html) · [reflex](https://anshul48.github.io/anima/reflex.html) — each with its film and something you can click.

## Watch it

- 🎬 **[ANIMA films](https://anshul48.github.io/anima/)** — How (73 s): the wrong total travels five stops; Do (59 s): the same map lit by truth, ending where you can touch it. Files `docs/assets/anima-how/do.mp4` (720p H.264, captions on the page; voice is synthetic).
- 🎬 **Helper films** — a How + Do pair per page: `substrate`, `sst`, `stc`, `entorhinal`, `reflex` under `docs/assets/`, each with posters + captions, no autoplay.
- 🖱️ **Always something moving** — every page pairs its film with living visuals: the traveling story, the clickable map, crash-and-merge loops, debates, inspections.

## Proof (one line)

Five helpers that run on your own machine, every suite green, beside a frozen 10M-memory map — receipts in [TEST-REPORT.md](TEST-REPORT.md) and [docs/TRACE-REPRODUCE.md](docs/TRACE-REPRODUCE.md).

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

Five independently installable research helpers plus a thin alias
namespace. There is no shared server, no cross-component wiring, and
no hosted service here. Shared background and proposals live in
[docs/anima/](docs/anima/).

### Helpers

| Helper | Distribution | Status (plain words) | Guide |
|---|---|---|---|
| [substrate](components/substrate/) | `anima-substrate` 0.1.1 | Early research build: workspaces that survive force-quit; suite green (counts in TEST-REPORT.md) | [Component README](components/substrate/README.md) |
| [sst](components/sst/) | `sst-engine` 0.1.0 | Debates with rehearsal stand-ins; suite green and matching its frozen copy; real-model debates need your key | [Component README](components/sst/README.md) |
| [stc](components/stc/) | `stc` 0.1.0 | Plans in, signed proof out; four checks + smoke re-verified here; big badge counts are upstream claims, not re-runs | [Component README](components/stc/README.md) |
| [entorhinal](components/entorhinal/) | `entorhinal` 0.1.0 | Whispering briefs from your own machine; zero power to change anything; identity check green | [Component README](components/entorhinal/README.md) |
| [reflex](components/reflex/) | `reflex` 0.1.0 | Early seed: speed and cost figures are hopes to measure; the privacy scrubber is the one green chip | [Component README](components/reflex/README.md) |

Component READMEs are the authoritative per-component guides. Native
imports (`import anima_substrate`, `import sst`, ...) are primary;
`anima.<component>` modules are same-object convenience aliases.

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

- **Agent builders** who want workspaces with explicit custody: saved
  work, clear budgets, and crash-proof state instead of hidden global
  state. Built for local, attributable execution — use substrate to
  explore it.
- **Multi-model orchestrators** who want arguing, checking, and
  remembering as separate budgeted concerns: SST for debates with
  strict approval, STC for small capped work packages with signed
  proof, entorhinal for briefs that can never change anything on
  their own.
- **Cost-conscious teams**: budgets are explicit before work runs, so
  model spend is attributable per helper and per task.

## TRACE: the memory layer

TRACE is ANIMA's memory layer: one frozen, receipt-backed 10M-token build (codenamed seam12a) — ten million filed memories (a token is a small piece of text) with replayable paths and a measured found-it score. Numbers live in [docs/TRACE-REPRODUCE.md](docs/TRACE-REPRODUCE.md); the system lives at [github.com/Anshul48/trace](https://github.com/Anshul48/trace) with its [live replay](https://anshul48.github.io/trace/play/) and [explorer](https://anshul48.github.io/trace/explorer/).

## Vision (direction — not shipped)

> The dream is a living workshop that rewires itself while it runs:
> workspaces that split, merge, and seal off problems the way cells
> divide and immune systems isolate; software that improves the way
> gardens do — many seedlings tried, only the proven kept, seeds of
> verified work replanted. A cost cascade keeps that growth
> affordable: the sharpest model decides rarely, a coordinator
> budgets, swarms of cheap models do the abundant work. Everything
> in this section is direction, not a claim about what exists — the
> composition it describes is a proposal today, not shipped wiring.

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

Maturity, scope, roadmap outlook, and history live in [docs/ROADMAP.md](docs/ROADMAP.md); the GitHub About text in [docs/ABOUT.md](docs/ABOUT.md); illustration prompts in [docs/image-prompts.md](docs/image-prompts.md). Shared tokens:
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
