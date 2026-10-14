# ANIMA architecture

ANIMA is a mono-repo of five independently installable Python components
plus a thin namespace package. There is deliberately **no shared runtime**:
no common server, no cross-component imports, and no orchestration layer.
Each component can be installed, run, and tested alone under its own
distribution name.

![ANIMA repository architecture: the anima alias package over five independent distributions](../assets/anima-architecture.svg)

## Layers

1. **Namespace package** ([`src/anima/`](../src/anima/), distribution
   `anima`): convenience aliases only. `anima.<component>` *is* the native
   component module (same object, re-exported), and
   `anima.components()` reports which distributions are importable.
   Native imports (`import anima_substrate`, `import sst`, ...) are the
   primary form, especially for deep submodules such as `sst.cli`.
2. **Components** ([`components/`](../components/)): five self-contained
   packages, each with its own `pyproject.toml`, README, source tree under
   `src/`, and test suite.
3. **Shared background** ([`docs/anima/`](anima/)): curated proposals,
   catalogue pins, and reading-room material. This is documentation, not
   code the components load at runtime.

## Components

| Component | Distribution | Native import | What it does | Entry points |
|---|---|---|---|---|
| [substrate](../components/substrate/) | `anima-substrate` 0.1.1 | `anima_substrate` | Offline, stdlib-only host for persistent project worlds: pinned participants, delegated budgets, crash-atomic state in a caller-selected directory | `anima-substrate` CLI; `examples/quickstart.py` |
| [sst](../components/sst/) | `sst-engine` 0.1.0 | `sst` | Heuristic search: asymmetric dialectic MCTS (diverge / refine / gate-verify / synthesize) over a state-space tree with event-sourced persistence | `sst` CLI |
| [stc](../components/stc/) | `stc` 0.1.0 | `stc` | Spec-to-code engineering engine: Socratic intake, bounded context compilation, worktree leases, deterministic quality gates, blind judiciary verification | `stc` CLI |
| [entorhinal](../components/entorhinal/) | `entorhinal` 0.1.0 | `entorhinal` | Local-first advisory temporal context: records task evidence, compiles multi-timescale projections, serves context snapshots under user control (corrections, consent, cascade deletion, audit) | `entorhinal` CLI (Typer); optional loopback FastAPI `entorhinal serve` |
| [reflex](../components/reflex/) | `reflex` 0.1.0 | `reflex` | Vision/perception for computer use: spatial affordance detection, relevance filtering, and escalation of small crops to heavier models | `python components/reflex/main.py` (no console script) |

## Dependency rules

- Components never import each other; the arrows in the diagram are
  import *aliases* in the namespace package, not data flow.
- `substrate` has zero runtime dependencies (stdlib only). Other
  components declare their own dependencies in their own
  `pyproject.toml`; `sst` and `stc` also ship frozen `uv.lock` files.
- State always lives in caller-selected directories, never inside an
  installed package.

## Further reading

- [Code tour](CODE-TOUR.md) — where to start reading each component.
- [`docs/anima/architecture/`](anima/architecture/) — background proposals
  and responsibility notes that motivated the components (historical
  context, not a description of shipped wiring).
- Component READMEs are the authoritative per-component guides.
