# ANIMA

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

## Boundaries (what is NOT here)

- No unified runtime, orchestration, or hosted integration between
  components; no claim that any exists.
- No private data: live stores, timelines, tracked events, captured traces,
  consented corpora, run logs, credentials, or `.env` files are excluded.
  See [SECRET-SCAN.md](SECRET-SCAN.md) and
  [components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md](components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md).
- No browser/editor extensions, no JS plugin runtimes (STC's `DSH_PIN` and
  contract files ship; pilot evidence and `node_modules` do not), no frozen
  model weights, no datasets.
- `docs/anima/` is a curated subset: proposals, syntheses, reading room,
  module catalogue and freeze pins. Operational coordination records, live
  progress logs, verbatim message archives, and session conversation records
  are excluded. See [MANIFEST.md](MANIFEST.md) for the exact include/exclude
  lists and provenance.

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

## License status (per component, as found upstream)

No license text was added or changed in staging. Each directory keeps
exactly what its source carried:

| Path | License file | Terms |
|---|---|---|
| `components/substrate/` | `LICENSE` (Apache-2.0) | Apache-2.0 |
| `components/stc/` | `LICENSE` (Apache-2.0) | Apache-2.0 |
| `components/sst/` | none (pyproject *states* Apache-2.0; README badge notes unlicensed, links nowhere) | unlicensed as shipped — owner to confirm |
| `components/entorhinal/` | none | unlicensed as shipped — owner to confirm |
| `components/reflex/` | none | unlicensed as shipped — owner to confirm |
| repo root / `src/anima/` / docs | none | staging files; owner to license |

Until the owner adds terms, unlicensed paths are all-rights-reserved by
default even though visible here.
