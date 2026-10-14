# anima-substrate

A small, offline, stdlib-only Python host for **persistent project worlds**:
create worlds, nest experiment worlds with delegated budgets, run
participant families through pinned contracts, survive real process kills,
fuse/fission/quarantine organizations, and export composites that run
unmodified elsewhere on the same host.

Who can use it: researchers and engineers experimenting with accountable
local computation — worlds with explicit custody, resources, lifecycle,
and evidence. This is an **alpha research artifact** (0.1.1), not a
production runtime.

## Install

Linux/Ubuntu + Python 3.11–3.12 (verified: 3.12 locally; 3.11 + 3.12 in CI):

```
pip install dist/anima_substrate-0.1.1-py3-none-any.whl   # local artifact
```

(PyPI publication pending; install from the release asset for now.)

From a checkout (developers):

```
python3 -m venv --without-pip .venv
curl -sL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
./.venv/bin/python /tmp/get-pip.py
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m pip install pytest ruff build  # dev tooling
```

Zero runtime dependencies. State always lives in a caller-selected
directory, never in the installed package.

## Working example

```
python examples/quickstart.py
```

It builds a tiny release tree, runs the release-check participant,
closes and reopens with byte-identical state, recovers, and settles —
or drive the CLI yourself:

```
D=/tmp/demo-state
anima-substrate init --state-dir $D
anima-substrate inspect --state-dir $D
anima-substrate j1-init --state-dir $D --project PROJ --reason demo
anima-substrate ops nest --state-dir $D --project PROJ --child EXP1 \
    --delegate 0.5,30,50 --custody j1.budget --reason demo
anima-substrate ops j1-status --state-dir $D
```

Full journey (interruption, fusion, quarantine, reuse):
[examples/quickstart.py](examples/quickstart.py) and
[docs/RECOVERY.md](docs/RECOVERY.md).

## Implemented capabilities

- Persistent worlds with ledger-recorded state, custody, grants, and
  lifecycle; close/reopen with byte-verified organizational snapshots.
- Nested delegation with real sub-grants (never manufactured) and
  custody handoff; over-delegation refused with zero mutation.
- Versioned participant families behind a published contract; SST
  snapshot search as an optional caller-staged integration (pinned
  commit, compat probe, no vendored bytes).
- Real-SIGKILL interruption with byte-identical resume and zero
  re-executed invokes; quarantine-transfer repair via supported
  complete/rollback operator paths.
- Fusion/fission/quarantine/revision/revocation/reuse with lineage;
  portable executable composites consumable unmodified in a fresh
  state directory (same host, explicit new grants).
- Propose → assess → retain → reuse loop with measured costs against
  a from-scratch baseline (validated retention/reuse — not learning).

## Important limitations

Single host, toy scale, process-crash-only (no fsync; power/media loss
is out of scope). No cross-host, multi-writer, or disk-loss tolerance.
No learning of any kind: no policy invention, learned mappings, or
autonomous discovery. Delegation amounts are operator-supplied. STC
material is explicitly unqualified (full-replay semantics only).
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/ROADMAP.md](docs/ROADMAP.md).

## Links

- Contracts: [docs/CONTRACTS.md](docs/CONTRACTS.md) ·
  Recovery: [docs/RECOVERY.md](docs/RECOVERY.md) ·
  Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Roadmap/gaps (18 vectors, A → C → B → D): [docs/ROADMAP.md](docs/ROADMAP.md)
- Technical report / artifact guide:
  [docs/TECHNICAL-REPORT.md](docs/TECHNICAL-REPORT.md)
- Reproduction of historical evidence: [REPRODUCE-ALL.md](REPRODUCE-ALL.md)
- Research archive curation: [docs/RESEARCH-ARCHIVE.md](docs/RESEARCH-ARCHIVE.md)

## Development

```
./.venv/bin/python -m pytest tests/     # full suite
./.venv/bin/python -m ruff check src tests examples
./.venv/bin/python -m ruff format --check src tests examples
./.venv/bin/python -m build             # wheel + sdist in dist/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[CHANGELOG.md](CHANGELOG.md).

## License and citation

Apache License 2.0 — see [LICENSE](LICENSE). Copyright 2026
Anshul48; per-file `SPDX-License-Identifier: Apache-2.0` headers
apply to maintained original code. Citation metadata:
[CITATION.cff](CITATION.cff).
