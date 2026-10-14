# Contributing to ANIMA

Each component under `components/` is independently owned: install, test,
and change it in its own directory. The root only carries the `anima`
namespace aliases (`src/anima/`), shared docs (`docs/anima/`), and the
import-map smoke tests (`tests/`).

## Ground rules

- Keep components independently installable: no new cross-component imports.
  The `anima.*` aliases are same-object re-exports, not integration.
- No private data in commits: live stores, timelines, tracked events,
  credentials, `.env` files, or consented corpora. See `SECRET-SCAN.md`.
- Match the component's existing style and test layout; add a test with
  every behavior change.
- Update the component README and the root README table when you change
  install, imports, CLIs, or test status.

## Quick checks before a PR

```bash
pip install -r requirements/components-all.txt
pytest tests/ -q
pytest components/<name>/tests/ -q
```

## Reporting security issues

Do not open a public issue for vulnerabilities — see `SECURITY.md`.
