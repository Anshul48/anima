# ANIMA

[![CI](https://github.com/Anshul48/anima/actions/workflows/ci.yml/badge.svg)](https://github.com/Anshul48/anima/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

![ANIMA component overview: five cards for substrate, SST, STC, entorhinal, and reflex](assets/anima-overview.svg)

## What ANIMA is

ANIMA is a collection of reusable research components for attributable
local computation: persistent project worlds, heuristic search,
spec-to-code engineering, advisory temporal context, and computer-use
perception. The direction they serve is neuro-symbolic scaffolds for
externalized cognition — durable symbolic structure (worlds, budgets,
specs, evidence, audit trails) around model-driven search and synthesis,
with a cost model that keeps architect decisions, coordinator
scheduling, and swarm model calls separately budgeted and attributable.

That composition is a proposal today, not shipped wiring. What this
repository actually ships is five independently installable components
plus a thin alias namespace: there is no shared server, no
cross-component wiring, and no hosted service here. Shared background
and proposals live in [docs/anima/](docs/anima/).

## Status

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

## Constraints

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

## Modules

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

## Packaging & Import Structure

The repository contains six distinct distribution packages across six `pyproject.toml` files: one root alias package and five independent component packages.

The root package `anima` exposes convenience import aliases only, mapping directly to five native packages:

| Alias | Distribution Name | Native Import Name | Component Directory | Description |
|---|---|---|---|---|
| `anima.substrate` | `anima-substrate` (0.1.1) | `import anima_substrate` | [`components/substrate/`](components/substrate/) | Persistent project worlds, pinned participants, crash-atomic local state (stdlib-only) |
| `anima.sst` | `sst-engine` (0.1.0) | `import sst` | [`components/sst/`](components/sst/) | Asymmetric dialectic MCTS heuristic search engine |
| `anima.stc` | `stc` (0.1.0) | `import stc` | [`components/stc/`](components/stc/) | Biomimetic spec-to-code autonomous engineering engine |
| `anima.entorhinal` | `entorhinal` (0.1.0) | `import entorhinal` | [`components/entorhinal/`](components/entorhinal/) | Local-first advisory temporal context (evidence, projections, user-controlled snapshots) |
| `anima.reflex` | `reflex` (0.1.0) | `import reflex` | [`components/reflex/`](components/reflex/) | Autonomous computer-use vision & perception (fast spatial affordances & crop routing) |

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

## TRACE: the memory layer (frozen seam12a 10M build)

TRACE is the memory layer for this ecosystem: an experimental retrieval
architecture that organizes continuous document streams into an
overlapping multi-tier DAG without global clustering recomputation. The
frozen build below is measured, not projected. Live explorer:
[anshul48.github.io/trace/explorer/](https://anshul48.github.io/trace/explorer/).
Source: [github.com/Anshul48/trace](https://github.com/Anshul48/trace).

Freeze identity (pinned): **seam12a**, tarball sha256
`8d3bbb6bf53e1731811065a9de156a9997be740d598cd1dfa0a3d946928dbf64`,
run **o94-scale10m**, probes `b332d62d...`, harness `9f78479a...`,
final commits `164195`. The freeze holds 253 files (`frozen_ok=true`).

Measured numbers (receipt-quoted): 10003381 tokens, 13081 docs, 63441
atoms, 5353 source commits, 164195 final commits. Guided recall@10
0.7367 all / 0.4883 LSO (120 probes across chunk/noisy/cross
families); flat recall@10 0.055 / 0.0017. Repair ran 6 iterations,
5847 to 0, with 0 pending. Query-complete latency p50/p95 96.8/115.5 ms
(n=33, all within 5 s); append ack-to-query 0.114 s; 27796 reader
requests over 2 threads at p50 74.7 ms. Wall 9494.9 s; RSS peaks tree
9700.9 MiB (transient, at t=3097 s) / parent 8489.1 / child 7169.2
MiB; 2.85 GiB retained on disk (VM-side figures). No broad-benchmark
or state-of-the-art claim is made: this is the project team's
prototype evaluation protocol, nothing more.

### Run the frozen build (quickstart, verified 2026-10-18)

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

### Full-10M reproduction: two blockers, no one-click path today

A full 10M-token reproduction is blocked by two facts, and there is no
one-click 10M repro today: (a) the external corpus `docs-100m.jsonl`
plus its embedding cache is absent — the 1.2 MB freeze tarball is
source-only and ships no dataset; (b) the `--profile vm` path exits
unless the hostname is `trace-build500`
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

## Installation & Environment

The root metadata targets Python `>=3.11` (and `substrate` alone runs on stdlib-only Python 3.11+). However, running all five components requires Python 3.12+. From the repository root:

```bash
# Install a single component (e.g. substrate, stdlib-only):
pip install -e components/substrate

# Install all components plus the anima alias package:
pip install -r requirements/components-all.txt
```

Alternatively, Astral's [`uv`](https://github.com/astral-sh/uv) can be used:
```bash
uv pip install -e . -e components/substrate
```
Components [sst](components/sst/) and [stc](components/stc/) also provide frozen `uv.lock` files from their pinned releases.

## Component Guides & Verified Usage

### 1. `substrate` (`anima-substrate`) — Persistent Project Worlds

Offline, stdlib-only host for persistent project worlds. Manages pinned participant families, delegated budgets, and crash-atomic state in a caller-selected directory with zero external runtime dependencies.

* **Install**: `pip install -e components/substrate`
* **CLI Quickstart**:
  ```bash
  anima-substrate --help
  anima-substrate families
  ```
* **Python API**:
  ```python
  import tempfile, pathlib, json, hashlib
  from anima_substrate.host import api
  from anima_substrate.participants import get_family

  work = pathlib.Path(tempfile.mkdtemp(prefix="sub-demo-"))
  state = work / "state"
  api.init_run(state)

  tree = work / "release"
  tree.mkdir(parents=True)
  (tree / "app.py").write_text("print('hello')\n")
  manifest = work / "pins.json"
  manifest.write_text(json.dumps({
      "manifest_version": 1,
      "release": "v1",
      "files": {"app.py": hashlib.sha256(b"print('hello')\n").hexdigest()}
  }))

  fam = get_family("relcheck", "v1")
  fam.create(state, "RC1", {}, "runner")
  rep = fam.run(state, "RC1", {
      "task_id": "T1",
      "manifest_path": str(manifest),
      "tree_root": str(tree)
  })
  print("relcheck valid:", rep["valid"])
  ```

---

### 2. `sst` (`sst-engine`) — Dialectic MCTS Heuristic Search

Dialectic MCTS heuristic tree search engine discovering verified code implementations via asymmetric rollouts: high-entropy divergent planning, low-entropy monotropic refinement, deterministic gate verification, and value synthesis.

* **Install**: `pip install -e components/sst`
* **Runtime Requirements**: Local search data structures and budget policies run purely locally. Model-driven tree rollouts require either local Ollama models (`ollama run ...`) or external LLM provider configurations.
* **CLI Commands**:
  ```bash
  # Display CLI help and subcommands
  sst --help

  # Execute bounded MCTS search with acceptance test verification
  sst run --help

  # Launch Cytoscape.js DAG visualizer or task UI
  sst visualize --help
  sst ui --help
  ```
* **Python API**:
  ```python
  from sst.core import SSTNode, NodeRole, NodeStatus, DomainMode, PayloadType
  from sst.search.policy import BudgetTracker

  tracker = BudgetTracker()
  node = SSTNode(
      tree_id="tree_demo",
      node_id="node_root",
      parent_id=None,
      depth=0,
      role=NodeRole.PLANNER,
      domain=DomainMode.AUTOBUILD,
      title="Goal: Fast Parser",
      payload_type=PayloadType.GOAL,
      content="Synthesize verified parser",
      status=NodeStatus.UNEXPANDED
  )
  print(f"SST Node created: id={node.node_id}, role={node.role.value}")
  ```

---

### 3. `stc` (`stc`) — Spec-To-Code Autonomous Engineering

Autonomous engineering engine implementing biomimetic separation of concerns: Socratic spec intake, bounded context compilation (strict <= 25 KB task bundles), ephemeral Git worktree leases, and deterministic quality gates (Ruff, Mypy Strict, Pytest, Mutmut).

* **Install**: `pip install -e components/stc`
* **Runtime Requirements**: Local decomposition, bundle compilation, and worktree leases run offline with git. Full worker execution uses local tool harnesses (such as Aider/Agy) and configured models.
* **CLI Commands**:
  ```bash
  # Inspect runtime environment and invariants
  stc info
  stc health

  # Compile an atomic sub-25KB task bundle from a spec
  stc compile TASK-001 --spec components/stc/examples/sample_spec.yaml

  # Manage ephemeral Git worktree leases
  stc worktree lease --help
  stc worktree list
  ```
* **Python API**:
  ```python
  import hashlib
  from stc.schemas.models import SpecAtom
  from stc.socratic import SocraticDecomposer

  raw_spec = "Goal: Implement secure token validator.\nInvariants: Must reject expired tokens.\n"
  spec = SpecAtom(
      spec_id="SPEC-001",
      source_path="inline",
      raw_content=raw_spec,
      content_sha256=hashlib.sha256(raw_spec.encode()).hexdigest()
  )
  decomposer = SocraticDecomposer()
  toc = decomposer.decompose(spec)
  print("Socratic ambiguity score:", toc.ambiguity_score)
  print("Domain invariants:", toc.domain_invariants.invariants)
  ```

---

### 4. `entorhinal` (`entorhinal`) — Local-First Advisory Temporal Context

Local-first temporal context engine: records task evidence, compiles multi-timescale projections, serves context snapshots to local consumers, and enforces cryptographic hash-chained audit trails, user corrections, and cascade deletion. Operates strictly under advisory authority (zero autonomous mutation authority).

* **Install**: `pip install -e components/entorhinal`
* **Runtime Requirements**: Evidence logging, audit querying, and retention policies run on local SQLite. AI projection distillation optionally integrates with local Ollama (`qwen3.8:27b`, `nomic-embed-text`) or external providers.
* **CLI Commands**:
  ```bash
  # Inspect measured health and projection state
  entorhinal status

  # Inspect real-time chronological evidence timeline
  entorhinal inspect timeline

  # Audit access grants and consumer query logs
  entorhinal audit

  # Display local loopback FastAPI daemon options
  entorhinal serve --help

  # Bootstrap and inspect HTTP principal credentials
  entorhinal auth --help
  ```
  *(Note: Demo and test paths operate unauthenticated by design, printing an advisory banner. Serving over HTTP requires authenticated credentials managed via `entorhinal auth` or [`AuthStore`](components/entorhinal/src/entorhinal/runtime/auth.py); see [components/entorhinal/README.md](components/entorhinal/README.md) and [docs/BUILDER-AUTHORITY-BOUNDARY.md](components/entorhinal/docs/BUILDER-AUTHORITY-BOUNDARY.md))*.
* **Python API (Offline Policy & Auth Store Example)**:
  ```python
  import tempfile, pathlib
  from entorhinal.policy.engine import PolicyEngine
  from entorhinal.runtime.auth import AuthStore, ROLE_ADMIN

  # Offline consent rule registration (does not initialize server runtime)
  engine = PolicyEngine()
  rule_id = engine.add_consent_rule(allow=True, priority=10)
  print("Consent rule registered:", rule_id)

  # Principal credential configuration in a temporary auth store
  with tempfile.TemporaryDirectory() as tmpdir:
      store = AuthStore(pathlib.Path(tmpdir) / "auth.json")
      principal, secret = store.create_principal(role=ROLE_ADMIN, principal_id="admin-demo")
      authenticated = store.authenticate(secret)
      print("Configured principal:", authenticated.principal_id, "role:", authenticated.role)
  ```

---

### 5. `reflex` (`reflex`) — Computer-Use Vision & Perception

System 1 vision and perception engine designed for autonomous computer-use workflows: fast spatial affordance detection, cheap relevance filtering, and targeted escalation of small crops to heavier vision models instead of forwarding entire high-resolution desktop frames.

* **Install**: `pip install -e components/reflex`
* **Runtime Requirements**: Computer-use console uses a mock window manager substrate on Linux/CI environments (`--mock`). Real desktop interaction targets Windows desktop environments.
* **CLI Quickstart**:
  ```bash
  # Display Jarvis computer-use console help
  python components/reflex/main.py --help

  # Run automated demonstration in mock window mode (offline safe)
  python components/reflex/main.py --mock --demo
  ```
* **Python API**:
  ```python
  from reflex.perception.vision.vision_grounder import MockVisionGrounder

  grounder = MockVisionGrounder()
  print("Reflex VisionGrounder initialized:", grounder.__class__.__name__)
  ```

---

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

## Roadmap

Labeled outlook only — none of this is claimed as shipped:

- **TRACE scale-up (100M+ tokens)**: the frozen seam12a build above is
  a 10M-token measurement; larger corpora need a fetchable dataset and
  a reproducible large-machine path first.
- **Composed worlds**: running substrate worlds with SST search, STC
  construction, entorhinal memory, and TRACE retrieval under one
  budgeted arrangement is the stated direction in
  [docs/anima/](docs/anima/), not a qualified integration today.
- **Cost accounting**: per-participant budgets exist in substrate now;
  extending that accounting across coordinator scheduling and model
  calls is future work.

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
