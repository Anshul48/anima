# Reproduce everything (Linux/WSL, $0, offline)

Tested on: Ubuntu/WSL2 (`6.6.87.2-microsoft-standard-WSL2`, x86_64),
system `python3` 3.12.3, `prototype/w1/.venv` python 3.12.3
(pydantic 2.13.5, for SST legs only). No keys, no network, no installs.

```sh
U=<workspace-root>
S=$U/substrate
export PYTHONDONTWRITEBYTECODE=1
```

## 0. Identities (prove the bytes before running)

```sh
cd $S/prototype/w1-harden && sha256sum -c ../../prototype/closeout-20261004/IDENTITY.sha256
# expect: 20 lines, all OK
cd $S/prototype/w1 && sha256sum -c ../w1-harden/FREEZE.w1
# expect: 7 lines, all OK
```

## 1. Hardened pilot (frozen)

```sh
cd $S/prototype/w1-harden && python3 -m unittest test_w1_harden test_failures test_recovery
# expect: Ran 33 tests ... OK
python3 $S/prototype/w1-harden/demo_T.py --state-dir /tmp/h-check --ledger /tmp/h-check/ledger.jsonl
# expect: exit 0, 40 ledger entries, spend $0.0, conservation OK
python3 $S/prototype/w1-harden/recovery_exercise.py --evidence-dir /tmp/h-evidence
# expect: exit 0, child_returncode -9, re_executed_invokes 0
```

Full matrix (3 interpreter/CWD combos, SST-TEST demo): see
`prototype/w1-harden/REPRODUCE.md`. NOTE: the SST-TEST leg's frozen
bytes have drifted in the live SST tree (4/14 modules); reruns test
current HEAD, not the frozen evidence. The successor stages SST cand-02.

## 2. Reuse demo (Q3)

```sh
cd $S/prototype/reuse-demo-001 && python3 -m unittest test_reuse
# expect: Ran 10 tests ... OK
python3 $S/prototype/reuse-demo-001/reuse_demo.py
# expect: exit 0, RESULT: PASS (drop-kill + SIGKILL rc=-9, 0 re-invokes)
```

## 3. X3 (H3a)

```sh
rm -rf /tmp/x3-repro && cp -r $S/prototype/x3-20261004 /tmp/x3-repro \
  && rm -rf /tmp/x3-repro/runs && cd /tmp/x3-repro && python3 x3_run.py
# expect: exit 0, verdict H (H3a supported) H=3 C=0, recovery-fail none,
# RESULT.md byte-identical to prototype/x3-20261004/RESULT.md
```

(Run in a scratch copy to preserve the worker's evidence in place.)

## 4. Release r1 (frozen, independently accepted)

```sh
cd $S/prototype/successor-002 && sha256sum -c IDENTITY.sha256
# expect: 41 lines, all OK
PYTHONDONTWRITEBYTECODE=1 python3 test_successor.py   # Ran 17 ... OK (~60 s)
PYTHONDONTWRITEBYTECODE=1 python3 test_fission.py     # Ran 7 ... OK
PYTHONDONTWRITEBYTECODE=1 python3 test_conformance.py # Ran 9 ... OK
PYTHONDONTWRITEBYTECODE=1 python3 successor_demo.py   # exit 0, SST MATCH + champion_found $0
PYTHONDONTWRITEBYTECODE=1 python3 calibrate.py        # 2.61x (bytes-only)
PYTHONDONTWRITEBYTECODE=1 python3 verify_snapshot.py  # snapshot MATCH: files=54
```

Consumer entry points + Ubuntu setup: `prototype/successor-002/CONSUMER.md`.
Full procedure: `prototype/successor-002/REPRODUCE.md`.
Predecessor `prototype/successor-001/` kept intact (see its own REPRODUCE.md;
its SST cand-02 staging leg is superseded by r1's df78f42 snapshot).

## 5. Preserved pilot evidence

`prototype/evidence-20261004/` (11 dirs, byte-identical to the
original `/tmp/substrate-*` scratch; see its README.md). Original
per-run commands live in each dir's RUN-LOG/RESULT files.
