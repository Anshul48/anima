# Entorhinal

Local-first advisory temporal context: a memory system that records task
evidence, compiles multi-timescale projections, serves context snapshots to
local consumers, and enforces user control (corrections, consent, cascade
deletion, audit). No shared runtime with the other ANIMA components; the
`anima.entorhinal` module is a same-object alias of `entorhinal`.

## Install

Python 3.12+ required. From the repository root:

```bash
pip install -e components/entorhinal
```

Upstream `pyproject.toml` lists `pytest` and `pytest-asyncio` as runtime
dependencies; that oddity ships as found.

## Run

```bash
entorhinal --help
entorhinal status
entorhinal inspect timeline
entorhinal grants list
entorhinal audit
entorhinal serve   # local loopback FastAPI daemon
```

```python
import entorhinal          # native import (primary)
import anima.entorhinal    # convenience alias, same object
```

Note: importing `entorhinal` prints a legacy/test-path
`API running WITHOUT authentication` banner. For local serving, configure HTTP
principal credentials via `entorhinal auth --help`.

## Tests

From this directory:

```bash
pytest tests/ -q
```

Smoke scope verified for this release: `tests/test_fact_identity.py`
(9 passed). The Track 1/Track 2 evaluation test
(`tests/test_phase4_user_control_and_evals.py::test_evaluation_runner_track1_and_track2`)
skips its consented-corpus leg when the deliberately excluded private fixture
(`src/entorhinal/fixtures/consented_trace/manifest.json`) is absent; the
product still returns `BLOCKED` without a manifest by design, and the scoring
thresholds are unchanged. See the repo-root `TEST-REPORT.md` for the exact
qualification scope.

## Docs

- [Builder authority boundary](docs/BUILDER-AUTHORITY-BOUNDARY.md) — the
  builder works only with synthetic, user-provided, or consented data; live
  user memory is out of scope.
- [Dev-task emitter spec](docs/dev-task-emitter-spec.md)
- [Evaluation notes](docs/evals)
- Sources under [src/entorhinal/](src/entorhinal/), tests under
  [tests/](tests/).

## Limits

- No private corpus, live stores, timelines, run logs, or credentials ship;
  consented fixtures are excluded (see `MANIFEST.md`).
- No cross-component wiring: entorhinal runs standalone.
- License: Apache-2.0 ([LICENSE](LICENSE), added at publication).
  See the repo-root README license table.
