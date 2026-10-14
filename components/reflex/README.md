# Reflex (`relfex`)

System 1 vision and perception for computer use, designed to work alongside
LLMs as their eyes: fast spatial affordance detection, cheap relevance
filtering, and targeted escalation of small crops to heavier models instead
of full frames. See [REFLEX-AMBITION.md](REFLEX-AMBITION.md) for the
architectural ambition (escalation ladder, O(N) crop routing) and
[ARCHITECTURE.md](ARCHITECTURE.md) for the research/seed architecture note.

No shared runtime with the other ANIMA components; the `anima.reflex` module
is a same-object alias of `reflex`.

## Install

Python 3.12+ required. From the repository root:

```bash
pip install -e components/reflex
```

Note: the `reflex` import name collides with the unrelated Reflex web
framework on PyPI — do not install both in one environment.

## Run

There is no installed console script; the entry point is `main.py` (Jarvis
autonomous computer-use console):

```bash
python components/reflex/main.py --help
```

```python
import reflex          # native import (primary)
import anima.reflex    # convenience alias, same object
```

Component sources live under [src/reflex/](src/reflex/); contracts and eval
notes under [docs/](docs/).

## Tests

From this directory:

```bash
pytest tests/ -q
```

Smoke scope verified for this release: `tests/test_privacy_redactor.py`
(14 passed). Four upstream test files that shipped upstream with all bodies
reduced to `pass`, plus the script that stripped them, are excluded from this
public tree (preserved privately by the owner); they are not claimed as
passing. See the repo-root `TEST-REPORT.md` for the exact qualification scope.

## Limits

- Research/seed stage: model names, latency figures, and complexity claims in
  `ARCHITECTURE.md` are hypotheses to measure, not release commitments.
- No cross-component wiring: reflex runs standalone.
- License: Apache-2.0 ([LICENSE](LICENSE), added at publication).
  See the repo-root README license table.
