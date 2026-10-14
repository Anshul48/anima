# ANIMA

[![CI](https://github.com/Anshul48/anima/actions/workflows/ci.yml/badge.svg)](https://github.com/Anshul48/anima/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

![ANIMA component overview: five cards for substrate, SST, STC, entorhinal, and reflex](assets/anima-overview.svg)

Reusable research components for attributable local computation: persistent
project worlds ([substrate](components/substrate/)), heuristic search
([sst](components/sst/)), spec-to-code engineering ([stc](components/stc/)),
advisory temporal context ([entorhinal](components/entorhinal/)), and
vision/perception for computer use ([reflex](components/reflex/)).

Each component is independently installable, runnable, and tested under its
own distribution name. This repository claims no runtime integration beyond
that: there is no shared server, no cross-component wiring, and no hosted
service here. Shared background and proposals live in
[docs/anima/](docs/anima/).


## Capabilities

| Component | Install | Capability | Start here |
|---|---|---|---|
| substrate | `pip install -e components/substrate` | Persistent project worlds with pinned participants and crash-atomic local state (stdlib-only) | [components/substrate/](components/substrate/) |
| sst | `pip install -e components/sst` | Heuristic search: asymmetric dialectic MCTS with deterministic gate verification | [components/sst/](components/sst/) |
| stc | `pip install -e components/stc` | Spec-to-code engineering: Socratic intake, worktree leases, quality gates, blind judiciary | [components/stc/](components/stc/) |
| entorhinal | `pip install -e components/entorhinal` | Advisory temporal context: evidence recording, multi-timescale projections, user-controlled snapshots | [components/entorhinal/](components/entorhinal/) |
| reflex | `pip install -e components/reflex` | Vision/perception for computer use: affordance detection and crop escalation | [components/reflex/](components/reflex/) |

## Quickstart

The fastest end-to-end check installs the namespace package plus the
stdlib-only substrate component, then runs a real substrate journey
(participant run, byte-identical close/reopen, recovery):

```bash
pip install -e . -e components/substrate
python examples/quickstart.py   # ends with: ANIMA quickstart OK
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit
together and [docs/CODE-TOUR.md](docs/CODE-TOUR.md) for where to start
reading each component.

## Architecture

![ANIMA repository architecture: the anima alias package over five independent distributions](assets/anima-architecture.svg)

The [`anima` alias package](src/anima/) re-exports the five native
distributions as same-object convenience aliases (`anima.substrate`,
`anima.sst`, ...). Native imports (`import anima_substrate`, `import sst`,
...) are primary; the diagram arrows are import aliases, not data flow.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architecture guide and [docs/anima/architecture/](docs/anima/architecture/) for background proposals.

## Layout

```
anima/
  components/substrate/    anima-substrate 0.1.1 — stdlib-only world host
  components/sst/          sst-engine 0.1.0 — dialectic MCTS search
  components/stc/          stc 0.1.0 — spec-to-code engine
  components/entorhinal/   entorhinal 0.1.0 — advisory temporal context
  components/reflex/       reflex 0.1.0 — perception / computer use
  src/anima/               convenience alias modules (anima.sst, ...)
  docs/anima/              curated ANIMA context, proposals, catalogue pins
  tests/                   import-map smoke tests
```

## Install

Python 3.12+ recommended (substrate alone works on 3.11+). From the repo root:

```bash
# one component (example)
pip install -e components/substrate

# everything, plus the anima alias package
pip install -r requirements/components-all.txt
```

`uv` works too (`uv pip install -e components/sst`, ...). Components
[sst](components/sst/)/[stc](components/stc/) ship their frozen `uv.lock`
files from the pinned release commits below.

## Import map

Native distribution imports are primary; `anima.<component>` modules are
same-object convenience aliases (see [src/anima/](src/anima/)):

| Alias | Distribution | Native import |
|---|---|---|
| `anima.substrate` | `anima-substrate` | `import anima_substrate` |
| `anima.sst` | `sst-engine` | `import sst` |
| `anima.stc` | `stc` | `import stc` |
| `anima.entorhinal` | `entorhinal` | `import entorhinal` |
| `anima.reflex` | `reflex` | `import reflex` |

```python
import anima
anima.components()   # {'entorhinal': ..., 'reflex': ..., ...} availability

import anima.substrate
anima.substrate.__name__  # 'anima_substrate'
```

Use native imports for deep submodule access (e.g. `import sst.cli`).
Note: the `reflex` import name collides with the unrelated Reflex web
framework on PyPI — do not install both in one environment.

## Run

Substrate is stdlib-only and the quickest check:

```bash
pip install -e components/substrate
python components/substrate/examples/quickstart.py
anima-substrate --help
pytest components/substrate/tests/ -q
```

Each component's README documents its own CLIs, examples, and test suites;
start there. Root smoke tests: `pytest tests/ -q` (no components needed).
The root [examples/quickstart.py](examples/quickstart.py) goes beyond
the alias map: it reports component availability and drives a real
substrate participant run with byte-identical close/reopen.

## Scope

This repository ships the five components, the alias package, tests, and
curated background docs only: no unified runtime or hosted service, and
no private data, credentials, model weights, or datasets. The exact
include/exclude lists and provenance are in [MANIFEST.md](MANIFEST.md);
see [SECRET-SCAN.md](SECRET-SCAN.md) for the secret-scan record.

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

Upstream remotes: `anima-substrate`, `entorhinal`, `relfex`,
`utilities-sst` (all `github.com/Anshul48/...`); stc has no remote
configured. Per-file history stays in those sources; this repo starts fresh.

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
