# accept/ — frozen acceptance-input pack

Frozen task inputs (`S1.json` … `S6-followup.json`, dumped byte-exact
from `sched_inputs.py` at build time) plus `EXPECTED.json` (expected
VALID/quality + routing expectations per task, from the qualifying
demo run `runs/demo-20261004T100134Z`).

## Exact vs reference fields

- EXACT (acceptance compares these for equality): `valid`,
  `quality`, `prefs_total`, `lane`, `via`, `lineage_ok`,
  `probe_denied`, `child_killed`, `re_executed_invokes`,
  `skipped_pre_kill`, `revoked`, `representation`,
  `standby_completed`, fusion/fission records, SST
  (`snapshot_check`, `champion_found`, `cost_usd`, `envelope_keys`,
  `pydantic`), routing decision count, settle terminals/markers.
- REFERENCE (observed on this build; informational):
  `central_bytes_ref`, `direct_bytes_ref` — canonical-JSON bytes
  handled per lane. Compared by eye, not gated, because any future
  message-shape change moves them while VALID/quality stay exact.

## How to run acceptance

From the repo root, with `PYTHONDONTWRITEBYTECODE=1`:

1. `python3 prototype/successor-002/successor_demo.py` → exit 0,
   `successor-002 integrated demo: OK`.
2. Compare the new `runs/demo-*/EVIDENCE.json` against `EXPECTED.json`
   field by field (exact fields must match; byte refs eyeballed).
3. `python3 prototype/successor-002/test_successor.py` → 17/17 OK;
   `test_fission.py` → 7/7 OK; `test_conformance.py` → 8/8 OK.
4. `python3 prototype/successor-002/calibrate.py` → ratio ≈ 2.61x
   (S2 both lanes; bytes-only claim).
5. `cd prototype/successor-002 && sha256sum -c IDENTITY.sha256` →
   all OK.
6. `cd prototype && sha256sum -c successor-002/FROZEN-BASELINE.sha256`
   → all OK (frozen dirs + successor-001 intact).

Inputs are FROZEN: do not edit `accept/*.json` to make a run pass —
a mismatch is a product finding, not a pack bug.
