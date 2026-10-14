# ANIMA code tour

Start at the root, then read one component at a time. Every component is
self-contained, so the order below is by increasing dependency weight, not
by coupling.

## Root

- [`src/anima/__init__.py`](../src/anima/__init__.py) — the whole namespace
  package: `_COMPONENTS` maps each alias to its distribution import name;
  `components()` reports importability. The sibling modules
  (`substrate.py`, `sst.py`, `stc.py`, `entorhinal.py`, `reflex.py`) are
  same-object re-exports.
- [`tests/test_import_map.py`](../tests/test_import_map.py) — root smoke
  tests pinning the alias/native import map.
- [`examples/quickstart.py`](../examples/quickstart.py) — runnable root
  example: availability report plus a real substrate journey.
- [`requirements/components-all.txt`](../requirements/components-all.txt) —
  editable install of the root plus all five components.

## substrate (`anima_substrate`, stdlib-only)

- [`components/substrate/examples/quickstart.py`](../components/substrate/examples/quickstart.py)
  — the guided journey: init -> participant run -> relate ->
  close/reopen byte-verify -> recover -> settle.
- `src/anima_substrate/host/` — run-root host API (`api.init_run`,
  snapshots, settle); `participants/` — pinned participant families such
  as `relcheck`; `cli.py` — the `anima-substrate` command;
  `accept/` and `demos/` — acceptance packs and demos.
- Tests: `components/substrate/tests/`.

## sst (`sst`)

- `src/sst/search/` — the dialectic MCTS search loop; `core/` — state and
  node types; `sandbox/` — deterministic gate verification; `storage/` —
  event-sourced persistence; `cli/` — the `sst` command; `gateway/`,
  `context/`, `prompts/`, `protocols/` — model access and prompt/context
  plumbing; `ui/` and `visualizer/` — live DAG views.
- Tests: `components/sst/tests/`. See the component README for the
  diverge/refine/verify/synthesize phase diagram.

## stc (`stc`)

- `src/stc/socratic/` — spec intake and decomposition; `compiler/` and
  `memory/` — context compilation and retrieval; `worktree/` — git
  worktree leases; `substrate/` — deterministic quality gates;
  `judiciary/` — blind verification; `orchestrator/`, `services/`,
  `integration/` — pipeline wiring; `schemas/`, `protocols/`, `core/` —
  shared types; `genome/` — verified-solution reuse; `cli.py` — the
  `stc` command.
- `components/stc/examples/sample_spec.yaml` — a sample input spec.
- Tests: `components/stc/tests/`.

## entorhinal (`entorhinal`)

- `src/entorhinal/cli/` — the `entorhinal` Typer command (`status`,
  `inspect`, `grants`, `audit`, `serve`); `ingest/` and `sources/` —
  evidence intake; `temporal/` and `projections/` — multi-timescale
  context compilation; `query/` — snapshot serving; `user_control/` and
  `policy/` — corrections, consent, cascade deletion; `api/` — the
  loopback FastAPI daemon; `fixtures/` — synthetic evaluation fixtures;
  `evals/` and `tool_qualification/` — evaluation harnesses.
- Start with [`docs/BUILDER-AUTHORITY-BOUNDARY.md`](../components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md)
  for the data-handling boundary. Tests: `components/entorhinal/tests/`.

## reflex (`reflex`)

- `components/reflex/main.py` — computer-use console entry point (there
  is no console script).
- `src/reflex/perception/` and `grounding/` — affordance detection and
  spatial grounding; `cognition/` and `agent/` — decision loop;
  `execution/` and `host/` — acting on the host; `verification/` —
  post-action checks; `episodes/`, `evals/` — episode records and
  evaluation; `service/`, `ports/`, `integrations/`, `schemas/` —
  service surface and shared types.
- Read `REFLEX-AMBITION.md` and `ARCHITECTURE.md` in the component root
  for design intent (research/seed stage). Tests:
  `components/reflex/tests/`.
